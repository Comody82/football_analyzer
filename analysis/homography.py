"""
Punto unico per trasformazione pixel → coordinate campo (metri).

Tutti i moduli che necessitano di coordinate in metri (event engine, metriche:
distanza percorsa, heatmap sul campo, zone tattiche) devono usare get_calibrator()
e non aprire field_calibration.json direttamente.

Uso:
  from analysis.homography import get_calibrator
  cal = get_calibrator(calibration_path)
  if cal:
      mx, my = cal.pixel_to_field(px, py)
"""
from pathlib import Path
from typing import Optional

from .field_calibration import FieldCalibrator

# Cache per path → calibrator (evita rilettura file ripetuta)
_calibrator_cache: dict = {}


def get_calibrator(calibration_path: Optional[str]) -> Optional[FieldCalibrator]:
    """
    Restituisce un FieldCalibrator caricato dal file di calibrazione, o None se
    il path è assente/invalido o la calibrazione non è valida (es. < 4 punti).

    Usare questo come unico punto di accesso per pixel_to_field / field_to_pixel
    in event engine e metriche.
    """
    if not calibration_path:
        return None
    path = Path(calibration_path).resolve()
    key = str(path)
    if key in _calibrator_cache:
        return _calibrator_cache[key]
    if not path.exists():
        return None
    cal = FieldCalibrator()
    if not cal.load(path):
        return None
    _calibrator_cache[key] = cal
    return cal


def clear_calibrator_cache(calibration_path: Optional[str] = None):
    """
    Invalida la cache. Se calibration_path è None, svuota tutta la cache.
    Utile dopo aver riscritto field_calibration.json dalla UI.
    """
    global _calibrator_cache
    if calibration_path is None:
        _calibrator_cache.clear()
        return
    key = str(Path(calibration_path).resolve())
    _calibrator_cache.pop(key, None)
