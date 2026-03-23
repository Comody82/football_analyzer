"""
Configurazione per analisi automatica partita.
"""
import os
from pathlib import Path

# Backend detection opzionale: "soccernet" per usare un modello SoccerNet (vedi docs/LIMITI_E_COME_MIGLIORARE.md)
DETECTION_BACKEND = os.environ.get("FOOTBALL_ANALYZER_DETECTION_BACKEND", "").strip().lower() or None

# Campi standard FIFA
FIELD_LENGTH_M = 105.0
FIELD_WIDTH_M = 68.0

# Preprocessing video
MAX_RESOLUTION = (1280, 720)  # 720p max
MAX_FPS = 25

# Percorsi output
ANALYSIS_OUTPUT_DIR = "analysis_output"
CALIBRATION_FILE = "field_calibration.json"


def get_analysis_output_path(project_dir: str = None) -> Path:
    """Restituisce il percorso della cartella output analisi."""
    if project_dir:
        return Path(project_dir) / ANALYSIS_OUTPUT_DIR
    return Path(ANALYSIS_OUTPUT_DIR)


def get_calibration_path(project_dir: str = None) -> Path:
    """Restituisce il percorso del file di calibrazione campo."""
    base = get_analysis_output_path(project_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base / CALIBRATION_FILE


class AnalysisConfig:
    """Configurazione runtime per l'analisi."""
    def __init__(self):
        self.field_length_m = FIELD_LENGTH_M
        self.field_width_m = FIELD_WIDTH_M
        self.max_resolution = MAX_RESOLUTION
        self.max_fps = MAX_FPS
