"""Dialog per ball detection e tracking - analisi automatica."""
from pathlib import Path
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QMessageBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from analysis.ball_detection import run_ball_detection, get_ball_detections_path, _get_yolox_predictor
from analysis.ball_tracking import run_ball_tracking, get_ball_tracks_path
from analysis.config import get_calibration_path


class BallDetectionWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, video_path: str, detections_path: str, tracks_path: str, predictor=None, calibration_path: str = None):
        super().__init__()
        self.video_path = video_path
        self.detections_path = detections_path
        self.tracks_path = tracks_path
        self._predictor = predictor
        self.calibration_path = calibration_path

    def run(self):
        def on_progress(frame_idx: int, total: int, msg: str):
            self.progress.emit(frame_idx, total, msg)

        try:
            ok, err_msg = run_ball_detection(
                self.video_path,
                self.detections_path,
                conf_thresh=0.25,
                progress_callback=on_progress,
                predictor=getattr(self, "_predictor", None),
                target_fps=10.0,
                calibration_path=self.calibration_path,
            )
            if not ok:
                self.finished_signal.emit(False, err_msg or "Errore durante la detection della palla.")
                return
            ok = run_ball_tracking(
                self.detections_path,
                self.tracks_path,
                progress_callback=on_progress,
            )
            if ok:
                self.finished_signal.emit(True, self.tracks_path)
            else:
                self.finished_signal.emit(False, "Errore durante il tracking della palla.")
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class BallDetectionDialog(QDialog):
    """Dialog per ball detection + tracking."""

    def __init__(self, video_path: str, project_analysis_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ball detection - Analisi automatica")
        self.setFixedSize(440, 200)
        self.setWindowFlags(Qt.Dialog)
        self._video_path = video_path
        self._project_analysis_dir = project_analysis_dir
        self._detections_path = str(get_ball_detections_path(project_analysis_dir))
        self._tracks_path = str(get_ball_tracks_path(project_analysis_dir))
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1a2332,
                    stop:1 #0d1520
                );
                border: 1px solid #2a3f5f;
                border-radius: 8px;
            }
            QLabel {
                color: #e8f0fa;
                font-size: 13px;
            }
            QLabel#percentLabel {
                color: #4ade80;
                font-size: 36px;
                font-weight: bold;
                letter-spacing: 2px;
            }
            QLabel#statusLabel {
                color: #94a3b8;
                font-size: 12px;
            }
            QProgressBar {
                border: 1px solid #334155;
                border-radius: 4px;
                text-align: center;
                background: #0f172a;
                min-height: 12px;
                max-height: 12px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #22c55e,
                    stop:0.5 #4ade80,
                    stop:1 #22c55e
                );
                border-radius: 3px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        title = QLabel("BALL DETECTION")
        title.setStyleSheet("color: #4ade80; font-size: 14px; font-weight: bold; letter-spacing: 3px;")
        layout.addWidget(title)

        self._percent_label = QLabel("0%")
        self._percent_label.setObjectName("percentLabel")
        self._percent_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._percent_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        self._status = QLabel("Avvio...")
        self._status.setObjectName("statusLabel")
        self._status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status)

    def start(self):
        predictor, err = _get_yolox_predictor()
        if predictor is None:
            QMessageBox.warning(self, "Errore", err or "YOLOX non inizializzato.")
            return
        cal_path = None
        try:
            p = Path(get_calibration_path(self._project_analysis_dir))
            cal_path = str(p) if p.exists() else None
        except Exception:
            pass
        self._worker = BallDetectionWorker(
            self._video_path,
            self._detections_path,
            self._tracks_path,
            predictor=predictor,
            calibration_path=cal_path,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, current: int, total: int, msg: str):
        if total > 0:
            pct = int(100 * current / total)
        else:
            pct = 0
        self._progress.setValue(min(100, pct))
        self._percent_label.setText(f"{min(100, pct)}%")
        self._status.setText(msg or f"Frame {current}/{total}")

    def _on_finished(self, ok: bool, message: str):
        if ok:
            self._progress.setValue(100)
            self._percent_label.setText("100%")
            self._status.setText("Completato")
        if ok:
            QMessageBox.information(self, "Completato", f"Ball detection e tracking salvati in:\n{message}")
        else:
            QMessageBox.warning(self, "Errore", message)
        self.accept()
