"""
Video widget basato su OpenCV - compatibile con MP4 e altri formati su Windows.
Alternativa affidabile a QMediaPlayer che spesso ha problemi con i codec.
Riproduzione sincronizzata al tempo reale tramite clock monotono.
Usa DrawingOverlay (QGraphicsView) per video + disegni in scena unificata.
"""
import os
import time
import cv2
from PyQt5.QtWidgets import QWidget, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap

from .drawing_overlay import DrawingOverlay


class OpenCVVideoWidget(QWidget):
    """Widget video che usa OpenCV per la riproduzione (funziona con MP4 su Windows)."""
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    playbackStateChanged = pyqtSignal(bool)  # True=playing, False=paused
    zoomLevelChanged = pyqtSignal(float)
    zoomZoneFactorChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: black;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._graphics_view = DrawingOverlay(self)
        self._graphics_view.setMinimumSize(320, 240)
        self._graphics_view.setStyleSheet("background-color: black;")
        layout.addWidget(self._graphics_view)
        self.drawing_overlay = self._graphics_view

        self._capture = None
        self._path = None
        self._position_ms = 0
        self._duration_ms = 0
        self._fps = 25
        self._playing = False
        self._playback_rate = 1.0
        self._frame_by_frame = False
        self._zoom_level = 1.0
        self._zoom_x0 = 0
        self._zoom_y0 = 0
        self._play_start_time = 0.0  # time.monotonic() quando inizia play
        self._play_start_position_ms = 0  # posizione video al via
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)  # un tick per volta, intervallo compensato
        self._timer.timeout.connect(self._next_frame)
        self._zoom_zone_factor = 2.0  # fattore zoom nella zona (1.0–5.0)
        self._zoom_zone_pan = (0, 0)  # (pan_x, pan_y) in frame pixels per pan nella zona
        self._ball_tracks = None
        self._player_tracks = None
        self._show_tracking = False
        self._graphics_view.zoomZoneDefined.connect(self._on_zoom_zone_defined)
        self._graphics_view.zoomZoneWheelRequested.connect(self._on_zoom_zone_wheel)
        self._graphics_view.zoomPanDelta.connect(self._on_zoom_pan_delta)

    def load(self, path: str) -> bool:
        """Carica un video dal path. Ritorna True se successo."""
        self.stop()
        path = str(path).replace("\\", "/")
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return False
        self._capture = cap
        self._path = path
        # FPS: OpenCV può restituire 0, calcola fallback da frame count e durata
        raw_fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if raw_fps and raw_fps > 0:
            self._fps = raw_fps
            self._duration_ms = int(frame_count / raw_fps * 1000)
        elif frame_count > 0:
            # FPS sconosciuto: stima da frame count (alcuni codec non espongono FPS)
            self._fps = 25.0  # fallback comune
            self._duration_ms = int(frame_count / self._fps * 1000)
        else:
            self._fps = 25.0
            self._duration_ms = 0
        self._position_ms = 0
        self._zoom_level = 1.0
        self._zoom_x0 = self._zoom_y0 = 0
        self.zoomLevelChanged.emit(1.0)
        if hasattr(self._graphics_view, 'clearZoomZone'):
            self._graphics_view.clearZoomZone()
        self._zoom_zone_pan = (0, 0)
        self.durationChanged.emit(self._duration_ms)
        self.positionChanged.emit(0)
        # Mostra primo frame
        ret, frame = cap.read()
        if ret:
            self._display_frame(frame)
            cap.set(cv2.CAP_PROP_POS_MSEC, 0)
        return True

    def setPlaybackRate(self, rate: float):
        """Imposta velocità (2.0=2x, 1.0=1x, 0.5=0.5x). rate=0 per frame-by-frame."""
        self._frame_by_frame = (rate == 0)
        self._playback_rate = rate if rate > 0 else 1.0
        if self._playing and not self._frame_by_frame:
            # Ricalcola punto di partenza per il nuovo rate
            self._play_start_time = time.monotonic()
            self._play_start_position_ms = self._position_ms
            self._timer.stop()
            self._schedule_next_frame()

    def playbackRate(self) -> float:
        return 0.0 if self._frame_by_frame else self._playback_rate

    def zoomLevel(self) -> float:
        """Livello zoom corrente (1.0–5.0)."""
        return self._zoom_level

    def setZoomLevel(self, level: float):
        """Zoom 1.0 = normale, 2.0 = 2x, max 5.0."""
        self._zoom_level = max(1.0, min(5.0, float(level)))
        if self._zoom_level <= 1.0:
            self._zoom_x0 = self._zoom_y0 = 0
        self.zoomLevelChanged.emit(self._zoom_level)

    def setZoomAt(self, level: float, mouse_x: int, mouse_y: int):
        """Zoom centrato sul puntatore del mouse (mx, my = coords viewport)."""
        lw = self._graphics_view.viewport().width()
        lh = self._graphics_view.viewport().height()
        if lw < 1 or lh < 1:
            self.setZoomLevel(level)
            return
        zoom_new = max(1.0, min(5.0, float(level)))
        zoom_old = self._zoom_level
        x0_old, y0_old = self._zoom_x0, self._zoom_y0
        if zoom_new <= 1.0:
            self._zoom_level = 1.0
            self._zoom_x0 = self._zoom_y0 = 0
            self.zoomLevelChanged.emit(1.0)
            return
        if zoom_old <= 1.0:
            w, h = 1, 1
            if self._capture:
                w = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if w < 1 or h < 1:
                self.setZoomLevel(zoom_new)
                return
            scale = min(lw / w, lh / h) or 1
            pad_x = (lw - w * scale) / 2
            pad_y = (lh - h * scale) / 2
            fx = max(0, min(w - 0.01, (mouse_x - pad_x) / scale))
            fy = max(0, min(h - 0.01, (mouse_y - pad_y) / scale))
            zw, zh = max(lw, int(w * zoom_new)), max(lh, int(h * zoom_new))
            self._zoom_level = zoom_new
            self._zoom_x0 = max(0, min(zw - lw, int(fx * zoom_new - mouse_x)))
            self._zoom_y0 = max(0, min(zh - lh, int(fy * zoom_new - mouse_y)))
            self.zoomLevelChanged.emit(zoom_new)
            return
        x0_new = (x0_old + mouse_x) * (zoom_new / zoom_old) - mouse_x
        y0_new = (y0_old + mouse_y) * (zoom_new / zoom_old) - mouse_y
        zw = max(lw, int(1 if not self._capture else self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)) * zoom_new)
        zh = max(lh, int(1 if not self._capture else self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) * zoom_new)
        self._zoom_level = zoom_new
        self._zoom_x0 = max(0, min(zw - lw, int(x0_new)))
        self._zoom_y0 = max(0, min(zh - lh, int(y0_new)))
        self.zoomLevelChanged.emit(zoom_new)

    def stepForward(self):
        """Avanza di un singolo frame (avanzamento manuale)."""
        if not self._capture:
            return
        ret, frame = self._capture.read()
        if ret:
            self._position_ms = int(self._capture.get(cv2.CAP_PROP_POS_MSEC))
            self.positionChanged.emit(self._position_ms)
            self._display_frame(frame)
            if self._playing:
                self._playing = False
                self._timer.stop()

    def _schedule_next_frame(self, next_delay_ms: float = None):
        """Pianifica il prossimo frame. Usa intervallo compensato o predefinito."""
        if not self._playing or not self._capture or self._frame_by_frame:
            return
        if next_delay_ms is None:
            next_delay_ms = 1000.0 / (self._fps * self._playback_rate)
        self._timer.start(max(1, int(next_delay_ms)))

    def _next_frame(self):
        if not self._capture or not self._playing:
            return
        t_start = time.monotonic()
        ret, frame = self._capture.read()
        if not ret:
            self._playing = False
            self._timer.stop()
            return
        self._position_ms = int(self._capture.get(cv2.CAP_PROP_POS_MSEC))
        self.positionChanged.emit(self._position_ms)
        self._display_frame(frame)

        # Sincronizzazione clock: posizione attesa in base al tempo reale
        elapsed_real_sec = time.monotonic() - self._play_start_time
        target_position_ms = self._play_start_position_ms + elapsed_real_sec * self._playback_rate * 1000
        target_position_ms = min(target_position_ms, self._duration_ms)

        # Compensa tempo elaborazione per il prossimo tick
        t_elapsed_ms = (time.monotonic() - t_start) * 1000
        frame_interval_ms = 1000.0 / (self._fps * self._playback_rate)
        next_delay_ms = max(1, frame_interval_ms - t_elapsed_ms)

        # Se siamo in ritardo (>1 frame), accorcia il delay per recuperare
        if self._position_ms < target_position_ms - frame_interval_ms * 0.5:
            next_delay_ms = max(1, next_delay_ms * 0.5)

        if self._playing:
            self._schedule_next_frame(next_delay_ms)

    def getCurrentFrameAsQImage(self):
        """Restituisce il frame corrente come QImage (RGB), o None se nessun video."""
        if not self._capture:
            return None
        pos = self._position_ms
        self._capture.set(cv2.CAP_PROP_POS_MSEC, pos)
        ret, frame = self._capture.read()
        self._capture.set(cv2.CAP_PROP_POS_MSEC, pos)
        if not ret or frame is None:
            return None
        h, w = frame.shape[:2]
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        bytes_per_line = w * 3
        return QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()

    def getZoomZoneFactor(self) -> float:
        """Fattore zoom zona (1.0–5.0)."""
        return self._zoom_zone_factor

    def _on_zoom_pan_delta(self, dx: int, dy: int):
        """Drag per spostare lo zoom (main o zona)."""
        if self._zoom_level > 1.0:
            self._zoom_x0 = max(0, self._zoom_x0 - dx)
            self._zoom_y0 = max(0, self._zoom_y0 - dy)
            if self._capture:
                w = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                zw = max(1, int(w * self._zoom_level))
                zh = max(1, int(h * self._zoom_level))
                vw = self._graphics_view.viewport().width()
                vh = self._graphics_view.viewport().height()
                self._zoom_x0 = min(zw - vw, self._zoom_x0)
                self._zoom_y0 = min(zh - vh, self._zoom_y0)
            self._on_zoom_zone_defined(None)
        elif self._graphics_view.getZoomZoneRect():
            lw = self._graphics_view.viewport().width()
            lh = self._graphics_view.viewport().height()
            h, w = 1, 1
            if self._capture:
                h = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                w = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            scale = min(lw / w, lh / h) if w and h else 1.0
            pan_x = int(dx / scale)
            pan_y = int(dy / scale)
            self._zoom_zone_pan = (
                self._zoom_zone_pan[0] + pan_x,
                self._zoom_zone_pan[1] + pan_y
            )
            self._on_zoom_zone_defined(None)

    def _on_zoom_zone_wheel(self, delta: int):
        """Rotella sulla zona zoom: aumenta/diminuisce il fattore zoom (1.0–5.0)."""
        factor = 1.0 + (delta / 1200.0)
        self._zoom_zone_factor *= factor
        self._zoom_zone_factor = max(1.0, min(5.0, self._zoom_zone_factor))
        self.zoomZoneFactorChanged.emit(self._zoom_zone_factor)
        self._on_zoom_zone_defined(None)  # forza ri-render

    def _on_zoom_zone_defined(self, rect):
        """Chiamato quando l'utente definisce o cancella la zona zoom. Ri-renderizza il frame corrente."""
        if rect is not None:
            self._zoom_zone_pan = (0, 0)
            self.zoomZoneFactorChanged.emit(self._zoom_zone_factor)
        if not self._capture:
            return
        pos_ms = self._position_ms
        self._capture.set(cv2.CAP_PROP_POS_MSEC, pos_ms)
        ret, frame = self._capture.read()
        if ret:
            self._display_frame(frame)
        self._capture.set(cv2.CAP_PROP_POS_MSEC, pos_ms)

    def setTrackingOverlay(self, ball_tracks: dict = None, player_tracks: dict = None):
        """Imposta i dati per overlay (ball_tracks.json, player_tracks.json)."""
        self._ball_tracks = ball_tracks
        self._player_tracks = player_tracks

    def setShowTracking(self, show: bool):
        """Mostra/nascondi overlay tracking sul video."""
        self._show_tracking = bool(show)
        if self._capture:
            pos = self._position_ms
            self._capture.set(cv2.CAP_PROP_POS_MSEC, pos)
            ret, frame = self._capture.read()
            if ret:
                self._display_frame(frame)
            self._capture.set(cv2.CAP_PROP_POS_MSEC, pos)

    def getShowTracking(self) -> bool:
        """Ritorna se l'overlay tracking è visibile."""
        return self._show_tracking

    def _draw_tracking_overlay(self, frame):
        """Disegna ball e player tracking sul frame (BGR)."""
        if not self._show_tracking or (not self._ball_tracks and not self._player_tracks):
            return
        pos_ms = getattr(self, '_position_ms', 0)
        duration_ms = getattr(self, '_duration_ms', 0)
        fh, fw = frame.shape[:2]
        # Indice frame: usa rapporto temporale per allineare display video ↔ analisi
        # (display e analisi possono avere FPS/durata diversi se uno è preprocessato)
        def _get_frame_idx(frames_data):
            n = len(frames_data)
            if n == 0:
                return -1
            if duration_ms and duration_ms > 0:
                ratio = min(1.0, max(0.0, pos_ms / duration_ms))
                return min(n - 1, int(ratio * n))
            fps = 25
            for data in (self._ball_tracks, self._player_tracks):
                if data and data.get("fps"):
                    fps = float(data.get("fps", 25))
                    break
            else:
                fps = getattr(self, '_fps', 25) or 25
            idx = int(round(pos_ms * fps / 1000))
            return max(0, min(n - 1, idx))
        # Scala coordinate: JSON = risoluzione video analisi, frame = risoluzione video mostrato
        def _scale(x, y, w, h, src_w, src_h):
            # Corregge w/h negativi: se negativi, (x,y) è angolo opposto, normalizza a (x_top, y_top, w, h)
            x, y, w, h = float(x), float(y), float(w), float(h)
            if w < 0:
                x += w
                w = abs(w)
            if h < 0:
                y += h
                h = abs(h)
            w, h = max(1, w), max(1, h)
            if not src_w or not src_h or src_w <= 0 or src_h <= 0:
                return int(x), int(y), int(w), int(h)
            sx = fw / src_w
            sy = fh / src_h
            return int(x * sx), int(y * sy), max(1, int(w * sx)), max(1, int(h * sy))

        # Ball: cerchio arancione
        if self._ball_tracks:
            frames_data = self._ball_tracks.get("frames", [])
            src_w = int(self._ball_tracks.get("width", 0) or 0)
            src_h = int(self._ball_tracks.get("height", 0) or 0)
            frame_idx = _get_frame_idx(frames_data)
            if os.environ.get("FOOTBALL_ANALYZER_DEBUG") and frames_data:
                import logging
                logging.debug("tracking ball: pos_ms=%s duration=%s frame_idx=%s len=%s", pos_ms, duration_ms, frame_idx, len(frames_data))
            if 0 <= frame_idx < len(frames_data):
                det = frames_data[frame_idx].get("detection")
                if det:
                    x, y, bw, bh = det.get("x", 0), det.get("y", 0), det.get("w", 0), det.get("h", 0)
                    x, y, bw, bh = float(x), float(y), float(bw), float(bh)
                    x, y, bw, bh = _scale(x, y, bw, bh, src_w, src_h)
                    cx = x + bw // 2
                    cy = y + bh // 2
                    r = max(14, min(bw, bh) // 2 + 2)
                    cv2.circle(frame, (cx, cy), r, (0, 165, 255), 4)  # BGR arancione, più visibile

        # Players: rettangoli con track_id, colore per team
        if self._player_tracks:
            frames_data = self._player_tracks.get("frames", [])
            src_w = int(self._player_tracks.get("width", 0) or 0)
            src_h = int(self._player_tracks.get("height", 0) or 0)
            frame_idx = _get_frame_idx(frames_data)
            if 0 <= frame_idx < len(frames_data):
                for d in frames_data[frame_idx].get("detections", []):
                    x, y, pw, ph = _scale(
                        d.get("x", 0), d.get("y", 0), d.get("w", 0), d.get("h", 0),
                        src_w, src_h
                    )
                    team = d.get("team", -1)
                    role = d.get("role", "player")
                    tid = d.get("track_id", -1)
                    # Colore per ruolo (BGR)
                    if role == "ball":
                        color = (0, 165, 255)    # arancione - palla
                    elif role == "goal":
                        color = (255, 255, 255)  # bianco - porta
                    elif role == "goalie":
                        color = (0, 255, 255)    # ciano - portiere
                    elif role == "referee":
                        color = (180, 180, 180)  # grigio - arbitro
                    elif team == 0:
                        color = (255, 100, 100)  # blu - squadra A
                    elif team == 1:
                        color = (100, 100, 255)  # rosso - squadra B
                    else:
                        color = (0, 200, 255)    # giallo - giocatore non assegnato
                    # Etichetta: abbreviazione ruolo + track_id
                    label_map = {"ball": "BALL", "goal": "GOAL", "goalie": "GK", "referee": "REF"}
                    label = label_map.get(role, str(tid) if tid >= 0 else "?")
                    cv2.rectangle(frame, (x, y), (x + pw, y + ph), color, 3)
                    cv2.putText(frame, label, (x, max(20, y - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    def _display_frame(self, frame):
        if frame is None:
            return
        self._draw_tracking_overlay(frame)
        h, w = frame.shape[:2]
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        lw = self._graphics_view.viewport().width()
        lh = self._graphics_view.viewport().height()
        if lw < 1 or lh < 1:
            lw, lh = w, h
        if self._zoom_level <= 1.0:
            scale = min(lw / w, lh / h) if w and h else 1.0
            pw, ph = max(1, int(w * scale)), max(1, int(h * scale))
            base = cv2.resize(frame_rgb, (pw, ph), interpolation=cv2.INTER_LINEAR)
            zz = self._graphics_view.getZoomZoneRect()
            if zz and pw > 0 and ph > 0:
                zx, zy = int(zz.x()), int(zz.y())
                zw, zh = max(1, int(zz.width())), max(1, int(zz.height()))
                zx = max(0, min(pw - zw, zx))
                zy = max(0, min(ph - zh, zy))
                sx, sy = pw / w, ph / h
                fx1 = max(0, min(w - 1, int(zx / sx)))
                fy1 = max(0, min(h - 1, int(zy / sy)))
                fw = max(1, min(w - fx1, int(zw / sx)))
                fh = max(1, min(h - fy1, int(zh / sy)))
                zf = max(1.0, self._zoom_zone_factor)
                src_cx = fx1 + fw // 2 + self._zoom_zone_pan[0]
                src_cy = fy1 + fh // 2 + self._zoom_zone_pan[1]
                half_w, half_h = max(1, int(fw / (2 * zf))), max(1, int(fh / (2 * zf)))
                x1 = max(0, src_cx - half_w)
                y1 = max(0, src_cy - half_h)
                x2 = min(w, x1 + half_w * 2)
                y2 = min(h, y1 + half_h * 2)
                crop = frame_rgb[y1:y2, x1:x2]
                if crop.size > 0:
                    zoomed = cv2.resize(crop, (zw, zh), interpolation=cv2.INTER_LINEAR)
                    base[zy:zy + zh, zx:zx + zw] = zoomed
                    cv2.rectangle(base, (zx, zy), (zx + zw - 1, zy + zh - 1), (0, 0, 0), 1)
            bytes_per_line = pw * 3
            qimg = QImage(base.data, pw, ph, bytes_per_line, QImage.Format_RGB888)
            scaled = QPixmap.fromImage(qimg.copy())
        else:
            zw, zh = max(lw, int(w * self._zoom_level)), max(lh, int(h * self._zoom_level))
            zoomed = cv2.resize(frame_rgb, (zw, zh), interpolation=cv2.INTER_LINEAR)
            x0 = max(0, min(zw - lw, self._zoom_x0))
            y0 = max(0, min(zh - lh, self._zoom_y0))
            crop_w = min(lw, zw - x0)
            crop_h = min(lh, zh - y0)
            crop = zoomed[y0:y0 + crop_h, x0:x0 + crop_w]
            if crop.size == 0:
                return
            ch, cw = crop.shape[:2]
            bytes_per_line = cw * 3
            qimg = QImage(crop.tobytes(), cw, ch, bytes_per_line, QImage.Format_RGB888)
            scaled = QPixmap.fromImage(qimg.copy())
        self._graphics_view.setVideoPixmap(scaled)

    def play(self):
        if not self._capture:
            return
        if self._frame_by_frame:
            self.stepForward()
            return
        self._playing = True
        self.playbackStateChanged.emit(True)
        self._play_start_time = time.monotonic()
        self._play_start_position_ms = self._position_ms
        self._schedule_next_frame()

    def pause(self):
        self._playing = False
        self.playbackStateChanged.emit(False)
        self._timer.stop()

    def stop(self):
        if self._playing:
            self.playbackStateChanged.emit(False)
        self._playing = False
        self._timer.stop()
        if self._capture:
            self._capture.release()
            self._capture = None
        self._path = None
        self._position_ms = 0
        self._duration_ms = 0
        self._zoom_level = 1.0
        self._zoom_x0 = self._zoom_y0 = 0
        self.zoomLevelChanged.emit(1.0)
        self._graphics_view.clearVideoPixmap()
        if hasattr(self._graphics_view, 'clearZoomZone'):
            self._graphics_view.clearZoomZone()
        self._zoom_zone_pan = (0, 0)
        self.durationChanged.emit(0)
        self.positionChanged.emit(0)

    def setPosition(self, ms: int):
        if not self._capture:
            return
        self._capture.set(cv2.CAP_PROP_POS_MSEC, ms)
        self._position_ms = ms
        self.positionChanged.emit(ms)
        if self._playing:
            self._play_start_time = time.monotonic()
            self._play_start_position_ms = ms
        ret, frame = self._capture.read()
        if ret:
            self._display_frame(frame)
        self._capture.set(cv2.CAP_PROP_POS_MSEC, ms)

    def position(self) -> int:
        return self._position_ms

    def duration(self) -> int:
        return self._duration_ms

    def state(self):
        """Compatibilità con QMediaPlayer.StoppedState/PlayingState/PausedState."""
        class States:
            StoppedState, PlayingState, PausedState = 0, 1, 2
        if not self._capture:
            return States.StoppedState
        return States.PlayingState if self._playing else States.PausedState

    def resizeEvent(self, event):
        super().resizeEvent(event)
