"""Finestra principale Football Analyzer."""
import sys
import uuid
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QFileDialog, QListWidget, QListWidgetItem,
    QSlider, QGroupBox, QTabWidget, QScrollArea, QFrame, QGridLayout,
    QSpinBox, QMessageBox, QInputDialog, QColorDialog, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QProgressBar, QLineEdit,
    QButtonGroup, QMenu, QTextEdit, QGraphicsDropShadowEffect, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QEvent, QSize, QSettings, QRect
from PyQt5.QtGui import QIcon, QFont, QColor, QKeyEvent, QPainter, QLinearGradient, QBrush, QPen
from config import (
    DEFAULT_EVENT_TYPES, DRAW_COLORS, DEFAULT_CLIP_PRE_SECONDS,
    DEFAULT_CLIP_POST_SECONDS, HIGHLIGHTS_FOLDER, FREEZE_DURATION_SECONDS
)
from core import EventManager, Event, Project, ClipManager, StatisticsManager
from core.project import PlaylistItem
from core.events import EventType
from .event_buttons_config_dialog import (
    EventButtonsConfigDialog,
    load_saved_event_types,
    save_event_types_as_default,
    clear_default_config,
)
from .theme import get_stylesheet, apply_palette, ACCENT
from .drawing_overlay import DrawingOverlay, DrawTool, ArrowLineStyle
from .draw_icons import get_draw_tool_icon
from .opencv_video_widget import OpenCVVideoWidget


class EventTimelineBar(QFrame):
    """Barra timeline con eventi cliccabili."""
    eventClicked = pyqtSignal(int)  # timestamp_ms

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(80)
        self.setStyleSheet("""
            EventTimelineBar {
                background-color: #1A2332;
                border-radius: 8px;
                border: 1px solid #30363D;
            }
        """)
        self._duration_ms = 1
        self._position_ms = 0
        self._events = []  # [(timestamp_ms, event_type_id, color), ...]
        self._event_colors = {}

    def set_duration(self, ms: int):
        self._duration_ms = max(1, ms)
        self.update()

    def set_position(self, ms: int):
        self._position_ms = ms
        self.update()

    def set_events(self, events_list, event_colors: dict):
        self._events = events_list
        self._event_colors = event_colors
        self.update()

    def mousePressEvent(self, event):
        if self._duration_ms and event.button() == Qt.LeftButton:
            x = event.pos().x()
            pct = x / self.width() if self.width() else 0
            pct = max(0, min(1, pct))
            ts = int(pct * self._duration_ms)
            self.eventClicked.emit(ts)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QBrush, QPen, QColor
        from PyQt5.QtCore import QRect
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if w < 10 or self._duration_ms <= 0:
            return

        # Background bar
        bar_h = 12
        bar_y = (h - bar_h) // 2
        p.fillRect(10, bar_y, w - 20, bar_h, QColor("#243447"))
        p.setPen(QPen(QColor("#30363D")))
        p.drawRoundedRect(10, bar_y, w - 20, bar_h, 4, 4)

        # Position indicator
        pos_pct = self._position_ms / self._duration_ms
        pos_x = 10 + int(pos_pct * (w - 20))
        p.fillRect(10, bar_y, pos_x - 10, bar_h, QColor("#00D9A5"))
        p.setPen(QPen(QColor("#00D9A5"), 2))
        p.drawLine(pos_x, bar_y - 4, pos_x, bar_y + bar_h + 4)

        # Event markers
        for ts_ms, evt_type_id, _ in self._events:
            pct = ts_ms / self._duration_ms
            x = 10 + int(pct * (w - 20))
            color = QColor(self._event_colors.get(evt_type_id, "#888888"))
            p.setBrush(QBrush(color))
            p.setPen(Qt.NoPen)
            p.drawEllipse(x - 5, bar_y - 4, 10, 10)
        p.end()


class _EventRowWidget(QWidget):
    """Riga lista eventi con doppio clic per cercare e campo descrizione."""

    def __init__(self, evt, on_seek=None, on_description_changed=None, parent=None):
        super().__init__(parent)
        self._evt = evt
        self._on_seek = on_seek
        self._on_description_changed = on_description_changed

    def mouseDoubleClickEvent(self, event):
        if self._on_seek and self._evt:
            self._on_seek(self._evt.timestamp_ms)
        super().mouseDoubleClickEvent(event)


class _ClipCardWidget(QFrame):
    """Card professionale SaaS dark - glow disegnato direttamente nel paintEvent."""

    def __init__(self, clip: dict, is_editing: bool, is_playing: bool,
                 on_play=None, on_edit_click=None, on_delete=None,
                 on_update_start=None, on_update_end=None, on_save=None, on_cancel=None,
                 parent=None):
        super().__init__(parent)
        self._clip = clip
        self._is_editing = is_editing
        self._is_playing = is_playing
        self._on_play = on_play
        self._on_edit_click = on_edit_click
        self._on_delete = on_delete
        self._on_update_start = on_update_start
        self._on_update_end = on_update_end
        self._on_save = on_save
        self._on_cancel = on_cancel
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._build_ui()

    def sizeHint(self):
        h = 200 if not self._is_editing else 320
        return QSize(300, h)

    def paintEvent(self, event):
        """Disegna card + glow verde laterale se playing."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        
        # Card background + border
        bg_color = QColor("#0f1b2e")
        border_color = QColor(255, 255, 255, int(0.06 * 255))
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(r.adjusted(1, 1, -1, -1), 14, 14)
        
        # Glow verde laterale se playing
        playing = self._is_editing or self._is_playing
        if playing:
            glow_width = 20
            glow_x = r.right() - glow_width
            gradient = QLinearGradient(glow_x, 0, r.right(), 0)
            gradient.setColorAt(0.0, QColor(34, 197, 94, 0))      # trasparente a sinistra
            gradient.setColorAt(0.4, QColor(34, 197, 94, 60))
            gradient.setColorAt(0.7, QColor(34, 197, 94, 140))
            gradient.setColorAt(1.0, QColor(34, 197, 94, 200))    # verde pieno a destra
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRect(glow_x, 0, glow_width, r.height()), 14, 14)
        
        painter.end()

    def _build_ui(self):
        """Layout professionale: titolo + durata + bottoni affiancati + elimina."""
        self.setMinimumWidth(300)
        self.setCursor(Qt.PointingHandCursor if not self._is_editing else Qt.ArrowCursor)
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(16, 16, 16, 16)

        # Riga 1: status-dot + titolo
        header = QHBoxLayout()
        header.setSpacing(8)
        status_dot = QFrame()
        status_dot.setFixedSize(6, 6)
        status_dot.setStyleSheet("background-color: #22c55e; border-radius: 3px;")
        _dot_glow = QGraphicsDropShadowEffect()
        _dot_glow.setBlurRadius(4)
        _dot_glow.setOffset(0, 0)
        _dot_glow.setColor(QColor(34, 197, 94, 150))
        status_dot.setGraphicsEffect(_dot_glow)
        header.addWidget(status_dot)
        from html import escape
        name_esc = escape(str(self._clip["name"]))
        title = QLabel(name_esc)
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #e2e8f0;")
        title.setWordWrap(True)
        header.addWidget(title, 1)
        layout.addLayout(header)
        layout.addSpacing(8)

        # Riga 2: durata
        durata = QLabel(f"Durata: {self._clip['duration'] // 1000}s")
        durata.setStyleSheet("font-size: 13px; color: #94a3b8;")
        layout.addWidget(durata)
        layout.addSpacing(12)

        # Riga 3: bottoni affiancati - altezza 36px, spacing 8px
        actions = QHBoxLayout()
        actions.setSpacing(8)
        _btn_style = (
            "padding: 8px 16px; border-radius: 8px; border: none; "
            "font-weight: 500; font-size: 13px;"
        )
        play_btn = QPushButton("Riproduci")
        play_btn.setStyleSheet(
            f"{_btn_style} color: white; "
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
            "stop:0 #22c55e, stop:1 #16a34a);"
        )
        play_btn.setCursor(Qt.PointingHandCursor)
        play_btn.setFixedHeight(36)
        play_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        play_btn.clicked.connect(lambda checked=False, c=self._clip: self._on_play and self._on_play(c))
        
        edit_btn = QPushButton("Modifica")
        edit_btn.setStyleSheet(
            f"{_btn_style} color: #94a3b8; background-color: #1e293b;"
        )
        edit_btn.setCursor(Qt.PointingHandCursor)
        edit_btn.setFixedHeight(36)
        edit_btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        edit_btn.clicked.connect(lambda checked=False, c=self._clip: self._on_edit_click and self._on_edit_click(c))
        
        actions.addWidget(play_btn)
        actions.addWidget(edit_btn)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addSpacing(8)

        # Riga editing (se attiva)
        if self._is_editing:
            edit_row = QHBoxLayout()
            edit_row.setSpacing(8)
            _eb = "padding: 8px 12px; border-radius: 6px; font-size: 11px; font-weight: 500; color: #e2e8f0; background-color: #1e293b;"
            upd_start = QPushButton("Aggiorna Inizio")
            upd_start.setStyleSheet(_eb)
            upd_start.clicked.connect(lambda: self._on_update_start and self._on_update_start())
            upd_end = QPushButton("Aggiorna Fine")
            upd_end.setStyleSheet(_eb)
            upd_end.clicked.connect(lambda: self._on_update_end and self._on_update_end())
            edit_row.addWidget(upd_start)
            edit_row.addWidget(upd_end)
            save_btn = QPushButton("Salva")
            save_btn.setStyleSheet(
                "padding: 8px 12px; border-radius: 6px; font-size: 11px; font-weight: 500; "
                "color: white; background-color: #22c55e; border: none;"
            )
            save_btn.clicked.connect(lambda: self._on_save and self._on_save())
            cancel_btn = QPushButton("Annulla")
            cancel_btn.setStyleSheet(
                "padding: 8px 12px; border-radius: 6px; font-size: 11px; "
                "color: #94a3b8; background: transparent; border: 1px solid #334155;"
            )
            cancel_btn.clicked.connect(lambda: self._on_cancel and self._on_cancel())
            edit_row.addWidget(save_btn)
            edit_row.addWidget(cancel_btn)
            edit_row.addStretch()
            layout.addLayout(edit_row)
            layout.addSpacing(8)

        # Elimina: centrato, spazio sopra
        layout.addSpacing(4)
        del_row = QHBoxLayout()
        del_row.addStretch()
        del_btn = QPushButton("Elimina")
        del_btn.setFlat(True)
        del_btn.setStyleSheet(
            "font-size: 12px; color: #ef4444; background: transparent; border: none; "
            "padding: 4px 8px;"
        )
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(lambda checked=False, c=self._clip: self._on_delete and self._on_delete(c))
        del_row.addWidget(del_btn)
        del_row.addStretch()
        layout.addLayout(del_row)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.update()

    def mousePressEvent(self, event):
        """Clic ovunque sulla card (eccetto pulsanti) → Riproduci."""
        if self._is_editing:
            return super().mousePressEvent(event)
        child = self.childAt(event.pos())
        while child and child != self:
            if isinstance(child, QPushButton):
                return super().mousePressEvent(event)
            child = child.parentWidget()
        if self._on_play:
            self._on_play(self._clip)
            event.accept()
            return
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """Finestra principale dell'applicazione."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Football Analyzer")
        self.setStyleSheet(get_stylesheet())

        # Core
        self.event_manager = EventManager()
        # Carica configurazione salvata se esiste, altrimenti usa i predefiniti
        saved = load_saved_event_types()
        if saved:
            self.event_manager.load_event_types(saved)
        else:
            self.event_manager.load_default_types(DEFAULT_EVENT_TYPES)
        if not self.event_manager.get_event_type("annotazione"):
            self.event_manager.add_event_type(EventType("annotazione", "Annotazione", "✏️", "#00D9A5"))
        self._focus_label_event_id = None  # dopo refresh, metti focus sul campo nome di questo evento
        self.clips = []  # finestre temporali indipendenti: [{id, start, end, duration, name}]
        self.temp_clip_start = None  # ms, posizione Inizio prima di premere Fine
        self.active_clip_id = None   # id clip in riproduzione (stop a end)
        self.editing_clip_id = None  # id clip in modifica Inizio/Fine
        self._editing_clip_backup = None  # backup valori per Annulla
        self.project = Project()
        self.clip_manager = ClipManager(HIGHLIGHTS_FOLDER)
        self.stats_manager = StatisticsManager(self.event_manager)

        # Media - OpenCV per MP4 su Windows (più affidabile di QMediaPlayer)
        self.video_player = OpenCVVideoWidget()

        # Container video + overlay disegno
        self.video_container = QWidget()
        video_layout = QVBoxLayout(self.video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_layout.addWidget(self.video_player)
        self.drawing_overlay = DrawingOverlay(self.video_player)
        self.drawing_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.drawing_overlay.raise_()

        # Zoom continuo (rotella) max 5x quando strumento Zoom è attivo
        self._zoom_level = 1.0
        self._zoom_max = 5.0
        self._last_position_ms = 0

        # Timeline
        self.timeline_bar = EventTimelineBar()
        self.timeline_bar.eventClicked.connect(self._seek_to)

        # Controlli video
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self.video_player.setPosition)

        self._speed_options = [
            (2.0, "2x - Veloce"),
            (1.0, "1x - Normale"),
            (0.75, "0.75x - Leggermente rallentato"),
            (0.5, "0.5x - Rallentato"),
            (0.25, "0.25x - Analisi tecnica"),
            (0.1, "0.1x - Ultra slow motion"),
            (0.0, "Frame-by-frame - Avanzamento manuale"),
        ]
        self._current_speed_rate = 1.0
        self.speed_btn = QPushButton("1x")
        self.speed_btn.setToolTip("Velocità riproduzione")
        self.speed_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.speed_btn.clicked.connect(self._show_speed_menu)
        self.frame_btn = QPushButton("▶|")
        self.frame_btn.setToolTip("Avanzamento frame per frame")
        self.frame_btn.clicked.connect(self._step_frame)

        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setProperty("accent", True)
        self.play_btn.clicked.connect(self._toggle_play)
        self.pause_btn = QPushButton("⏸ Pausa")
        self.pause_btn.clicked.connect(self.video_player.pause)
        # Skip seconds per -Ns / +Ns (default 5, personalizzabile con click destro)
        self._skip_seconds = QSettings().value("video/skip_seconds", 5, type=int)
        self._skip_seconds = max(1, min(120, self._skip_seconds))
        self.rewind_btn = QPushButton(f"–{self._skip_seconds}s")
        self.rewind_btn.setToolTip(f"Riavvolgi {self._skip_seconds} secondi (click destro per modificare)")
        self.rewind_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.rewind_btn.customContextMenuRequested.connect(self._show_skip_seconds_menu)
        self.rewind_btn.clicked.connect(self._seek_backward)
        self.forward_btn = QPushButton(f"+{self._skip_seconds}s")
        self.forward_btn.setToolTip(f"Avanza {self._skip_seconds} secondi (click destro per modificare)")
        self.forward_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.forward_btn.customContextMenuRequested.connect(self._show_skip_seconds_menu)
        self.forward_btn.clicked.connect(self._seek_forward)

        self.time_label = QLabel("0:00 / 0:00")

        # Eventi
        self.events_list = QListWidget()
        self.events_list.setUniformItemSizes(False)
        self.events_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.events_list.customContextMenuRequested.connect(self._show_events_list_context_menu)
        self.events_list.itemDoubleClicked.connect(self._on_event_double_click)

        # Timer freeze frame al disegno (3 sec)
        self._freeze_timer = QTimer(self)
        self._freeze_timer.setSingleShot(True)
        self._freeze_timer.timeout.connect(self._on_freeze_ended)

        # Build UI
        self._build_ui()
        self._connect_signals()
        self._refresh_events_list()
        self.event_manager.set_on_change(self._on_events_changed)

    def _build_ui(self):
        # Sidebar sinistra - Eventi
        sidebar = QVBoxLayout()
        sidebar_label = QLabel("🏷️ EVENTI")
        sidebar_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #00D9A5;")
        sidebar.addWidget(sidebar_label)

        open_video_btn = QPushButton("📂 Apri Video")
        open_video_btn.setProperty("accent", "true")
        open_video_btn.clicked.connect(self.open_file)
        sidebar.addWidget(open_video_btn)

        crea_evento_btn = QPushButton("Crea Evento")
        crea_evento_btn.clicked.connect(self._crea_evento)
        sidebar.addWidget(crea_evento_btn)

        # Pulsanti eventi (si aggiornano quando si aggiungono tipi personalizzati)
        self.event_btns_widget = QWidget()
        self.event_btns_grid = QGridLayout(self.event_btns_widget)
        self._populate_event_buttons()
        sidebar.addWidget(self.event_btns_widget)

        add_custom_btn = QPushButton("Modifica Pulsanti Evento")
        add_custom_btn.clicked.connect(self._open_event_buttons_config)
        add_custom_btn.setProperty("accent", False)
        sidebar.addWidget(add_custom_btn)

        sidebar.addWidget(QLabel("Lista eventi:"))
        sidebar.addWidget(self.events_list, 1)

        # Pannello centrale - Video e timeline
        center = QVBoxLayout()
        center.addWidget(self.video_container, 1)
        center.addWidget(self.position_slider)
        ctrl_row = QHBoxLayout()
        self.restart_btn = QPushButton("↺ Restart")
        self.restart_btn.setToolTip("Riavvia dall'inizio e play")
        self.restart_btn.clicked.connect(self._restart_video)
        ctrl_row.addWidget(self.restart_btn)
        ctrl_row.addWidget(self.speed_btn)
        ctrl_row.addWidget(self.frame_btn)
        ctrl_row.addWidget(self.play_btn)
        ctrl_row.addWidget(self.pause_btn)
        ctrl_row.addWidget(self.rewind_btn)
        ctrl_row.addWidget(self.forward_btn)
        self.prev_event_btn = QPushButton("⏮")
        self.prev_event_btn.setToolTip("Evento precedente")
        self.prev_event_btn.clicked.connect(self._go_to_prev_event)
        ctrl_row.addWidget(self.prev_event_btn)
        self.next_event_btn = QPushButton("⏭")
        self.next_event_btn.setToolTip("Evento successivo")
        self.next_event_btn.clicked.connect(self._go_to_next_event)
        ctrl_row.addWidget(self.next_event_btn)
        self.zoom_btn = QPushButton()
        self.zoom_btn.setProperty("drawToolBtn", True)
        self.zoom_btn.setIcon(get_draw_tool_icon("zoom", 18))
        self.zoom_btn.setIconSize(QSize(18, 18))
        self.zoom_btn.setToolTip("Zoom (rotella verso il puntatore)")
        self.zoom_btn.setCheckable(True)
        self.zoom_btn.clicked.connect(self._toggle_zoom_tool)
        ctrl_row.addWidget(self.zoom_btn)
        ctrl_row.addWidget(self.time_label, 1)
        # Separatore verticale
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("background-color: #30363D; max-width: 1px; margin: 0 8px;")
        ctrl_row.addWidget(sep)
        # Sezione Crea Clip
        clip_grp = QFrame()
        clip_grp.setStyleSheet("QFrame { background-color: transparent; }")
        clip_hl = QHBoxLayout(clip_grp)
        clip_hl.setContentsMargins(4, 0, 4, 0)
        clip_hl.setSpacing(8)
        clip_lbl = QLabel("🎬 Crea Clip")
        clip_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #F0F6FC;")
        clip_lbl.setToolTip("Inizio → Fine: crea una finestra temporale")
        clip_hl.addWidget(clip_lbl)
        self.clip_inizio_btn = QPushButton("Inizio")
        self.clip_inizio_btn.setToolTip("Imposta la posizione corrente come inizio della clip")
        self.clip_inizio_btn.clicked.connect(self._on_clip_inizio)
        self.clip_fine_btn = QPushButton("Fine")
        self.clip_fine_btn.setToolTip("Imposta la fine e crea la clip")
        self.clip_fine_btn.clicked.connect(self._on_clip_fine)
        clip_hl.addWidget(self.clip_inizio_btn)
        clip_hl.addWidget(self.clip_fine_btn)
        ctrl_row.addWidget(clip_grp)
        center.addLayout(ctrl_row)
        center.addWidget(QLabel("Timeline eventi:"))
        center.addWidget(self.timeline_bar)

        # Strumenti disegno
        draw_group = QGroupBox("✏️ Strumenti disegno")
        draw_layout = QHBoxLayout()
        self.draw_btn_group = QButtonGroup()
        self.draw_btn_group.setExclusive(True)
        self._draw_btns = {}
        tooltips = {
            DrawTool.CIRCLE: "Cerchio",
            DrawTool.ARROW: "Freccia",
            DrawTool.LINE: "Linea",
            DrawTool.RECTANGLE: "Rettangolo",
            DrawTool.TEXT: "Testo",
            DrawTool.PENCIL: "Matita",
            DrawTool.CURVED_LINE: "Linea curva",
            DrawTool.CURVED_ARROW: "Freccia curva",
            DrawTool.PARABOLA_ARROW: "Parabola",
            DrawTool.DASHED_ARROW: "Freccia tratteggiata",
            DrawTool.ZIGZAG_ARROW: "Freccia zigzag",
            DrawTool.DOUBLE_ARROW: "Freccia doppia punta",
            DrawTool.DASHED_LINE: "Linea tratteggiata",
            DrawTool.POLYGON: "Poligono",
        }
        for tool in [
            DrawTool.CIRCLE, DrawTool.ARROW, DrawTool.LINE, DrawTool.RECTANGLE,
            DrawTool.TEXT, DrawTool.PENCIL,
            DrawTool.CURVED_LINE, DrawTool.CURVED_ARROW, DrawTool.PARABOLA_ARROW,
            DrawTool.DASHED_ARROW, DrawTool.ZIGZAG_ARROW, DrawTool.DOUBLE_ARROW, DrawTool.DASHED_LINE,
            DrawTool.POLYGON,
        ]:
            btn = QPushButton()
            btn.setIcon(get_draw_tool_icon(tool.value, 18))
            btn.setIconSize(QSize(18, 18))
            btn.setToolTip(tooltips[tool])
            btn.setProperty("drawToolBtn", True)
            btn.setCheckable(True)
            btn.setProperty("draw_tool", tool)
            btn.clicked.connect(lambda checked, t=tool: self._set_draw_tool(t))
            self.draw_btn_group.addButton(btn)
            self._draw_btns[tool] = btn
            draw_layout.addWidget(btn)
        self._line_widths = [1, 2, 3, 4, 5, 6, 8, 10]
        self._color_btn = QPushButton("🎨 Colore / Spessore")
        self._color_btn.setProperty("drawToolbarBtn", True)
        self._color_btn.clicked.connect(self._show_color_size_menu)
        draw_layout.addWidget(self._color_btn)
        clear_btn = QPushButton("🗑️ Cancella disegni")
        clear_btn.clicked.connect(self.drawing_overlay.clearDrawings)
        draw_layout.addWidget(clear_btn)
        draw_group.setLayout(draw_layout)
        center.addWidget(draw_group)

        # Tab destra: Statistiche, Clip, Playlist
        right_panel = QTabWidget()
        # Statistiche
        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        self.stats_label = QLabel(
            "Le statistiche non sono collegate ai tasti evento.\n"
            "Usa Aggiorna per aggiornare."
        )
        self.stats_label.setWordWrap(True)
        stats_layout.addWidget(self.stats_label)
        refresh_stats_btn = QPushButton("🔄 Aggiorna statistiche")
        refresh_stats_btn.clicked.connect(self._refresh_statistics)
        stats_layout.addWidget(refresh_stats_btn)
        right_panel.addTab(stats_tab, "📊 Statistiche")

        # Clip e Highlights
        clip_tab = QWidget()
        clip_layout = QVBoxLayout(clip_tab)
        clip_layout.addWidget(QLabel("Crea clip dagli eventi:"))
        pre_spin = QSpinBox()
        pre_spin.setRange(0, 120)
        pre_spin.setValue(DEFAULT_CLIP_PRE_SECONDS)
        pre_spin.setSuffix(" sec prima")
        post_spin = QSpinBox()
        post_spin.setRange(0, 120)
        post_spin.setValue(DEFAULT_CLIP_POST_SECONDS)
        post_spin.setSuffix(" sec dopo")
        clip_layout.addWidget(QLabel("Secondi prima dell'evento:"))
        clip_layout.addWidget(pre_spin)
        clip_layout.addWidget(QLabel("Secondi dopo l'evento:"))
        clip_layout.addWidget(post_spin)
        self.pre_seconds_spin = pre_spin
        self.post_seconds_spin = post_spin
        create_clips_btn = QPushButton("✂️ Crea clip da tutti gli eventi")
        create_clips_btn.setProperty("accent", True)
        create_clips_btn.clicked.connect(self._create_clips_from_events)
        clip_layout.addWidget(create_clips_btn)
        assemble_btn = QPushButton("🎬 Assembla highlights")
        assemble_btn.clicked.connect(self._assemble_highlights)
        clip_layout.addWidget(assemble_btn)
        clip_layout.addWidget(QLabel("Le tue clip (finestre temporali):"))
        self.clips_list = QListWidget()
        self.clips_list.setMinimumHeight(180)
        self.clips_list.setUniformItemSizes(False)
        clip_layout.addWidget(self.clips_list)
        self.clip_status_label = QLabel("")
        clip_layout.addWidget(self.clip_status_label)
        clip_layout.addStretch()
        right_panel.addTab(clip_tab, "✂️ Clip")

        # Layout principale
        splitter = QSplitter(Qt.Horizontal)
        left_w = QWidget()
        left_w.setLayout(sidebar)
        left_w.setMaximumWidth(280)
        splitter.addWidget(left_w)
        center_w = QWidget()
        center_w.setLayout(center)
        splitter.addWidget(center_w)
        right_w = QWidget()
        right_w.setLayout(QVBoxLayout())
        right_w.layout().addWidget(right_panel)
        right_w.setMaximumWidth(320)
        splitter.addWidget(right_w)
        # Dimensioni splitter che restano entro lo schermo disponibile (evita setGeometry warning)
        screen = QApplication.primaryScreen()
        avail = (screen.availableGeometry().width() - 40) if screen else 1600
        center_sz = max(500, avail - 280 - 320)
        splitter.setSizes([280, center_sz, 320])

        self.setCentralWidget(splitter)

    def _connect_signals(self):
        self.video_player.positionChanged.connect(self._on_position_changed)
        self.video_player.durationChanged.connect(self._on_duration_changed)
        self.video_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.video_player.installEventFilter(self)
        self.drawing_overlay.drawingStarted.connect(self._on_drawing_started)
        self.drawing_overlay.drawingConfirmed.connect(self._on_drawing_confirmed)
        self.drawing_overlay.annotationDeleted.connect(self._on_annotation_deleted)
        self.drawing_overlay.annotationModified.connect(self._on_annotation_modified)
        self.drawing_overlay.zoomRequested.connect(self._on_zoom_requested)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if self._handle_video_shortcut(event):
                return True
        if obj == self.video_player and event.type() == QEvent.Resize:
            w, h = self.video_player.width(), self.video_player.height()
            self.drawing_overlay.setGeometry(0, 0, w, h)
            self.drawing_overlay.setSceneRect(0, 0, w, h)
        return super().eventFilter(obj, event)

    def _handle_video_shortcut(self, event: QKeyEvent) -> bool:
        """Gestisce scorciatoie video. Ritorna True se consuma l'evento."""
        fw = QApplication.focusWidget()
        if fw:
            if isinstance(fw, (QLineEdit, QTextEdit, QSpinBox, QComboBox)):
                return False
            if fw == self.drawing_overlay and self.drawing_overlay.is_editing_text():
                return False
        key = event.key()
        mods = event.modifiers()
        if mods not in (Qt.NoModifier, Qt.KeypadModifier):
            return False
        if key == Qt.Key_Space:
            self._toggle_play()
            return True
        if key == Qt.Key_R:
            self._restart_video()
            return True
        if key == Qt.Key_Left:
            self._seek_backward()
            return True
        if key == Qt.Key_Right:
            self._seek_forward()
            return True
        if key in (Qt.Key_Comma, Qt.Key_Less):  # virgola, anche layout non-US
            self._go_to_prev_event()
            return True
        if key in (Qt.Key_Period, Qt.Key_Greater):  # punto, anche layout non-US
            self._go_to_next_event()
            return True
        return False

    def _on_zoom_requested(self, delta: int, mouse_x: int, mouse_y: int):
        """Rotella con strumento Zoom attivo: zoom verso il puntatore (max 5x)."""
        factor = 1.0 + (delta / 1200.0)  # ~1.1 per step tipico
        self._zoom_level *= factor
        self._zoom_level = max(1.0, min(self._zoom_max, self._zoom_level))
        self.video_player.setZoomAt(self._zoom_level, mouse_x, mouse_y)
        if self.video_player.duration() > 0:
            self.video_player.setPosition(self.video_player.position())

    def _on_duration_changed(self, ms):
        self.project.duration_ms = ms
        self.position_slider.setRange(0, ms)
        self.timeline_bar.set_duration(ms)
        self._update_timeline_events()

    def _on_position_changed(self, ms):
        last = self._last_position_ms
        self._last_position_ms = ms
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(ms)
        self.position_slider.blockSignals(False)
        self.timeline_bar.set_position(ms)
        d = self.video_player.duration()
        self.time_label.setText(
            f"{ms // 60000}:{(ms % 60000) // 1000:02d} / "
            f"{d // 60000}:{(d % 60000) // 1000:02d}"
        )
        if self.video_player.state() == 1:
            if self.active_clip_id is not None:
                clip = self._get_clip_by_id(self.active_clip_id)
                if clip and ms >= clip["end"]:
                    self.video_player.pause()
                    self.active_clip_id = None
                    self._refresh_clips_list()
                    self.statusBar().showMessage("Fine della clip", 2000)
            else:
                evt = self._get_event_reached_while_playing(last, ms)
                if evt is not None:
                    self.video_player.pause()
                    self.video_player.setPosition(evt.timestamp_ms)
                    self._last_position_ms = evt.timestamp_ms
        self._refresh_drawings_visibility()

    def _get_event_reached_while_playing(self, from_ms: int, to_ms: int):
        """Ritorna il primo evento nel range (from_ms, to_ms], o None."""
        if from_ms >= to_ms:
            return None
        events = self.event_manager.get_events()
        for evt in events:
            if from_ms < evt.timestamp_ms <= to_ms:
                return evt
        return None

    def _on_playback_state_changed(self, playing: bool):
        """Video in play: nasconde disegni. In pausa: mostra disegni per timestamp corrente."""
        self._refresh_drawings_visibility()

    def _get_annotations_at(self, ts_ms: int):
        """Ritorna tutte le annotazioni al timestamp con event_id/ann_index per delete."""
        result = list(self.project.get_drawings_at(ts_ms))
        for evt in self.event_manager.get_events():
            if evt.timestamp_ms == ts_ms and evt.annotations:
                for i, ann in enumerate(evt.annotations):
                    result.append({"data": ann, "event_id": evt.id, "ann_index": i})
        return result

    def _refresh_drawings_visibility(self):
        """Aggiorna visibilità disegni: nascosti se in play, visibili se in pausa al timestamp corrente."""
        if self.video_player.state() == 1:  # PlayingState
            self.drawing_overlay.setDrawingsVisibility(False)
        else:
            pos = self.video_player.position()
            self.drawing_overlay.loadDrawingsFromProject(self._get_annotations_at(pos))
            self.drawing_overlay.setDrawingsVisibility(True)

    def _on_annotation_modified(self, event_id: str, ann_index: int, new_data: dict):
        """Salva modifiche (posizione, dimensioni) nell'evento."""
        self.event_manager.update_annotation_in_event(event_id, ann_index, new_data)

    def _on_annotation_deleted(self, event_id: str, ann_index: int):
        """Rimuove annotazione da evento (chiamato da menu contestuale Elimina)."""
        self.event_manager.remove_annotation_from_event(event_id, ann_index)
        self._refresh_drawings_visibility()
        self._refresh_events_list()

    def _on_drawing_confirmed(self, item):
        """Annotazione confermata: 1 evento per timestamp, tutte le annotazioni nello stesso evento."""
        if not self.project.video_path:
            return
        data = self.drawing_overlay.item_to_serializable_data(item)
        if not data:
            return
        ts = self.video_player.position()
        evt = self.event_manager.get_annotazione_event_at_timestamp(ts)
        if evt:
            self.event_manager.add_annotation_to_event(evt.id, data)
        else:
            self.event_manager.add_event(
                "annotazione",
                ts,
                label=f"Annotazione {ts // 1000}s",
                annotations=[data]
            )
        self.drawing_overlay.removeItemForSave(item)
        self._refresh_drawings_visibility()
        self._refresh_events_list()

    def _on_drawing_started(self):
        """Freeze automatico quando si inizia a disegnare (stile Kinovea)."""
        self.video_player.pause()
        self._freeze_timer.stop()
        self._freeze_timer.start(FREEZE_DURATION_SECONDS * 1000)

    def _on_freeze_ended(self):
        """Fine del freeze frame - il video resta in pausa, l'utente può premere Play."""
        pass

    def _toggle_play(self):
        if self.video_player.state() == 1:  # PlayingState
            self.video_player.pause()
        else:
            self.video_player.play()

    def _show_speed_menu(self):
        menu = QMenu(self)
        for rate, label in self._speed_options:
            a = menu.addAction(label)
            a.setData(rate)
        action = menu.exec_(self.speed_btn.mapToGlobal(self.speed_btn.rect().bottomLeft()))
        if action:
            rate = action.data()
            self._current_speed_rate = rate
            self.video_player.setPlaybackRate(rate)
            if rate == 0:
                self.speed_btn.setText("Frame")
            else:
                self.speed_btn.setText(f"{rate}x")

    def _step_frame(self):
        self.video_player.stepForward()

    def _seek_backward(self):
        """Riavvolgi di _skip_seconds secondi (min 0)."""
        pos = self.video_player.position()
        new_pos = max(0, pos - self._skip_seconds * 1000)
        self.video_player.setPosition(new_pos)

    def _seek_forward(self):
        """Avanza di _skip_seconds secondi (max duration)."""
        pos = self.video_player.position()
        duration = self.video_player.duration()
        new_pos = min(duration, pos + self._skip_seconds * 1000)
        self.video_player.setPosition(new_pos)

    def _show_skip_seconds_menu(self, pos):
        """Menu contestuale per modificare i secondi di skip."""
        menu = QMenu(self)
        presets = [3, 5, 8, 10, 15, 30, 60]
        for s in presets:
            a = menu.addAction(f"{s}s")
            a.setData(s)
        menu.addSeparator()
        custom_action = menu.addAction("Personalizza...")
        btn = self.sender()
        global_pos = btn.mapToGlobal(pos) if btn else self.rewind_btn.mapToGlobal(pos)
        action = menu.exec_(global_pos)
        if action == custom_action:
            v, ok = QInputDialog.getInt(
                self, "Secondi di skip",
                "Secondi (1–120):",
                self._skip_seconds, 1, 120
            )
            if ok:
                self._set_skip_seconds(v)
        elif action and action.data() is not None:
            self._set_skip_seconds(action.data())

    def _set_skip_seconds(self, seconds: int):
        """Aggiorna il valore di skip, salva in QSettings e aggiorna le etichette."""
        self._skip_seconds = max(1, min(120, seconds))
        QSettings().setValue("video/skip_seconds", self._skip_seconds)
        self.rewind_btn.setText(f"–{self._skip_seconds}s")
        self.rewind_btn.setToolTip(f"Riavvolgi {self._skip_seconds} secondi (click destro per modificare)")
        self.forward_btn.setText(f"+{self._skip_seconds}s")
        self.forward_btn.setToolTip(f"Avanza {self._skip_seconds} secondi (click destro per modificare)")

    def _seek_to(self, ms: int):
        self.video_player.setPosition(ms)

    def _restart_video(self):
        """Riavvia dall'inizio e avvia la riproduzione."""
        self.video_player.setPosition(0)
        self._last_position_ms = 0
        self.video_player.play()

    def _go_to_prev_event(self):
        """Vai all'evento precedente rispetto alla posizione corrente."""
        pos = self.video_player.position()
        events = [e for e in self.event_manager.get_events() if e.timestamp_ms < pos]
        if not events:
            return
        prev_evt = max(events, key=lambda e: e.timestamp_ms)
        self.video_player.setPosition(prev_evt.timestamp_ms)
        self.video_player.pause()
        self._refresh_drawings_visibility()

    def _go_to_next_event(self):
        """Vai all'evento successivo rispetto alla posizione corrente."""
        pos = self.video_player.position()
        events = [e for e in self.event_manager.get_events() if e.timestamp_ms > pos]
        if not events:
            return
        next_evt = min(events, key=lambda e: e.timestamp_ms)
        self.video_player.setPosition(next_evt.timestamp_ms)
        self.video_player.pause()
        self._refresh_drawings_visibility()

    def _add_event(self, event_type_id: str):
        pos = self.video_player.position()
        evt = self.event_manager.add_event(event_type_id, pos, team="home")
        if evt:
            self._refresh_events_list()
            self._update_timeline_events()

    def _crea_evento(self):
        """Crea subito un evento nella lista con nome editabile inline (senza popup)."""
        evt = self.event_manager.add_event("evento", self.video_player.position(), label="Nuovo Evento")
        if evt:
            self._focus_label_event_id = evt.id
            self._refresh_events_list()
            self._update_timeline_events()

    def _populate_event_buttons(self):
        """Aggiorna i pulsanti eventi (chiamato all'avvio e dopo aver aggiunto tipi personalizzati)."""
        # Rimuovi pulsanti esistenti
        while self.event_btns_grid.count():
            child = self.event_btns_grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        # Aggiungi pulsante per ogni tipo (escluso annotazione: creata automaticamente dai disegni)
        types_to_show = [et for et in self.event_manager.get_event_types() if et.id != "annotazione"]
        for i, et in enumerate(types_to_show):
            btn = QPushButton(et.name)
            btn.setStyleSheet(f"border-left: 4px solid {et.color};")
            btn.setProperty("event_type_id", et.id)
            btn.clicked.connect(lambda checked, tid=et.id: self._add_event(tid))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, b=btn: self._show_event_button_context_menu(b, pos)
            )
            self.event_btns_grid.addWidget(btn, i // 2, i % 2)

    def _show_event_button_context_menu(self, btn, pos):
        """Menu contestuale sul pulsante evento: modifica nome."""
        tid = btn.property("event_type_id")
        if not tid:
            return
        et = self.event_manager.get_event_type(tid)
        if not et:
            return
        menu = QMenu(self)
        menu.addAction("Modifica nome evento")
        action = menu.exec_(btn.mapToGlobal(pos))
        if action and action.text() == "Modifica nome evento":
            new_name, ok = QInputDialog.getText(
                self, "Modifica nome evento", "Nuovo nome:",
                text=et.name
            )
            if ok and new_name.strip():
                if self.event_manager.update_event_type_name(tid, new_name.strip()):
                    self._populate_event_buttons()

    def _open_event_buttons_config(self):
        """Apre la finestra di configurazione dei pulsanti evento."""
        try:
            current = self.event_manager.get_event_types()
            dlg = EventButtonsConfigDialog(current, self)
            if dlg.exec() == QDialog.Accepted:
                new_types = dlg.get_event_types()
                if not new_types:
                    QMessageBox.warning(
                        self, "Attenzione",
                        "Deve restare almeno un pulsante evento."
                    )
                    return
                self.event_manager.load_event_types(new_types)
                self._populate_event_buttons()
                if dlg.save_as_default():
                    if save_event_types_as_default(new_types):
                        self.statusBar().showMessage(
                            "Configurazione salvata come predefinita. Verrà usata alla prossima apertura.",
                            4000
                        )
                    else:
                        QMessageBox.warning(
                            self, "Errore",
                            "Impossibile salvare la configurazione su disco."
                        )
                else:
                    clear_default_config()  # Rimuove config salvata se l'utente ha deselezionato
                    self.statusBar().showMessage(
                        "Modifiche applicate solo a questa sessione.",
                        3000
                    )
        except Exception as ex:
            QMessageBox.warning(self, "Errore", str(ex))

    def _on_events_changed(self):
        self._refresh_events_list()
        self._update_timeline_events()

    def _refresh_events_list(self):
        self.events_list.clear()
        types = {t.id: t for t in self.event_manager.get_event_types()}
        focus_evt_id = self._focus_label_event_id
        self._focus_label_event_id = None
        for evt in self.event_manager.get_events():
            t = types.get(evt.event_type_id)
            type_name = t.name if t else evt.event_type_id
            display_name = evt.label if evt.label else type_name
            item = QListWidgetItem()
            item.setData(Qt.UserRole, evt)
            row = _EventRowWidget(
                evt,
                on_seek=self.video_player.setPosition,
                on_description_changed=self._on_event_description_changed,
            )
            row.setFixedHeight(88)
            main_layout = QVBoxLayout(row)
            main_layout.setContentsMargins(4, 1, 4, 1)
            main_layout.setSpacing(2)
            top_layout = QHBoxLayout()
            top_layout.setSpacing(4)
            name_edit = QLineEdit()
            name_edit.setPlaceholderText(type_name)
            name_edit.setText(display_name)
            name_edit.setMinimumHeight(26)
            name_edit.setStyleSheet("font-size: 11px; padding: 2px 4px; font-weight: normal;")
            name_edit.setToolTip("Doppio clic sulla riga per cercare nel video. Invio o click fuori per salvare.")
            name_edit.editingFinished.connect(
                lambda e=evt, n=name_edit: self._on_event_label_finished(e, n)
            )
            top_layout.addWidget(name_edit, 1)
            main_layout.addLayout(top_layout)
            desc_edit = QLineEdit()
            desc_edit.setPlaceholderText("Descrizione...")
            desc_edit.setText(evt.description or "")
            desc_edit.setMinimumHeight(30)
            desc_edit.setStyleSheet("font-size: 11px; padding: 4px;")
            desc_edit.editingFinished.connect(
                lambda e=evt, d=desc_edit: self._on_event_description_changed(e, d.text())
            )
            main_layout.addWidget(desc_edit)
            item.setSizeHint(QSize(0, 88))
            self.events_list.addItem(item)
            self.events_list.setItemWidget(item, row)
            if focus_evt_id == evt.id:
                QTimer.singleShot(50, lambda ne=name_edit: self._focus_and_select_label(ne))

    def _update_timeline_events(self):
        types = {t.id: t.color for t in self.event_manager.get_event_types()}
        events_data = [
            (e.timestamp_ms, e.event_type_id, types.get(e.event_type_id, "#888"))
            for e in self.event_manager.get_events()
        ]
        self.timeline_bar.set_events(events_data, types)

    def _show_events_list_context_menu(self, pos):
        """Menu contestuale sulla lista eventi: elimina evento."""
        item = self.events_list.itemAt(pos)
        if not item:
            return
        evt = item.data(Qt.UserRole)
        if not evt:
            return
        menu = QMenu(self)
        elimina_act = menu.addAction("Elimina")
        action = menu.exec_(self.events_list.mapToGlobal(pos))
        if action == elimina_act:
            clip_paths = self.project.remove_playlist_items_by_event_id(evt.id)
            for p in clip_paths:
                try:
                    Path(p).unlink()
                except OSError:
                    pass
            if evt.drawing_id:
                self.project.remove_drawing(evt.drawing_id)
                self._refresh_drawings_visibility()
            self.event_manager.remove_event(evt.id)
            self._refresh_events_list()
            self._update_timeline_events()

    def _on_event_double_click(self, item):
        evt = item.data(Qt.UserRole)
        if evt:
            self._refresh_events_list()
            self.video_player.setPosition(evt.timestamp_ms)

    def _on_event_description_changed(self, evt, text: str):
        """Salva la descrizione modificata dall'utente."""
        self.event_manager.update_event_description(evt.id, text or "")

    def _focus_and_select_label(self, name_edit: QLineEdit):
        """Mette il cursore nel campo nome e seleziona tutto per modifica immediata."""
        name_edit.setFocus(Qt.OtherFocusReason)
        name_edit.selectAll()

    def _on_event_label_finished(self, evt, name_edit: QLineEdit):
        """Chiamato da editingFinished (Invio o click fuori): salva il nome o default se vuoto."""
        text = name_edit.text().strip()
        if not text:
            text = self.event_manager._next_default_event_label()
        # Differiamo l'aggiornamento per evitare di distruggere il widget durante il callback
        evt_id = evt.id
        QTimer.singleShot(0, lambda: self._save_event_label(evt_id, text))

    def _save_event_label(self, evt_id: str, text: str):
        """Salva il label dell'evento (chiamato in modo differito)."""
        self.event_manager.update_event_label(evt_id, text)

    def _format_time_mmss(self, ms: int) -> str:
        """Formatta ms come mm:ss."""
        s = ms // 1000
        return f"{s // 60:02d}:{s % 60:02d}"

    def _update_clip_inizio_btn_state(self):
        """Aggiorna lo stato visivo del pulsante Inizio (evidenziato se attivo)."""
        active = self.temp_clip_start is not None
        self.clip_inizio_btn.setProperty("accent", "true" if active else False)
        self.clip_inizio_btn.style().unpolish(self.clip_inizio_btn)
        self.clip_inizio_btn.style().polish(self.clip_inizio_btn)

    def _on_clip_inizio(self):
        """Imposta la posizione corrente come inizio della clip."""
        self.temp_clip_start = self.video_player.position()
        self._update_clip_inizio_btn_state()
        ts_str = self._format_time_mmss(self.temp_clip_start)
        self.statusBar().showMessage(f"Inizio impostato a {ts_str}", 4000)

    def _on_clip_fine(self):
        """Crea la clip dall'inizio salvato alla posizione corrente."""
        if self.temp_clip_start is None:
            QMessageBox.warning(self, "Attenzione", "Imposta prima l'inizio della clip")
            return
        current_ms = self.video_player.position()
        if current_ms <= self.temp_clip_start:
            QMessageBox.warning(
                self, "Attenzione",
                "Il punto di fine deve essere successivo all'inizio"
            )
            return
        clip_id = str(uuid.uuid4())[:8]
        duration_ms = current_ms - self.temp_clip_start
        clip = {
            "id": clip_id,
            "start": self.temp_clip_start,
            "end": current_ms,
            "duration": duration_ms,
            "name": f"Clip {len(self.clips) + 1}"
        }
        self.clips.append(clip)
        self.temp_clip_start = None
        self._update_clip_inizio_btn_state()
        self._refresh_clips_list()
        self.statusBar().showMessage("Clip creata con successo", 3000)

    def _get_clip_by_id(self, clip_id: str):
        """Ritorna la clip con id dato o None."""
        for c in self.clips:
            if c["id"] == clip_id:
                return c
        return None

    def _refresh_clips_list(self):
        """Aggiorna la lista clip nell'UI."""
        self.clips_list.clear()
        for clip in self.clips:
            item = QListWidgetItem()
            card = _ClipCardWidget(
                clip,
                is_editing=(self.editing_clip_id == clip["id"]),
                is_playing=(self.active_clip_id == clip["id"]),
                on_play=self._play_clip,
                on_edit_click=self._enter_clip_edit,
                on_delete=self._delete_clip,
                on_update_start=self._clip_update_start,
                on_update_end=self._clip_update_end,
                on_save=self._clip_save_edit,
                on_cancel=self._clip_cancel_edit,
            )
            h = 320 if self.editing_clip_id == clip["id"] else 200
            item.setSizeHint(QSize(0, h))
            item.setData(Qt.UserRole, clip)
            self.clips_list.addItem(item)
            self.clips_list.setItemWidget(item, card)

    def _play_clip(self, clip: dict):
        """Riproduce la clip (seek a start, play, stop a end)."""
        if self.editing_clip_id and self.editing_clip_id != clip["id"]:
            self._clip_cancel_edit()
        self.active_clip_id = clip["id"]
        self.video_player.setPosition(clip["start"])
        self.video_player.play()
        self._refresh_clips_list()

    def _enter_clip_edit(self, clip: dict):
        """Entra in modalità modifica Inizio/Fine per la clip."""
        self._editing_clip_backup = {
            "start": clip["start"],
            "end": clip["end"],
            "duration": clip["duration"],
        }
        self.editing_clip_id = clip["id"]
        self.video_player.setPosition(clip["start"])
        self.video_player.pause()
        self._refresh_clips_list()
        self.statusBar().showMessage("Modifica: usa 'Aggiorna Inizio' e 'Aggiorna Fine', poi 'Salva'", 4000)

    def _clip_update_start(self):
        """Aggiorna start della clip in editing con posizione corrente."""
        clip = self._get_clip_by_id(self.editing_clip_id)
        if not clip:
            return
        clip["start"] = self.video_player.position()
        if clip["end"] <= clip["start"]:
            clip["end"] = clip["start"] + 1000
        clip["duration"] = clip["end"] - clip["start"]
        self.video_player.setPosition(clip["start"])
        self._refresh_clips_list()
        self.statusBar().showMessage("Inizio aggiornato", 2000)

    def _clip_update_end(self):
        """Aggiorna end della clip in editing con posizione corrente."""
        clip = self._get_clip_by_id(self.editing_clip_id)
        if not clip:
            return
        clip["end"] = self.video_player.position()
        if clip["end"] <= clip["start"]:
            clip["start"] = max(0, clip["end"] - 1000)
        clip["duration"] = clip["end"] - clip["start"]
        self._refresh_clips_list()
        self.statusBar().showMessage("Fine aggiornata", 2000)

    def _clip_save_edit(self):
        """Esce da modalità editing senza ripristinare."""
        self.editing_clip_id = None
        self._editing_clip_backup = None
        self._refresh_clips_list()
        self.statusBar().showMessage("Modifiche salvate", 2000)

    def _clip_cancel_edit(self):
        """Annulla modifiche e esce da modalità editing."""
        clip = self._get_clip_by_id(self.editing_clip_id)
        if clip and self._editing_clip_backup:
            clip["start"] = self._editing_clip_backup["start"]
            clip["end"] = self._editing_clip_backup["end"]
            clip["duration"] = self._editing_clip_backup["duration"]
        self.editing_clip_id = None
        self._editing_clip_backup = None
        self._refresh_clips_list()
        self.statusBar().showMessage("Modifiche annullate", 2000)

    def _delete_clip(self, clip: dict):
        """Elimina la clip dalla lista."""
        self.clips = [c for c in self.clips if c["id"] != clip["id"]]
        if self.active_clip_id == clip["id"]:
            self.video_player.pause()
            self.active_clip_id = None
        if self.editing_clip_id == clip["id"]:
            self.editing_clip_id = None
            self._editing_clip_backup = None
        self._refresh_clips_list()

    def _set_draw_tool(self, tool: DrawTool):
        self.drawing_overlay.setTool(tool)
        for t, btn in self._draw_btns.items():
            btn.setChecked(t == tool)
        if hasattr(self, "zoom_btn"):
            self.zoom_btn.setChecked(tool == DrawTool.ZOOM)
        if tool in (DrawTool.ARROW, DrawTool.LINE):
            self.drawing_overlay.setArrowLineStyle(ArrowLineStyle.STRAIGHT)

    def _toggle_zoom_tool(self):
        """Attiva/disattiva zoom dalla riga Play/Pausa."""
        if self.zoom_btn.isChecked():
            self._set_draw_tool(DrawTool.ZOOM)
        else:
            self.drawing_overlay.setTool(DrawTool.NONE)
            self.zoom_btn.setChecked(False)
            for t, btn in self._draw_btns.items():
                btn.setChecked(False)

    def _show_color_size_menu(self):
        menu = QMenu(self)
        col_act = menu.addAction("Scegli colore...")
        col_act.triggered.connect(lambda: self.drawing_overlay.chooseColor())
        menu.addSeparator()
        menu.addAction("Dimensioni linea:").setEnabled(False)
        current_w = self.drawing_overlay.penWidth()
        for w in self._line_widths:
            a = menu.addAction(f"{w} px")
            a.setData(w)
            a.setCheckable(True)
            a.setChecked(w == current_w)
        action = menu.exec_(self._color_btn.mapToGlobal(self._color_btn.rect().bottomLeft()))
        if action and action.data() is not None:
            self.drawing_overlay.setPenWidth(action.data())

    def _refresh_statistics(self):
        """Le statistiche non sono collegate ai tasti evento."""
        stats = self.stats_manager.compute(self.project.duration_ms)
        summary = self.stats_manager.get_summary_dict(stats)
        lines = []
        for k, v in summary.items():
            if v is not None:
                lines.append(f"{k}: {v}")
        self.stats_label.setText("\n".join(lines) if lines else "Nessun dato.")

    def _create_clips_from_events(self):
        if not self.project.video_path:
            QMessageBox.warning(self, "Attenzione", "Carica prima un video.")
            return
        if not self.clip_manager.is_available():
            QMessageBox.warning(
                self, "FFmpeg",
                "FFmpeg non trovato. Installa FFmpeg e aggiungilo al PATH per creare clip."
            )
            return
        events = self.event_manager.get_events()
        if not events:
            QMessageBox.warning(self, "Attenzione", "Aggiungi almeno un evento.")
            return
        types = {t.id: t.name for t in self.event_manager.get_event_types()}
        evt_list = [(e.timestamp_ms, types.get(e.event_type_id, "evento")) for e in events]
        pre = self.pre_seconds_spin.value()
        post = self.post_seconds_spin.value()
        paths = self.clip_manager.create_clips_from_events(
            self.project.video_path, evt_list, pre, post
        )
        self.clip_status_label.setText(f"Creati {len(paths)} clip in {HIGHLIGHTS_FOLDER}/")
        for p in paths:
            self.project.add_to_playlist(
                PlaylistItem(clip_path=p, start_ms=0, end_ms=0, label=Path(p).stem)
            )

    def _assemble_highlights(self):
        if not self.clip_manager.is_available():
            QMessageBox.warning(self, "FFmpeg", "FFmpeg non trovato.")
            return
        # Usa i clip creati nella cartella Highlights
        import glob
        clips = list(Path(HIGHLIGHTS_FOLDER).glob("clip_*.mp4"))
        if not clips:
            QMessageBox.warning(self, "Attenzione", "Crea prima dei clip.")
            return
        paths = [str(p) for p in sorted(clips)]
        out = self.clip_manager.assemble_highlights(paths, "highlights_assembled")
        if out:
            self.clip_status_label.setText(f"Video salvato: {out}")
            QMessageBox.information(self, "Completato", f"Highlights assemblati in:\n{out}")
        else:
            QMessageBox.warning(self, "Errore", "Impossibile assemblare il video.")

    def _clear_all_for_new_video(self):
        """Ripulisce eventi, disegni e clip quando si carica un nuovo video."""
        self._last_position_ms = 0
        self.event_manager.clear_events()
        self.drawing_overlay.clearDrawings()
        self.project.clear_playlist()
        self.project.drawings.clear()
        self.clips = []
        self.temp_clip_start = None
        self.active_clip_id = None
        self.editing_clip_id = None
        self._editing_clip_backup = None
        self._update_clip_inizio_btn_state()
        self.video_player.setZoomLevel(1.0)
        self._refresh_events_list()
        self._update_timeline_events()
        self._refresh_clips_list()
        self.clip_status_label.setText("")

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Apri Video",
            "",
            "Video (*.mp4 *.avi *.mkv *.mov *.wmv);;Tutti (*.*)"
        )
        if path:
            if self.video_player.load(path):
                self._clear_all_for_new_video()
                self.project.video_path = path
                self.video_player.play()
                self._refresh_statistics()
            else:
                QMessageBox.warning(
                    self, "Errore",
                    "Impossibile aprire il video.\nVerifica che il file esista e che il formato sia supportato (MP4, AVI, ecc.)."
                )

    def closeEvent(self, event):
        self.video_player.stop()
        event.accept()


# Export
def run_app():
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseHighDpiScaling, True)
    apply_palette(app)
    win = MainWindow()
    # Menu
    menu = win.menuBar().addMenu("File")
    open_act = menu.addAction("Apri Video")
    open_act.triggered.connect(win.open_file)
    menu.addAction("Esci", app.quit)
    win.show()
    return app.exec_()
