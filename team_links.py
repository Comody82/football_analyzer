"""
Associazione tra squadre rilevate dall'IA (team 0 / team 1)
e nomi/colori reali definiti dall'utente.

Salvato come JSON per progetto: projects/<project_id>_team_links.json
"""
import json
from pathlib import Path
from typing import Optional, Dict


_DEFAULT_COLORS = {0: "#ef4444", 1: "#3b82f6"}  # rosso / blu
_DEFAULT_NAMES  = {0: "Squadra A", 1: "Squadra B"}


class ProjectTeamLinks:
    """
    Gestisce il collegamento AI team index → nome/colore reale.

    Struttura JSON salvata:
    {
      "team_0": {"name": "Juventus", "color": "#000000"},
      "team_1": {"name": "Inter",    "color": "#0000ff"}
    }
    """

    def __init__(self, path: str):
        self._path = Path(path)
        self._data: Dict[int, dict] = {
            0: {"name": _DEFAULT_NAMES[0], "color": _DEFAULT_COLORS[0]},
            1: {"name": _DEFAULT_NAMES[1], "color": _DEFAULT_COLORS[1]},
        }
        if self._path != Path(":memory:") and self._path.exists():
            self._load()

    # ── I/O ────────────────────────────────────────────────────────────────
    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for key, idx in (("team_0", 0), ("team_1", 1)):
                if key in raw:
                    self._data[idx] = {
                        "name":  str(raw[key].get("name",  _DEFAULT_NAMES[idx])),
                        "color": str(raw[key].get("color", _DEFAULT_COLORS[idx])),
                    }
        except Exception:
            pass  # usa defaults

    def save(self):
        if self._path == Path(":memory:"):
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        raw = {
            "team_0": self._data[0],
            "team_1": self._data[1],
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)

    # ── Lettura ────────────────────────────────────────────────────────────
    def get_name(self, team_idx: int) -> str:
        return self._data.get(team_idx, {}).get("name", _DEFAULT_NAMES.get(team_idx, f"Team {team_idx}"))

    def get_color(self, team_idx: int) -> str:
        return self._data.get(team_idx, {}).get("color", _DEFAULT_COLORS.get(team_idx, "#888888"))

    def get_team_names_dict(self) -> Dict[int, str]:
        """Ritorna {0: "NomeA", 1: "NomeB"} — usato da StatisticsDialog."""
        return {idx: self.get_name(idx) for idx in (0, 1)}

    def get_team_colors_dict(self) -> Dict[int, str]:
        """Ritorna {0: "#rrggbb", 1: "#rrggbb"} — usato da StatisticsDialog."""
        return {idx: self.get_color(idx) for idx in (0, 1)}

    # ── Scrittura ──────────────────────────────────────────────────────────
    def set_team(self, team_idx: int, name: str, color: str):
        self._data[team_idx] = {"name": name.strip() or _DEFAULT_NAMES.get(team_idx, f"Team {team_idx}"),
                                "color": color or _DEFAULT_COLORS.get(team_idx, "#888888")}

    def is_configured(self) -> bool:
        """True se l'utente ha già assegnato almeno un nome personalizzato."""
        return (self.get_name(0) != _DEFAULT_NAMES[0] or
                self.get_name(1) != _DEFAULT_NAMES[1])
