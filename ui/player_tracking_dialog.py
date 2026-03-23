"""Dialog per player tracking - analisi automatica."""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QMessageBox,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from analysis.player_tracking import run_player_tracking, get_tracks_path


class PlayerTrackingWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, detections_path: str, output_path: str):
        super().__init__()
        self.detections_path = detections_path
        self.output_path = output_path

    def run(self):
        def on_progress(frame_idx: int, total: int, msg: str):
            self.progress.emit(frame_idx, total, msg)

        ok = run_player_tracking(
            self.detections_path,
            self.output_path,
            progress_callback=on_progress,
        )
        if ok:
            self.finished_signal.emit(True, self.output_path)
        else:
            self.finished_signal.emit(False, "Errore durante il tracking.")


class PlayerTrackingDialog(QDialog):
    """Dialog con barra progresso per player tracking."""

    def __init__(self, detections_path: str, project_analysis_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Player tracking - Analisi automatica")
        self.setFixedSize(440, 200)
        self.setWindowFlags(Qt.Dialog)
        self._detections_path = detections_path
        self._output_path = str(get_tracks_path(project_analysis_dir))
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

        title = QLabel("PLAYER TRACKING")
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
        self._worker = PlayerTrackingWorker(self._detections_path, self._output_path)
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
            QMessageBox.information(self, "Completato", f"Tracking salvato in:\n{message}")
        else:
            QMessageBox.warning(self, "Errore", message)
        self.accept()
