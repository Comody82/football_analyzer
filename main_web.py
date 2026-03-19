"""
Football Analyzer - Web UI Version
Interfaccia moderna basata su QWebEngineView + HTML/CSS/JS
"""
import sys
import os
import json
import logging
import traceback
from pathlib import Path
from datetime import datetime

# Fix encoding per Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Solo errori nel terminale (evita spam). Per debug: FOOTBALL_ANALYZER_DEBUG=1 python main_web.py
_log_level = logging.DEBUG if os.environ.get('FOOTBALL_ANALYZER_DEBUG') else logging.ERROR
logging.basicConfig(level=_log_level, format='%(levelname)s: %(message)s')
# YOLOX: silenzia messaggi INFO ("Infer time" ecc.)
logging.getLogger("yolox").setLevel(logging.ERROR)

# Precarica PyTorch prima di Qt per evitare WinError 1114 (c10.dll) su Windows
try:
    import torch  # noqa: F401
except ImportError:
    pass

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QDialog,
    QDialogButtonBox,
    QAbstractItemView,
    QShortcut,
    QMessageBox,
    QMenu,
    QWidget,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QStackedLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QCheckBox,
    QLineEdit,
    QSpinBox,
    QGroupBox,
    QFileDialog,
    QInputDialog,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QSizePolicy,
    QFrame,
    QRadioButton,
)
from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QPoint, QTimer, QPropertyAnimation, QEasingCurve, QThread, QSettings
from PyQt5.QtGui import QContextMenuEvent, QKeySequence, QColor, QPainter, QLinearGradient, QRadialGradient, QPen, QPixmap
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel

from backend import BackendBridge
from ui.opencv_video_widget import OpenCVVideoWidget
from ui.drawing_overlay import DrawTool
from ui.highlight_image_creator import HighlightImageCreatorDialog
from ui.highlight_progress_dialog import HighlightProgressDialog
from ui.field_calibration_dialog import FieldCalibrationDialog
from ui.video_preprocessing_dialog import VideoPreprocessingDialog
from ui.player_detection_dialog import get_video_for_detection as get_video_for_player_detection
from ui.analysis_process_dialog import AnalysisProcessDialog, has_checkpoint
from ui.cloud_analysis_dialog import CloudAnalysisDialog
from ui.statistics_dialog import StatisticsDialog
from project_repository import ProjectRepository
from ui.hardware_check import run_hardware_check


# Modalità workspace: "legacy" (3 WebView). d_migration rimosso (layout identico, stesso codice).
WORKSPACE_UI_MODE = os.environ.get("FOOTBALL_WORKSPACE_UI", "legacy")

# Preferenze Fase 3: analisi Locale / Cloud (QSettings)
SETTINGS_ORG = "FootballAnalyzer"
SETTINGS_APP = "FootballAnalyzer"
KEY_ANALYSIS_MODE = "analysis_mode"
KEY_HARDWARE_WARNING_DISMISSED = "hardware_warning_dismissed"
DEFAULT_ANALYSIS_MODE = "cloud"

# Fase 4: base URL API cloud (env o default locale)
CLOUD_API_BASE_URL = os.environ.get("FOOTBALL_ANALYZER_API_URL", "http://localhost:8000")


class HighlightGenerateWorker(QThread):
    """Worker per generazione highlights in background."""
    progress = pyqtSignal(int, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, backend, sequence, output_path):
        super().__init__()
        self._backend = backend
        self._sequence = sequence
        self._output_path = output_path

    def run(self):
        def on_progress(pct, msg):
            self.progress.emit(pct, msg)
        ok, result = self._backend.generate_highlights_package_from_sequence(
            self._sequence, output_path=self._output_path, progress_callback=on_progress
        )
        self.finished_signal.emit(ok, result)


def _log_workspace_bootstrap(stage: str, extra: str = ""):
    """Log tecnico per bootstrap workspace (confronto legacy vs d_migration)."""
    if os.environ.get("FOOTBALL_ANALYZER_DEBUG"):
        logging.debug("[workspace_bootstrap] %s %s", stage, extra)


class CustomWebEngineView(QWebEngineView):
    """QWebEngineView senza menu contestuale browser. Estendibile per menu custom."""

    def contextMenuEvent(self, event: QContextMenuEvent):
        # Disabilita il menu browser standard (Back, Reload, View source, ecc)
        event.accept()
        # Per menu contestuale personalizzato futuro:
        # custom_menu = self._build_custom_context_menu(event.pos())
        # if custom_menu:
        #     custom_menu.exec_(self.mapToGlobal(event.pos()))


class DashboardDivider(QWidget):
    """Divisorio sottile con fade verticale + glow dinamico."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._glow_y = 120
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_glow_global_y(self, global_y: int):
        local = self.mapFromGlobal(QPoint(0, int(global_y)))
        self._glow_y = max(0, min(self.height(), local.y()))
        self.update()

    def paintEvent(self, _event):
        if self.width() <= 0 or self.height() <= 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        h = self.height()
        cx = w / 2.0

        # Linea centrale: sottile e sfumata in alto/basso.
        vgrad = QLinearGradient(0, 0, 0, h)
        vgrad.setColorAt(0.00, QColor(62, 106, 170, 0))
        vgrad.setColorAt(0.20, QColor(68, 118, 188, 22))
        vgrad.setColorAt(0.50, QColor(78, 138, 212, 42))
        vgrad.setColorAt(0.80, QColor(68, 118, 188, 22))
        vgrad.setColorAt(1.00, QColor(62, 106, 170, 0))
        p.setPen(QPen(vgrad, 0.8))
        p.drawLine(int(cx), 0, int(cx), h)

        # Glow locale elegante (core sottile + halo morbido).
        glow_halo = QRadialGradient(cx, float(self._glow_y), 18.0)
        glow_halo.setColorAt(0.00, QColor(62, 171, 243, 48))
        glow_halo.setColorAt(1.00, QColor(62, 171, 243, 0))
        p.fillRect(max(0, int(cx) - 1), 0, 3, h, glow_halo)

        glow_core = QRadialGradient(cx, float(self._glow_y), 9.5)
        glow_core.setColorAt(0.00, QColor(53, 230, 176, 112))
        glow_core.setColorAt(1.00, QColor(53, 230, 176, 0))
        p.fillRect(int(cx), 0, 1, h, glow_core)


class WorkspacePage(QWidget):
    """Workspace Analisi (incapsulato in routing, riceve projectId)."""

    backToDashboardRequested = pyqtSignal()

    def __init__(self, project_id: str, project_repository: ProjectRepository):
        super().__init__()
        project_meta = project_repository.get(project_id)
        project_name = project_meta.name if project_meta else "Progetto"
        self.setStyleSheet("""
        QWidget#workspaceTopBar {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(10, 16, 28, 0.80),
                stop:0.5 rgba(24, 34, 52, 0.76),
                stop:1 rgba(10, 16, 28, 0.80)
            );
            border: none;
            border-top: 1px solid rgba(255, 255, 255, 0.10);
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        QLabel#workspaceBrand {
            color: #e9f2ff;
            font-size: 19px;
            font-weight: 700;
        }
        QLabel#workspaceProjectChip {
            color: #dce8fb;
            font-size: 13px;
            font-weight: 600;
            padding: 8px 14px;
            border-radius: 14px;
            background: rgba(16, 30, 54, 0.76);
            border: none;
        }
        QPushButton[class="workspaceTopBtn"] {
            min-height: 34px;
            padding: 0 14px;
            border-radius: 8px;
            border: none;
            background: rgba(18, 30, 52, 0.86);
            color: #e6f0ff;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton[class="workspaceTopBtn"]:hover {
            background: rgba(34, 52, 84, 0.92);
            border: none;
        }
        QPushButton#workspaceDashboardBtn {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #0f5d4d,
                stop:0.52 #17806a,
                stop:1 #29b48d
            );
            color: #e8f2ff;
            border: none;
            font-weight: 700;
        }
        QPushButton#workspaceDashboardBtn:hover {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #137261,
                stop:0.52 #1e947c,
                stop:1 #33c89f
            );
        }
        QPushButton#workspaceSaveBtn {
            min-width: 154px;
            padding-right: 34px;
        }
        QLabel#workspaceSaveCheck {
            color: rgb(120, 180, 255);
            font-size: 14px;
            font-weight: 800;
            background: transparent;
        }
        background: qradialgradient(
            cx: 0.50, cy: 0.05, radius: 1.20,
            fx: 0.52, fy: 0.06,
            stop: 0 #101d35,
            stop: 0.20 #0b162b,
            stop: 0.46 #081223,
            stop: 0.74 #060d1a,
            stop: 1 #030712
        );
        """)
        self.setContentsMargins(0, 0, 0, 0)
        self.project_id = project_id
        self.project_repository = project_repository
        self.setWindowTitle("Football Analyzer - Web Edition")
        self.setObjectName("workspaceRoot")
        self._ui_mode = WORKSPACE_UI_MODE
        self._video_source_locked = False
        self._loaded_webviews = 0
        self._webviews_ready = {"left": False, "center": False, "right": False}
        self._frontend_ready = {"left": False, "center": False, "right": False}
        self._initial_ui_revealed = False
        self._ui_boot_locked = True
        self._highlights_mode = False
        self._highlights_image_items = []
        self._analysis_in_progress = False
        self._analysis_dialog = None
        # Fase 3: rilevamento hardware (cache a ogni avvio workspace)
        self._hardware_check_result = run_hardware_check()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        topbar = QWidget()
        topbar.setObjectName("workspaceTopBar")
        topbar.setFixedHeight(56)
        self._topbar = topbar
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(14, 8, 14, 8)
        topbar_layout.setSpacing(10)

        brand = QLabel("⚽ Football Analyzer")
        brand.setObjectName("workspaceBrand")
        topbar_layout.addWidget(brand, 0, Qt.AlignVCenter)

        project_chip = QLabel(f"▴ {project_name} - Analisi")
        project_chip.setObjectName("workspaceProjectChip")
        topbar_layout.addWidget(project_chip, 0, Qt.AlignVCenter)
        topbar_layout.addStretch(1)

        btn_stats = QPushButton("Statistiche")
        btn_stats.setProperty("class", "workspaceTopBtn")
        btn_stats.clicked.connect(self._on_statistics_clicked)
        topbar_layout.addWidget(btn_stats, 0, Qt.AlignVCenter)

        self.btn_export_report = QPushButton("Esporta report")
        self.btn_export_report.setProperty("class", "workspaceTopBtn")
        self.btn_export_report.clicked.connect(self._on_export_report_clicked)
        topbar_layout.addWidget(self.btn_export_report, 0, Qt.AlignVCenter)

        self.btn_save_project = QPushButton("Salva Progetto")
        self.btn_save_project.setObjectName("workspaceSaveBtn")
        self.btn_save_project.setProperty("class", "workspaceTopBtn")
        self.btn_save_project.clicked.connect(self._on_save_project_clicked)
        topbar_layout.addWidget(self.btn_save_project, 0, Qt.AlignVCenter)
        self.save_check_label = QLabel("✓", self.btn_save_project)
        self.save_check_label.setObjectName("workspaceSaveCheck")
        self.save_check_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.save_check_opacity = QGraphicsOpacityEffect(self.save_check_label)
        self.save_check_label.setGraphicsEffect(self.save_check_opacity)
        self.save_check_opacity.setOpacity(0.0)
        self.save_check_anim = QPropertyAnimation(self.save_check_opacity, b"opacity", self)
        self.save_check_anim.setDuration(1800)
        self.save_check_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.save_check_label.raise_()

        btn_dashboard = QPushButton("Dashboard")
        btn_dashboard.setObjectName("workspaceDashboardBtn")
        btn_dashboard.setProperty("class", "workspaceTopBtn")
        btn_dashboard.clicked.connect(self._go_back_to_dashboard)
        topbar_layout.addWidget(btn_dashboard, 0, Qt.AlignVCenter)
        root_layout.addWidget(topbar, 0)

        from PyQt5.QtWebEngineWidgets import QWebEngineSettings

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        root_layout.addLayout(main_layout, 1)

        self._build_ui_legacy(main_layout, QWebEngineSettings)

        # Scorciatoie, curtain, etc. (comuni)
        self._setup_shortcuts()
        self._dragging_window = False
        self._drag_offset = None
        self._position_save_check()
        self._position_open_video_button()
        self._update_open_video_cta_visibility()
        self._setup_startup_curtain()
        self.setUpdatesEnabled(False)
        QTimer.singleShot(4500, self._force_reveal_if_stuck)

    def _build_ui_legacy(self, main_layout, QWebEngineSettings):
        """Layout legacy: 3 WebView (Eventi | Video+Controlli | Clip)."""
        _log_workspace_bootstrap("build", "legacy")
        self.web_view_unified = None

        self.web_view_left = CustomWebEngineView()
        self.web_view_left.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        self.web_view_left.page().setBackgroundColor(QColor(0x0B, 0x13, 0x20))
        self.web_view_left.setStyleSheet("background: transparent; border: none;")
        self.web_view_left.setFixedWidth(300)
        main_layout.addWidget(self.web_view_left, 0)

        # Colonna centrale: host con stack (workspace normale / studio highlights)
        self._center_widget = QWidget()
        self._center_widget.setStyleSheet("background: transparent; border: none;")
        self._center_stack = QStackedLayout(self._center_widget)
        self._center_stack.setContentsMargins(0, 0, 0, 0)
        self._center_stack.setSpacing(0)

        center_normal_widget = QWidget()
        center_normal_widget.setStyleSheet("background: transparent; border: none;")
        center_layout = QVBoxLayout(center_normal_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        self._center_normal_widget = center_normal_widget

        self.video_player = OpenCVVideoWidget()
        self.video_player.setStyleSheet("background-color: #0B1220; border-radius: 12px;")
        center_layout.addWidget(self.video_player, 5)
        self.drawing_overlay = self.video_player.drawing_overlay

        # CTA nell'area video vuota: apre il file video direttamente dal centro.
        self.btn_open_video_overlay = QPushButton("📹 Apri Video", self.video_player)
        self.btn_open_video_overlay.setFixedHeight(46)
        self.btn_open_video_overlay.setMinimumWidth(176)
        self.btn_open_video_overlay.setCursor(Qt.PointingHandCursor)
        self.btn_open_video_overlay.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #394250,
                    stop:0.52 #4a5567,
                    stop:1 #5d6b82
                );
                color: #eef3fa;
                border: 1px solid rgba(210, 220, 236, 0.24);
                border-radius: 12px;
                padding: 0 18px;
                font-size: 14px;
                font-weight: 700;
                letter-spacing: 0.02em;
                text-align: center;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #465366,
                    stop:0.52 #58657c,
                    stop:1 #6a7892
                );
                border: 1px solid rgba(224, 234, 248, 0.36);
            }
            QPushButton:pressed {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #313947,
                    stop:0.52 #3f4a5c,
                    stop:1 #4e5a70
                );
            }
        """)
        cta_shadow = QGraphicsDropShadowEffect(self.btn_open_video_overlay)
        cta_shadow.setBlurRadius(28)
        cta_shadow.setOffset(0, 10)
        cta_shadow.setColor(QColor(8, 12, 20, 170))
        self.btn_open_video_overlay.setGraphicsEffect(cta_shadow)
        self.btn_open_video_overlay.raise_()

        # Connect drawing overlay (video + disegni in scena unificata)
        self.drawing_overlay.emptyAreaLeftClicked.connect(self._on_empty_area_clicked)
        self.drawing_overlay.drawingConfirmed.connect(self._on_drawing_confirmed)
        self.drawing_overlay.drawingStarted.connect(self._on_drawing_started)
        self.drawing_overlay.annotationDeleted.connect(self._on_annotation_deleted)
        self.drawing_overlay.annotationModified.connect(self._on_annotation_modified)
        self.drawing_overlay.zoomRequested.connect(self._on_zoom_requested)
        self._zoom_level = 1.0
        self._zoom_max = 5.0
        if hasattr(self.video_player, 'zoomLevelChanged'):
            self.video_player.zoomLevelChanged.connect(self._on_zoom_level_changed)

        # Resize overlays quando video player viene ridimensionato
        self.video_player.resizeEvent = self._video_player_resized

        # Timeline e controlli sotto il video (WebView dedicata)
        self.web_view_center_controls = CustomWebEngineView()
        self.web_view_center_controls.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        self.web_view_center_controls.page().setBackgroundColor(QColor(0x0B, 0x13, 0x20))
        self.web_view_center_controls.setStyleSheet("background: transparent; border: none;")
        center_layout.addWidget(self.web_view_center_controls, 2)
        self._center_stack.addWidget(center_normal_widget)

        # Colonna destra: WebView Clip/Statistiche
        self._highlights_studio_panel = self._build_highlights_studio_panel()
        self._center_stack.addWidget(self._highlights_studio_panel)
        self._center_stack.setCurrentWidget(self._center_normal_widget)
        main_layout.addWidget(self._center_widget, 1)

        # Colonna destra: WebView Clip/Statistiche
        self.web_view_right = CustomWebEngineView()
        self.web_view_right.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        self.web_view_right.page().setBackgroundColor(QColor(0x0B, 0x13, 0x20))
        self.web_view_right.setStyleSheet("background: transparent; border: none;")
        self.web_view_right.setFixedWidth(300)
        main_layout.addWidget(self.web_view_right, 0)

        # Reveal sincronizzato: evita comparsa "a cascata" delle colonne al boot.
        self.web_view_left.setVisible(False)
        self._center_widget.setVisible(False)
        self.web_view_right.setVisible(False)

        # Refresh disegni al cambio posizione e al passaggio play/pausa (es. pausa su evento)
        self.video_player.positionChanged.connect(self._refresh_drawings_visibility)
        self.video_player.playbackStateChanged.connect(self._refresh_drawings_visibility)
        self.video_player.playbackStateChanged.connect(self._block_play_during_analysis)
        
        # Backend bridge
        self.backend = BackendBridge(
            video_player=self.video_player,
            drawing_overlay=self.drawing_overlay,
            parent_window=self
        )
        self.backend.load_project_from_path(
            project_id=self.project_id,
            project_file_path=self.project_repository.get_project_file_path(self.project_id),
        )
        self._restore_saved_project_video()
        
        # QWebChannel per comunicazione Python ↔ JavaScript
        self.channel = QWebChannel()
        self.channel.registerObject('backend', self.backend)
        self.web_view_left.page().setWebChannel(self.channel)
        self.web_view_center_controls.page().setWebChannel(self.channel)
        self.web_view_right.page().setWebChannel(self.channel)
        self.btn_open_video_overlay.clicked.connect(self._handle_open_video_request)
        self.backend.videoLoaded.connect(lambda _path: self._update_open_video_cta_visibility())
        self.backend.videoLoaded.connect(lambda _path: self._load_tracking_overlay())
        self.web_view_left.loadFinished.connect(lambda ok: self._on_any_webview_loaded("left", ok))
        self.web_view_center_controls.loadFinished.connect(lambda ok: self._on_any_webview_loaded("center", ok))
        self.web_view_right.loadFinished.connect(lambda ok: self._on_any_webview_loaded("right", ok))
        
        # Carica frontend modulare 3 colonne
        frontend_path = Path(__file__).parent / 'frontend'
        if frontend_path.exists():
            left_url = QUrl.fromLocalFile(str((frontend_path / 'events.html').absolute()))
            center_url = QUrl.fromLocalFile(str((frontend_path / 'timeline_controls.html').absolute()))
            right_url = QUrl.fromLocalFile(str((frontend_path / 'clips.html').absolute()))
            self.web_view_left.setUrl(left_url)
            self.web_view_center_controls.setUrl(center_url)
            self.web_view_right.setUrl(right_url)
            logging.info("Loading Web UI (3 columns)")
        else:
            logging.error(f"Frontend not found: {frontend_path}")

    def _on_draw_tool_changed(self, tool):
        """Callback cambio strumento disegno (barra testo ora con tasto destro)."""
        pass

    def _setup_shortcuts(self):
        """Configura scorciatoie da tastiera per controlli video."""
        b = self.backend
        # Space: Play/Pausa
        QShortcut(QKeySequence(Qt.Key_Space), self, b.togglePlayPause, context=Qt.ApplicationShortcut)
        # R: Restart
        QShortcut(QKeySequence(Qt.Key_R), self, b.restartVideo, context=Qt.ApplicationShortcut)
        # Left: Indietro 5s
        QShortcut(QKeySequence(Qt.Key_Left), self, lambda: b.videoRewind(5), context=Qt.ApplicationShortcut)
        # Right: Avanti 5s
        QShortcut(QKeySequence(Qt.Key_Right), self, lambda: b.videoForward(5), context=Qt.ApplicationShortcut)
        # , oppure < : Evento precedente (layout US e non-US)
        QShortcut(QKeySequence(Qt.Key_Comma), self, b.goToPrevEvent, context=Qt.ApplicationShortcut)
        QShortcut(QKeySequence(Qt.Key_Less), self, b.goToPrevEvent, context=Qt.ApplicationShortcut)
        # . oppure > : Evento successivo
        QShortcut(QKeySequence(Qt.Key_Period), self, b.goToNextEvent, context=Qt.ApplicationShortcut)
        QShortcut(QKeySequence(Qt.Key_Greater), self, b.goToNextEvent, context=Qt.ApplicationShortcut)
        # F1: Mostra lista scorciatoie
        QShortcut(QKeySequence(Qt.Key_F1), self, self._show_shortcuts_help, context=Qt.ApplicationShortcut)

    def _show_shortcuts_help(self):
        """Mostra dialog con lista scorciatoie da tastiera."""
        msg = """<h3>Scorciatoie da tastiera</h3>
        <table style='font-family: sans-serif;'>
        <tr><td><b>Spazio</b></td><td>Play / Pausa</td></tr>
        <tr><td><b>R</b></td><td>Restart (dall'inizio)</td></tr>
        <tr><td><b>←</b> Freccia sinistra</td><td>Indietro 5 secondi</td></tr>
        <tr><td><b>→</b> Freccia destra</td><td>Avanti 5 secondi</td></tr>
        <tr><td><b>,</b> o <b>&lt;</b></td><td>Evento precedente</td></tr>
        <tr><td><b>.</b> o <b>&gt;</b></td><td>Evento successivo</td></tr>
        <tr><td><b>F1</b></td><td>Mostra questa guida</td></tr>
        </table>"""
        QMessageBox.information(self, "Scorciatoie da tastiera", msg)

    def _video_player_resized(self, event):
        """Layout ridimensiona drawing_overlay; fitSceneToView da resizeEvent dell'overlay."""
        if hasattr(self, 'drawing_overlay'):
            self.drawing_overlay.fitSceneToView()
        self._position_open_video_button()
        self._position_save_check()
        self._ensure_video_frame_rendered()
        OpenCVVideoWidget.resizeEvent(self.video_player, event)
        self._position_save_check()
        self._ensure_video_frame_rendered()
        OpenCVVideoWidget.resizeEvent(self.video_player, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_startup_curtain()

    def _position_save_check(self):
        if not hasattr(self, "btn_save_project") or not hasattr(self, "save_check_label"):
            return
        btn = self.btn_save_project
        x = max(8, btn.width() - 18)
        y = max(6, (btn.height() - self.save_check_label.sizeHint().height()) // 2)
        self.save_check_label.move(x, y)

    def _show_save_check_feedback(self, success: bool):
        if not hasattr(self, "save_check_opacity"):
            return
        self.save_check_anim.stop()
        if not success:
            self.save_check_opacity.setOpacity(0.0)
            return
        self.save_check_opacity.setOpacity(1.0)
        self.save_check_anim.setStartValue(1.0)
        self.save_check_anim.setEndValue(0.0)
        self.save_check_anim.start()
        self._position_save_check()

    def _on_save_project_clicked(self):
        ok = self.persist_project()
        self._show_save_check_feedback(bool(ok))

    def _on_statistics_clicked(self):
        """Apre il dialog Statistiche con possesso %, passaggi, tiri, recuperi, pressing e metriche."""
        project_dir = self._get_project_analysis_dir()
        if not project_dir:
            QMessageBox.warning(self.window(), "Statistiche", "Progetto non valido.")
            return
        from analysis.config import get_analysis_output_path
        metrics_path = Path(get_analysis_output_path(project_dir)) / "metrics.json"
        if not metrics_path.exists():
            QMessageBox.information(
                self.window(),
                "Statistiche",
                "Esegui prima un'analisi automatica completa per vedere possesso, passaggi e metriche.",
            )
            return
        dlg = StatisticsDialog(project_dir, parent=self.window())
        dlg.exec_()

    def _get_project_analysis_dir(self):
        """Restituisce la cartella analysis del progetto corrente o None."""
        if not hasattr(self, "project_id") or not self.project_id or not hasattr(self, "project_repository"):
            return None
        base = getattr(self.project_repository, "base_path", None)
        if not base:
            return None
        return str(Path(base) / "analysis" / str(self.project_id))

    def _on_export_report_clicked(self):
        """Menu Esporta report: JSON, CSV, PDF (Fase 8)."""
        project_dir = self._get_project_analysis_dir()
        if not project_dir:
            QMessageBox.warning(self.window(), "Esporta report", "Progetto non valido.")
            return
        from analysis.report import export_json, export_csv, export_pdf
        from analysis.config import get_analysis_output_path
        if not (Path(get_analysis_output_path(project_dir)) / "metrics.json").exists():
            QMessageBox.information(
                self.window(),
                "Esporta report",
                "Esegui prima un'analisi completa (Analisi automatica) per generare metriche e eventi.",
            )
            return
        menu = QMenu(self.window())
        act_json = menu.addAction("Esporta come JSON (risultato completo)")
        act_csv = menu.addAction("Esporta come CSV (tabelle)")
        act_pdf = menu.addAction("Esporta come PDF (report)")
        pos = self.btn_export_report.mapToGlobal(self.btn_export_report.rect().bottomLeft()) if hasattr(self, "btn_export_report") else self._topbar.mapToGlobal(self._topbar.rect().bottomRight())
        act = menu.exec_(pos)
        if not act:
            return
        if act == act_json:
            path, _ = QFileDialog.getSaveFileName(self.window(), "Esporta JSON", "", "JSON (*.json)")
            if path:
                ok = export_json(project_dir, path, source="local", project_id=getattr(self, "project_id", None))
                QMessageBox.information(self.window(), "Esporta report", "Export completato." if ok else "Export fallito.")
        elif act == act_csv:
            path = QFileDialog.getExistingDirectory(self.window(), "Cartella per file CSV")
            if path:
                ok = export_csv(project_dir, path, include_events=True)
                QMessageBox.information(self.window(), "Esporta report", "Export CSV completato." if ok else "Export fallito.")
        elif act == act_pdf:
            path, _ = QFileDialog.getSaveFileName(self.window(), "Esporta PDF", "", "PDF (*.pdf)")
            if path:
                try:
                    ok = export_pdf(project_dir, path, source="local", project_id=getattr(self, "project_id", None))
                    QMessageBox.information(self.window(), "Esporta report", "Export PDF completato." if ok else "Export fallito.")
                except ImportError as e:
                    QMessageBox.warning(self.window(), "Esporta report", "Per il PDF installa reportlab: pip install reportlab")

    def _handle_open_video_request(self):
        if self._video_source_locked:
            QMessageBox.information(
                self,
                "Video bloccato",
                "Questo progetto ha gia' un video associato. "
                "Per coerenza del progetto il cambio video e' disabilitato."
            )
            return
        self.backend.openVideo()

    def _restore_saved_project_video(self):
        """Carica il video gia' salvato sul progetto e blocca il cambio sorgente.
        Se esiste preprocessato, lo usa per allineare display e dati di tracking."""
        saved_path = str(getattr(self.backend.project, "video_path", "") or "").strip()
        if not saved_path:
            self._video_source_locked = False
            return
        p = Path(saved_path)
        if not p.exists():
            logging.warning("Video salvato non trovato: %s", saved_path)
            self._video_source_locked = False
            return
        project_dir = None
        if hasattr(self, "project_id") and self.project_id and hasattr(self, "project_repository"):
            base = getattr(self.project_repository, "base_path", None)
            if base:
                project_dir = str(Path(base) / "analysis" / str(self.project_id))
        video_to_load = str(p)
        if project_dir:
            from analysis.video_preprocessing import get_preprocessed_path
            preprocessed = get_preprocessed_path(project_dir)
            if Path(preprocessed).exists():
                video_to_load = str(preprocessed)
        self.video_player.load(video_to_load)
        self.backend.project.video_path = str(p)
        self.backend.videoLoaded.emit(str(p))
        self._video_source_locked = True
        self._load_tracking_overlay()
        QTimer.singleShot(0, self._ensure_video_frame_rendered)
        QTimer.singleShot(180, self._ensure_video_frame_rendered)

    def load_analysis_result(self, project_dir=None, result_payload=None):
        """
        Caricamento risultati unificato (Fase 3.6): accetta sia percorso locale (cartella progetto)
        sia payload da API (GET /v1/jobs/{id}/result). Stesso schema → stessa UI (timeline, overlay).
        """
        if not getattr(self, "video_player", None):
            return
        ball_tracks = None
        player_tracks = None
        if result_payload is not None:
            try:
                tracking = result_payload.get("tracking") or {}
                player_tracks = tracking.get("player_tracks")
                ball_tracks = tracking.get("ball_tracks")
                events = result_payload.get("events") or {}
                automatic = events.get("automatic", [])
                if automatic and getattr(self, "backend", None):
                    self.backend.setAutomaticEvents(json.dumps(automatic))
            except Exception as e:
                logging.warning("Caricamento risultato da payload fallito: %s", e)
            self.video_player.setTrackingOverlay(ball_tracks, player_tracks)
            return
        if project_dir:
            try:
                from analysis.ball_tracking import get_ball_tracks_path
                from analysis.player_tracking import get_tracks_path
                from analysis.config import get_analysis_output_path
                ball_path = Path(get_ball_tracks_path(project_dir)).resolve()
                pt_path = Path(get_tracks_path(project_dir)).resolve()
                if ball_path.exists():
                    with open(ball_path, "r", encoding="utf-8") as f:
                        ball_tracks = json.load(f)
                if pt_path.exists():
                    with open(pt_path, "r", encoding="utf-8") as f:
                        player_tracks = json.load(f)
                # Fase 8: carica eventi automatici (event engine) per timeline
                if getattr(self, "backend", None):
                    events_engine_path = Path(get_analysis_output_path(project_dir)) / "detections" / "events_engine.json"
                    if events_engine_path.exists():
                        with open(events_engine_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        self.backend.setAutomaticEvents(json.dumps(data.get("automatic", [])))
                    else:
                        self.backend.setAutomaticEvents("[]")
            except Exception as e:
                logging.warning("Caricamento tracking da progetto fallito: %s", e)
            self.video_player.setTrackingOverlay(ball_tracks, player_tracks)
            return
        self.video_player.setTrackingOverlay(None, None)

    def _load_tracking_overlay(self):
        """Carica ball_tracks e player_tracks dal progetto e li passa al video widget (usa percorso unificato)."""
        project_dir = None
        if hasattr(self, "project_id") and self.project_id and hasattr(self, "project_repository"):
            base = getattr(self.project_repository, "base_path", None)
            if base:
                project_dir = str(Path(base) / "analysis" / str(self.project_id))
                project_dir = str(Path(project_dir).resolve())
        self.load_analysis_result(project_dir=project_dir)

    def _ensure_video_frame_rendered(self):
        """Forza il render del frame corrente quando il widget acquisisce dimensione."""
        if not getattr(self, "video_player", None):
            return
        if self.video_player.duration() <= 0:
            return
        if self.video_player.state() == 1:
            return
        pos = max(0, self.video_player.position())
        self.video_player.setPosition(pos)
        _log_workspace_bootstrap("video_render_ready", "")

    def _position_open_video_button(self):
        if not hasattr(self, "btn_open_video_overlay"):
            return
        vp_rect = self.video_player.rect()
        x = max(10, (vp_rect.width() - self.btn_open_video_overlay.width()) // 2)
        y = max(10, (vp_rect.height() - self.btn_open_video_overlay.height()) // 2)
        self.btn_open_video_overlay.move(x, y)
        self.btn_open_video_overlay.raise_()

    def _update_open_video_cta_visibility(self):
        if not hasattr(self, "btn_open_video_overlay"):
            return
        if getattr(self, "_highlights_mode", False):
            self.btn_open_video_overlay.setVisible(False)
            return
        has_loaded_video = bool(self.video_player and self.video_player.duration() > 0)
        self.btn_open_video_overlay.setVisible((not has_loaded_video) and (not self._video_source_locked))
        if not has_loaded_video:
            self._position_open_video_button()

    def _build_highlights_studio_panel(self):
        panel = QWidget()
        panel.setStyleSheet("""
            QWidget {
                background: transparent;
                color: #e8f0fa;
            }
            QLabel#hlTitle {
                font-size: 22px;
                font-weight: 700;
                color: #f1f7ff;
            }
            QLabel#hlSubtitle {
                font-size: 12px;
                color: #9db3cc;
            }
            QCheckBox {
                font-size: 13px;
                color: #d9e6f6;
            }
            QListWidget {
                background: rgba(20, 30, 50, 0.75);
                border: 1px solid rgba(120, 156, 206, 0.35);
                border-radius: 10px;
                padding: 6px;
            }
            QPushButton {
                min-height: 34px;
                padding: 0 14px;
                border-radius: 8px;
                border: 1px solid rgba(120, 156, 206, 0.28);
                background: rgba(24, 38, 62, 0.88);
                color: #e8f2ff;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(34, 52, 84, 0.94);
            }
            QPushButton#hlGenerateBtn {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2d4a6a,
                    stop:0.52 #3d5f8a,
                    stop:1 #5a82b5
                );
                border: none;
                color: #eafff8;
                font-weight: 700;
            }
            QPushButton#hlGenerateBtn:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #137261,
                    stop:0.52 #1e947c,
                    stop:1 #33c89f
                );
            }
            QGroupBox#hlMatchGroup {
                font-size: 12px;
                font-weight: 600;
                color: #b8cde8;
                border: 1px solid rgba(120, 156, 206, 0.4);
                border-radius: 8px;
                margin-top: 8px;
                padding: 10px 12px 6px 12px;
            }
            QGroupBox#hlMatchGroup::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: #c8daf0;
            }
            QSpinBox {
                min-width: 48px;
                background: rgba(20, 30, 50, 0.8);
                color: #e8f0fa;
                border: 1px solid rgba(120, 156, 206, 0.35);
                border-radius: 6px;
                padding: 4px 8px;
            }
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        title = QLabel("Studio Highlights")
        title.setObjectName("hlTitle")
        subtitle = QLabel("Seleziona clip, ordina la sequenza e inserisci immagini dove vuoi.")
        subtitle.setObjectName("hlSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Dati partita (per pre-compilare Crea Immagine)
        match_group = QGroupBox("Dati partita")
        match_group.setObjectName("hlMatchGroup")
        match_layout = QHBoxLayout(match_group)
        match_layout.addWidget(QLabel("Squadra casa:"))
        self._edit_team_home = QLineEdit()
        self._edit_team_home.setPlaceholderText("es. Milan")
        self._edit_team_home.setMaximumWidth(140)
        self._edit_team_home.editingFinished.connect(self._save_match_metadata)
        match_layout.addWidget(self._edit_team_home)
        match_layout.addWidget(QLabel("Squadra ospiti:"))
        self._edit_team_away = QLineEdit()
        self._edit_team_away.setPlaceholderText("es. Inter")
        self._edit_team_away.setMaximumWidth(140)
        self._edit_team_away.editingFinished.connect(self._save_match_metadata)
        match_layout.addWidget(self._edit_team_away)
        match_layout.addWidget(QLabel("Punteggio:"))
        self._spin_score_home = QSpinBox()
        self._spin_score_home.setRange(0, 99)
        self._spin_score_home.setValue(0)
        self._spin_score_home.valueChanged.connect(self._save_match_metadata)
        match_layout.addWidget(self._spin_score_home)
        match_layout.addWidget(QLabel("-"))
        self._spin_score_away = QSpinBox()
        self._spin_score_away.setRange(0, 99)
        self._spin_score_away.setValue(0)
        self._spin_score_away.valueChanged.connect(self._save_match_metadata)
        match_layout.addWidget(self._spin_score_away)
        match_layout.addWidget(QLabel("Data:"))
        self._edit_match_date = QLineEdit()
        self._edit_match_date.setPlaceholderText("es. 15 Gen 2025")
        self._edit_match_date.setMaximumWidth(120)
        self._edit_match_date.editingFinished.connect(self._save_match_metadata)
        match_layout.addWidget(self._edit_match_date)
        match_layout.addStretch(1)
        layout.addWidget(match_group)

        self.chk_hl_all = QCheckBox("Includi tutte le clip")
        self.chk_hl_all.setChecked(True)
        self.chk_hl_all.stateChanged.connect(self._on_hl_select_all_changed)
        layout.addWidget(self.chk_hl_all)

        self.list_hl_clips = QListWidget()
        layout.addWidget(self.list_hl_clips, 1)

        seq_label = QLabel("Sequenza finale (trascina per riordinare):")
        layout.addWidget(seq_label)
        self.list_hl_sequence = QListWidget()
        self.list_hl_sequence.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_hl_sequence.setDefaultDropAction(Qt.MoveAction)
        self.list_hl_sequence.itemDoubleClicked.connect(self._on_hl_sequence_item_double_clicked)
        layout.addWidget(self.list_hl_sequence, 2)

        seq_row = QHBoxLayout()
        btn_add_img = QPushButton("+ Aggiungi immagine")
        btn_add_img.clicked.connect(self._add_highlight_image)
        btn_create_img = QPushButton("Crea Immagine")
        btn_create_img.clicked.connect(self._create_highlight_image)
        btn_add_clips = QPushButton("Aggiungi clip selezionate")
        btn_add_clips.clicked.connect(self._add_selected_clips_to_sequence)
        btn_remove_seq = QPushButton("Rimuovi selezionato")
        btn_remove_seq.clicked.connect(self._remove_from_sequence)
        seq_row.addWidget(btn_add_clips)
        seq_row.addWidget(btn_add_img)
        seq_row.addWidget(btn_create_img)
        seq_row.addWidget(btn_remove_seq)
        layout.addLayout(seq_row)

        actions = QHBoxLayout()
        actions.addStretch(1)
        btn_close = QPushButton("Chiudi studio")
        btn_close.clicked.connect(self.hide_highlights_studio)
        btn_generate = QPushButton("Genera Highlights")
        btn_generate.setObjectName("hlGenerateBtn")
        btn_generate.clicked.connect(self._generate_highlights_from_studio)
        actions.addWidget(btn_close, 0)
        actions.addWidget(btn_generate, 0)
        layout.addLayout(actions)
        return panel

    def _save_match_metadata(self):
        """Salva i dati partita nel progetto."""
        md = getattr(self.backend.project, "match_metadata", None)
        if md is None:
            self.backend.project.match_metadata = {}
            md = self.backend.project.match_metadata
        md["team_home"] = (self._edit_team_home.text() or "").strip()
        md["team_away"] = (self._edit_team_away.text() or "").strip()
        md["score_home"] = self._spin_score_home.value()
        md["score_away"] = self._spin_score_away.value()
        md["match_date"] = (self._edit_match_date.text() or "").strip()

    def _refresh_match_metadata_fields(self):
        """Carica i dati partita dal progetto nei campi."""
        md = getattr(self.backend.project, "match_metadata", None) or {}
        self._edit_team_home.setText(str(md.get("team_home", "")))
        self._edit_team_away.setText(str(md.get("team_away", "")))
        self._spin_score_home.setValue(int(md.get("score_home", 0)))
        self._spin_score_away.setValue(int(md.get("score_away", 0)))
        self._edit_match_date.setText(str(md.get("match_date", "")))

    def _refresh_highlights_clip_list(self):
        if not hasattr(self, "list_hl_clips"):
            return
        self.list_hl_clips.clear()
        for clip in self.backend.clips:
            label = clip.get("name", "Clip")
            start = int(clip.get("start", 0))
            end = int(clip.get("end", 0))
            item = QListWidgetItem(f"{label}   ({start//1000}s - {end//1000}s)")
            item.setData(Qt.UserRole, clip.get("id"))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.list_hl_clips.addItem(item)
        self._on_hl_select_all_changed(Qt.Checked if self.chk_hl_all.isChecked() else Qt.Unchecked)

    def _on_hl_select_all_changed(self, state):
        enable_checks = state != Qt.Checked
        if hasattr(self, "list_hl_clips"):
            self.list_hl_clips.setEnabled(enable_checks)

    def _ask_insert_position(self, label_default="Alla fine") -> int:
        """Chiede dove inserire. Ritorna indice (0=inizio, n=posizione)."""
        n = self.list_hl_sequence.count()
        if n == 0:
            return 0
        opts = ["All'inizio"] + [f"Dopo elemento {i + 1}" for i in range(n)] + ["Alla fine"]
        choice, ok = QInputDialog.getItem(
            self, "Dove inserire?", "Posizione:", opts, n + 1, False
        )
        if not ok:
            return -1
        idx = opts.index(choice)
        return idx

    def _hl_insert_item(self, seq_item: dict, index: int):
        """Inserisce un item (clip o image) nella sequenza alla posizione index."""
        if seq_item.get("type") == "clip":
            clip = next((c for c in self.backend.clips if c.get("id") == seq_item.get("clip_id")), None)
            label = (clip or {}).get("name", "Clip")
            start = int((clip or {}).get("start", 0))
            end = int((clip or {}).get("end", 0))
            txt = f"Clip: {label}   ({start//1000}s - {end//1000}s)"
        else:
            path = seq_item.get("path", "")
            dur = seq_item.get("duration_sec", 3)
            txt = f"Img: {Path(path).name}   ({dur}s)"
        item = QListWidgetItem(txt)
        item.setData(Qt.UserRole, seq_item)
        if index < 0 or index >= self.list_hl_sequence.count():
            self.list_hl_sequence.addItem(item)
        else:
            self.list_hl_sequence.insertItem(index, item)

    def _add_selected_clips_to_sequence(self):
        clip_ids = self._selected_highlight_clip_ids()
        if not clip_ids:
            QMessageBox.information(self, "Sequenza", "Nessuna clip selezionata.")
            return
        idx = self._ask_insert_position()
        if idx < 0:
            return
        for cid in clip_ids:
            self._hl_insert_item({"type": "clip", "clip_id": cid}, idx)
            idx += 1

    def _create_highlight_image(self):
        match_metadata = getattr(self.backend.project, "match_metadata", None) or {}
        dlg = HighlightImageCreatorDialog(self, match_metadata=match_metadata)
        if dlg.exec_() != QDialog.Accepted:
            return
        path = getattr(dlg, "_image_path", None)
        duration = getattr(dlg, "_duration_sec", 3)
        if path:
            seq_item = {"type": "image", "path": path, "duration_sec": duration}
            idx = self._ask_insert_position()
            if idx >= 0:
                self._hl_insert_item(seq_item, idx)

    def _add_highlight_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona immagine highlights",
            "",
            "Image Files (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*.*)"
        )
        if not path:
            return
        seconds, ok = QInputDialog.getInt(
            self,
            "Durata immagine",
            "Durata (secondi):",
            value=3,
            min=1,
            max=60
        )
        if not ok:
            return
        seq_item = {"type": "image", "path": path, "duration_sec": int(seconds)}
        idx = self._ask_insert_position()
        if idx >= 0:
            self._hl_insert_item(seq_item, idx)

    def _on_hl_sequence_item_double_clicked(self, item):
        """Alla doppia pressione su un'immagine nella sequenza, mostra anteprima."""
        data = item.data(Qt.UserRole) if item else None
        if not isinstance(data, dict) or data.get("type") != "image":
            return
        path = data.get("path", "")
        if not path or not Path(path).exists():
            QMessageBox.warning(self, "Anteprima", "File immagine non trovato.")
            return
        pix = QPixmap(path)
        if pix.isNull():
            QMessageBox.warning(self, "Anteprima", "Impossibile caricare l'immagine.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(Path(path).name)
        layout = QVBoxLayout(dlg)
        label = QLabel()
        label.setAlignment(Qt.AlignCenter)
        label.setMinimumSize(400, 300)
        scaled = pix.scaled(960, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(scaled)
        layout.addWidget(label)
        close_btn = QPushButton("Chiudi")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        dlg.exec_()

    def _remove_from_sequence(self):
        if not hasattr(self, "list_hl_sequence"):
            return
        row = self.list_hl_sequence.currentRow()
        if row < 0:
            return
        self.list_hl_sequence.takeItem(row)

    def _selected_highlight_clip_ids(self):
        """Ritorna lista ID clip selezionate (checkbox)."""
        if self.chk_hl_all.isChecked():
            return [c.get("id") for c in self.backend.clips if c.get("id")]
        selected = []
        for i in range(self.list_hl_clips.count()):
            item = self.list_hl_clips.item(i)
            if item and item.checkState() == Qt.Checked:
                cid = item.data(Qt.UserRole)
                if cid:
                    selected.append(cid)
        return selected

    def _hl_sequence_to_backend_format(self):
        """Costruisce la sequenza ordinata per il backend."""
        seq = []
        for i in range(self.list_hl_sequence.count()):
            item = self.list_hl_sequence.item(i)
            if item:
                data = item.data(Qt.UserRole)
                if isinstance(data, dict):
                    seq.append(data)
        return seq

    def _generate_highlights_from_studio(self):
        sequence = self._hl_sequence_to_backend_format()
        if not sequence:
            QMessageBox.warning(self, "Genera Highlights", "La sequenza è vuota. Aggiungi clip o immagini.")
            return
        default_name = f"highlights_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salva Highlights",
            str(Path.home() / "Videos" / default_name),
            "Video MP4 (*.mp4);;Tutti i file (*.*)"
        )
        if not save_path:
            return
        if not save_path.lower().endswith(".mp4"):
            save_path += ".mp4"

        self._hl_progress_dlg = HighlightProgressDialog(self)
        self._hl_progress_dlg.set_progress(0, "Avvio...")
        self._hl_progress_dlg.setModal(True)
        self._hl_progress_dlg.show()
        self._hl_progress_dlg.raise_()

        self._hl_worker = HighlightGenerateWorker(self.backend, sequence, save_path)
        self._hl_worker.progress.connect(self._on_hl_progress)
        self._hl_worker.finished_signal.connect(self._on_hl_finished)
        self._hl_worker.start()

    def _on_hl_progress(self, percent: int, status: str):
        if hasattr(self, "_hl_progress_dlg") and self._hl_progress_dlg:
            self._hl_progress_dlg.set_progress(percent, status)

    def _on_hl_finished(self, ok: bool, result: str):
        if hasattr(self, "_hl_progress_dlg") and self._hl_progress_dlg:
            self._hl_progress_dlg.close()
            self._hl_progress_dlg = None
        if hasattr(self, "_hl_worker") and self._hl_worker:
            self._hl_worker.deleteLater()
            self._hl_worker = None
        if not ok:
            QMessageBox.warning(self, "Genera Highlights", result)
            return
        QMessageBox.information(self, "Genera Highlights", f"Highlights creato:\n{result}")

    def show_highlights_studio(self):
        self._highlights_mode = True
        self._refresh_match_metadata_fields()
        self.web_view_left.setVisible(False)
        self._center_widget.setVisible(True)
        self._center_stack.setCurrentWidget(self._highlights_studio_panel)
        if hasattr(self, "list_hl_sequence"):
            self.list_hl_sequence.clear()
        self._refresh_highlights_clip_list()
        for cid in self._selected_highlight_clip_ids():
            self._hl_insert_item({"type": "clip", "clip_id": cid}, self.list_hl_sequence.count())
        self._update_open_video_cta_visibility()

    def hide_highlights_studio(self):
        self._highlights_mode = False
        self._center_stack.setCurrentWidget(self._center_normal_widget)
        self.web_view_left.setVisible(True)
        self._update_open_video_cta_visibility()

    def show_field_calibration(self):
        """Apre il dialog di calibrazione campo (per analisi automatica)."""
        if not getattr(self, "video_player", None):
            QMessageBox.warning(self, "Calibrazione", "Apri prima un video.")
            return
        qimg = self.video_player.getCurrentFrameAsQImage()
        if qimg is None or qimg.isNull():
            QMessageBox.warning(self, "Calibrazione", "Impossibile acquisire il frame corrente.")
            return
        project_dir = None
        if hasattr(self, "project_id") and self.project_id and hasattr(self, "project_repository"):
            base = getattr(self.project_repository, "base_path", None)
            if base:
                project_dir = str(base / "analysis" / str(self.project_id))
        dlg = FieldCalibrationDialog(qimg, project_dir=project_dir, parent=self.window())
        from analysis.homography import clear_calibrator_cache
        dlg.calibrationSaved.connect(clear_calibrator_cache)
        dlg.exec_()

    def show_video_preprocessing(self):
        """Apre il dialog di preprocessing video (per analisi automatica)."""
        video_path = str(getattr(self.backend.project, "video_path", "") or "").strip()
        if not video_path or not os.path.isfile(video_path):
            QMessageBox.warning(self, "Preprocessing", "Apri prima un video valido.")
            return
        project_dir = None
        if hasattr(self, "project_id") and self.project_id and hasattr(self, "project_repository"):
            base = getattr(self.project_repository, "base_path", None)
            if base:
                project_dir = str(base / "analysis" / str(self.project_id))
        if not project_dir:
            QMessageBox.warning(self, "Preprocessing", "Progetto non valido.")
            return
        dlg = VideoPreprocessingDialog(video_path, project_dir, parent=self.window())
        dlg.start()
        dlg.exec_()

    def _launch_analysis_dialog(self, mode: str, title: str):
        """Helper: validazione, eventuale prompt ripresa, avvio dialog analisi."""
        video_path = str(getattr(self.backend.project, "video_path", "") or "").strip()
        if not video_path or not os.path.isfile(video_path):
            QMessageBox.warning(self, title, "Apri prima un video valido.")
            return
        project_dir = None
        if hasattr(self, "project_id") and self.project_id and hasattr(self, "project_repository"):
            base = getattr(self.project_repository, "base_path", None)
            if base:
                project_dir = str(base / "analysis" / str(self.project_id))
        if not project_dir:
            QMessageBox.warning(self, title, "Progetto non valido.")
            return
        resume = False
        if has_checkpoint(project_dir, mode):
            mb = QMessageBox(self)
            mb.setWindowTitle("Analisi interrotta")
            mb.setIcon(QMessageBox.Question)
            mb.setText("Analisi interrotta. Riprendere dall'ultimo punto salvato?")
            btn_riprendi = mb.addButton("Riprendi", QMessageBox.AcceptRole)
            btn_ricomincia = mb.addButton("Ricomincia da capo", QMessageBox.ResetRole)
            btn_annulla = mb.addButton("Annulla", QMessageBox.RejectRole)
            mb.setDefaultButton(btn_riprendi)
            mb.exec_()
            if mb.clickedButton() == btn_annulla:
                return
            if mb.clickedButton() == btn_riprendi:
                resume = True
        run_preprocess = (mode == "full" and getattr(self, "_run_preprocess_choice", False))
        input_video = get_video_for_player_detection(project_dir, video_path)
        if getattr(self, "video_player", None) and self.video_player.duration() > 0:
            self.video_player.pause()
        self._analysis_in_progress = True
        self._analysis_dialog = None
        offer_cloud = mode == "full"
        dlg = AnalysisProcessDialog(
            input_video, project_dir, mode, parent=self.window(),
            resume=resume, run_preprocess=run_preprocess,
            offer_cloud_fallback=offer_cloud,
        )
        self._analysis_dialog = dlg
        dlg.finished_ok.connect(self._load_tracking_overlay)
        dlg.finished.connect(self._on_analysis_dialog_closed)
        if offer_cloud:
            dlg.failed_with_error.connect(self._on_local_analysis_failed_offer_cloud)
        dlg.start()
        dlg.show()

    def show_player_detection(self):
        """Apre il dialog di analisi giocatori (processo separato)."""
        self._launch_analysis_dialog("player", "Player detection")

    def show_player_tracking(self):
        """Apre il dialog di analisi giocatori (processo separato, detection+tracking)."""
        self._launch_analysis_dialog("player", "Player tracking")

    def show_ball_detection(self):
        """Apre il dialog di analisi palla (processo separato)."""
        self._launch_analysis_dialog("ball", "Ball detection")

    def _get_analysis_mode(self):
        """Preferenza salvata: 'local' | 'cloud'. Default cloud."""
        s = QSettings(SETTINGS_ORG, SETTINGS_APP)
        return str(s.value(KEY_ANALYSIS_MODE, DEFAULT_ANALYSIS_MODE, type=str))

    def _set_analysis_mode(self, mode: str):
        """Salva preferenza analisi (local | cloud)."""
        if mode not in ("local", "cloud"):
            return
        s = QSettings(SETTINGS_ORG, SETTINGS_APP)
        s.setValue(KEY_ANALYSIS_MODE, mode)

    def _get_hardware_warning_dismissed(self):
        """True se l'utente ha scelto 'Non mostrare di nuovo' per l'avviso hardware."""
        s = QSettings(SETTINGS_ORG, SETTINGS_APP)
        return s.value(KEY_HARDWARE_WARNING_DISMISSED, False, type=bool)

    def _set_hardware_warning_dismissed(self, dismissed: bool):
        s = QSettings(SETTINGS_ORG, SETTINGS_APP)
        s.setValue(KEY_HARDWARE_WARNING_DISMISSED, dismissed)

    def show_full_analysis(self):
        """Apre dialog opzioni e avvia analisi automatica completa (preprocess + player + ball + clustering squadre). Un solo pulsante: Locale → pipeline locale, Cloud → upload + API (stub Fase 4)."""
        video_path = str(getattr(self.backend.project, "video_path", "") or "").strip()
        if not video_path or not os.path.isfile(video_path):
            QMessageBox.warning(self, "Analisi automatica", "Apri prima un video valido.")
            return
        project_dir = None
        if hasattr(self, "project_id") and self.project_id and hasattr(self, "project_repository"):
            base = getattr(self.project_repository, "base_path", None)
            if base:
                project_dir = str(base / "analysis" / str(self.project_id))
        if not project_dir:
            QMessageBox.warning(self, "Analisi automatica", "Progetto non valido.")
            return
        from analysis.video_preprocessing import get_preprocessed_path
        preprocessed_exists = get_preprocessed_path(project_dir).exists()
        current_mode = self._get_analysis_mode()

        dlg = QDialog(self.window())
        dlg.setWindowTitle("Analisi automatica")
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(
            "Esegue in sequenza: Preprocesso video (opzionale), Player detection, Player tracking,\n"
            "Ball detection, Ball tracking, Clustering globale squadre."
        ))
        tip = QLabel("Suggerimento: per risultati migliori calibra il campo (Analisi step-by-step) e usa video 720p+.")
        tip.setStyleSheet("color: #888; font-size: 11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        grp_mode = QGroupBox("Modalità analisi")
        grp_layout = QVBoxLayout(grp_mode)
        rb_local = QRadioButton("Locale (analisi sul tuo PC)")
        rb_cloud = QRadioButton("Cloud (analisi sui nostri server)")
        if current_mode == "local":
            rb_local.setChecked(True)
        else:
            rb_cloud.setChecked(True)
        grp_layout.addWidget(rb_local)
        grp_layout.addWidget(rb_cloud)
        cloud_msg = QLabel("L'analisi verrà eseguita sui nostri server. Per analisi offline scegli \"Locale\".")
        cloud_msg.setStyleSheet("color: #888; font-size: 11px;")
        cloud_msg.setWordWrap(True)
        grp_layout.addWidget(cloud_msg)
        layout.addWidget(grp_mode)

        chk = QCheckBox("Preprocessa video (720p) se non già presente")
        chk.setChecked(not preprocessed_exists)
        chk.setToolTip("Consigliato se il video è in risoluzione maggiore di 720p. (Solo per analisi locale.)")
        layout.addWidget(chk)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        layout.addWidget(bb)
        if dlg.exec_() != QDialog.Accepted:
            return

        use_local = rb_local.isChecked()
        self._run_preprocess_choice = chk.isChecked()

        if use_local:
            self._set_analysis_mode("local")
            hw = self._hardware_check_result
            if not hw["hardware_ok"] and not self._get_hardware_warning_dismissed():
                msg = QMessageBox(self.window())
                msg.setWindowTitle("Risorse limitate")
                msg.setText(
                    "Il tuo PC potrebbe non essere adatto per l'analisi locale (nessuna GPU / risorse limitate). "
                    "L'analisi potrebbe essere molto lenta. Consigliamo l'analisi in cloud."
                )
                btn_local_anyway = msg.addButton("Usa comunque locale", QMessageBox.AcceptRole)
                btn_switch_cloud = msg.addButton("Passa a Cloud", QMessageBox.RejectRole)
                chk_dismiss = QCheckBox("Non mostrare di nuovo")
                msg.setCheckBox(chk_dismiss)
                msg.exec_()
                if msg.clickedButton() == btn_switch_cloud:
                    self._set_analysis_mode("cloud")
                    if chk_dismiss.isChecked():
                        self._set_hardware_warning_dismissed(True)
                    self._start_cloud_analysis()
                    return
                if chk_dismiss.isChecked():
                    self._set_hardware_warning_dismissed(True)
            self._launch_analysis_dialog("full", "Analisi automatica")
        else:
            self._set_analysis_mode("cloud")
            self._start_cloud_analysis()

    def _start_cloud_analysis(self):
        """Avvio analisi in cloud: upload R2 → RunPod Serverless → download risultati."""
        video_path = str(getattr(self.backend.project, "video_path", "") or "").strip()
        if not video_path or not os.path.isfile(video_path):
            QMessageBox.warning(self.window(), "Analisi in cloud", "Apri prima un video valido.")
            return
        options = {
            "conf_thresh": 0.3,
            "target_fps": 5.0,
        }
        dlg = CloudAnalysisDialog(video_path, options, parent=self.window())
        dlg.finished_ok.connect(self._on_cloud_result_ready)
        dlg.failed.connect(self._on_cloud_job_failed)
        dlg.error.connect(self._on_cloud_error)
        dlg.finished.connect(self._on_cloud_dialog_finished)
        self._analysis_in_progress = True
        dlg.start()
        dlg.exec_()
        self._analysis_in_progress = False

    def _on_cloud_result_ready(self, payload: dict):
        """Risultato analisi cloud pronto: carica in UI unificata."""
        self.load_analysis_result(result_payload=payload)
        QMessageBox.information(
            self.window(),
            "Analisi in cloud",
            "Analisi completata. I risultati sono stati caricati.",
        )

    def _on_cloud_job_failed(self, job_id: str, message: str):
        QMessageBox.warning(
            self.window(),
            "Analisi in cloud",
            f"Analisi fallita.\n\n{message}",
        )

    def _on_cloud_error(self, message: str):
        QMessageBox.warning(
            self.window(),
            "Analisi in cloud",
            f"Impossibile avviare l'analisi in cloud.\n\n{message}\n\n"
            "Verifica che il server sia raggiungibile (es. FOOTBALL_ANALYZER_API_URL) e riprova.",
        )

    def _on_cloud_dialog_finished(self):
        self._analysis_in_progress = False

    def _on_local_analysis_failed_offer_cloud(self, err_msg: str):
        """Dopo fallimento analisi locale (full): mostra errore e propone passaggio a Cloud."""
        msg = QMessageBox(self.window())
        msg.setWindowTitle("Analisi locale non riuscita")
        msg.setIcon(QMessageBox.Warning)
        msg.setText(
            "L'analisi locale non è riuscita (es. GPU o modelli non disponibili).\n\n"
            "Dettaglio: " + (err_msg[:400] + "…" if len(err_msg) > 400 else err_msg)
        )
        msg.setInformativeText("Vuoi usare l'analisi in cloud?")
        btn_cloud = msg.addButton("Sì, passa a Cloud", QMessageBox.YesRole)
        msg.addButton("No", QMessageBox.NoRole)
        msg.setDefaultButton(btn_cloud)
        msg.exec_()
        if msg.clickedButton() == btn_cloud:
            self._set_analysis_mode("cloud")
            self._start_cloud_analysis()

    def show_recluster_teams(self):
        """Esegue solo il clustering globale squadre su player_tracks già presenti."""
        project_dir = None
        if hasattr(self, "project_id") and self.project_id and hasattr(self, "project_repository"):
            base = getattr(self.project_repository, "base_path", None)
            if base:
                project_dir = str(base / "analysis" / str(self.project_id))
        if not project_dir:
            QMessageBox.warning(self, "Ricalcola squadre", "Progetto non valido.")
            return
        from analysis.player_tracking import get_tracks_path
        if not get_tracks_path(project_dir).exists():
            QMessageBox.warning(
                self, "Ricalcola squadre",
                "Nessun file player_tracks.json trovato.\nEsegui prima Player detection e Player tracking.",
            )
            return
        from PyQt5.QtWidgets import QProgressDialog
        progress = QProgressDialog("Ricalcolo squadre (clustering globale)...", None, 0, 0, self.window())
        progress.setWindowTitle("Ricalcola squadre")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()
        try:
            from analysis.global_team_clustering import run_global_team_clustering
            ok = run_global_team_clustering(project_dir)
        finally:
            progress.close()
        if ok:
            self._load_tracking_overlay()
            QMessageBox.information(self, "Ricalcola squadre", "Clustering completato. Overlay aggiornato.")
        else:
            QMessageBox.warning(self, "Ricalcola squadre", "Impossibile aggiornare i dati.")

    def _on_analysis_dialog_closed(self):
        self._analysis_in_progress = False
        self._analysis_dialog = None

    def get_analysis_process(self):
        """Ritorna il processo analysis in corso, o None."""
        dlg = getattr(self, "_analysis_dialog", None)
        if dlg and getattr(dlg, "_process", None) and dlg._process.poll() is None:
            return dlg._process
        return None

    def terminate_analysis_and_close_dialog(self):
        """Termina il processo di analisi e chiude il dialog."""
        dlg = getattr(self, "_analysis_dialog", None)
        if dlg:
            if getattr(dlg, "_process", None) and dlg._process.poll() is None:
                dlg._process.terminate()
            dlg.close()
        self._analysis_in_progress = False
        self._analysis_dialog = None

    def save_background_analysis_flag(self):
        """Salva flag per messaggio 'Analisi completata in background' al riavvio."""
        project_dir = None
        if hasattr(self, "project_id") and self.project_id:
            base = getattr(self.project_repository, "base_path", None)
            if base:
                project_dir = str(base / "analysis" / str(self.project_id))
        if not project_dir:
            return
        try:
            flag_path = self.project_repository.base_path / "pending_background_analysis.json"
            with open(flag_path, "w", encoding="utf-8") as f:
                json.dump({"project_analysis_dir": project_dir}, f)
        except Exception:
            pass

    def _block_play_during_analysis(self, playing: bool):
        """Durante analisi, impedisce play per evitare rallentamenti."""
        if playing and getattr(self, "_analysis_in_progress", False):
            if getattr(self, "video_player", None):
                self.video_player.pause()

    def _on_any_webview_loaded(self, area: str, ok: bool):
        """Quando una webview è caricata, spinge i dati iniziali."""
        if not ok:
            return
        if area in self._webviews_ready:
            self._webviews_ready[area] = True
        self._loaded_webviews += 1
        self._push_initial_data_to_webviews()
        if all(self._webviews_ready.values()):
            QTimer.singleShot(180, self._push_initial_data_to_webviews)
            QTimer.singleShot(220, self._ensure_video_frame_rendered)

    def _on_frontend_ready(self, area: str):
        """Riceve ACK dal frontend (legacy: left/center/right; d_migration: unified)."""
        if area == "unified":
            for k in self._frontend_ready:
                self._frontend_ready[k] = True
        elif area in self._frontend_ready:
            self._frontend_ready[area] = True
        else:
            return
        if all(self._frontend_ready.values()):
            _log_workspace_bootstrap("web_ready", f"mode={getattr(self, '_ui_mode', 'legacy')}")
            self._reveal_workspace_columns()

    def _reveal_workspace_columns(self):
        """Mostra colonne per apertura uniforme (3 WebView + video in layout)."""
        if self._initial_ui_revealed:
            return
        _log_workspace_bootstrap("ui_reveal", f"mode={getattr(self, '_ui_mode', 'legacy')}")
        self.web_view_left.setVisible(not self._highlights_mode)
        self._center_widget.setVisible(True)
        self.web_view_right.setVisible(True)
        self._initial_ui_revealed = True
        self._ui_boot_locked = False
        self.setUpdatesEnabled(True)
        self._fade_out_startup_curtain()
        self._position_open_video_button()
        self._update_open_video_cta_visibility()
        self._ensure_video_frame_rendered()

    def _setup_startup_curtain(self):
        """Copertura temporanea per uniformare la comparsa iniziale."""
        self._startup_curtain = QFrame(self)
        self._startup_curtain.setFrameShape(QFrame.NoFrame)
        self._startup_curtain.setStyleSheet("background: #060d1a; border: none;")
        self._startup_curtain_opacity = QGraphicsOpacityEffect(self._startup_curtain)
        self._startup_curtain.setGraphicsEffect(self._startup_curtain_opacity)
        self._startup_curtain_opacity.setOpacity(1.0)
        self._startup_curtain_anim = QPropertyAnimation(self._startup_curtain_opacity, b"opacity", self)
        self._startup_curtain_anim.setDuration(80)
        self._startup_curtain_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._position_startup_curtain()
        self._startup_curtain.raise_()
        self._startup_curtain.show()

    def _position_startup_curtain(self):
        if not hasattr(self, "_startup_curtain") or self._startup_curtain is None:
            return
        top_h = self._topbar.height() if hasattr(self, "_topbar") and self._topbar else 0
        self._startup_curtain.setGeometry(0, top_h, self.width(), max(0, self.height() - top_h))

    def _fade_out_startup_curtain(self):
        if not hasattr(self, "_startup_curtain") or self._startup_curtain is None:
            return
        if not self._startup_curtain.isVisible():
            return
        if not hasattr(self, "_startup_curtain_anim") or self._startup_curtain_anim is None:
            self._startup_curtain.hide()
            return
        self._startup_curtain_anim.stop()
        self._startup_curtain_anim.setStartValue(1.0)
        self._startup_curtain_anim.setEndValue(0.0)
        self._startup_curtain_anim.finished.connect(self._startup_curtain.hide)
        self._startup_curtain_anim.start()

    def _force_reveal_if_stuck(self):
        """Sicurezza: sblocca UI solo se il bootstrap non è mai andato a buon fine."""
        if self._initial_ui_revealed:
            return
        self._reveal_workspace_columns()

    def _push_initial_data_to_webviews(self):
        if not getattr(self, "backend", None):
            return
        clips_json = self.backend.getClips()
        event_types_json = self.backend.getEventTypes()
        events_json = self.backend.getEvents()
        time_json = self.backend.getCurrentTime()
        script = (
            f"if (typeof onClipsUpdated === 'function') onClipsUpdated({json.dumps(clips_json)});"
            f"if (typeof onEventTypesUpdated === 'function') onEventTypesUpdated({json.dumps(event_types_json)});"
            f"if (typeof onEventsUpdated === 'function') onEventsUpdated({json.dumps(events_json)});"
            f"if (typeof onTimeUpdated === 'function') onTimeUpdated({json.dumps(time_json)});"
        )
        if getattr(self, "web_view_unified", None) and self.web_view_unified.page():
            self.web_view_unified.page().runJavaScript(script)
        else:
            for view in (getattr(self, "web_view_left", None), getattr(self, "web_view_center_controls", None), getattr(self, "web_view_right", None)):
                if view and view.page():
                    view.page().runJavaScript(script)

    def _get_annotations_at(self, ts_ms, tolerance_ms=50):
        """Annotazioni eventi al timestamp. Usa tolleranza ±tolerance_ms (default 50ms)."""
        result = []
        for evt in self.backend.event_manager.get_events():
            if not getattr(evt, 'annotations', None):
                continue
            if abs(evt.timestamp_ms - ts_ms) <= tolerance_ms:
                for i, ann in enumerate(evt.annotations):
                    result.append({"data": ann, "event_id": evt.id, "ann_index": i})
        return result

    def force_render_drawings_at(self, ts_ms: int):
        """Forza il rendering dei disegni al timestamp (non dipende da positionChanged)."""
        anns = self._get_annotations_at(ts_ms, tolerance_ms=50)
        vw, vh = self.drawing_overlay.getVideoSize()
        if vw <= 0 or vh <= 0:
            vw, vh = max(1, self.video_player.width()), max(1, self.video_player.height())
        self.drawing_overlay.loadDrawingsFromProject(anns, view_w_override=vw, view_h_override=vh)
        self.drawing_overlay.setDrawingsVisibility(True)
        self.drawing_overlay.viewport().update()

    def _refresh_drawings_visibility(self):
        """Aggiorna visibilità disegni. Usa _seek_target_ms durante seek per evitare race."""
        ts = getattr(self, '_seek_target_ms', None)
        if ts is None:
            ts = self.video_player.position()
        vw, vh = self.drawing_overlay.getVideoSize()
        if vw <= 0 or vh <= 0:
            vw, vh = max(1, self.video_player.width()), max(1, self.video_player.height())
        if self.video_player.state() == 1:
            if self.backend.active_clip_id:
                anns = self._get_annotations_at(ts, tolerance_ms=50)
                self.drawing_overlay.loadDrawingsFromProject(anns, view_w_override=vw, view_h_override=vh)
                self.drawing_overlay.setDrawingsVisibility(True)
            else:
                self.drawing_overlay.setDrawingsVisibility(False)
        else:
            self.drawing_overlay.loadDrawingsFromProject(
                self._get_annotations_at(ts, tolerance_ms=50),
                view_w_override=vw, view_h_override=vh
            )
            self.drawing_overlay.setDrawingsVisibility(True)
        self.drawing_overlay.viewport().update()

    def _on_drawing_confirmed(self, item):
        """Salva disegno come annotazione evento."""
        if not getattr(self.backend.project, 'video_path', None):
            return
        data = self.drawing_overlay.item_to_serializable_data(item)
        if not data:
            return
        ts = self.video_player.position()
        evt = self.backend.event_manager.get_event_at_timestamp(ts)
        new_evt = None
        if evt:
            self.backend.event_manager.add_annotation_to_event(evt.id, data)
        else:
            new_evt = self.backend.event_manager.add_event(
                "annotazione", ts,
                label=f"Annotazione {ts // 1000}s",
                annotations=[data]
            )
            if new_evt and self.video_player:
                self.video_player.setPlaybackRate(1.0)
        self.drawing_overlay.removeItemForSave(item)
        self._refresh_drawings_visibility()
        self.backend.eventsUpdated.emit(self.backend.getEvents())
        if new_evt:
            self.backend.eventCreated.emit(new_evt.id)

    def _on_drawing_started(self):
        """Pausa video quando si inizia a disegnare."""
        self.video_player.pause()

    def _on_annotation_deleted(self, event_id, ann_index):
        self.backend.event_manager.remove_annotation_from_event(event_id, ann_index)
        self._refresh_drawings_visibility()
        self.backend.eventsUpdated.emit(self.backend.getEvents())

    def _on_annotation_modified(self, event_id, ann_index, new_data):
        self.backend.event_manager.update_annotation_in_event(event_id, ann_index, new_data)

    def _on_zoom_requested(self, delta: int, mouse_x: int, mouse_y: int):
        """Rotella con strumento Zoom attivo: zoom verso il puntatore (max 5x)."""
        factor = 1.0 + (delta / 1200.0)
        self._zoom_level *= factor
        self._zoom_level = max(1.0, min(self._zoom_max, self._zoom_level))
        self.video_player.setZoomAt(self._zoom_level, mouse_x, mouse_y)
        if self.video_player.duration() > 0:
            self.video_player.setPosition(self.video_player.position())

    def _on_zoom_level_changed(self, level: float):
        """Sincronizza _zoom_level quando lo zoom cambia (es. da slider)."""
        self._zoom_level = level

    def _on_empty_area_clicked(self, x, y):
        """Click su area vuota con tool=NONE → equivale a video click (per eventi)."""
        timestamp = self.video_player.position() if self.video_player else 0
        if hasattr(self.backend, 'onVideoClick'):
            self.backend.onVideoClick(float(x), float(y), timestamp)

    def _on_video_clicked(self, x, y, timestamp):
        """Handler per click singolo sul video"""
        logging.debug(f"[MAIN] Video clicked: ({x}, {y}) at {timestamp}ms")
        # Notifica backend
        if hasattr(self.backend, 'onVideoClick'):
            self.backend.onVideoClick(float(x), float(y), timestamp)
    
    def _on_mouse_pressed(self, x, y, timestamp):
        """Handler per mouse press sul video"""
        logging.debug(f"[MAIN] Mouse pressed: ({x}, {y}) at {timestamp}ms")
    
    def _on_mouse_moved(self, x, y, timestamp):
        """Handler per mouse move sul video (durante drag)"""
        # print(f"[MAIN] Mouse moved: ({x}, {y})") # Commentato per evitare spam
        pass
    
    def _on_mouse_released(self, x, y, timestamp):
        """Handler per mouse release sul video"""
        logging.debug(f"[MAIN] Mouse released: ({x}, {y}) at {timestamp}ms")

    def _start_window_drag(self, global_x: int, global_y: int):
        win = self.window()
        self._dragging_window = True
        self._drag_offset = win.frameGeometry().topLeft() - QPoint(global_x, global_y)

    def _move_window_drag(self, global_x: int, global_y: int):
        if not self._dragging_window or self._drag_offset is None:
            return
        win = self.window()
        win.move(QPoint(global_x, global_y) + self._drag_offset)

    def _end_window_drag(self):
        self._dragging_window = False
        self._drag_offset = None

    def persist_project(self):
        """Salva stato workspace sul progetto corrente."""
        ok = self.backend.save_project_to_path(
            self.project_repository.get_project_file_path(self.project_id)
        )
        if ok:
            self.project_repository.touch(self.project_id)
        return bool(ok)

    def _go_back_to_dashboard(self):
        self.persist_project()
        self.backToDashboardRequested.emit()
    
    def closeEvent(self, event):
        """Cleanup on close"""
        self.persist_project()
        if self.video_player:
            self.video_player.stop()  # stop() chiama release() su capture
        event.accept()


class DashboardPage(QWidget):
    """Dashboard iniziale con progetti recenti."""

    openProjectRequested = pyqtSignal(str)
    _worn_tile = None

    def __init__(self, project_repository: ProjectRepository):
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)
        self.project_repository = project_repository
        self.setObjectName("dashboardPage")
        self._armed_delete_project_btn = None
        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)
        self._build_ui()
        self.refresh_projects()

    def paintEvent(self, event):
        """Sfondo dashboard multilayer per profondita' 'blu notte'."""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect()
        if r.width() <= 0 or r.height() <= 0:
            super().paintEvent(event)
            return

        w = float(r.width())
        h = float(r.height())
        diag = (w * w + h * h) ** 0.5

        # Base: stessa famiglia cromatica del workspace web
        base = QLinearGradient(0, 0, 0, h)
        base.setColorAt(0.00, QColor(6, 15, 31))
        base.setColorAt(0.45, QColor(5, 11, 24))
        base.setColorAt(1.00, QColor(3, 7, 16))
        p.fillRect(r, base)

        # Radiale alto (night-blue diffuso)
        top_glow = QRadialGradient(w * 0.56, h * 0.08, diag * 0.60)
        top_glow.setColorAt(0.00, QColor(46, 74, 126, 54))
        top_glow.setColorAt(0.35, QColor(18, 34, 62, 30))
        top_glow.setColorAt(0.68, QColor(7, 14, 27, 10))
        top_glow.setColorAt(1.00, QColor(0, 0, 0, 0))
        p.fillRect(r, top_glow)

        # Radiale basso-sinistra (profondita' morbida)
        low_glow = QRadialGradient(w * 0.16, h * 0.84, diag * 0.46)
        low_glow.setColorAt(0.00, QColor(16, 49, 95, 36))
        low_glow.setColorAt(0.42, QColor(8, 20, 41, 20))
        low_glow.setColorAt(0.78, QColor(4, 10, 20, 8))
        low_glow.setColorAt(1.00, QColor(0, 0, 0, 0))
        p.fillRect(r, low_glow)

        # Patina "usurata" non circolare concentrata in basso
        wear_haze = QLinearGradient(0, h * 0.72, w, h * 0.95)
        wear_haze.setColorAt(0.00, QColor(0, 0, 0, 0))
        wear_haze.setColorAt(0.24, QColor(134, 148, 170, 8))
        wear_haze.setColorAt(0.55, QColor(178, 156, 126, 9))
        wear_haze.setColorAt(0.80, QColor(126, 146, 178, 7))
        wear_haze.setColorAt(1.00, QColor(0, 0, 0, 0))
        p.fillRect(r, wear_haze)

        # Texture filmica "immagine consumata"
        tile = self._get_worn_tile()
        if tile is not None:
            p.setOpacity(0.020)
            p.drawTiledPixmap(r, tile)
            p.setOpacity(0.009)
            p.drawTiledPixmap(r, tile, QPoint(67, 41))
            p.setOpacity(1.0)

        # Vignetta globale simile al layer web
        vignette = QRadialGradient(w * 0.5, h * 0.5, diag * 0.74)
        vignette.setColorAt(0.48, QColor(0, 0, 0, 0))
        vignette.setColorAt(0.72, QColor(0, 0, 0, 82))
        vignette.setColorAt(1.00, QColor(0, 0, 0, 148))
        p.fillRect(r, vignette)

        super().paintEvent(event)

    @classmethod
    def _get_worn_tile(cls):
        if cls._worn_tile is not None:
            return cls._worn_tile

        size = 384
        tile = QPixmap(size, size)
        tile.fill(Qt.transparent)

        painter = QPainter(tile)
        # Grana fine pseudo-random deterministica (evita banding/righe)
        for y in range(size):
            for x in range(size):
                v = ((x * 73856093) ^ (y * 19349663) ^ ((x + y) * 83492791)) & 255
                if v < 2:
                    painter.setPen(QColor(255, 255, 255, 12))
                    painter.drawPoint(x, y)
                elif v in (5, 6):
                    painter.setPen(QColor(150, 174, 210, 9))
                    painter.drawPoint(x, y)

        # Micro "smoke dust" soffuso (pattern organico non geometrico)
        for i in range(220):
            cx = ((i * 53) + (i * i * 17)) % size
            cy = ((i * 71) + (i * i * 9)) % size
            alpha = 3 + (i % 3)
            tone = QColor(185, 172, 152, alpha) if i % 2 == 0 else QColor(136, 156, 188, max(2, alpha - 1))
            painter.setPen(tone)
            painter.drawPoint(cx, cy)
        painter.end()

        cls._worn_tile = tile
        return cls._worn_tile

    def _build_ui(self):
        self.setStyleSheet("""
        QWidget#dashboardPage {
            background: transparent;
            color: #e8f0fa;
        }
        QWidget#dashboardTopBar {
            background: transparent;
            border: none;
        }
        QLabel#dashboardTopBrand {
            font-size: 15px;
            font-weight: 700;
            color: #eaf3ff;
        }
        QLabel#dashboardTopDot {
            color: #2ed8a3;
            font-size: 12px;
            font-weight: 700;
        }
        QWidget#dashboardSidebar {
            background: transparent;
            border: none;
        }
        QLabel#dashboardBrand {
            font-size: 16px;
            font-weight: 700;
            color: #eaf3ff;
        }
        QPushButton.dashboardNavBtn {
            text-align: left;
            padding: 10px 14px;
            border-radius: 8px;
            border: 1px solid transparent;
            background: transparent;
            color: #a9b9cc;
            font-size: 13px;
        }
        QPushButton.dashboardNavBtn[active="true"] {
            color: #e8fff8;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #0f5d4d,
                stop:0.52 #17806a,
                stop:1 #29b48d
            );
        }
        QWidget#dashboardContent {
            background: transparent;
        }
        QLabel#dashboardTitle {
            font-size: 38px;
            font-weight: 700;
            color: #f1f6ff;
        }
        QLabel#dashboardSubtitle {
            font-size: 30px;
            font-weight: 600;
            color: #dfe9f7;
        }
        QWidget#dashboardActionPanel {
            background: transparent;
            border: none;
            border-radius: 0px;
        }
        QPushButton#dashboardNewBtn {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #0f5d4d,
                stop:0.52 #17806a,
                stop:1 #29b48d
            );
            color: #f6fffd;
            border: 0px solid transparent;
            border-radius: 8px;
            padding: 12px 20px;
            font-size: 18px;
            font-weight: 700;
        }
        QPushButton#dashboardNewBtn:hover {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #137261,
                stop:0.52 #1e947c,
                stop:1 #33c89f
            );
        }
        QWidget#projectCard {
            background: rgba(15, 26, 47, 0.82);
            border: 1px solid rgba(116, 156, 220, 0.22);
            border-radius: 10px;
        }
        QLabel.projectName {
            font-size: 14px;
            font-weight: 700;
            color: #e9f1ff;
        }
        QLabel.projectUpdated {
            font-size: 12px;
            color: #9eb0c8;
        }
        QPushButton#cardOpenBtn {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #0f5d4d,
                stop:0.52 #17806a,
                stop:1 #29b48d
            );
            color: #eafff8;
            border: none;
            border-radius: 6px;
            padding: 6px 16px;
            font-weight: 600;
        }
        QPushButton#cardOpenBtn:hover {
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #137261,
                stop:0.52 #1e947c,
                stop:1 #33c89f
            );
        }
        QPushButton#cardDeleteBtn {
            background: rgba(255, 255, 255, 0.08);
            color: #d9e5f4;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 6px;
            padding: 6px 12px;
            font-weight: 600;
        }
        QPushButton#cardDeleteBtn:hover {
            background: rgba(213, 69, 69, 0.24);
            border-color: rgba(234, 96, 96, 0.42);
        }
        QWidget#emptyCard {
            background: rgba(11, 18, 32, 0.28);
            border: 1px dashed rgba(165, 187, 215, 0.30);
            border-radius: 10px;
        }
        QLabel#emptyCardLabel {
            color: #a9b9cc;
            font-size: 14px;
        }
        QScrollArea {
            border: none;
            background: transparent;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 8px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: rgba(255, 255, 255, 0.18);
            border-radius: 4px;
            min-height: 24px;
        }
        """)

        root = self._root_layout
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        topbar = QWidget()
        topbar.setObjectName("dashboardTopBar")
        topbar.setFixedHeight(38)
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(12, 0, 12, 0)
        topbar_layout.setSpacing(8)
        top_dot = QLabel("●")
        top_dot.setObjectName("dashboardTopDot")
        topbar_layout.addWidget(top_dot, 0, Qt.AlignVCenter)
        top_brand = QLabel("Football | Analyzer")
        top_brand.setObjectName("dashboardTopBrand")
        topbar_layout.addWidget(top_brand, 0, Qt.AlignVCenter)
        topbar_layout.addStretch(1)
        root.addWidget(topbar, 0)

        shell = QWidget()
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        # Sidebar sinistra
        sidebar = QWidget()
        sidebar.setObjectName("dashboardSidebar")
        sidebar.setFixedWidth(216)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 16, 16, 16)
        sidebar_layout.setSpacing(10)
        sidebar_layout.addSpacing(6)

        nav_projects = QPushButton("⌂  Progetti")
        nav_projects.setProperty("class", "dashboardNavBtn")
        nav_projects.setProperty("active", True)
        nav_projects.setObjectName("dashboardNavProjects")
        sidebar_layout.addWidget(nav_projects)

        nav_new_project = QPushButton("＋  Nuovo Progetto")
        nav_new_project.setProperty("class", "dashboardNavBtn")
        nav_new_project.setObjectName("dashboardNavNewProject")
        nav_new_project.clicked.connect(self._on_new_project)
        sidebar_layout.addWidget(nav_new_project)

        nav_teams_players = QPushButton("👥  Squadre e Giocatori")
        nav_teams_players.setProperty("class", "dashboardNavBtn")
        nav_teams_players.setObjectName("dashboardNavTeamsPlayers")
        sidebar_layout.addWidget(nav_teams_players)

        nav_settings = QPushButton("⚙  Impostazioni")
        nav_settings.setProperty("class", "dashboardNavBtn")
        nav_settings.setObjectName("dashboardNavSettings")
        sidebar_layout.addWidget(nav_settings)

        nav_license = QPushButton("◔  Licenza")
        nav_license.setProperty("class", "dashboardNavBtn")
        nav_license.setObjectName("dashboardNavLicense")
        sidebar_layout.addWidget(nav_license)
        sidebar_layout.addStretch(1)

        divider = DashboardDivider()
        self._dashboard_divider = divider
        divider.setFixedWidth(8)

        # Contenuto principale (stack per Progetti / Squadre e Giocatori)
        from PyQt5.QtWidgets import QStackedWidget
        content_stacked = QStackedWidget()
        content_stacked.setObjectName("dashboardContent")

        # Pagina Progetti
        projects_page = QWidget()
        content_layout = QVBoxLayout(projects_page)
        content_layout.setContentsMargins(34, 30, 34, 22)
        content_layout.setSpacing(16)
        title = QLabel("Progetti")
        title.setObjectName("dashboardTitle")
        content_layout.addWidget(title)

        action_panel = QWidget()
        action_panel.setObjectName("dashboardActionPanel")
        action_row = QHBoxLayout(action_panel)
        action_row.setContentsMargins(16, 12, 16, 12)
        action_row.setSpacing(8)
        self.btn_new = QPushButton("+  Nuovo Progetto")
        self.btn_new.setObjectName("dashboardNewBtn")
        self.btn_new.clicked.connect(self._on_new_project)
        action_row.addWidget(self.btn_new, 0, Qt.AlignLeft)
        action_row.addStretch(1)
        content_layout.addWidget(action_panel)

        subtitle = QLabel("Progetti Salvati")
        subtitle.setObjectName("dashboardSubtitle")
        content_layout.addWidget(subtitle)

        from PyQt5.QtWidgets import QScrollArea, QGridLayout
        self.projects_scroll = QScrollArea()
        self.projects_scroll.setWidgetResizable(True)
        self.projects_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.projects_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.projects_scroll.setStyleSheet("QScrollArea{background: transparent; border: none;} QScrollArea > QWidget > QWidget { background: transparent; }")

        self.projects_host = QWidget()
        self.projects_host.setAttribute(Qt.WA_StyledBackground, True)
        self.projects_host.setStyleSheet("background: transparent;")
        self.projects_grid = QGridLayout(self.projects_host)
        self.projects_grid.setContentsMargins(0, 2, 0, 0)
        self.projects_grid.setHorizontalSpacing(14)
        self.projects_grid.setVerticalSpacing(14)
        self.projects_grid.setColumnStretch(0, 1)
        self.projects_grid.setColumnStretch(1, 1)
        self.projects_scroll.setWidget(self.projects_host)
        content_layout.addWidget(self.projects_scroll, 1)
        content_stacked.addWidget(projects_page)

        # Pagina Squadre e Giocatori
        teams_page = QWidget()
        teams_layout = QVBoxLayout(teams_page)
        teams_layout.setContentsMargins(34, 30, 34, 22)
        teams_layout.setSpacing(16)
        teams_title = QLabel("Squadre e Giocatori")
        teams_title.setObjectName("dashboardTitle")
        teams_layout.addWidget(teams_title)
        teams_sub = QLabel("Gestisci squadre e giocatori. Potrai collegare i track ID (da Player tracking) ai giocatori per statistiche personalizzate.")
        teams_sub.setObjectName("dashboardSubtitle")
        teams_sub.setWordWrap(True)
        teams_layout.addWidget(teams_sub)
        teams_layout.addStretch(1)
        content_stacked.addWidget(teams_page)

        content = content_stacked

        shell_layout.addWidget(sidebar, 0)
        shell_layout.addWidget(divider, 0)
        shell_layout.addWidget(content, 1)
        root.addWidget(shell, 1)

        self._dashboard_nav_buttons = [nav_projects, nav_teams_players, nav_settings, nav_license]
        self._content_stacked = content_stacked
        self._nav_to_index = {nav_projects: 0, nav_teams_players: 1}
        for btn in self._dashboard_nav_buttons:
            btn.clicked.connect(lambda _=False, b=btn: self._set_active_nav_button(b))
        QTimer.singleShot(0, lambda: self._set_active_nav_button(nav_projects))

    def _set_active_nav_button(self, active_button: QPushButton):
        for btn in getattr(self, "_dashboard_nav_buttons", []):
            btn.setProperty("active", btn is active_button)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()
        idx = getattr(self, "_nav_to_index", {}).get(active_button, 0)
        stack = getattr(self, "_content_stacked", None)
        if stack is not None and 0 <= idx < stack.count():
            stack.setCurrentIndex(idx)
        divider = getattr(self, "_dashboard_divider", None)
        if divider is not None and active_button is not None:
            center_global = active_button.mapToGlobal(active_button.rect().center())
            divider.set_glow_global_y(center_global.y())

    def _open_project_context_menu(self, project_id: str, global_pos):
        menu = QMenu(self)
        rename_action = menu.addAction("Rinomina progetto")
        selected = menu.exec_(global_pos)
        if selected == rename_action:
            self._rename_project(project_id)

    def _rename_project(self, project_id: str):
        meta = self.project_repository.get(project_id)
        current_name = meta.name if meta else "Progetto"
        new_name, ok = QInputDialog.getText(
            self,
            "Rinomina progetto",
            "Nuovo nome progetto:",
            text=current_name
        )
        if not ok:
            return
        if self.project_repository.rename(project_id, new_name):
            self.refresh_projects()

    def refresh_projects(self):
        try:
            grid = self.projects_grid
            host = self.projects_host
        except RuntimeError:
            # La pagina e' gia' stata distrutta (switch dashboard/workspace rapido).
            return
        except AttributeError:
            return

        if grid is None or host is None:
            return

        try:
            while grid.count():
                item = grid.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        except RuntimeError:
            return

        projects = self.project_repository.list_recent()
        for idx, meta in enumerate(projects):
            card = QWidget()
            card.setObjectName("projectCard")
            card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            card.setMinimumHeight(154)
            card.setMaximumHeight(154)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(10)
            card.setContextMenuPolicy(Qt.CustomContextMenu)
            card.customContextMenuRequested.connect(
                lambda pos, pid=meta.id, w=card: self._open_project_context_menu(pid, w.mapToGlobal(pos))
            )

            name = QLabel(meta.name)
            name.setProperty("class", "projectName")
            name.setStyleSheet("font-size: 14px; font-weight: 700; color: #e9f1ff;")
            name.setContextMenuPolicy(Qt.CustomContextMenu)
            name.customContextMenuRequested.connect(
                lambda pos, pid=meta.id, w=name: self._open_project_context_menu(pid, w.mapToGlobal(pos))
            )
            updated = QLabel(f"Ultima modifica {meta.updatedAt.replace('T', ' ').replace('Z', '')}")
            updated.setProperty("class", "projectUpdated")
            updated.setStyleSheet("font-size: 12px; color: #9eb0c8;")
            updated.setContextMenuPolicy(Qt.CustomContextMenu)
            updated.customContextMenuRequested.connect(
                lambda pos, pid=meta.id, w=updated: self._open_project_context_menu(pid, w.mapToGlobal(pos))
            )

            actions = QHBoxLayout()
            actions.setContentsMargins(0, 0, 0, 0)
            actions.setSpacing(8)
            actions.addStretch(1)

            open_btn = QPushButton("Apri")
            open_btn.setObjectName("cardOpenBtn")
            open_btn.setMinimumWidth(56)
            open_btn.setFixedHeight(28)
            open_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 #0f5d4d,
                        stop:0.52 #17806a,
                        stop:1 #29b48d
                    );
                    color: #eafff8;
                    border: none;
                    border-radius: 6px;
                    padding: 0 14px;
                    font-size: 12px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background: qlineargradient(
                        x1:0, y1:0, x2:1, y2:0,
                        stop:0 #137261,
                        stop:0.52 #1e947c,
                        stop:1 #33c89f
                    );
                }
            """)
            open_btn.clicked.connect(lambda _=False, pid=meta.id: self.openProjectRequested.emit(pid))
            del_btn = QPushButton("Elimina")
            del_btn.setObjectName("cardDeleteBtn")
            del_btn.setFixedHeight(28)
            del_btn.clicked.connect(lambda _=False, pid=meta.id, btn=del_btn: self._on_delete_project_clicked(pid, btn))

            actions.addWidget(open_btn, 0)
            actions.addWidget(del_btn, 0)

            card_layout.addWidget(name)
            card_layout.addWidget(updated)
            card_layout.addLayout(actions)

            row = idx // 2
            col = idx % 2
            grid.addWidget(card, row, col, 1, 1, Qt.AlignTop)

        # Spinge le card verso l'alto (evita espansione verticale "gigante").
        grid.setRowStretch((len(projects) + 1) // 2, 1)

        # Se numero dispari, mostra una card placeholder tratteggiata come reference.
        if projects and len(projects) % 2 == 1:
            row = len(projects) // 2
            placeholder = QWidget()
            placeholder.setObjectName("emptyCard")
            placeholder.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            placeholder.setMinimumHeight(154)
            placeholder.setMaximumHeight(154)
            ph_layout = QVBoxLayout(placeholder)
            ph_layout.setContentsMargins(0, 0, 0, 0)
            ph_layout.setSpacing(0)
            ph_label = QLabel("Nessun video caricato")
            ph_label.setObjectName("emptyCardLabel")
            ph_label.setAlignment(Qt.AlignCenter)
            ph_layout.addWidget(ph_label, 1)
            grid.addWidget(placeholder, row, 1, 1, 1, Qt.AlignTop)

        if not projects:
            empty = QWidget()
            empty.setObjectName("emptyCard")
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(0, 0, 0, 0)
            empty_layout.setSpacing(0)
            label = QLabel("Nessun progetto disponibile")
            label.setObjectName("emptyCardLabel")
            label.setAlignment(Qt.AlignCenter)
            empty_layout.addWidget(label, 1)
            grid.addWidget(empty, 0, 0, 1, 2)

    def _on_new_project(self):
        name, ok = QInputDialog.getText(self, "Nuovo Progetto", "Nome progetto:")
        if not ok:
            return
        project = self.project_repository.create(name.strip() or "Nuovo Progetto")
        self.refresh_projects()
        self.openProjectRequested.emit(project.id)

    def _delete_project(self, project_id: str):
        self.project_repository.delete(project_id)
        self.refresh_projects()

    def _on_delete_project_clicked(self, project_id: str, btn: QPushButton):
        """Doppio click di conferma (stesso pattern delle clip card)."""
        if btn is None:
            return

        # Se c'e' un altro bottone armato, lo resetta.
        prev_btn = getattr(self, "_armed_delete_project_btn", None)
        if prev_btn is not None and prev_btn is not btn:
            try:
                prev_btn.setProperty("confirmDelete", False)
                prev_btn.setText("Elimina")
            except RuntimeError:
                pass
            self._armed_delete_project_btn = None

        armed = bool(btn.property("confirmDelete"))
        if not armed:
            btn.setProperty("confirmDelete", True)
            btn.setText("Conferma")
            self._armed_delete_project_btn = btn

            def _auto_reset():
                if self._armed_delete_project_btn is not btn:
                    return
                try:
                    if bool(btn.property("confirmDelete")):
                        btn.setProperty("confirmDelete", False)
                        btn.setText("Elimina")
                except RuntimeError:
                    pass
                self._armed_delete_project_btn = None

            QTimer.singleShot(2500, _auto_reset)
            return

        btn.setProperty("confirmDelete", False)
        btn.setText("Elimina")
        self._armed_delete_project_btn = None
        self._delete_project(project_id)


class CloseAnalysisDialog(QDialog):
    """Dialog per chiusura durante analisi, con spiegazione sotto ogni pulsante."""

    Ferma, Continua, Annulla = 1, 2, 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._result = self.Annulla
        self.setWindowTitle("Analisi in corso")
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        lbl = QLabel(
            "Analisi in corso. Chiudere l'app non fermerà il motore.\n"
            "Vuoi continuare?"
        )
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        def add_option(btn_text, desc, role_val):
            btn = QPushButton(btn_text)
            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #666; font-size: 11px; margin-left: 8px;")
            row = QVBoxLayout()
            row.setSpacing(4)
            row.addWidget(btn)
            row.addWidget(desc_lbl)
            layout.addLayout(row)
            btn.clicked.connect(lambda: self._choose(role_val))
            return btn

        add_option(
            "Ferma",
            "Interrompi l'analisi e chiudi l'app (progressi salvati).",
            self.Ferma,
        )
        add_option(
            "Continua",
            "Chiudi l'app e lascia l'analisi in corso; riceverai notifica al termine.",
            self.Continua,
        )
        add_option(
            "Annulla",
            "Torna indietro e continua a usare l'app.",
            self.Annulla,
        )
        self.setMinimumWidth(380)

    def _choose(self, val):
        self._result = val
        self.accept()

    def result_choice(self):
        return self._result


class AppRouter(QMainWindow):
    """Routing app: DashboardPage <-> WorkspacePage(projectId)."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)
        self.setContentsMargins(0, 0, 0, 0)
        self.setWindowTitle("Football Analyzer")
        self.setStyleSheet("""
QMainWindow {
    background: qradialgradient(
        cx: 0.50, cy: 0.05, radius: 1.20,
        fx: 0.52, fy: 0.06,
        stop: 0 #101d35,
        stop: 0.20 #0b162b,
        stop: 0.46 #081223,
        stop: 0.74 #060d1a,
        stop: 1 #030712
    );
}
""")
        self.project_repository = ProjectRepository(str((Path(__file__).parent / "data").absolute()))
        self.dashboard_page = None
        self.workspace_page = None
        self._opening_workspace = False
        self._show_dashboard()

    def _dispose_workspace_page(self):
        """Teardown esplicito workspace prima del replace central widget.
        Evita leak di risorse video/webengine su aperture ripetute.
        """
        if self.workspace_page is None:
            return
        try:
            self.workspace_page.persist_project()
        except Exception:
            pass
        try:
            if getattr(self.workspace_page, "video_player", None):
                self.workspace_page.video_player.stop()
        except Exception:
            pass
        self.workspace_page.deleteLater()
        self.workspace_page = None

    def _open_workspace(self, project_id: str):
        if self._opening_workspace:
            return
        self._opening_workspace = True
        try:
            self._dispose_workspace_page()
            self.dashboard_page = None
            self.workspace_page = WorkspacePage(project_id, self.project_repository)
            self.workspace_page.backToDashboardRequested.connect(self._show_dashboard)
            self.setCentralWidget(self.workspace_page)
            self.centralWidget().setContentsMargins(0, 0, 0, 0)
        except Exception as ex:
            logging.exception("Errore apertura workspace %s: %s", project_id, ex)
            self._append_workspace_open_error_log(project_id, ex)
            QMessageBox.critical(
                self,
                "Errore apertura progetto",
                "Impossibile aprire il progetto selezionato. "
                "Il programma e' stato riportato alla dashboard."
            )
            self.workspace_page = None
            self._show_dashboard()
        finally:
            self._opening_workspace = False

    def _append_workspace_open_error_log(self, project_id: str, ex: Exception):
        """Scrive un log locale dedicato agli errori in apertura progetto."""
        try:
            log_dir = self.project_repository.base_path
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "workspace_open_errors.log"
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            trace = traceback.format_exc()
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{now}] project_id={project_id}\n")
                f.write(f"error={type(ex).__name__}: {ex}\n")
                f.write(trace.rstrip() + "\n")
                f.write("-" * 72 + "\n")
        except Exception:
            # Non interrompere il flusso UI se anche il logging su file fallisce.
            logging.exception("Errore scrittura workspace_open_errors.log")

    def _show_dashboard(self):
        self._dispose_workspace_page()
        self.dashboard_page = DashboardPage(self.project_repository)
        self.dashboard_page.openProjectRequested.connect(self._open_workspace)
        self.setCentralWidget(self.dashboard_page)
        self.centralWidget().setContentsMargins(0, 0, 0, 0)

    def closeEvent(self, event):
        wp = self.workspace_page
        if wp is not None and getattr(wp, "_analysis_in_progress", False):
            dlg = CloseAnalysisDialog(self)
            dlg.exec_()
            choice = dlg.result_choice()
            if choice == CloseAnalysisDialog.Annulla:
                event.ignore()
                return
            if choice == CloseAnalysisDialog.Ferma:
                wp.terminate_analysis_and_close_dialog()
            else:
                wp.save_background_analysis_flag()
        if wp is not None:
            wp.persist_project()
        event.accept()


def main():
    """Entry point"""
    # High DPI scaling - DEVE essere prima di QApplication
    if hasattr(Qt, 'AA_UseHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_UseHighDpiScaling, True)
    elif hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Football Analyzer Web")
    app.setOrganizationName("FootballAnalyzer")
    
    win = AppRouter()
    win.resize(1400, 900)
    win.show()

    def _check_background_analysis_completed():
        """Se l'utente ha chiuso con 'Continua' e l'analisi è terminata, mostra messaggio."""
        try:
            repo = ProjectRepository(str((Path(__file__).parent / "data").absolute()))
            flag_path = repo.base_path / "pending_background_analysis.json"
            if not flag_path.exists():
                return
            with open(flag_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            project_analysis_dir = data.get("project_analysis_dir")
            if not project_analysis_dir:
                flag_path.unlink(missing_ok=True)
                return
            finished_path = Path(project_analysis_dir) / "analysis_output" / "finished.json"
            if not finished_path.exists():
                return
            with open(finished_path, "r", encoding="utf-8") as f:
                fin = json.load(f)
            if fin.get("success"):
                QMessageBox.information(
                    win,
                    "Analisi completata",
                    "Analisi completata in background. File pronti.",
                )
            flag_path.unlink(missing_ok=True)
        except Exception:
            try:
                flag_path.unlink(missing_ok=True)
            except Exception:
                pass

    QTimer.singleShot(1500, _check_background_analysis_completed)
    
    logging.debug("Football Analyzer Web UI started")
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
