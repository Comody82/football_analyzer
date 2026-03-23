"""
GameSegmentDialog — rileva primo/secondo tempo e permette il taglio prima dell'upload cloud.

Layout compatto: ogni segmento occupa UNA riga con Inizio + Fine affiancati.
Primo Tempo e Secondo Tempo sono sempre abilitati.
Supplementari visibili solo se rilevati automaticamente.

Limiti upload cloud:
  ≤ 2 segmenti: MAX_NORMAL_MIN = 110 min
  3-4 segmenti: MAX_EXTRA_MIN  = 150 min
"""
from __future__ import annotations

import os
import time as _time
import cv2
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QFrame, QWidget, QSizePolicy, QStackedWidget,
    QSlider, QScrollArea,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QImage, QPixmap

# ── Costanti ──────────────────────────────────────────────────────────────────
MAX_NORMAL_MIN = 110
MAX_EXTRA_MIN  = 150

_DARK_BG = "#0d1520"
_CARD_BG = "#1a2535"
_BORDER  = "#2a3f5f"
_ACCENT  = "#3b82f6"
_GREEN   = "#22c55e"
_MUTED   = "rgba(200,220,255,0.45)"
_TEXT    = "#e8f0fa"

_SEGMENT_LABELS = ["Primo Tempo", "Secondo Tempo", "Primo Tempo Suppl.", "Secondo Tempo Suppl."]


def _fmt(ms: int) -> str:
    s  = max(0, ms) // 1000
    h  = s // 3600
    m  = (s % 3600) // 60
    ss = s % 60
    return f"{h:02d}:{m:02d}:{ss:02d}" if h else f"{m:02d}:{ss:02d}"


def _max_min(n_segments: int) -> int:
    return MAX_EXTRA_MIN if n_segments > 2 else MAX_NORMAL_MIN


# ─────────────────────────────────────────────────────────────────────────────
# Worker detection
# ─────────────────────────────────────────────────────────────────────────────

class SegmentDetectionWorker(QThread):
    progress    = pyqtSignal(int, int)
    finished_ok = pyqtSignal(dict)
    failed      = pyqtSignal(str)

    def __init__(self, video_path: str):
        super().__init__()
        self.video_path = video_path

    def run(self):
        try:
            from analysis.game_segment_detection import detect_game_segments
            result = detect_game_segments(
                self.video_path,
                progress_cb=lambda cur, tot: self.progress.emit(cur, tot),
            )
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Mini video player (OpenCV + QLabel)
# ─────────────────────────────────────────────────────────────────────────────

class MiniVideoPlayer(QWidget):
    positionChanged = pyqtSignal(int)   # ms

    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self._path             = video_path
        self._cap              = None
        self._fps              = 25.0
        self._dur_ms           = 0
        self._pos_ms           = 0
        self._playing          = False
        self._play_start_mono  = 0.0
        self._play_start_ms    = 0
        self._dragging         = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self._build_ui()
        self._open()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._lbl = QLabel()
        self._lbl.setAlignment(Qt.AlignCenter)
        self._lbl.setFixedHeight(220)
        self._lbl.setStyleSheet("background:#000; border-radius:4px;")
        self._lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(self._lbl)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)

        self._btn = QPushButton("▶  Play")
        self._btn.setFixedWidth(80)
        self._btn.setStyleSheet(
            f"QPushButton {{ background:{_CARD_BG}; color:{_TEXT}; border:1px solid {_BORDER}; "
            f"border-radius:4px; padding:4px 8px; font-size:11px; }}"
            f"QPushButton:hover {{ background:#243048; }}"
        )
        self._btn.clicked.connect(self.toggle_play)
        ctrl.addWidget(self._btn)

        self._lbl_time = QLabel("00:00 / 00:00")
        self._lbl_time.setStyleSheet(f"color:{_MUTED}; font-size:11px; min-width:100px;")
        ctrl.addWidget(self._lbl_time)

        self._seek = QSlider(Qt.Horizontal)
        self._seek.setRange(0, 10000)
        self._seek.setValue(0)
        self._seek.setStyleSheet(
            f"QSlider::groove:horizontal {{ background:#0d1a2a; height:5px; border-radius:2px; }}"
            f"QSlider::handle:horizontal {{ background:{_ACCENT}; width:12px; height:12px; "
            f"margin:-4px 0; border-radius:6px; }}"
            f"QSlider::sub-page:horizontal {{ background:{_ACCENT}; border-radius:2px; }}"
        )
        self._seek.sliderPressed.connect(self._on_press)
        self._seek.sliderMoved.connect(self._on_move)
        self._seek.sliderReleased.connect(self._on_release)
        ctrl.addWidget(self._seek)

        lay.addLayout(ctrl)

    def _open(self):
        cap = cv2.VideoCapture(str(self._path))
        if not cap.isOpened():
            return
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        n   = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        self._cap    = cap
        self._fps    = fps
        self._dur_ms = int(n / fps * 1000) if fps > 0 else 0
        self._show_frame_at(0)

    def _show_frame_at(self, ms: int):
        if not self._cap:
            return
        self._cap.set(cv2.CAP_PROP_POS_MSEC, ms)
        ret, frame = self._cap.read()
        if not ret:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        img  = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
        pw   = self._lbl.width() or 600
        ph   = self._lbl.height() or 220
        self._lbl.setPixmap(
            QPixmap.fromImage(img).scaled(pw, ph, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _tick(self):
        if not self._playing:
            return
        elapsed_ms = int((_time.monotonic() - self._play_start_mono) * 1000)
        pos = self._play_start_ms + elapsed_ms
        if pos >= self._dur_ms:
            pos = self._dur_ms
            self._playing = False
            self._btn.setText("▶  Play")
            self._timer.stop()
        self._pos_ms = pos
        self._show_frame_at(pos)
        self._update_ctrl(pos)
        self.positionChanged.emit(pos)

    def _update_ctrl(self, ms: int):
        if self._dur_ms > 0:
            self._seek.setValue(int(ms / self._dur_ms * 10000))
        self._lbl_time.setText(f"{_fmt(ms)} / {_fmt(self._dur_ms)}")

    # ── public ──

    def seek(self, ms: int):
        ms = max(0, min(self._dur_ms, ms))
        self._pos_ms = ms
        was = self._playing
        if was:
            self._timer.stop()
        self._show_frame_at(ms)
        self._update_ctrl(ms)
        self.positionChanged.emit(ms)
        if was:
            self._play_start_mono = _time.monotonic()
            self._play_start_ms   = ms
            self._timer.start(33)

    def position(self) -> int:
        return self._pos_ms

    def duration(self) -> int:
        return self._dur_ms

    def toggle_play(self):
        if self._playing:
            self._playing = False
            self._btn.setText("▶  Play")
            self._timer.stop()
        else:
            self._playing = True
            self._btn.setText("⏸  Pausa")
            self._play_start_mono = _time.monotonic()
            self._play_start_ms   = self._pos_ms
            self._timer.start(33)

    def pause(self):
        if self._playing:
            self.toggle_play()

    def _on_press(self):
        self._dragging = True
        if self._playing:
            self._timer.stop()

    def _on_move(self, val: int):
        if self._dur_ms:
            ms = int(val / 10000 * self._dur_ms)
            self._pos_ms = ms
            self._show_frame_at(ms)
            self._lbl_time.setText(f"{_fmt(ms)} / {_fmt(self._dur_ms)}")
            self.positionChanged.emit(ms)

    def _on_release(self):
        self._dragging = False
        if self._playing:
            self._play_start_mono = _time.monotonic()
            self._play_start_ms   = self._pos_ms
            self._timer.start(33)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._show_frame_at(self._pos_ms)

    def cleanup(self):
        self._timer.stop()
        if self._cap:
            self._cap.release()
            self._cap = None


# ─────────────────────────────────────────────────────────────────────────────
# Activity chart cliccabile
# ─────────────────────────────────────────────────────────────────────────────

class ActivityChart(QWidget):
    seek_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._times_ms:  list[int]   = []
        self._scores:    list[float] = []
        self._segments:  list[dict]  = []
        self._dur_ms:    int         = 1
        self._cursor_ms: int         = 0
        self.setFixedHeight(48)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

    def set_data(self, times_ms, scores, segments, dur_ms):
        self._times_ms = times_ms
        self._scores   = scores
        self._segments = segments
        self._dur_ms   = max(1, dur_ms)
        self.update()

    def set_cursor(self, ms: int):
        self._cursor_ms = ms
        self.update()

    def _x(self, ms: int) -> int:
        return 4 + int((ms / self._dur_ms) * (self.width() - 8))

    def mousePressEvent(self, ev):
        if self._dur_ms <= 1:
            return
        frac = (ev.x() - 4) / max(1, self.width() - 8)
        self.seek_requested.emit(int(max(0.0, min(1.0, frac)) * self._dur_ms))

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H, PAD = self.width(), self.height(), 4
        p.fillRect(0, 0, W, H, QColor("#111d2e"))
        if not self._times_ms:
            p.end(); return
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(34, 197, 94, 55))
        for seg in self._segments:
            x1, x2 = self._x(seg['start_ms']), self._x(seg['end_ms'])
            p.drawRect(x1, PAD, max(1, x2 - x1), H - 2 * PAD)
        p.setPen(QPen(QColor("#3b82f6"), 1.5))
        pts = [(self._x(ms), H - PAD - int(sc * (H - 2 * PAD)))
               for ms, sc in zip(self._times_ms, self._scores)]
        for i in range(len(pts) - 1):
            p.drawLine(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
        try:
            from analysis.game_segment_detection import ACTIVITY_THRESHOLD as TH
        except Exception:
            TH = 0.28
        th_y = H - PAD - int(TH * (H - 2 * PAD))
        pen2 = QPen(QColor(239, 68, 68, 120), 1); pen2.setStyle(Qt.DashLine)
        p.setPen(pen2); p.drawLine(PAD, th_y, W - PAD, th_y)
        if self._cursor_ms > 0:
            p.setPen(QPen(QColor(250, 204, 21, 200), 1.5))
            cx = self._x(self._cursor_ms)
            p.drawLine(cx, 0, cx, H)
        p.end()


# ─────────────────────────────────────────────────────────────────────────────
# AnchorPoint (mezzo bottone: Inizio oppure Fine)
# ─────────────────────────────────────────────────────────────────────────────

class AnchorPoint(QWidget):
    """
    Bottone cliccabile → jump al tempo rilevato.
    Bottone "✓ Imposta" → salva posizione corrente player.
    """
    jump_requested  = pyqtSignal(int)   # ms
    set_requested   = pyqtSignal()      # utente vuole impostare posizione qui

    def __init__(self, label: str, detected_ms: int, parent=None):
        super().__init__(parent)
        self._detected_ms  = detected_ms
        self._confirmed_ms = detected_ms
        self._active       = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._btn_jump = QPushButton(f"📍  {label}   {_fmt(detected_ms)}")
        self._btn_jump.setStyleSheet(self._jump_style(False))
        self._btn_jump.setCursor(Qt.PointingHandCursor)
        self._btn_jump.clicked.connect(self._on_jump)
        self._btn_jump.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(self._btn_jump)

        self._btn_set = QPushButton("✓")
        self._btn_set.setFixedWidth(36)
        self._btn_set.setToolTip("Imposta posizione corrente del video")
        self._btn_set.setStyleSheet(self._set_style(False))
        self._btn_set.setEnabled(False)
        self._btn_set.clicked.connect(self.set_requested.emit)
        lay.addWidget(self._btn_set)

    @staticmethod
    def _jump_style(active: bool) -> str:
        bg  = "#1e3a5f" if active else _CARD_BG
        bc  = _ACCENT   if active else _BORDER
        col = "#93c5fd" if active else _TEXT
        return (
            f"QPushButton {{ background:{bg}; color:{col}; border:1px solid {bc}; "
            f"border-radius:5px; padding:4px 10px; font-size:11px; text-align:left; }}"
            f"QPushButton:hover {{ background:#243048; border-color:{_ACCENT}; }}"
        )

    @staticmethod
    def _set_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background:#166534; color:#86efac; border:1px solid #22c55e; "
                f"border-radius:5px; font-size:13px; font-weight:700; }}"
                f"QPushButton:hover {{ background:#15803d; }}"
            )
        return (
            f"QPushButton {{ background:{_CARD_BG}; color:{_MUTED}; border:1px solid {_BORDER}; "
            f"border-radius:5px; font-size:13px; }}"
            f"QPushButton:disabled {{ color:rgba(200,220,255,0.15); }}"
        )

    def _on_jump(self):
        self.set_active(True)
        self.jump_requested.emit(self._confirmed_ms)

    def set_active(self, active: bool):
        self._active = active
        self._btn_jump.setStyleSheet(self._jump_style(active))
        self._btn_set.setStyleSheet(self._set_style(active))
        self._btn_set.setEnabled(active)

    def set_confirmed_ms(self, ms: int):
        self._confirmed_ms = ms
        parts = self._btn_jump.text().rsplit("   ", 1)
        if len(parts) == 2:
            self._btn_jump.setText(f"{parts[0]}   {_fmt(ms)}")

    def confirmed_ms(self) -> int:
        return self._confirmed_ms

    def set_enabled_anchor(self, enabled: bool):
        self._btn_jump.setEnabled(enabled)
        if not enabled:
            self._btn_jump.setStyleSheet(
                f"QPushButton {{ background:#0d1520; color:rgba(200,220,255,0.2); "
                f"border:1px dashed #1e2d3d; border-radius:5px; padding:4px 10px; "
                f"font-size:11px; text-align:left; }}"
            )
            self._btn_set.setEnabled(False)


# ─────────────────────────────────────────────────────────────────────────────
# SegmentRow — UNA riga = un tempo (Inizio + Fine affiancati)
# ─────────────────────────────────────────────────────────────────────────────

class SegmentRow(QFrame):
    """Una riga orizzontale: [Label]  [📍 Inizio …][✓]   [📍 Fine …][✓]"""
    any_jump      = pyqtSignal(int)           # ms → player seek
    anchor_activated = pyqtSignal(object)     # AnchorPoint attivato

    def __init__(self, label: str, start_ms: int, end_ms: int,
                 enabled: bool = True, parent=None):
        super().__init__(parent)
        self._enabled = enabled
        self.setStyleSheet(
            f"QFrame {{ background:{_CARD_BG}; border:1px solid "
            f"{'#1e2d3d' if not enabled else _BORDER}; border-radius:6px; }}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)

        lbl = QLabel(label)
        lbl.setFixedWidth(105)
        col = "rgba(200,220,255,0.2)" if not enabled else _TEXT
        lbl.setStyleSheet(f"color:{col}; font-size:11px; font-weight:600;")
        lay.addWidget(lbl)

        self.anchor_start = AnchorPoint(f"Inizio {label}", start_ms)
        self.anchor_end   = AnchorPoint(f"Fine {label}",   end_ms)

        for anchor in (self.anchor_start, self.anchor_end):
            anchor.jump_requested.connect(self.any_jump)
            anchor.jump_requested.connect(lambda ms, a=anchor: self.anchor_activated.emit(a))
            anchor.set_requested.connect(lambda a=anchor: self.anchor_activated.emit(a))
            if not enabled:
                anchor.set_enabled_anchor(False)

        lay.addWidget(self.anchor_start, 1)
        lay.addWidget(self.anchor_end,   1)

    def deactivate_all(self):
        self.anchor_start.set_active(False)
        self.anchor_end.set_active(False)

    def get_segment(self) -> dict | None:
        if not self._enabled:
            return None
        s = self.anchor_start.confirmed_ms()
        e = self.anchor_end.confirmed_ms()
        if s == 0 and e == 0:
            return None   # non impostato
        return {'start_ms': s, 'end_ms': e}

    def is_enabled(self) -> bool:
        return self._enabled


# ─────────────────────────────────────────────────────────────────────────────
# Main dialog
# ─────────────────────────────────────────────────────────────────────────────

class GameSegmentDialog(QDialog):
    video_ready = pyqtSignal(str)

    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self._video_path  = video_path
        self._worker      = None
        self._cut_worker  = None
        self._rows:       list[SegmentRow] = []
        self._active_anchor: AnchorPoint | None = None
        self._result:     dict | None = None
        self._duration_ms = 0

        self.setWindowTitle("Rilevamento segmenti partita")
        self.setMinimumWidth(760)
        self.setMaximumHeight(900)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self._apply_style()
        self._build_ui()

    def _apply_style(self):
        self.setStyleSheet(f"""
            QDialog {{ background:{_DARK_BG}; border:1px solid {_BORDER}; border-radius:8px; }}
            QLabel  {{ color:{_TEXT}; background:transparent; }}
            QPushButton {{
                background:{_CARD_BG}; color:{_TEXT}; border:1px solid {_BORDER};
                border-radius:5px; padding:6px 14px; font-size:12px;
            }}
            QPushButton:hover {{ background:#243048; border-color:{_ACCENT}; }}
            QPushButton:disabled {{ color:rgba(200,220,255,0.25); }}
            QProgressBar {{
                background:#0d1a2a; border:1px solid {_BORDER}; border-radius:4px;
                height:10px; color:{_TEXT}; font-size:10px;
            }}
            QProgressBar::chunk {{ background:{_ACCENT}; border-radius:3px; }}
        """)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── banner ─────────────────────────────────────────────────────────
        banner = QFrame()
        banner.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #7c2d12, stop:1 #92400e); border:none; }"
        )
        b = QVBoxLayout(banner)
        b.setContentsMargins(14, 8, 14, 8)
        b.setSpacing(2)
        t1 = QLabel("⚠  L'analisi risulta MOLTO PIÙ PRECISA se il video contiene solo il gioco attivo")
        t1.setStyleSheet("color:#fed7aa; font-weight:700; font-size:12px; background:transparent;")
        t1.setWordWrap(True)
        b.addWidget(t1)
        t2 = QLabel(
            "Rimuovi pre-partita, intervallo e post-partita — ogni frame fuori dal gioco "
            "riduce l'accuratezza del tracking e del clustering squadre."
        )
        t2.setStyleSheet("color:#fdba74; font-size:11px; background:transparent;")
        t2.setWordWrap(True)
        b.addWidget(t2)
        root.addWidget(banner)

        # ── inner ──────────────────────────────────────────────────────────
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(14, 12, 14, 12)
        inner_lay.setSpacing(8)
        root.addWidget(inner)

        title = QLabel("Rilevamento segmenti partita")
        title.setFont(QFont("Arial", 12, QFont.Bold))
        inner_lay.addWidget(title)

        # stack progress | risultati
        self._stack = QStackedWidget()
        inner_lay.addWidget(self._stack)

        # ── pagina 1: progress ─────────────────────────────────────────────
        pg1 = QWidget()
        l1 = QVBoxLayout(pg1)
        l1.setContentsMargins(0, 8, 0, 8)
        l1.setSpacing(8)
        self._prog_label = QLabel("Analisi in corso...")
        self._prog_label.setStyleSheet(f"color:{_MUTED}; font-size:11px;")
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        l1.addWidget(self._prog_label)
        l1.addWidget(self._progress)
        l1.addStretch()
        self._stack.addWidget(pg1)

        # ── pagina 2: risultati ────────────────────────────────────────────
        pg2 = QWidget()
        l2 = QVBoxLayout(pg2)
        l2.setContentsMargins(0, 4, 0, 4)
        l2.setSpacing(6)

        self._player = MiniVideoPlayer(self._video_path)
        self._player.positionChanged.connect(self._on_player_pos)
        l2.addWidget(self._player)

        hint = QLabel(
            "Clicca sulla timeline per navigare  •  Verde = gioco attivo  •  Rosso = soglia"
        )
        hint.setStyleSheet(f"color:{_MUTED}; font-size:10px;")
        l2.addWidget(hint)

        self._chart = ActivityChart()
        self._chart.seek_requested.connect(self._player.seek)
        l2.addWidget(self._chart)

        instr = QLabel(
            "Clicca  📍  per saltare al punto rilevato — regola con la barra — poi clicca  ✓  per impostare."
        )
        instr.setStyleSheet(f"color:{_TEXT}; font-size:11px;")
        l2.addWidget(instr)

        # righe segmenti
        self._rows_container = QVBoxLayout()
        self._rows_container.setSpacing(5)
        l2.addLayout(self._rows_container)

        self._saving_lbl = QLabel("")
        self._saving_lbl.setStyleSheet(f"color:{_GREEN}; font-size:11px;")
        l2.addWidget(self._saving_lbl)

        self._limit_lbl = QLabel("")
        self._limit_lbl.setStyleSheet(
            f"color:#fca5a5; font-size:11px; font-weight:600; "
            f"background:#450a0a; border:1px solid #7f1d1d; border-radius:5px; padding:5px 8px;"
        )
        self._limit_lbl.setWordWrap(True)
        self._limit_lbl.setVisible(False)
        l2.addWidget(self._limit_lbl)

        self._stack.addWidget(pg2)

        # ── bottoni ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()
        self._btn_cut = QPushButton("✂  Taglia e usa questi segmenti")
        self._btn_cut.setEnabled(False)
        self._btn_cut.setStyleSheet(
            f"QPushButton {{ background:{_ACCENT}; color:white; border:none; border-radius:5px; "
            f"padding:7px 16px; font-size:12px; font-weight:600; }}"
            f"QPushButton:hover {{ background:#2563eb; }}"
            f"QPushButton:disabled {{ background:#1e3a6e; color:rgba(255,255,255,0.3); }}"
        )
        self._btn_cut.clicked.connect(self._cut_and_use)
        btn_row.addWidget(self._btn_cut)
        inner_lay.addLayout(btn_row)

        self._cut_progress = QProgressBar()
        self._cut_progress.setRange(0, 0)
        self._cut_progress.setVisible(False)
        inner_lay.addWidget(self._cut_progress)
        self._cut_label = QLabel("")
        self._cut_label.setStyleSheet(f"color:{_MUTED}; font-size:10px;")
        self._cut_label.setVisible(False)
        inner_lay.addWidget(self._cut_label)

    # ── Detection ──────────────────────────────────────────────────────────

    def start_detection(self):
        self._stack.setCurrentIndex(0)
        self._worker = SegmentDetectionWorker(self._video_path)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_detected)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.finished.connect(lambda: setattr(self, '_worker', None))
        self._worker.start()

    def _on_progress(self, cur: int, tot: int):
        self._progress.setValue(int(cur / max(1, tot) * 100))
        self._prog_label.setText(f"Analisi campioni: {cur}/{tot}")

    def _on_failed(self, msg: str):
        self._prog_label.setText(f"Errore: {msg}")
        self._stack.setCurrentIndex(1)
        self._build_rows([])

    def _on_detected(self, result: dict):
        self._result      = result
        segs              = result.get('segments', [])
        self._duration_ms = result.get('duration_ms', self._player.duration())
        self._progress.setValue(100)

        self._chart.set_data(
            result.get('times_ms', []),
            result.get('scores',   []),
            segs,
            self._duration_ms,
        )
        self._build_rows(segs)
        self._update_saving_info()
        self._stack.setCurrentIndex(1)
        self._btn_cut.setEnabled(any(r.get_segment() for r in self._rows))


    # ── Anchor interaction ─────────────────────────────────────────────────

    def _on_anchor_activated(self, anchor: AnchorPoint):
        """Disattiva tutti, attiva l'anchor cliccato o impostato."""
        for row in self._rows:
            row.deactivate_all()
        self._active_anchor = anchor
        anchor.set_active(True)
        # se è un set_requested → imposta subito la posizione corrente
        # distinguiamo: se l'anchor è già attivo è un "set", altrimenti è un "jump"
        # Il signal set_requested arriva sempre come "imposta qui" → catturiamo
        # Dobbiamo capire se veniva da jump o da set:
        # Soluzione: colleghiamo separatamente

    def _on_set_here(self, anchor: AnchorPoint):
        ms = self._player.position()
        anchor.set_confirmed_ms(ms)
        anchor.set_active(False)
        self._active_anchor = None
        self._update_saving_info()
        # aggiorna bottone taglia
        self._btn_cut.setEnabled(any(r.get_segment() for r in self._rows))

    def _on_player_pos(self, ms: int):
        self._chart.set_cursor(ms)

    # ── Limiti ─────────────────────────────────────────────────────────────

    def _active_segments(self) -> list[dict]:
        return [s for r in self._rows for s in [r.get_segment()] if s]

    def _check_limit(self, total_ms: int, n: int) -> tuple[bool, str]:
        lim = _max_min(n)
        if total_ms > lim * 60 * 1000:
            tipo = "supplementari" if n > 2 else "normale"
            return False, (
                f"🚫  {total_ms/60000:.0f} min supera il limite di {lim} min (partita {tipo}). "
                f"Devi tagliare il video per procedere."
            )
        return True, ""

    def _update_saving_info(self):
        segs   = self._active_segments()
        n      = len(segs)
        dur    = self._duration_ms or 1
        if segs:
            tot = sum(s['end_ms'] - s['start_ms'] for s in segs)
            pct = max(0, int((1 - tot / dur) * 100))
            self._saving_lbl.setText(
                f"Risparmio stimato: ~{pct}% — {_fmt(dur - tot)} tagliati su {_fmt(dur)} totali"
            )
        if segs:
            tot = sum(s['end_ms'] - s['start_ms'] for s in segs)
            ok_cut, msg2 = self._check_limit(tot, n)
            if not ok_cut:
                self._btn_cut.setEnabled(False)
                self._limit_lbl.setText(msg2)
                self._limit_lbl.setVisible(True)
            else:
                self._btn_cut.setEnabled(True)
                self._limit_lbl.setVisible(False)

    # ── Actions ────────────────────────────────────────────────────────────

    def _use_full_video(self):
        self._player.pause()
        self.video_ready.emit(self._video_path)
        self.accept()

    def _cut_and_use(self):
        self._update_saving_info()
        segments = self._active_segments()
        if not segments:
            self._use_full_video(); return

        src = Path(self._video_path)
        out = str(src.parent / f"{src.stem}_segments{src.suffix}")
        self._btn_cut.setEnabled(False)
        self._player.pause()
        self._cut_progress.setVisible(True)
        self._cut_label.setText("Taglio video con FFmpeg (nessuna ricodifica)...")
        self._cut_label.setVisible(True)

        class _CutWorker(QThread):
            done = pyqtSignal(bool, str, str)
            def __init__(self, v, s, o):
                super().__init__(); self._v, self._s, self._o = v, s, o
            def run(self):
                from analysis.game_segment_detection import cut_and_merge_segments
                ok, err = cut_and_merge_segments(self._v, self._s, self._o)
                self.done.emit(ok, err if not ok else self._o, self._o)

        self._cut_worker = _CutWorker(self._video_path, segments, out)
        self._cut_worker.done.connect(self._on_cut_done)
        self._cut_worker.finished.connect(self._cut_worker.deleteLater)
        self._cut_worker.finished.connect(lambda: setattr(self, '_cut_worker', None))
        self._cut_worker.start()

    def _on_cut_done(self, ok: bool, msg: str, out_path: str):
        self._cut_progress.setVisible(False)
        self._cut_label.setVisible(False)
        if ok and os.path.isfile(out_path):
            self.video_ready.emit(out_path)
            self.accept()
        else:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Taglio fallito",
                f"FFmpeg errore:\n{msg}\n\nVerrà usato il video completo.")
            self._use_full_video()

    def _cleanup_workers(self):
        for w in (self._worker, self._cut_worker):
            if w and w.isRunning():
                w.requestInterruption()
                w.wait(1000)

    def reject(self):
        if self._result is not None:
            segs = self._result.get('segments', [])
            ok, _ = self._check_limit(self._duration_ms, len(segs))
            if not ok:
                return
        self._player.pause()
        self._cleanup_workers()
        super().reject()   # non emette video_ready → analisi non parte

    def closeEvent(self, ev):
        self._player.cleanup()
        self._cleanup_workers()
        super().closeEvent(ev)

    def _build_rows(self, segs: list):
        """Costruisce le 4 righe con collegamento corretto per set_requested."""
        for i, label in enumerate(_SEGMENT_LABELS):
            seg     = segs[i] if i < len(segs) else None
            start   = seg['start_ms'] if seg else 0
            end     = seg['end_ms']   if seg else 0
            enabled = (i < 2) or (seg is not None)
            row = SegmentRow(label, start, end, enabled=enabled)
            row.any_jump.connect(self._player.seek)
            # jump → attiva anchor (mostra blu + abilita ✓)
            row.anchor_start._btn_jump.clicked.connect(
                lambda _=None, a=row.anchor_start: self._activate_anchor(a)
            )
            row.anchor_end._btn_jump.clicked.connect(
                lambda _=None, a=row.anchor_end: self._activate_anchor(a)
            )
            # ✓ Imposta qui → cattura posizione corrente
            row.anchor_start._btn_set.clicked.connect(
                lambda _=None, a=row.anchor_start: self._on_set_here(a)
            )
            row.anchor_end._btn_set.clicked.connect(
                lambda _=None, a=row.anchor_end: self._on_set_here(a)
            )
            self._rows.append(row)
            self._rows_container.addWidget(row)

    def _activate_anchor(self, anchor: AnchorPoint):
        for row in self._rows:
            row.deactivate_all()
        anchor.set_active(True)
        self._active_anchor = anchor
