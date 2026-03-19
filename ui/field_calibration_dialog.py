"""
Dialog per calibrazione manuale del campo.
L'utente clicca 4 angoli del campo nel video, associati a coordinate FIFA (105x68m).
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFrame, QMessageBox, QScrollArea, QWidget,
)
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont

from analysis.field_calibration import FieldCalibrator
from analysis.config import FIELD_LENGTH_M, FIELD_WIDTH_M, get_calibration_path


class CalibrationFrameWidget(QFrame):
    """
    Widget che mostra un frame video e permette di cliccare per aggiungere punti.
    """
    pointAdded = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("CalibrationFrameWidget { background: #1a1a2e; border-radius: 8px; }")
        self._pixmap = QPixmap()
        self._points = []  # [(x, y), ...]
        self._current_label = None

    def set_frame(self, qimage: QImage):
        """Imposta il frame da mostrare."""
        self._pixmap = QPixmap.fromImage(qimage)
        self.update()

    def set_points(self, points: list):
        """Imposta i punti da visualizzare."""
        self._points = list(points)
        self.update()

    def add_point(self, x: float, y: float):
        """Aggiunge un punto e lo emette."""
        self._points.append((x, y))
        self.pointAdded.emit(x, y)
        self.update()

    def clear_points(self):
        """Rimuove tutti i punti."""
        self._points.clear()
        self.update()

    def get_points(self):
        return list(self._points)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._pixmap.isNull():
            p = QPainter(self)
            p.setPen(QColor(100, 100, 100))
            p.setFont(QFont("Arial", 14))
            p.drawText(self.rect(), Qt.AlignCenter, "Nessun frame caricato.\nApri un video e avvia la calibrazione.")
            return
        p = QPainter(self)
        scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x_off = (self.width() - scaled.width()) // 2
        y_off = (self.height() - scaled.height()) // 2
        p.drawPixmap(x_off, y_off, scaled)
        # Scala i punti dall'immagine originale al widget
        if self._pixmap.width() > 0 and self._pixmap.height() > 0:
            scale_x = scaled.width() / self._pixmap.width()
            scale_y = scaled.height() / self._pixmap.height()
            for i, (px, py) in enumerate(self._points):
                wx = x_off + px * scale_x
                wy = y_off + py * scale_y
                p.setPen(QPen(QColor(0, 255, 0), 3))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(int(wx) - 8, int(wy) - 8, 16, 16)
                p.setPen(QColor(255, 255, 255))
                p.setFont(QFont("Arial", 10, QFont.Bold))
                p.drawText(int(wx) + 12, int(wy) + 4, str(i + 1))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x_off = (self.width() - scaled.width()) // 2
            y_off = (self.height() - scaled.height()) // 2
            mx, my = event.pos().x(), event.pos().y()
            # Converti da coordinate widget a coordinate immagine
            scale_x = self._pixmap.width() / scaled.width() if scaled.width() > 0 else 1
            scale_y = self._pixmap.height() / scaled.height() if scaled.height() > 0 else 1
            px = (mx - x_off) * scale_x
            py = (my - y_off) * scale_y
            if 0 <= px <= self._pixmap.width() and 0 <= py <= self._pixmap.height():
                self.add_point(px, py)
                event.accept()
                return
        super().mousePressEvent(event)


class FieldCalibrationDialog(QDialog):
    """
    Dialog completo per calibrazione campo.
    Step 1: utente clicca 4 angoli (nell'ordine: sx-basso, dx-basso, dx-alto, sx-alto)
    Step 2: calcolo homography e salvataggio
    """
    calibrationSaved = pyqtSignal(str)  # path del file salvato

    LABELS = [
        "1. Angolo basso-sinistra",
        "2. Angolo basso-destro",
        "3. Angolo alto-destro",
        "4. Angolo alto-sinistra",
    ]

    FIELD_COORDS = [
        (0, 0),           # sx-basso
        (FIELD_LENGTH_M, 0),   # dx-basso
        (FIELD_LENGTH_M, FIELD_WIDTH_M),  # dx-alto
        (0, FIELD_WIDTH_M),    # sx-alto
    ]

    def __init__(self, frame_image: QImage, project_dir: str = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Calibrazione campo - Analisi automatica")
        self.setMinimumSize(900, 600)
        self._frame_image = frame_image
        self._project_dir = project_dir
        self._calibrator = FieldCalibrator()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Istruzioni
        instr = QLabel(
            "Clicca sui 4 angoli del campo nell'ordine indicato. "
            "Usa gli angoli della linea di fondo e laterali (dove si vede meglio il campo)."
        )
        instr.setWordWrap(True)
        instr.setStyleSheet("color: #b0b0b0; padding: 8px;")
        layout.addWidget(instr)

        # Label punto corrente
        self._label_current = QLabel(self.LABELS[0])
        self._label_current.setStyleSheet("font-weight: bold; color: #22C55E; font-size: 14px;")
        layout.addWidget(self._label_current)

        # Area frame cliccabile
        self._frame_widget = CalibrationFrameWidget(self)
        self._frame_widget.set_frame(frame_image)
        self._frame_widget.pointAdded.connect(self._on_point_added)
        layout.addWidget(self._frame_widget, 1)

        # Pulsanti
        btn_layout = QHBoxLayout()
        self._btn_undo = QPushButton("Annulla ultimo punto")
        self._btn_undo.clicked.connect(self._undo_point)
        self._btn_undo.setEnabled(False)
        self._btn_clear = QPushButton("Ricomincia")
        self._btn_clear.clicked.connect(self._clear_all)
        self._btn_save = QPushButton("Salva calibrazione")
        self._btn_save.clicked.connect(self._save_calibration)
        self._btn_save.setStyleSheet("background: #22C55E; color: white; padding: 10px 20px;")
        self._btn_save.setEnabled(False)
        btn_layout.addWidget(self._btn_undo)
        btn_layout.addWidget(self._btn_clear)
        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_save)
        layout.addLayout(btn_layout)

    def showEvent(self, event):
        super().showEvent(event)
        self._frame_widget.setFocus(Qt.OtherFocusReason)

    def _on_point_added(self, x: float, y: float):
        pts = self._frame_widget.get_points()
        n = len(pts)
        if n <= 4:
            idx = n - 1
            fx, fy = self.FIELD_COORDS[idx]
            self._calibrator.add_point(x, y, fx, fy)
            if n < 4:
                self._label_current.setText(self.LABELS[n])
            else:
                self._label_current.setText("Tutti e 4 i punti inseriti. Salva la calibrazione.")
                self._btn_save.setEnabled(True)
        self._btn_undo.setEnabled(self._calibrator.get_point_count() > 0)

    def _undo_point(self):
        pts = self._frame_widget.get_points()
        if pts:
            pts.pop()
            self._frame_widget.set_points(pts)
            self._calibrator.clear_points()
            for i, (px, py) in enumerate(pts):
                if i < 4:
                    fx, fy = self.FIELD_COORDS[i]
                    self._calibrator.add_point(px, py, fx, fy)
            n = len(pts)
            self._label_current.setText(self.LABELS[n] if n < 4 else "Tutti e 4 i punti inseriti.")
            self._btn_save.setEnabled(n >= 4)
        self._btn_undo.setEnabled(len(self._frame_widget.get_points()) > 0)

    def _clear_all(self):
        self._frame_widget.clear_points()
        self._calibrator.clear_points()
        self._label_current.setText(self.LABELS[0])
        self._btn_save.setEnabled(False)
        self._btn_undo.setEnabled(False)

    def _save_calibration(self):
        if not self._calibrator.compute_homography():
            QMessageBox.warning(self, "Errore", "Impossibile calcolare la trasformazione. Verifica i punti.")
            return
        path = get_calibration_path(self._project_dir)
        if self._calibrator.save(path):
            self.calibrationSaved.emit(str(path))
            QMessageBox.information(self, "Salvato", f"Calibrazione salvata in:\n{path}")
            self.accept()
        else:
            QMessageBox.warning(self, "Errore", "Impossibile salvare la calibrazione.")
