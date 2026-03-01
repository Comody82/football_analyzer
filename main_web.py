"""
Football Analyzer - Web UI Version
Interfaccia moderna basata su QWebEngineView + HTML/CSS/JS
"""
import sys
import os
import logging
from pathlib import Path

# Fix encoding per Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Solo errori nel terminale (evita spam). Per debug: FOOTBALL_ANALYZER_DEBUG=1 python main_web.py
_log_level = logging.DEBUG if os.environ.get('FOOTBALL_ANALYZER_DEBUG') else logging.WARNING
logging.basicConfig(level=_log_level, format='%(levelname)s: %(message)s')

from PyQt5.QtWidgets import QApplication, QMainWindow, QShortcut, QMessageBox
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QContextMenuEvent, QKeySequence
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel

from backend import BackendBridge
from ui.opencv_video_widget import OpenCVVideoWidget
from ui.video_interaction_overlay import VideoInteractionOverlay
from ui.drawing_overlay import DrawingOverlay, DrawTool


class CustomWebEngineView(QWebEngineView):
    """QWebEngineView senza menu contestuale browser. Estendibile per menu custom."""

    def contextMenuEvent(self, event: QContextMenuEvent):
        # Disabilita il menu browser standard (Back, Reload, View source, ecc)
        event.accept()
        # Per menu contestuale personalizzato futuro:
        # custom_menu = self._build_custom_context_menu(event.pos())
        # if custom_menu:
        #     custom_menu.exec_(self.mapToGlobal(event.pos()))


class WebUIMainWindow(QMainWindow):
    """Finestra principale con layout Qt originale: Eventi | Video+Controlli | Clip"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Football Analyzer - Web Edition")
        
        # Container principale
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSplitter
        from PyQt5.QtCore import Qt
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principale orizzontale
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Splitter orizzontale per 3 sezioni
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background: #0f1419;
                width: 2px;
            }
        """)
        
        # 1. Sidebar Sinistra (Web UI - Eventi)
        self.web_view_left = CustomWebEngineView()
        from PyQt5.QtWebEngineWidgets import QWebEngineSettings
        self.web_view_left.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        
        # 2. Centro (Video + Controlli sotto)
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        
        # Video player
        self.video_player = OpenCVVideoWidget()
        center_layout.addWidget(self.video_player, stretch=3)
        
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


        # Refresh disegni al cambio posizione e al passaggio play/pausa (es. pausa su evento)
        self.video_player.positionChanged.connect(self._refresh_drawings_visibility)
        self.video_player.playbackStateChanged.connect(self._refresh_drawings_visibility)
        
        # Web UI controlli sotto video
        self.web_view_center = CustomWebEngineView()
        self.web_view_center.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        center_layout.addWidget(self.web_view_center, stretch=1)
        
        # 3. Sidebar Destra (Web UI - Statistiche/Clip)
        self.web_view_right = CustomWebEngineView()
        self.web_view_right.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        
        # Aggiungi al splitter
        splitter.addWidget(self.web_view_left)
        splitter.addWidget(center_widget)
        splitter.addWidget(self.web_view_right)
        splitter.setSizes([180, 800, 180])  # Eventi 180px | Centro 800px | Clip 180px
        
        main_layout.addWidget(splitter)
        
        # Backend bridge
        self.backend = BackendBridge(
            video_player=self.video_player,
            drawing_overlay=self.drawing_overlay,
            parent_window=self
        )
        
        # QWebChannel per comunicazione Python ↔ JavaScript
        self.channel = QWebChannel()
        self.channel.registerObject('backend', self.backend)
        self.web_view_left.page().setWebChannel(self.channel)
        self.web_view_center.page().setWebChannel(self.channel)
        self.web_view_right.page().setWebChannel(self.channel)
        
        # Carica frontend - 3 pagine HTML separate
        frontend_path = Path(__file__).parent / 'frontend'
        if frontend_path.exists():
            # Sidebar sinistra - Eventi
            left_url = QUrl.fromLocalFile(str((frontend_path / 'sidebar_left.html').absolute()))
            self.web_view_left.setUrl(left_url)
            
            # Centro - Controlli
            center_url = QUrl.fromLocalFile(str((frontend_path / 'controls_center.html').absolute()))
            self.web_view_center.setUrl(center_url)
            
            # Sidebar destra - Clip
            right_url = QUrl.fromLocalFile(str((frontend_path / 'sidebar_right.html').absolute()))
            self.web_view_right.setUrl(right_url)
            
            logging.info("Loading Web UI (3 panels)")
        else:
            logging.error(f"Frontend not found: {frontend_path}")

        # Scorciatoie da tastiera globali
        self._setup_shortcuts()

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
        OpenCVVideoWidget.resizeEvent(self.video_player, event)

    def _get_annotations_at(self, ts_ms):
        """Annotazioni eventi al timestamp (per overlay disegni)."""
        result = []
        for evt in self.backend.event_manager.get_events():
            if evt.timestamp_ms == ts_ms and getattr(evt, 'annotations', None):
                for i, ann in enumerate(evt.annotations):
                    result.append({"data": ann, "event_id": evt.id, "ann_index": i})
        return result

    def _refresh_drawings_visibility(self):
        """Aggiorna visibilità disegni in base a play/pausa."""
        if self.video_player.state() == 1:
            self.drawing_overlay.setDrawingsVisibility(False)
        else:
            pos = self.video_player.position()
            self.drawing_overlay.loadDrawingsFromProject(self._get_annotations_at(pos))
            self.drawing_overlay.setDrawingsVisibility(True)

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
    
    def closeEvent(self, event):
        """Cleanup on close"""
        if self.video_player:
            self.video_player.stop()  # stop() chiama release() su capture
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
    
    win = WebUIMainWindow()
    win.resize(1400, 900)
    win.show()
    
    logging.debug("Football Analyzer Web UI started")
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
