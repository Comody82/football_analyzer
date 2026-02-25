"""
Video widget basato su OpenCV - compatibile con MP4 e altri formati su Windows.
Alternativa affidabile a QMediaPlayer che spesso ha problemi con i codec.
Riproduzione sincronizzata al tempo reale tramite clock monotono.
"""
import time
import cv2
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap


class OpenCVVideoWidget(QWidget):
    """Widget video che usa OpenCV per la riproduzione (funziona con MP4 su Windows)."""
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: black;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setMinimumSize(320, 240)
        self.label.setStyleSheet("background-color: black; color: gray;")
        self.label.setText("Nessun video caricato")
        layout.addWidget(self.label)

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

    def setZoomLevel(self, level: float):
        """Zoom 1.0 = normale, 2.0 = 2x, max 5.0."""
        self._zoom_level = max(1.0, min(5.0, float(level)))
        if self._zoom_level <= 1.0:
            self._zoom_x0 = self._zoom_y0 = 0

    def setZoomAt(self, level: float, mouse_x: int, mouse_y: int):
        """Zoom centrato sul puntatore del mouse (mx, my = coords label/overlay)."""
        lw = self.label.width()
        lh = self.label.height()
        if lw < 1 or lh < 1:
            self.setZoomLevel(level)
            return
        zoom_new = max(1.0, min(5.0, float(level)))
        zoom_old = self._zoom_level
        x0_old, y0_old = self._zoom_x0, self._zoom_y0
        if zoom_new <= 1.0:
            self._zoom_level = 1.0
            self._zoom_x0 = self._zoom_y0 = 0
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
            return
        x0_new = (x0_old + mouse_x) * (zoom_new / zoom_old) - mouse_x
        y0_new = (y0_old + mouse_y) * (zoom_new / zoom_old) - mouse_y
        zw = max(lw, int(1 if not self._capture else self._capture.get(cv2.CAP_PROP_FRAME_WIDTH)) * zoom_new)
        zh = max(lh, int(1 if not self._capture else self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) * zoom_new)
        self._zoom_level = zoom_new
        self._zoom_x0 = max(0, min(zw - lw, int(x0_new)))
        self._zoom_y0 = max(0, min(zh - lh, int(y0_new)))

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

    def _display_frame(self, frame):
        if frame is None:
            return
        h, w = frame.shape[:2]
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        lw, lh = self.label.width(), self.label.height()
        if lw < 1 or lh < 1:
            return
        if self._zoom_level <= 1.0:
            bytes_per_line = w * 3
            qimg = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)
            scaled = pixmap.scaled(lw, lh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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
        self.label.setPixmap(scaled)

    def play(self):
        if not self._capture:
            return
        if self._frame_by_frame:
            self.stepForward()
            return
        self._playing = True
        self._play_start_time = time.monotonic()
        self._play_start_position_ms = self._position_ms
        self._schedule_next_frame()

    def pause(self):
        self._playing = False
        self._timer.stop()

    def stop(self):
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
        self.label.clear()
        self.label.setText("Nessun video caricato")
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
