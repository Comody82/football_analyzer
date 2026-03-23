"""Dialog per analisi tramite processo separato (analysis_engine)."""
import json
import subprocess
import sys
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal

from analysis.config import get_calibration_path


def has_checkpoint(project_analysis_dir: str, mode: str) -> bool:
    """Verifica se esiste un checkpoint per la modalità indicata."""
    det_dir = Path(project_analysis_dir) / "analysis_output" / "detections"
    if mode in ("player", "full"):
        if list(det_dir.glob("player_detections_checkpoint_*.json")):
            return True
    if mode in ("ball", "full"):
        if list(det_dir.glob("ball_detections_checkpoint_*.json")):
            return True
    return False


def _get_engine_command(
    project_root: Path,
    video_path: str,
    project_analysis_dir: str,
    mode: str,
    resume: bool = False,
    run_preprocess: bool = False,
) -> list:
    """Ritorna comando per avviare analysis_engine. Preferisce script Python (exe ha bug YOLOX)."""
    exe_path = project_root / "dist" / "analysis_engine" / "analysis_engine.exe"
    script_path = project_root / "analysis_engine.py"
    use_crop = (get_calibration_path(project_analysis_dir)).exists()
    crop_args = ["--crop"] if use_crop else []
    base_args = [
        "--video", video_path,
        "--output", project_analysis_dir,
        "--mode", mode,
        "--fps", "10",
        "--checkpoint-first", "500",
        "--checkpoint-interval", "1000",
    ] + crop_args
    if resume:
        base_args.append("--resume")
    if run_preprocess:
        base_args.append("--run-preprocess")
    if script_path.exists():
        return [sys.executable, str(script_path)] + base_args
    if exe_path.exists():
        return [str(exe_path)] + base_args
    return [sys.executable, str(script_path)] + base_args


class AnalysisProcessDialog(QDialog):
    """Dialog che lancia analysis_engine come processo separato e monitora progress.json."""

    finished_ok = pyqtSignal()  # Emesso quando analisi completa con successo
    failed_with_error = pyqtSignal(str)  # Emesso quando avvio o processo fallisce (per proposta cloud)

    def __init__(
        self,
        video_path: str,
        project_analysis_dir: str,
        mode: str,
        parent=None,
        resume: bool = False,
        run_preprocess: bool = False,
        offer_cloud_fallback: bool = False,
    ):
        super().__init__(parent)
        self._video_path = video_path
        self._project_analysis_dir = project_analysis_dir
        self._mode = mode
        self._resume = resume
        self._run_preprocess = bool(run_preprocess)
        self._offer_cloud_fallback = bool(offer_cloud_fallback)
        self._process = None
        self._timer = None
        self._user_cancelled = False
        self._progress_path = Path(project_analysis_dir) / "analysis_output" / "progress.json"
        self._finished_path = Path(project_analysis_dir) / "analysis_output" / "finished.json"
        self._title = {
            "player": "Analisi giocatori",
            "ball": "Analisi palla",
            "full": "Analisi automatica",
        }.get(mode, "Analisi")
        self.setWindowTitle(self._title)
        self._phase_to_step = self._build_phase_to_step()
        self.setFixedSize(460, 220)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowTitleHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self._build_ui()

    def _build_phase_to_step(self):
        """Mappa phase da progress.json -> (step 1-based, total steps)."""
        if self._mode != "full":
            return {}
        order = [
            "preprocess",
            "player_detection",
            "player_tracking",
            "ball_detection",
            "ball_tracking",
            "global_team_clustering",
            "event_engine",
            "metrics",
        ]
        if not self._run_preprocess:
            order = order[1:]
        total = len(order)
        return {p: (i + 1, total) for i, p in enumerate(order)}

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

        title = QLabel(self._title.upper())
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

        init_msg = "Ripresa dall'ultimo punto salvato." if self._resume else "Analisi in corso – il video resterà in pausa per evitare rallentamenti. 0%"
        self._message_label = QLabel(init_msg)
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

    def start(self):
        project_root = Path(__file__).resolve().parent.parent
        cmd = _get_engine_command(
            project_root,
            self._video_path,
            self._project_analysis_dir,
            self._mode,
            resume=self._resume,
            run_preprocess=self._run_preprocess,
        )
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        except Exception as e:
            QMessageBox.warning(self, "Errore", f"Impossibile avviare il motore:\n{e}")
            self.reject()
            return
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(1500)

    def _poll(self):
        if self._process is None:
            return
        ret = self._process.poll()
        if ret is not None:
            self._timer.stop()
            self._on_process_finished(ret)
            return
        if self._progress_path.exists():
            try:
                with open(self._progress_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pct = data.get("pct", 0)
                cur = data.get("current_frame", 0)
                tot = data.get("total_frames", 1)
                phase = data.get("phase", "")
                self._progress.setValue(min(100, pct))
                self._percent_label.setText(f"{min(100, pct)}%")
                step_info = ""
                if getattr(self, "_phase_to_step", None) and phase:
                    step, total = self._phase_to_step.get(phase, (0, 0))
                    if total > 0:
                        step_info = f" – Fase {step}/{total}"
                if tot > 0:
                    status = f"Analisi in corso – Frame {cur}/{tot} ({min(100, pct)}%){step_info}"
                else:
                    status = f"Analisi in corso – {min(100, pct)}%{step_info}"
                self._message_label.setText(status)
            except Exception:
                pass

    def _on_process_finished(self, exit_code: int):
        self._cancel_btn.setEnabled(False)
        if exit_code == 0:
            self._progress.setValue(100)
            self._percent_label.setText("100%")
            self._message_label.setText("Analisi completata – puoi riprendere la riproduzione.")
            QMessageBox.information(
                self,
                "Completato",
                "Analisi completata – puoi riprendere la riproduzione.",
            )
            self.finished_ok.emit()
            self.accept()
        else:
            if self._user_cancelled:
                # Interruzione volontaria: chiudi senza popup (nessun messaggio di errore)
                pass
            else:
                err_msg = "Analisi interrotta."
                if self._finished_path.exists():
                    try:
                        with open(self._finished_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        err_msg = data.get("error", err_msg)
                    except Exception:
                        pass
                elif self._process and self._process.stderr:
                    try:
                        err_msg = self._process.stderr.read().decode("utf-8", errors="replace").strip()[-500:]
                    except Exception:
                        pass
                err_msg = err_msg or f"Exit code: {exit_code}"
                if self._offer_cloud_fallback:
                    self.failed_with_error.emit(err_msg)
                else:
                    QMessageBox.warning(self, "Errore", err_msg)
            self.reject()

    def _on_cancel(self):
        if self._process and self._process.poll() is None:
            self._user_cancelled = True
            self._process.terminate()
            self._message_label.setText("Interruzione in corso...")
            self._cancel_btn.setEnabled(False)
