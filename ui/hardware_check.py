"""
Rilevamento hardware per analisi locale (Fase 3).
Verifica GPU utilizzabile e RAM; usato per avviso "risorse limitate" e default Locale/Cloud.
"""
import sys
from typing import Dict, Any


# Soglia RAM sotto la quale si considera "risorse limitate" (GB)
RAM_LIMITED_THRESHOLD_GB = 8.0


def get_ram_gb() -> float:
    """Restituisce RAM totale in GB. 0 se non determinabile."""
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except ImportError:
        return 0.0


def is_gpu_available() -> bool:
    """True se è disponibile una GPU utilizzabile (CUDA, DirectML o Metal)."""
    try:
        import torch
        if torch.cuda.is_available():
            return True
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            # DirectML (Windows) - torch-directml se installato
            import torch
            if hasattr(torch, "dml") and torch.dml.is_available():
                return True
        except Exception:
            pass
    if sys.platform == "darwin":
        try:
            import torch
            if hasattr(torch.backends, "mps") and getattr(torch.backends.mps, "is_available", lambda: False)():
                return True
        except Exception:
            pass
    return False


def run_hardware_check() -> Dict[str, Any]:
    """
    Esegue il controllo hardware. Ritorna un dict con:
    - gpu_available: bool
    - ram_gb: float
    - hardware_ok: bool (True se GPU disponibile O RAM >= soglia; altrimenti False, mostra avviso)
    """
    gpu = is_gpu_available()
    ram_gb = get_ram_gb()
    # Consideriamo "ok" se c'è GPU oppure RAM sufficiente (>= 8 GB)
    ram_ok = ram_gb >= RAM_LIMITED_THRESHOLD_GB if ram_gb > 0 else True
    hardware_ok = gpu or ram_ok
    return {
        "gpu_available": gpu,
        "ram_gb": round(ram_gb, 1),
        "hardware_ok": hardware_ok,
    }
