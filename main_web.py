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
_log_level = logging.DEBUG if os.environ.get('FOOTBALL_ANALYZER_DEBUG') else logging.WARNING
logging.basicConfig(level=_log_level, format='%(levelname)s: %(message)s')

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
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
    QFileDialog,
    QInputDialog,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QSizePolicy,
    QFrame,
)
from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QPoint, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QContextMenuEvent, QKeySequence, QColor, QPainter, QLinearGradient, QRadialGradient, QPen, QPixmap
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel

from backend import BackendBridge
from ui.opencv_video_widget import OpenCVVideoWidget
from ui.video_interaction_overlay import VideoInteractionOverlay
from ui.drawing_overlay import DrawingOverlay, DrawTool
from project_repository import ProjectRepository


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
                stop:0 #0c1324,
                stop:0.48 #121d33,
                stop:1 #0a1224
            );
            border: none;
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
            color: #eafff8;
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
            color: rgb(88, 240, 176);
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
        self._video_source_locked = False
        self._loaded_webviews = 0
        self._webviews_ready = {"left": False, "center": False, "right": False}
        self._frontend_ready = {"left": False, "center": False, "right": False}
        self._initial_ui_revealed = False
        self._ui_boot_locked = True
        self._highlights_mode = False
        self._highlights_image_items = []

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
        topbar_layout.addWidget(btn_stats, 0, Qt.AlignVCenter)

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

        # Layout principale orizzontale a 3 colonne
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        root_layout.addLayout(main_layout, 1)

        from PyQt5.QtWebEngineWidgets import QWebEngineSettings

        # Colonna sinistra: WebView Eventi
        self.web_view_left = CustomWebEngineView()
        self.web_view_left.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        self.web_view_left.page().setBackgroundColor(QColor(0, 0, 0, 0))
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
        
        # Overlay interazione (click per eventi timeline)
        self.video_overlay = VideoInteractionOverlay(self.video_player, parent=self.video_player)
        self.video_overlay.setGeometry(self.video_player.rect())

        # Overlay disegno - SOPRA video_overlay, riceve click per disegni e right-click per menu
        self.drawing_overlay = DrawingOverlay(self.video_player)
        self.video_overlay.drawing_overlay = self.drawing_overlay  # Inoltro right-click se ricevuto da video_overlay
        r = self.video_player.rect()
        self.drawing_overlay.setGeometry(r)
        self.drawing_overlay.setSceneRect(0, 0, max(1, r.width()), max(1, r.height()))
        self.drawing_overlay.raise_()
        r = self.video_player.rect()
        self.drawing_overlay.setGeometry(r)
        self.drawing_overlay.setSceneRect(0, 0, max(1, r.width()), max(1, r.height()))

        # Connect overlay signals
        self.video_overlay.videoClicked.connect(self._on_video_clicked)
        self.video_overlay.mousePressed.connect(self._on_mouse_pressed)
        self.video_overlay.mouseMoved.connect(self._on_mouse_moved)
        self.video_overlay.mouseReleased.connect(self._on_mouse_released)

        # Connect drawing overlay
        self.drawing_overlay.emptyAreaLeftClicked.connect(self._on_empty_area_clicked)
        self.drawing_overlay.drawingConfirmed.connect(self._on_drawing_confirmed)
        self.drawing_overlay.drawingStarted.connect(self._on_drawing_started)
        self.drawing_overlay.annotationDeleted.connect(self._on_annotation_deleted)
        self.drawing_overlay.annotationModified.connect(self._on_annotation_modified)

        # Resize overlays quando video player viene ridimensionato
        self.video_player.resizeEvent = self._video_player_resized

        # Timeline e controlli sotto il video (WebView dedicata)
        self.web_view_center_controls = CustomWebEngineView()
        self.web_view_center_controls.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        self.web_view_center_controls.page().setBackgroundColor(QColor(0, 0, 0, 0))
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
        self.web_view_right.page().setBackgroundColor(QColor(0, 0, 0, 0))
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

        # Scorciatoie da tastiera globali
        self._setup_shortcuts()
        self._dragging_window = False
        self._drag_offset = None
        self._position_save_check()
        self._position_open_video_button()
        self._update_open_video_cta_visibility()
        self._setup_startup_curtain()
        # Blocca il repaint iniziale: evita che il video Qt compaia prima delle webview.
        self.setUpdatesEnabled(False)
        # Fallback solo di sicurezza: evita reveal anticipato che crea effetto a cascata.
        QTimer.singleShot(4500, self._force_reveal_if_stuck)

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
        """Ridimensiona overlay quando video player viene ridimensionato"""
        r = self.video_player.rect()
        if hasattr(self, 'video_overlay'):
            self.video_overlay.setGeometry(r)
        if hasattr(self, 'drawing_overlay'):
            self.drawing_overlay.setGeometry(r)
            self.drawing_overlay.setSceneRect(0, 0, r.width(), r.height())
        self._position_open_video_button()
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
        """Carica il video gia' salvato sul progetto e blocca il cambio sorgente."""
        saved_path = str(getattr(self.backend.project, "video_path", "") or "").strip()
        if not saved_path:
            self._video_source_locked = False
            return
        p = Path(saved_path)
        if not p.exists():
            logging.warning("Video salvato non trovato: %s", saved_path)
            self._video_source_locked = False
            return
        self.video_player.load(str(p))
        self.backend.project.video_path = str(p)
        self.backend.videoLoaded.emit(str(p))
        self._video_source_locked = True
        QTimer.singleShot(0, self._ensure_video_frame_rendered)
        QTimer.singleShot(180, self._ensure_video_frame_rendered)

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
                    stop:0 #0f5d4d,
                    stop:0.52 #17806a,
                    stop:1 #29b48d
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
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        title = QLabel("Studio Highlights")
        title.setObjectName("hlTitle")
        subtitle = QLabel("Seleziona clip e immagini da includere nel video finale.")
        subtitle.setObjectName("hlSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.chk_hl_all = QCheckBox("Includi tutte le clip")
        self.chk_hl_all.setChecked(True)
        self.chk_hl_all.stateChanged.connect(self._on_hl_select_all_changed)
        layout.addWidget(self.chk_hl_all)

        self.list_hl_clips = QListWidget()
        layout.addWidget(self.list_hl_clips, 2)

        img_row = QHBoxLayout()
        img_label = QLabel("Immagini da inserire (append):")
        img_row.addWidget(img_label, 1)
        btn_add_img = QPushButton("+ Aggiungi immagine")
        btn_add_img.clicked.connect(self._add_highlight_image)
        btn_remove_img = QPushButton("Rimuovi selezionata")
        btn_remove_img.clicked.connect(self._remove_highlight_image)
        img_row.addWidget(btn_add_img, 0)
        img_row.addWidget(btn_remove_img, 0)
        layout.addLayout(img_row)

        self.list_hl_images = QListWidget()
        layout.addWidget(self.list_hl_images, 1)

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
        rec = {"path": path, "duration_sec": int(seconds)}
        self._highlights_image_items.append(rec)
        self.list_hl_images.addItem(f"{Path(path).name}  -  {seconds}s")

    def _remove_highlight_image(self):
        if not hasattr(self, "list_hl_images"):
            return
        row = self.list_hl_images.currentRow()
        if row < 0:
            return
        self.list_hl_images.takeItem(row)
        if 0 <= row < len(self._highlights_image_items):
            self._highlights_image_items.pop(row)

    def _selected_highlight_clip_ids(self):
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

    def _generate_highlights_from_studio(self):
        clip_ids = self._selected_highlight_clip_ids()
        ok, result = self.backend.generate_highlights_package(clip_ids, self._highlights_image_items)
        if not ok:
            QMessageBox.warning(self, "Genera Highlights", result)
            return
        QMessageBox.information(self, "Genera Highlights", f"Highlights creato:\n{result}")

    def show_highlights_studio(self):
        self._highlights_mode = True
        self.web_view_left.setVisible(False)
        self._center_widget.setVisible(True)
        self._center_stack.setCurrentWidget(self._highlights_studio_panel)
        self._highlights_image_items = []
        if hasattr(self, "list_hl_images"):
            self.list_hl_images.clear()
        self._refresh_highlights_clip_list()
        self._update_open_video_cta_visibility()

    def hide_highlights_studio(self):
        self._highlights_mode = False
        self._center_stack.setCurrentWidget(self._center_normal_widget)
        self.web_view_left.setVisible(True)
        self._update_open_video_cta_visibility()

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
        """Riceve ACK dal frontend quando una colonna ha completato bootstrap/render."""
        if area not in self._frontend_ready:
            return
        self._frontend_ready[area] = True
        if all(self._frontend_ready.values()):
            self._reveal_workspace_columns()

    def _reveal_workspace_columns(self):
        """Mostra le 3 colonne insieme per un'apertura visivamente uniforme."""
        if self._initial_ui_revealed:
            return
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
        for view in (self.web_view_left, self.web_view_center_controls, self.web_view_right):
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
        self.drawing_overlay.loadDrawingsFromProject(anns)
        self.drawing_overlay.setDrawingsVisibility(True)
        self.drawing_overlay.viewport().update()

    def _refresh_drawings_visibility(self):
        """Aggiorna visibilità disegni. Usa _seek_target_ms durante seek per evitare race."""
        ts = getattr(self, '_seek_target_ms', None)
        if ts is None:
            ts = self.video_player.position()
        if self.video_player.state() == 1:
            if self.backend.active_clip_id:
                anns = self._get_annotations_at(ts, tolerance_ms=50)
                self.drawing_overlay.loadDrawingsFromProject(anns)
                self.drawing_overlay.setDrawingsVisibility(True)
            else:
                self.drawing_overlay.setDrawingsVisibility(False)
        else:
            self.drawing_overlay.loadDrawingsFromProject(self._get_annotations_at(ts, tolerance_ms=50))
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

        # Contenuto principale
        content = QWidget()
        content.setObjectName("dashboardContent")
        content_layout = QVBoxLayout(content)
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

        shell_layout.addWidget(sidebar, 0)
        shell_layout.addWidget(divider, 0)
        shell_layout.addWidget(content, 1)
        root.addWidget(shell, 1)

        self._dashboard_nav_buttons = [nav_projects, nav_settings, nav_license]
        for btn in self._dashboard_nav_buttons:
            btn.clicked.connect(lambda _=False, b=btn: self._set_active_nav_button(b))
        QTimer.singleShot(0, lambda: self._set_active_nav_button(nav_projects))

    def _set_active_nav_button(self, active_button: QPushButton):
        for btn in getattr(self, "_dashboard_nav_buttons", []):
            btn.setProperty("active", btn is active_button)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()
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


class AppRouter(QMainWindow):
    """Routing app: DashboardPage <-> WorkspacePage(projectId)."""

    def __init__(self):
        super().__init__()
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
        if self.workspace_page is not None:
            self.workspace_page.persist_project()
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
    
    logging.debug("Football Analyzer Web UI started")
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
