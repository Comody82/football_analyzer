"""
LicenseManager — Sistema licenze Prelyt
========================================
Gestisce attivazione, verifica e stato della licenza.

Flusso:
  1. DEV mode → sempre valido (file .dev_mode o env PRELYT_DEV=1)
  2. Carica licenza locale da %APPDATA%\Prelyt\license.dat
  3. Verifica scadenza + anti-tamper data di sistema
  4. Tenta check online (non bloccante, cache 24h)
  5. Grace period 30gg offline prima di bloccare

Piani: DEV · FREE · PRO · ELITE
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import threading
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# ── Costanti ──────────────────────────────────────────────────────────────────
GRACE_DAYS          = 30          # giorni offline prima di bloccare
ONLINE_CHECK_TTL_H  = 24          # ore tra un check online e il successivo
LICENSE_API_BASE    = "https://api.prelyt.com/v1/license"
PLANS               = ["DEV", "FREE", "PRO", "ELITE"]
KEY_FORMAT_HINT     = "PRLT-XXXX-XXXX-XXXX-XXXX"
_OBFUSCATE_KEY      = b"prelyt_lic_2025"   # XOR key leggera (non sicurezza, solo offuscamento)


# ── Dataclass stato ───────────────────────────────────────────────────────────
@dataclass
class LicenseStatus:
    valid: bool
    plan: str = "NONE"
    user_name: str = ""
    expires_at: Optional[str] = None        # ISO date o None = illimitato
    grace_remaining: int = GRACE_DAYS       # giorni offline rimanenti
    device_id: str = ""
    reason: str = ""                         # motivo se non valida
    is_dev: bool = False

    @property
    def plan_label(self) -> str:
        labels = {"DEV": "✦ SVILUPPO", "FREE": "Free", "PRO": "⚡ Pro", "ELITE": "★ Elite", "NONE": "—"}
        return labels.get(self.plan, self.plan)

    @property
    def expires_label(self) -> str:
        if self.is_dev:
            return "— (modalità sviluppo)"
        if not self.expires_at:
            return "Illimitata"
        try:
            dt = datetime.fromisoformat(self.expires_at)
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            return self.expires_at

    @property
    def status_label(self) -> str:
        if self.is_dev:
            return "✅ Attiva (Dev)"
        if self.valid:
            if self.grace_remaining < GRACE_DAYS:
                return f"✅ Attiva (offline — connettiti entro {self.grace_remaining}gg)"
            return "✅ Attiva"
        return f"❌ {self.reason or 'Non valida'}"

    @property
    def features(self) -> list[str]:
        base = [
            "✅  Analisi video automatica (YOLOX)",
            "✅  Tracking giocatori e palla",
            "✅  Lavagna tattica 2D",
            "✅  Heatmap e pressing map",
            "✅  Timeline eventi e clip",
            "✅  Statistiche partita",
            "✅  Database squadre e giocatori",
        ]
        if self.plan in ("DEV", "PRO", "ELITE"):
            base.append("✅  Analisi cloud (RunPod)")
        else:
            base.append("🔒  Analisi cloud  (richiede Piano Pro)")
        base += [
            "⏳  Fuorigioco automatico  (prossimamente)",
            "⏳  AI Tactical Text Generator  (prossimamente)",
            "⏳  Prelyt Mobile  (prossimamente)",
        ]
        return base


# ── Utility ───────────────────────────────────────────────────────────────────
def get_device_id() -> str:
    """Fingerprint stabile del dispositivo (SHA256 di hostname + MAC)."""
    try:
        parts = [
            platform.node(),
            platform.machine(),
            str(uuid.getnode()),          # MAC address come intero
            socket.gethostname(),
        ]
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16].upper()
    except Exception:
        return hashlib.sha256(b"fallback_device").hexdigest()[:16].upper()


def _license_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    d = Path(appdata) / "Prelyt"
    d.mkdir(parents=True, exist_ok=True)
    return d / "license.dat"


def _obfuscate(data: bytes) -> bytes:
    key = _OBFUSCATE_KEY
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _encode(obj: dict) -> str:
    raw = json.dumps(obj).encode()
    return base64.b64encode(_obfuscate(raw)).decode()


def _decode(s: str) -> dict:
    raw = _obfuscate(base64.b64decode(s.encode()))
    return json.loads(raw)


# ── LicenseManager ────────────────────────────────────────────────────────────
class LicenseManager:
    """Punto di accesso singolo per tutto il sistema licenze."""

    _instance: Optional["LicenseManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._device_id = get_device_id()
        self._cached_status: Optional[LicenseStatus] = None
        self._lock = threading.Lock()

    # ── Dev mode ──────────────────────────────────────────────────────────────
    def _is_dev_mode(self) -> bool:
        """Dev mode: env var PRELYT_DEV=1 oppure file .dev_mode nella cartella app."""
        if os.environ.get("PRELYT_DEV", "0") == "1":
            return True
        dev_file = Path(__file__).parent / ".dev_mode"
        return dev_file.exists()

    # ── Storage ───────────────────────────────────────────────────────────────
    def _load_raw(self) -> Optional[dict]:
        path = _license_path()
        if not path.exists():
            return None
        try:
            return _decode(path.read_text(encoding="utf-8").strip())
        except Exception as e:
            logger.warning(f"Errore lettura licenza: {e}")
            return None

    def _save_raw(self, data: dict):
        path = _license_path()
        path.write_text(_encode(data), encoding="utf-8")

    # ── Anti-tamper ───────────────────────────────────────────────────────────
    def _check_date_tamper(self, lic: dict) -> bool:
        """Ritorna True se la data di sistema sembra manipolata (clock tornato indietro)."""
        try:
            last_seen_str = lic.get("last_seen")
            if not last_seen_str:
                return False
            last_seen = datetime.fromisoformat(last_seen_str)
            now = datetime.now()
            # Se l'orologio è tornato indietro di più di 1 ora → sospetto
            return now < last_seen - timedelta(hours=1)
        except Exception:
            return False

    def _update_last_seen(self, lic: dict) -> dict:
        lic["last_seen"] = datetime.now().isoformat()
        return lic

    # ── Check online (async, non bloccante) ───────────────────────────────────
    def _should_check_online(self, lic: dict) -> bool:
        last_check = lic.get("last_online_check")
        if not last_check:
            return True
        try:
            dt = datetime.fromisoformat(last_check)
            return datetime.now() - dt > timedelta(hours=ONLINE_CHECK_TTL_H)
        except Exception:
            return True

    def _online_check_thread(self, lic: dict):
        """Verifica online in background — aggiorna cache se risponde."""
        try:
            payload = json.dumps({
                "license_key": lic.get("license_key", ""),
                "device_id": self._device_id,
            }).encode()
            req = urllib.request.Request(
                f"{LICENSE_API_BASE}/check",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                result = json.loads(resp.read().decode())
                if result.get("valid"):
                    with self._lock:
                        lic.update({
                            "plan": result.get("plan", lic.get("plan")),
                            "expires_at": result.get("expires_at"),
                            "user_name": result.get("user_name", ""),
                            "last_online_check": datetime.now().isoformat(),
                            "blacklisted": False,
                        })
                        self._update_last_seen(lic)
                        self._save_raw(lic)
                        self._cached_status = None   # forza ricalcolo
                        logger.info("Licenza verificata online OK")
                elif result.get("blacklisted"):
                    with self._lock:
                        lic["blacklisted"] = True
                        self._save_raw(lic)
                        self._cached_status = None
                        logger.warning("Licenza nella blacklist server")
        except Exception as e:
            logger.debug(f"Check online non riuscito (offline?): {e}")

    # ── Attivazione ───────────────────────────────────────────────────────────
    def activate(self, license_key: str) -> tuple[bool, str]:
        """
        Attiva una nuova licenza.
        Ritorna (success, message).
        """
        key = license_key.strip().upper()
        if not key:
            return False, "Inserisci una chiave licenza valida."

        try:
            payload = json.dumps({
                "license_key": key,
                "device_id": self._device_id,
                "platform": platform.system(),
                "app_version": "0.1.0",
            }).encode()
            req = urllib.request.Request(
                f"{LICENSE_API_BASE}/activate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode())
                return False, err.get("message", f"Errore server: {e.code}")
            except Exception:
                return False, f"Errore server: {e.code}"
        except Exception:
            # Server non raggiungibile: accetta la chiave localmente (verrà verificata al prossimo check online)
            result = {
                "valid": True,
                "plan": "PRO",
                "expires_at": None,
                "user_name": "",
                "offline_activation": True,
            }

        if not result.get("valid"):
            return False, result.get("message", "Chiave non valida.")

        lic = {
            "license_key": key,
            "plan": result.get("plan", "PRO"),
            "expires_at": result.get("expires_at"),
            "user_name": result.get("user_name", ""),
            "device_id": self._device_id,
            "activated_at": datetime.now().isoformat(),
            "last_online_check": datetime.now().isoformat() if not result.get("offline_activation") else None,
            "last_seen": datetime.now().isoformat(),
            "blacklisted": False,
        }
        self._save_raw(lic)
        self._cached_status = None
        note = " (attivazione offline — verifica al prossimo avvio)" if result.get("offline_activation") else ""
        return True, f"Licenza attivata! Piano: {lic['plan']}{note}"

    # ── Check stato ───────────────────────────────────────────────────────────
    def check(self, force: bool = False) -> LicenseStatus:
        """Ritorna lo stato aggiornato della licenza."""
        with self._lock:
            if self._cached_status and not force:
                return self._cached_status
            status = self._compute_status()
            self._cached_status = status
            return status

    def _compute_status(self) -> LicenseStatus:
        device_id = self._device_id

        # 1. Dev mode
        if self._is_dev_mode():
            return LicenseStatus(
                valid=True, plan="DEV", device_id=device_id,
                grace_remaining=GRACE_DAYS, is_dev=True,
            )

        # 2. Carica licenza
        lic = self._load_raw()
        if not lic:
            return LicenseStatus(
                valid=False, plan="NONE", device_id=device_id,
                reason="Nessuna licenza attivata",
            )

        # 3. Blacklist
        if lic.get("blacklisted"):
            return LicenseStatus(
                valid=False, plan=lic.get("plan", "NONE"), device_id=device_id,
                reason="Licenza disattivata — contatta il supporto",
            )

        # 4. Anti-tamper
        if self._check_date_tamper(lic):
            return LicenseStatus(
                valid=False, plan=lic.get("plan", "NONE"), device_id=device_id,
                reason="Verifica data di sistema",
            )

        # 5. Scadenza
        expires_at = lic.get("expires_at")
        if expires_at:
            try:
                if datetime.now() > datetime.fromisoformat(expires_at):
                    return LicenseStatus(
                        valid=False, plan=lic.get("plan", "NONE"), device_id=device_id,
                        reason="Licenza scaduta",
                        expires_at=expires_at,
                    )
            except Exception:
                pass

        # 6. Grace period
        last_online = lic.get("last_online_check")
        if last_online:
            try:
                days_offline = (datetime.now() - datetime.fromisoformat(last_online)).days
                grace_remaining = max(0, GRACE_DAYS - days_offline)
                if grace_remaining == 0:
                    return LicenseStatus(
                        valid=False, plan=lic.get("plan", "NONE"), device_id=device_id,
                        reason=f"Connessione internet richiesta (offline da {days_offline} giorni)",
                    )
            except Exception:
                grace_remaining = GRACE_DAYS
        else:
            grace_remaining = GRACE_DAYS

        # 7. Aggiorna last_seen e avvia check online async se necessario
        lic = self._update_last_seen(lic)
        self._save_raw(lic)
        if self._should_check_online(lic):
            threading.Thread(target=self._online_check_thread, args=(dict(lic),), daemon=True).start()

        return LicenseStatus(
            valid=True,
            plan=lic.get("plan", "PRO"),
            user_name=lic.get("user_name", ""),
            expires_at=lic.get("expires_at"),
            grace_remaining=grace_remaining,
            device_id=device_id,
        )

    def deactivate(self):
        """Rimuove la licenza locale."""
        path = _license_path()
        if path.exists():
            path.unlink()
        self._cached_status = None

    @property
    def device_id(self) -> str:
        return self._device_id
