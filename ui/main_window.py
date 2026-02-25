"""Finestra principale Football Analyzer."""
import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QFileDialog, QListWidget, QListWidgetItem,
    QSlider, QGroupBox, QTabWidget, QScrollArea, QFrame, QGridLayout,
    QSpinBox, QMessageBox, QInputDialog, QColorDialog, QComboBox,
    QDialog, QDialogButtonBox, QFormLayout, QProgressBar, QLineEdit,
    QButtonGroup, QMenu
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QEvent, QSize
from PyQt5.QtGui import QFont, QColor
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


class MainWindow(QMainWindow):
    """Finestra principale dell'applicazione."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Football Analyzer")
        # Dimensione iniziale compatibile con schermi 1920px (evita setGeometry error)
        self.setGeometry(100, 50, 1400, 850)
        self.setStyleSheet(get_stylesheet())

        # Core
        self.event_manager = EventManager()
        # Carica configurazione salvata se esiste, altrimenti usa i predefiniti
        saved = load_saved_event_types()
        if saved:
            self.event_manager.load_event_types(saved)
        else:
            self.event_manager.load_default_types(DEFAULT_EVENT_TYPES)
        self._event_clip_starts = {}  # evt_id -> start_ms per clip personalizzate
        self._clip_edit_event_id = None  # se impostato, modalità creazione clip per questo evento
        self._focus_label_event_id = None  # dopo refresh, metti focus sul campo nome di questo evento
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
        ctrl_row.addWidget(self.speed_btn)
        ctrl_row.addWidget(self.frame_btn)
        ctrl_row.addWidget(self.play_btn)
        ctrl_row.addWidget(self.pause_btn)
        ctrl_row.addWidget(self.time_label, 1)
        center.addLayout(ctrl_row)
        center.addWidget(QLabel("Timeline eventi:"))
        center.addWidget(self.timeline_bar)

        # Strumenti disegno
        draw_group = QGroupBox("✏️ Strumenti disegno")
        draw_layout = QHBoxLayout()
        self.draw_btn_group = QButtonGroup()
        self.draw_btn_group.setExclusive(True)
        self._draw_btns = {}
        for tool, label in [
            (DrawTool.CIRCLE, "⭕ Cerchio"),
            (DrawTool.ARROW, "➡️ Freccia"),
            (DrawTool.LINE, "— Linea"),
            (DrawTool.RECTANGLE, "▢ Rettangolo"),
            (DrawTool.TEXT, "T Testo"),
            (DrawTool.CONE, "🔦 Cono"),
            (DrawTool.ZOOM, "🔍 Zoom"),
            (DrawTool.PENCIL, "✏️ Matita"),
            (DrawTool.CURVED_LINE, "〰️ Linea curva"),
            (DrawTool.CURVED_ARROW, "↷ Freccia curva"),
            (DrawTool.PARABOLA_ARROW, "🏐 Parabola"),
        ]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("draw_tool", tool)
            btn.clicked.connect(lambda c, t=tool: self._set_draw_tool(t) if c else self._set_draw_tool(DrawTool.NONE))
            self.draw_btn_group.addButton(btn)
            self._draw_btns[tool] = btn
            draw_layout.addWidget(btn)
        self._line_widths = [1, 2, 3, 4, 5, 6, 8, 10]
        self._color_btn = QPushButton("🎨 Colore / Spessore")
        self._color_btn.clicked.connect(self._show_color_size_menu)
        draw_layout.addWidget(self._color_btn)
        clear_btn = QPushButton("🗑️ Cancella disegni")
        clear_btn.clicked.connect(self.drawing_overlay.clearDrawings)
        draw_layout.addWidget(clear_btn)
        self._style_widget = QWidget()
        style_row = QHBoxLayout(self._style_widget)
        style_row.setContentsMargins(0, 0, 0, 0)
        style_row.addWidget(QLabel("Stile:"))
        self.style_combo = QComboBox()
        for st in ArrowLineStyle:
            self.style_combo.addItem(st.value, st)
        self.style_combo.setCurrentIndex(0)
        self.style_combo.currentIndexChanged.connect(self._on_arrow_line_style_changed)
        style_row.addWidget(self.style_combo)
        self._style_widget.setVisible(False)
        draw_layout.addWidget(self._style_widget)
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
        splitter.setSizes([280, 1000, 320])

        self.setCentralWidget(splitter)

    def _connect_signals(self):
        self.video_player.positionChanged.connect(self._on_position_changed)
        self.video_player.durationChanged.connect(self._on_duration_changed)
        self.video_player.installEventFilter(self)
        self.drawing_overlay.drawingStarted.connect(self._on_drawing_started)
        self.drawing_overlay.zoomRequested.connect(self._on_zoom_requested)

    def eventFilter(self, obj, event):
        if obj == self.video_player and event.type() == QEvent.Resize:
            w, h = self.video_player.width(), self.video_player.height()
            self.drawing_overlay.setGeometry(0, 0, w, h)
            self.drawing_overlay.setSceneRect(0, 0, w, h)
        return super().eventFilter(obj, event)

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
        self.position_slider.blockSignals(True)
        self.position_slider.setValue(ms)
        self.position_slider.blockSignals(False)
        self.timeline_bar.set_position(ms)
        d = self.video_player.duration()
        self.time_label.setText(
            f"{ms // 60000}:{(ms % 60000) // 1000:02d} / "
            f"{d // 60000}:{(d % 60000) // 1000:02d}"
        )

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

    def _seek_to(self, ms: int):
        self.video_player.setPosition(ms)

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
        # Aggiungi pulsante per ogni tipo
        for i, et in enumerate(self.event_manager.get_event_types()):
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
            inizio_btn = QPushButton("Inizio")
            inizio_btn.setFixedSize(52, 26)
            inizio_btn.setStyleSheet("font-size: 11px; padding: 2px;")
            inizio_btn.setToolTip("Imposta la posizione corrente come inizio clip (attivo solo in modalità creazione)")
            inizio_btn.clicked.connect(lambda checked=False, e=evt: self._on_clip_inizio(e))
            inizio_btn.setEnabled(evt.id == self._clip_edit_event_id)
            top_layout.addWidget(inizio_btn)
            fine_btn = QPushButton("Fine")
            fine_btn.setFixedSize(52, 26)
            fine_btn.setStyleSheet("font-size: 11px; padding: 2px;")
            fine_btn.setToolTip("Imposta la posizione corrente come fine e crea la clip (attivo solo in modalità creazione)")
            fine_btn.clicked.connect(lambda checked=False, e=evt: self._on_clip_fine(e))
            fine_btn.setEnabled(evt.id == self._clip_edit_event_id)
            top_layout.addWidget(fine_btn)
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
        crea_clip_act = menu.addAction("Crea clip (modalità modifica)" if self._clip_edit_event_id != evt.id else "Esci da modalità creazione clip")
        elimina_act = menu.addAction("Elimina")
        action = menu.exec_(self.events_list.mapToGlobal(pos))
        if action == crea_clip_act:
            if self._clip_edit_event_id == evt.id:
                self._clip_edit_event_id = None
                self.statusBar().showMessage("Uscita da modalità creazione clip", 3000)
            else:
                self._clip_edit_event_id = evt.id
                self.statusBar().showMessage("Modalità creazione clip: usa Inizio e Fine per creare la clip", 4000)
            self._refresh_events_list()
        elif action == elimina_act:
            clip_paths = self.project.remove_playlist_items_by_event_id(evt.id)
            for p in clip_paths:
                try:
                    Path(p).unlink()
                except OSError:
                    pass
            self.event_manager.remove_event(evt.id)
            self._refresh_events_list()
            self._update_timeline_events()

    def _on_event_double_click(self, item):
        evt = item.data(Qt.UserRole)
        if evt:
            self._clip_edit_event_id = None
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

    def _on_clip_inizio(self, evt: Event):
        """Imposta la posizione video corrente come inizio della clip per questo evento."""
        if evt.id != self._clip_edit_event_id:
            return
        pos = self.video_player.position()
        self._event_clip_starts[evt.id] = pos
        self.statusBar().showMessage(f"Inizio impostato a {pos // 1000}s. Porta il video alla fine e clicca Fine.", 4000)

    def _on_clip_fine(self, evt: Event):
        """Crea la clip dall'inizio salvato alla posizione corrente."""
        if evt.id != self._clip_edit_event_id:
            return
        if not self.project.video_path:
            QMessageBox.warning(self, "Attenzione", "Carica prima un video.")
            return
        if not self.clip_manager.is_available():
            QMessageBox.warning(self, "FFmpeg", "FFmpeg non trovato. Installa FFmpeg e aggiungilo al PATH.")
            return
        end_ms = self.video_player.position()
        start_ms = self._event_clip_starts.get(evt.id)
        if start_ms is None:
            QMessageBox.warning(
                self, "Attenzione",
                "Clicca prima 'Inizio' alla posizione desiderata, poi 'Fine' alla fine."
            )
            return
        if end_ms <= start_ms:
            QMessageBox.warning(self, "Attenzione", "La fine deve essere dopo l'inizio.")
            return
        types = {t.id: t.name for t in self.event_manager.get_event_types()}
        label = types.get(evt.event_type_id, "evento")
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:20]
        name = f"clip_{safe_label}_{start_ms}_{end_ms}"
        path = self.clip_manager.create_clip_range(
            self.project.video_path, start_ms, end_ms, name
        )
        if path:
            self.project.add_to_playlist(
                PlaylistItem(clip_path=path, start_ms=0, end_ms=0, label=Path(path).stem, event_id=evt.id)
            )
            QMessageBox.information(self, "Clip creata", f"Clip salvata in:\n{path}")
            del self._event_clip_starts[evt.id]
            self._clip_edit_event_id = None
            self._refresh_events_list()
        else:
            QMessageBox.warning(self, "Errore", "Impossibile creare la clip.")

    def _set_draw_tool(self, tool: DrawTool):
        self.drawing_overlay.setTool(tool)
        for t, btn in self._draw_btns.items():
            btn.setChecked(t == tool)
        self._style_widget.setVisible(tool in (DrawTool.ARROW, DrawTool.LINE))
        if tool in (DrawTool.ARROW, DrawTool.LINE):
            self.drawing_overlay.setArrowLineStyle(self.style_combo.currentData())

    def _on_arrow_line_style_changed(self, _index):
        st = self.style_combo.currentData()
        if st is not None:
            self.drawing_overlay.setArrowLineStyle(st)

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
        self.event_manager.clear_events()
        self.drawing_overlay.clearDrawings()
        self.project.clear_playlist()
        self.project.drawings.clear()
        self._event_clip_starts.clear()
        self._clip_edit_event_id = None
        self.video_player.setZoomLevel(1.0)
        self._refresh_events_list()
        self._update_timeline_events()
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
