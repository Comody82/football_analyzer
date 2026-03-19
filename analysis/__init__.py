"""
Modulo Analisi automatica partita - Football Analyzer.
Pipeline: calibrazione campo → preprocessing → detection → tracking → eventi → metriche → report.
"""
from .config import AnalysisConfig
from .field_calibration import FieldCalibrator
from .video_preprocessing import preprocess_video, get_preprocessed_path
from .player_detection import PlayerDetector, run_player_detection, get_detections_path
from .player_tracking import run_player_tracking, get_tracks_path
from .ball_detection import run_ball_detection, get_ball_detections_path
from .ball_tracking import run_ball_tracking, get_ball_tracks_path

__all__ = [
    "AnalysisConfig",
    "FieldCalibrator",
    "preprocess_video",
    "get_preprocessed_path",
    "PlayerDetector",
    "run_player_detection",
    "get_detections_path",
    "run_player_tracking",
    "get_tracks_path",
    "run_ball_detection",
    "get_ball_detections_path",
    "run_ball_tracking",
    "get_ball_tracks_path",
]
