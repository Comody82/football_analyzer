"""Widget video con overlay per disegno."""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFrame
from PyQt5.QtCore import Qt
from PyQt5.QtMultimediaWidgets import QVideoWidget


class VideoWithOverlay(QFrame):
    """Container che combina video player e overlay di disegno."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("VideoWithOverlay { background: black; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.video_widget = QVideoWidget()
        layout.addWidget(self.video_widget)
        # Overlay viene aggiunto dal MainWindow dopo, come figlio del video_widget
        # così si ridimensiona insieme
