"""
Simple Video Interaction Overlay
Overlay trasparente sopra OpenCVVideoWidget per intercettare eventi mouse
"""
import logging
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QColor


class VideoInteractionOverlay(QWidget):
    """
    Overlay trasparente sopra il video per intercettare eventi mouse.
    
    Signals:
        videoClicked(x, y, timestamp): Emesso al click singolo
        mousePressed(x, y, timestamp): Emesso al mouseDown
        mouseMoved(x, y, timestamp): Emesso al mouseMove (se pressed)
        mouseReleased(x, y, timestamp): Emesso al mouseUp
    """
    
    # Signals
    videoClicked = pyqtSignal(int, int, int)  # x, y, timestamp_ms
    mousePressed = pyqtSignal(int, int, int)
    mouseMoved = pyqtSignal(int, int, int)
    mouseReleased = pyqtSignal(int, int, int)
    
    def __init__(self, video_player, parent=None):
        super().__init__(parent)
        
        self.video_player = video_player
        self.drawing_overlay = None  # Impostato da main_web per inoltro right-click
        self.is_pressing = False
        self.press_start_pos = None
        
        # Configurazione widget
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)  # Intercetta eventi
        self.setAttribute(Qt.WA_TranslucentBackground, True)  # Trasparente
        self.setMouseTracking(False)  # No tracking continuo (risparmia CPU)
        
        logging.debug("[OVERLAY] VideoInteractionOverlay initialized")
    
    def paintEvent(self, event):
        """
        Overlay completamente trasparente.
        Opzionale: Mostra debug border quando sviluppi.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Debug: Mostra bordo rosso semi-trasparente
        # Commentare quando non serve debug
        # painter.setPen(QPen(QColor(255, 0, 0, 100), 2))
        # painter.drawRect(self.rect())
    
    def mousePressEvent(self, event):
        """Intercetta mouse press"""
        if event.button() == Qt.RightButton and self.drawing_overlay:
            logging.debug("[OVERLAY] Right-click ricevuto da video_overlay, inoltro a drawing_overlay")
            # Inoltra right-click al drawing_overlay per menu contestuale su testo/forme
            from PyQt5.QtCore import QPoint
            view_pos = self.mapTo(self.drawing_overlay, event.pos())
            self.drawing_overlay._on_context_menu_requested(view_pos)
            event.accept()
            return
            # Inoltra right-click al drawing_overlay per menu contestuale su testo/forme
            from PyQt5.QtCore import QPoint
            view_pos = self.mapTo(self.drawing_overlay, event.pos())
            self.drawing_overlay._on_context_menu_requested(view_pos)
            event.accept()
            return
        if event.button() == Qt.LeftButton:
            self.is_pressing = True
            self.press_start_pos = event.pos()
            
            x, y = event.x(), event.y()
            timestamp = self._get_current_timestamp()
            
            logging.debug(f"[OVERLAY] Mouse PRESSED at ({x}, {y}) - Timestamp: {timestamp}ms")
            self.mousePressed.emit(x, y, timestamp)
    
    def mouseMoveEvent(self, event):
        """Intercetta mouse move (solo se pressing)"""
        if self.is_pressing:
            x, y = event.x(), event.y()
            timestamp = self._get_current_timestamp()
            
            # Log solo ogni 10px per evitare spam
            if self.press_start_pos:
                dx = abs(x - self.press_start_pos.x())
                dy = abs(y - self.press_start_pos.y())
                if dx > 10 or dy > 10:
                    logging.debug(f"[OVERLAY] Mouse MOVED to ({x}, {y})")
                    self.mouseMoved.emit(x, y, timestamp)
    
    def mouseReleaseEvent(self, event):
        """Intercetta mouse release"""
        if event.button() == Qt.LeftButton:
            x, y = event.x(), event.y()
            timestamp = self._get_current_timestamp()
            
            logging.debug(f"[OVERLAY] Mouse RELEASED at ({x}, {y}) - Timestamp: {timestamp}ms")
            self.mouseReleased.emit(x, y, timestamp)
            
            # Detect click (press + release senza movimento significativo)
            if self.press_start_pos:
                dx = abs(x - self.press_start_pos.x())
                dy = abs(y - self.press_start_pos.y())
                
                if dx < 5 and dy < 5:  # Movimento < 5px = click
                    logging.debug(f"[OVERLAY] VIDEO CLICK detected at ({x}, {y}) - Timestamp: {timestamp}ms")
                    self.videoClicked.emit(x, y, timestamp)
            
            self.is_pressing = False
            self.press_start_pos = None

    def contextMenuEvent(self, event):
        """Inoltra menu contestuale al drawing_overlay."""
        if self.drawing_overlay:
            view_pos = self.mapTo(self.drawing_overlay, event.pos())
            self.drawing_overlay._on_context_menu_requested(view_pos)
            event.accept()
        else:
            event.ignore()

    def _get_current_timestamp(self):
        """Ottiene timestamp corrente dal video player"""
        if self.video_player:
            return self.video_player.position()
        return 0
    
    def get_video_coordinates(self, widget_x, widget_y):
        """
        Converte coordinate widget in coordinate video originali.
        Utile se il video è scalato/letterboxed.
        
        Returns:
            (video_x, video_y) nelle coordinate originali del video
        """
        # TODO: Implementare conversione se il video è scalato
        # Per ora ritorna coordinate widget 1:1
        return widget_x, widget_y
    
    def resizeEvent(self, event):
        """Ridimensiona overlay per coprire esattamente il video"""
        super().resizeEvent(event)
        logging.debug(f"[OVERLAY] Resized to {self.width()}x{self.height()}")
