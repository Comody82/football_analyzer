"""Dialog di avanzamento generazione highlights - stile Pro Evolution."""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class HighlightProgressDialog(QDialog):
    """Dialog professionale per progresso generazione highlights."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generazione Highlights")
        self.setFixedSize(440, 200)
        self.setWindowFlags(Qt.Dialog)
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

        title = QLabel("GENERAZIONE HIGHLIGHTS")
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

        self._status = QLabel("Preparazione...")
        self._status.setObjectName("statusLabel")
        self._status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status)

    def set_progress(self, percent: int, status: str = ""):
        percent = max(0, min(100, int(percent)))
        self._progress.setValue(percent)
        self._percent_label.setText(f"{percent}%")
        if status:
            self._status.setText(status)
