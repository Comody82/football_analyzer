"""
Dialog per analisi in cloud: upload, progress da SSE/polling, pulsante Interrompi.
Emette segnali quando il risultato è pronto, il job fallisce o c'è un errore di connessione.
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
)

from ui.cloud_analysis_worker import CloudAnalysisWorker


class CloudAnalysisDialog(QDialog):
    """Mostra progresso analisi cloud; espone worker per sottoscrizione eventi."""

    finished_ok = pyqtSignal(dict)   # payload risultato (schema Step 0.1)
    failed = pyqtSignal(str, str)    # job_id, message
    error = pyqtSignal(str)          # messaggio errore connessione/upload

    def __init__(
        self,
        video_path: str,
        options: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Analisi in cloud")
        self.setFixedSize(460, 220)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self._worker = CloudAnalysisWorker(video_path, options, parent=self)
        self._worker.status_updated.connect(self._on_status)
        self._worker.result_ready.connect(self._on_result)
        self._worker.job_failed.connect(self._on_failed)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_finished)
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
            QPushButton {
                background: #334155;
                color: #e8f0fa;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover { background: #475569; }
            QPushButton:disabled { color: #64748b; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        title = QLabel("ANALISI IN CLOUD")
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

        self._message_label = QLabel("Upload e avvio analisi...")
        self._message_label.setObjectName("statusLabel")
        self._message_label.setAlignment(Qt.AlignCenter)
        self._message_label.setWordWrap(True)
        layout.addWidget(self._message_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._cancel_btn = QPushButton("Interrompi")
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def _on_status(self, ev: dict):
        pct = ev.get("progress", 0)
        msg = ev.get("message") or "In corso..."
        self._progress.setValue(min(100, pct))
        self._percent_label.setText(f"{min(100, pct)}%")
        self._message_label.setText(msg)

    def _on_result(self, payload: dict):
        self._cancel_btn.setEnabled(False)
        self._progress.setValue(100)
        self._percent_label.setText("100%")
        self._message_label.setText("Analisi pronta.")
        self.finished_ok.emit(payload)
        self.accept()

    def _on_failed(self, job_id: str, message: str):
        self._cancel_btn.setEnabled(False)
        self.failed.emit(job_id, message)
        self.reject()

    def _on_error(self, message: str):
        self._cancel_btn.setEnabled(False)
        self.error.emit(message)
        self.reject()

    def _on_worker_finished(self):
        self._cancel_btn.setEnabled(False)

    def _on_cancel(self):
        self._worker.cancel()
        self._message_label.setText("Interruzione in corso...")
        self._cancel_btn.setEnabled(False)

    def start(self):
        self._worker.start()
