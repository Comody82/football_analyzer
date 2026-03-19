"""Dialog per creare immagini personalizzate da inserire negli highlights."""
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QSpinBox, QColorDialog, QFrame, QSizePolicy, QComboBox,
    QFileDialog, QWidget, QStackedWidget, QFontComboBox, QMessageBox, QMenu,
    QInputDialog, QFontDialog, QGraphicsOpacityEffect,
)
from PyQt5.QtCore import Qt, QRect, QPoint, QRectF, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import (
    QImage, QPainter, QColor, QFont, QFontMetrics, QPen, QBrush, QPixmap,
    QLinearGradient, QRadialGradient, QConicalGradient, QMouseEvent, QWheelEvent,
    QContextMenuEvent, QPainterPath, QPainterPathStroker,
)


# Dimensioni canvas (Full HD)
CANVAS_W = 1920
CANVAS_H = 1080
HANDLE_SIZE = 10

GRADIENT_LINEARE = "lineare"
GRADIENT_RADIALE = "radiale"
GRADIENT_CONICO = "conico"


def _make_gradient(gtype: str, c1: QColor, c2: QColor, angle_deg: int, w: int, h: int):
    """Crea QBrush con gradiente: Lineare, Radiale o Conico."""
    import math
    cx, cy = w / 2, h / 2
    if gtype == GRADIENT_RADIALE:
        r = max(w, h) * 0.6
        grad = QRadialGradient(cx, cy, r)
    elif gtype == GRADIENT_CONICO:
        grad = QConicalGradient(cx, cy, angle_deg)
    else:
        # Lineare: angolo 0°=alto->basso, 90°=sinistra->destra
        rad = math.radians(angle_deg)
        dx = math.cos(rad) * max(w, h)
        dy = math.sin(rad) * max(w, h)
        grad = QLinearGradient(cx - dx, cy - dy, cx + dx, cy + dy)
    grad.setColorAt(0.0, c1)
    grad.setColorAt(1.0, c2)
    return QBrush(grad)


class _DragHandle(QWidget):
    """Barra superiore per trascinare la finestra."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setCursor(Qt.OpenHandCursor)
        self._drag_start = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 4, 12, 4)
        lbl = QLabel("⋮⋮")
        lbl.setStyleSheet("color: #94a3b8; font-size: 14px;")
        lay.addWidget(lbl)
        lay.addStretch(1)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_start = e.globalPos() - self.window().frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._drag_start is not None and (e.buttons() & Qt.LeftButton):
            self.window().move(e.globalPos() - self._drag_start)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_start = None
            self.setCursor(Qt.OpenHandCursor)


class AddTextDialog(QDialog):
    """Dialog moderna per aggiungere testo, stile editor di testo."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Testo")
        self._final_size = (520, 275)
        self.setFixedSize(*self._final_size)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self._text = ""
        self._font_family = "Arial"
        self._font_size = 48
        self._color = QColor(255, 255, 255)
        self._bold = False
        self._italic = False
        self._underline = False
        self._outline_color = None  # None = nessun contorno
        self._bg_color = None  # None = sfondo trasparente
        self._bg_outline_color = None  # colore contorno sfondo
        self._bg_outline_thickness = 2
        self._outline_thickness = 0   # 0 = auto (formula), 1-30 = px
        self._line_spacing = 100      # % interlinea (100 = normale)
        self._on_change = None  # callback per applicazione istantanea
        self._initial_result = None  # per ripristino su Annulla
        self._build_ui()
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_anim = None

    def showEvent(self, event):
        super().showEvent(event)
        self._opacity_effect.setOpacity(0.0)
        anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        anim.setDuration(700)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim = anim
        anim.finished.connect(lambda: setattr(self, "_fade_anim", None))
        anim.start()

    def _build_ui(self):
        self.setStyleSheet("""
            QDialog { background: #f5f6f8; border-radius: 12px; }
            QPlainTextEdit {
                font-size: 16px; padding: 12px 14px;
                border: 1px solid #d0d5dd; border-radius: 10px;
                background: white; color: #1a1a1a;
                selection-background-color: #3b82f6;
            }
            QPlainTextEdit:focus { border-color: #3b82f6; }
            QPushButton {
                min-width: 36px; min-height: 36px;
                border: none; border-radius: 8px;
                font-size: 14px; font-weight: 600;
            }
            QPushButton#btnOk {
                background: #22c55e; color: white;
            }
            QPushButton#btnOk:hover { background: #16a34a; }
            QPushButton#btnCancel {
                background: #ef4444; color: white;
            }
            QPushButton#btnCancel:hover { background: #dc2626; }
            QFrame#formatBar {
                background: #2d3748; border-radius: 10px;
                padding: 8px;
            }
            QFrame#formatBar QLabel { color: #e2e8f0; }
            QComboBox, QSpinBox, QPushButton#formatBtn {
                background: #4a5568; color: white;
                border: none; border-radius: 6px;
                padding: 6px 10px; min-height: 28px;
            }
            QComboBox:hover, QSpinBox:hover, QPushButton#formatBtn:hover {
                background: #5a6578;
            }
            QWidget#dragHandle {
                background: #e2e8f0; border-radius: 12px 12px 0 0;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        drag = _DragHandle(self)
        drag.setObjectName("dragHandle")
        layout.addWidget(drag)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(0)
        content_layout.setContentsMargins(16, 8, 16, 12)
        top = QHBoxLayout()
        self._edit = QPlainTextEdit()
        self._edit.setPlaceholderText("Inserire Testo")
        self._edit.setMaximumHeight(60)
        self._edit.textChanged.connect(self._apply_instant)
        top.addWidget(self._edit, 1)
        btn_ok = QPushButton("✓")
        btn_ok.setObjectName("btnOk")
        btn_ok.setToolTip("Conferma")
        btn_ok.clicked.connect(self.accept)
        top.addWidget(btn_ok)
        btn_cancel = QPushButton("✕")
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.setToolTip("Annulla")
        btn_cancel.clicked.connect(self._on_cancel)
        top.addWidget(btn_cancel)
        content_layout.addLayout(top)
        content_layout.addSpacing(12)
        bar = QFrame()
        bar.setObjectName("formatBar")
        bar.setMinimumWidth(480)
        bar_layout = QVBoxLayout(bar)
        bar_layout.setSpacing(6)
        bar_layout.setContentsMargins(4, 8, 10, 8)
        grid12 = QGridLayout()
        self._font_combo = QFontComboBox()
        self._font_combo.setCurrentFont(QFont("Arial"))
        self._font_combo.setMinimumWidth(100)
        self._font_combo.currentIndexChanged.connect(self._apply_instant)
        grid12.addWidget(self._font_combo, 0, 0, 1, 4)
        lbl_dim = QLabel("Dimensione:")
        lbl_dim.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        grid12.addWidget(lbl_dim, 0, 4, 1, 2, Qt.AlignRight | Qt.AlignVCenter)
        self._spin_size = QSpinBox()
        self._spin_size.setRange(12, 200)
        self._spin_size.setValue(48)
        self._spin_size.valueChanged.connect(self._apply_instant)
        grid12.addWidget(self._spin_size, 0, 6)
        self._btn_bold = QPushButton("B")
        self._btn_bold.setObjectName("formatBtn")
        self._btn_bold.setCheckable(True)
        self._btn_bold.setToolTip("Grassetto")
        self._btn_bold.setStyleSheet("font-weight: bold;")
        self._btn_bold.toggled.connect(self._apply_instant)
        self._btn_bold.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        grid12.addWidget(self._btn_bold, 1, 0)
        self._btn_italic = QPushButton("I")
        self._btn_italic.setObjectName("formatBtn")
        self._btn_italic.setCheckable(True)
        self._btn_italic.setToolTip("Corsivo")
        self._btn_italic.setStyleSheet("font-style: italic;")
        self._btn_italic.toggled.connect(self._apply_instant)
        self._btn_italic.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        grid12.addWidget(self._btn_italic, 1, 1)
        self._btn_underline = QPushButton("U")
        self._btn_underline.setObjectName("formatBtn")
        self._btn_underline.setCheckable(True)
        self._btn_underline.setToolTip("Sottolineato")
        self._btn_underline.setStyleSheet("text-decoration: underline;")
        self._btn_underline.toggled.connect(self._apply_instant)
        self._btn_underline.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        grid12.addWidget(self._btn_underline, 1, 2)
        self._color_btn = QPushButton("A")
        self._color_btn.setObjectName("formatBtn")
        self._color_btn.setStyleSheet("font-weight: bold;")
        self._color_btn.setToolTip("Colore testo")
        self._color_btn.clicked.connect(lambda: self._pick_color("text"))
        self._color_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        grid12.addWidget(self._color_btn, 1, 3)
        self._outline_btn = QPushButton("◎")
        self._outline_btn.setObjectName("formatBtn")
        self._outline_btn.setToolTip("Colore contorno testo")
        self._outline_btn.clicked.connect(lambda: self._pick_color("outline"))
        self._outline_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        grid12.addWidget(self._outline_btn, 1, 4)
        self._bgtext_btn = QPushButton("▤")
        self._bgtext_btn.setObjectName("formatBtn")
        self._bgtext_btn.setToolTip("Colore sfondo testo")
        self._bgtext_btn.clicked.connect(lambda: self._pick_color("bg"))
        self._bgtext_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        grid12.addWidget(self._bgtext_btn, 1, 5)
        self._bg_outline_btn = QPushButton("▣")
        self._bg_outline_btn.setObjectName("formatBtn")
        self._bg_outline_btn.setToolTip("Colore contorno sfondo")
        self._bg_outline_btn.clicked.connect(lambda: self._pick_color("bg_outline"))
        self._bg_outline_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        grid12.addWidget(self._bg_outline_btn, 1, 6)
        row3_w = QWidget()
        row3_lay = QHBoxLayout(row3_w)
        row3_lay.setContentsMargins(0, 0, 0, 0)
        row3_lay.setSpacing(8)
        g1 = QWidget()
        g1_lay = QHBoxLayout(g1)
        g1_lay.setContentsMargins(0, 0, 0, 0)
        lbl_interlinea = QLabel("Interlinea %")
        lbl_interlinea.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        g1_lay.addWidget(lbl_interlinea)
        self._spin_line_spacing = QSpinBox()
        self._spin_line_spacing.setRange(50, 250)
        self._spin_line_spacing.setValue(100)
        self._spin_line_spacing.setToolTip("Spazio Interlinea (100 = normale)")
        self._spin_line_spacing.valueChanged.connect(self._apply_instant)
        self._spin_line_spacing.setMinimumWidth(52)
        g1_lay.addWidget(self._spin_line_spacing)
        row3_lay.addWidget(g1, 1)
        g2 = QWidget()
        g2_lay = QHBoxLayout(g2)
        g2_lay.setContentsMargins(0, 0, 0, 0)
        lbl_outline = QLabel("Spessore cont.\ntesto:")
        lbl_outline.setAlignment(Qt.AlignCenter)
        lbl_outline.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        g2_lay.addWidget(lbl_outline)
        self._spin_outline = QSpinBox()
        self._spin_outline.setRange(0, 30)
        self._spin_outline.setValue(0)
        self._spin_outline.setSpecialValueText("auto")
        self._spin_outline.setToolTip("Spessore Contorno Testo (0=auto, 1-30 px)")
        self._spin_outline.valueChanged.connect(self._apply_instant)
        self._spin_outline.setMinimumWidth(65)
        g2_lay.addWidget(self._spin_outline)
        row3_lay.addWidget(g2, 1)
        g3 = QWidget()
        g3_lay = QHBoxLayout(g3)
        g3_lay.setContentsMargins(0, 0, 0, 0)
        lbl_bg_outline = QLabel("Spessore cont.\nsfondo:")
        lbl_bg_outline.setAlignment(Qt.AlignCenter)
        lbl_bg_outline.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        g3_lay.addWidget(lbl_bg_outline)
        self._spin_bg_outline = QSpinBox()
        self._spin_bg_outline.setRange(1, 20)
        self._spin_bg_outline.setValue(2)
        self._spin_bg_outline.setToolTip("Spessore Contorno Sfondo (px)")
        self._spin_bg_outline.valueChanged.connect(self._apply_instant)
        self._spin_bg_outline.setMinimumWidth(52)
        g3_lay.addWidget(self._spin_bg_outline)
        row3_lay.addWidget(g3, 1)
        grid12.addWidget(row3_w, 2, 0, 1, 7)
        for c in range(7):
            grid12.setColumnStretch(c, 1)
        bar_layout.addLayout(grid12)
        content_layout.addWidget(bar)
        layout.addWidget(content)

    def set_edit_callbacks(self, on_change, initial_result=None):
        """Per modifica: callback applicazione istantanea e dati iniziali per Annulla."""
        self._on_change = on_change
        self._initial_result = initial_result

    def _apply_instant(self):
        """Applica le modifiche istantaneamente al canvas (se in modalità modifica)."""
        if self._on_change:
            r = self.get_result()
            if r[0]:  # solo se c'è testo
                self._on_change(r)

    def _on_cancel(self):
        """Annulla: ripristina stato iniziale e chiude."""
        if self._initial_result is not None and self._on_change:
            self._on_change(self._initial_result)
        self.reject()

    def _pick_color(self, which: str):
        if which == "text":
            c = QColorDialog.getColor(self._color, self, "Colore testo")
            if c.isValid():
                self._color = c
                txt = "white" if c.lightness() < 128 else "#333"
                self._color_btn.setStyleSheet(
                    f"font-weight: bold; background: rgb({c.red()},{c.green()},{c.blue()}); color: {txt};"
                )
                self._apply_instant()
        elif which == "outline":
            c = QColorDialog.getColor(self._outline_color or QColor(0, 0, 0), self, "Colore contorno testo")
            if c.isValid():
                self._outline_color = c
                txt = "white" if c.lightness() < 128 else "#333"
                self._outline_btn.setStyleSheet(
                    f"background: rgb({c.red()},{c.green()},{c.blue()}); color: {txt};"
                )
                self._apply_instant()
        elif which == "bg":
            c = QColorDialog.getColor(self._bg_color or QColor(50, 50, 50), self, "Colore sfondo testo")
            if c.isValid():
                self._bg_color = c
                txt = "white" if c.lightness() < 128 else "#333"
                self._bgtext_btn.setStyleSheet(
                    f"background: rgb({c.red()},{c.green()},{c.blue()}); color: {txt};"
                )
                self._apply_instant()
        elif which == "bg_outline":
            c = QColorDialog.getColor(self._bg_outline_color or QColor(100, 100, 100), self, "Colore contorno sfondo")
            if c.isValid():
                self._bg_outline_color = c
                txt = "white" if c.lightness() < 128 else "#333"
                self._bg_outline_btn.setStyleSheet(
                    f"background: rgb({c.red()},{c.green()},{c.blue()}); color: {txt};"
                )
                self._apply_instant()

    def set_initial_data(self, t: dict):
        """Pre-compila il dialog per modificare un testo esistente."""
        self._edit.blockSignals(True)
        self._edit.setPlainText(t.get("text", ""))
        self._edit.blockSignals(False)
        font = QFont(t.get("font_family", "Arial"), t.get("font_size", 48))
        font.setBold(t.get("bold", False))
        font.setItalic(t.get("italic", False))
        self._font_combo.blockSignals(True)
        self._font_combo.setCurrentFont(font)
        self._font_combo.blockSignals(False)
        self._spin_size.blockSignals(True)
        self._spin_size.setValue(t.get("font_size", 48))
        self._spin_size.blockSignals(False)
        c = t.get("color", QColor(255, 255, 255))
        self._color = c if hasattr(c, "red") else QColor(255, 255, 255)
        txt = "white" if self._color.lightness() < 128 else "#333"
        self._color_btn.setStyleSheet(
            f"font-weight: bold; background: rgb({self._color.red()},{self._color.green()},{self._color.blue()}); color: {txt};"
        )
        self._btn_bold.blockSignals(True)
        self._btn_italic.blockSignals(True)
        self._btn_underline.blockSignals(True)
        self._btn_bold.setChecked(t.get("bold", False))
        self._btn_italic.setChecked(t.get("italic", False))
        self._btn_underline.setChecked(t.get("underline", False))
        self._btn_bold.blockSignals(False)
        self._btn_italic.blockSignals(False)
        self._btn_underline.blockSignals(False)
        oc = t.get("outline_color")
        self._outline_color = oc
        if oc is not None and hasattr(oc, "red"):
            txt = "white" if oc.lightness() < 128 else "#333"
            self._outline_btn.setStyleSheet(
                f"background: rgb({oc.red()},{oc.green()},{oc.blue()}); color: {txt};"
            )
        bc = t.get("bg_color")
        self._bg_color = bc
        if bc is not None and hasattr(bc, "red"):
            txt = "white" if bc.lightness() < 128 else "#333"
            self._bgtext_btn.setStyleSheet(
                f"background: rgb({bc.red()},{bc.green()},{bc.blue()}); color: {txt};"
            )
        boc = t.get("bg_outline_color")
        self._bg_outline_color = boc
        if boc is not None and hasattr(boc, "red"):
            txt = "white" if boc.lightness() < 128 else "#333"
            self._bg_outline_btn.setStyleSheet(
                f"background: rgb({boc.red()},{boc.green()},{boc.blue()}); color: {txt};"
            )
        self._spin_bg_outline.blockSignals(True)
        self._spin_outline.blockSignals(True)
        self._spin_line_spacing.blockSignals(True)
        self._spin_bg_outline.setValue(t.get("bg_outline_thickness", 2))
        self._spin_outline.setValue(t.get("outline_thickness", 0))
        self._spin_line_spacing.setValue(t.get("line_spacing", 100))
        self._spin_bg_outline.blockSignals(False)
        self._spin_outline.blockSignals(False)
        self._spin_line_spacing.blockSignals(False)

    def get_result(self):
        return (
            self._edit.toPlainText().strip().replace("\r\n", "\n").replace("\r", "\n"),
            self._font_combo.currentFont().family(),
            self._spin_size.value(),
            self._color,
            self._btn_bold.isChecked(),
            self._btn_italic.isChecked(),
            self._btn_underline.isChecked(),
            self._outline_color,
            self._bg_color,
            self._bg_outline_color,
            self._spin_bg_outline.value(),
            self._spin_outline.value(),
            self._spin_line_spacing.value(),
        )


class EditableImageCanvas(QWidget):
    """Canvas interattivo per template Personalizzabile: sfondo, testo spostabile, immagini overlay."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background: #1a1a1a; border: 1px solid #444;")
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        # Dati
        self._bg_color = QColor(24, 48, 72)
        self._bg_color2 = QColor(12, 24, 36)
        self._gradient_type = GRADIENT_LINEARE
        self._gradient_angle = 90
        self._bg_image_path = None
        self._overlays = []  # [{path, x, y, w, h}, ...]
        self._texts = []    # [{text, x, y, font_family, font_size, color}, ...]
        # Interazione
        self._selected = None   # ("text", idx) | ("overlay", idx) | None
        self._drag_start = None
        self._resize_handle = None  # "nw","n","ne","e","se","s","sw","w" | None

    def set_background_color(self, c: QColor):
        self._bg_color = c
        self.update()

    def set_background_gradient(self, gtype: str, c1: QColor, c2: QColor, angle: int):
        self._gradient_type = gtype
        self._bg_color = c1
        self._bg_color2 = c2
        self._gradient_angle = angle
        self.update()

    def set_background_image(self, path: str):
        self._bg_image_path = path
        self.update()

    def add_overlay(self, path: str):
        self._overlays.append({"path": path, "x": CANVAS_W // 2 - 100, "y": CANVAS_H // 2 - 100, "w": 200, "h": 200})
        self._selected = ("overlay", len(self._overlays) - 1)
        self.update()

    def add_text(self, text: str, font_family: str, font_size: int, color: QColor,
                 bold=False, italic=False, underline=False, outline_color=None, bg_color=None, bg_outline_color=None,
                 bg_outline_thickness=2, outline_thickness=0, line_spacing=100):
        self._texts.append({
            "text": text, "x": CANVAS_W // 2 - 150, "y": CANVAS_H // 2 - 30,
            "font_family": font_family, "font_size": font_size, "color": color,
            "bold": bold, "italic": italic, "underline": underline,
            "outline_color": outline_color, "bg_color": bg_color, "bg_outline_color": bg_outline_color,
            "bg_outline_thickness": bg_outline_thickness, "outline_thickness": outline_thickness, "line_spacing": line_spacing,
        })
        self._selected = ("text", len(self._texts) - 1)
        self.update()

    def get_data(self):
        return {
            "bg_color": self._bg_color,
            "bg_image": self._bg_image_path,
            "overlays": list(self._overlays),
            "texts": [
                {**t, "color": t["color"]}
                for t in self._texts
            ],
        }

    def _widget_to_canvas(self, wx: int, wy: int) -> tuple:
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return 0, 0
        scale = min(w / CANVAS_W, h / CANVAS_H)
        off_x = (w - CANVAS_W * scale) / 2
        off_y = (h - CANVAS_H * scale) / 2
        cx = int((wx - off_x) / scale)
        cy = int((wy - off_y) / scale)
        return cx, cy

    def _hit_overlay(self, cx: int, cy: int) -> int:
        for i in range(len(self._overlays) - 1, -1, -1):
            o = self._overlays[i]
            r = QRect(o["x"], o["y"], o["w"], o["h"])
            if r.contains(cx, cy):
                return i
        return -1

    def _hit_text(self, cx: int, cy: int) -> int:
        for i in range(len(self._texts) - 1, -1, -1):
            t = self._texts[i]
            font = QFont(t.get("font_family", "Arial"), t.get("font_size", 48))
            font.setBold(t.get("bold", False))
            font.setItalic(t.get("italic", False))
            fm = QFontMetrics(font)
            txt = (t.get("text") or "").replace("\r\n", "\n").replace("\r", "\n")
            lines = txt.split("\n")
            lh_base = fm.height()
            line_spacing = t.get("line_spacing", 100)
            lh = int(lh_base * line_spacing / 100)
            tx, ty = t["x"], t["y"]
            max_w = max(fm.horizontalAdvance(ln) for ln in lines) if lines else 0
            total_h = lh * len(lines) if lines else lh
            r = QRect(tx, ty - fm.ascent(), max_w, total_h)
            if r.contains(cx, cy):
                return i
        return -1

    def _hit_resize_handle(self, cx: int, cy: int) -> tuple:
        if not self._selected or self._selected[0] != "overlay":
            return None
        idx = self._selected[1]
        o = self._overlays[idx]
        x, y, w, h = o["x"], o["y"], o["w"], o["h"]
        hs = HANDLE_SIZE
        handles = {
            "nw": QRect(x - hs//2, y - hs//2, hs, hs),
            "n": QRect(x + w//2 - hs//2, y - hs//2, hs, hs),
            "ne": QRect(x + w - hs//2, y - hs//2, hs, hs),
            "e": QRect(x + w - hs//2, y + h//2 - hs//2, hs, hs),
            "se": QRect(x + w - hs//2, y + h - hs//2, hs, hs),
            "s": QRect(x + w//2 - hs//2, y + h - hs//2, hs, hs),
            "sw": QRect(x - hs//2, y + h - hs//2, hs, hs),
            "w": QRect(x - hs//2, y + h//2 - hs//2, hs, hs),
        }
        for name, r in handles.items():
            if r.contains(cx, cy):
                return name
        return None

    def _update_text_color(self, idx: int, color: QColor):
        if 0 <= idx < len(self._texts):
            self._texts[idx]["color"] = color
            self.update()

    def _update_text_font(self, idx: int, font_family: str):
        if 0 <= idx < len(self._texts):
            self._texts[idx]["font_family"] = font_family
            self.update()

    def _update_text_size(self, idx: int, size: int):
        if 0 <= idx < len(self._texts):
            self._texts[idx]["font_size"] = size
            self.update()

    def _update_text_bold(self, idx: int, v: bool):
        if 0 <= idx < len(self._texts):
            self._texts[idx]["bold"] = v
            self.update()

    def _update_text_italic(self, idx: int, v: bool):
        if 0 <= idx < len(self._texts):
            self._texts[idx]["italic"] = v
            self.update()

    def _update_text_underline(self, idx: int, v: bool):
        if 0 <= idx < len(self._texts):
            self._texts[idx]["underline"] = v
            self.update()

    def _update_text_outline(self, idx: int, c):
        if 0 <= idx < len(self._texts):
            self._texts[idx]["outline_color"] = c
            self.update()

    def _update_text_bg(self, idx: int, c):
        if 0 <= idx < len(self._texts):
            self._texts[idx]["bg_color"] = c
            self.update()

    def _apply_text_from_result(self, idx: int, r: tuple):
        """Applica il risultato del dialog al testo indicato (modifica istantanea)."""
        if 0 <= idx < len(self._texts) and len(r) >= 9:
            self._texts[idx]["text"] = r[0]
            self._texts[idx]["font_family"] = r[1]
            self._texts[idx]["font_size"] = r[2]
            self._texts[idx]["color"] = r[3]
            self._texts[idx]["bold"] = r[4]
            self._texts[idx]["italic"] = r[5]
            self._texts[idx]["underline"] = r[6]
            self._texts[idx]["outline_color"] = r[7]
            self._texts[idx]["bg_color"] = r[8]
            self._texts[idx]["bg_outline_color"] = r[9] if len(r) >= 10 else None
            self._texts[idx]["bg_outline_thickness"] = r[10] if len(r) >= 11 else 2
            self._texts[idx]["outline_thickness"] = r[11] if len(r) >= 12 else 0
            self._texts[idx]["line_spacing"] = r[12] if len(r) >= 13 else 100
            self.update()

    def contextMenuEvent(self, event: QContextMenuEvent):
        pos = event.pos()
        cx, cy = self._widget_to_canvas(pos.x(), pos.y())
        ti = self._hit_text(cx, cy)
        if ti < 0:
            event.ignore()
            return
        self._selected = ("text", ti)
        self.update()
        t = self._texts[ti]
        menu = QMenu(self)
        mod = menu.addAction("Modifica")
        elim = menu.addAction("Elimina")
        action = menu.exec_(event.globalPos())
        if action == mod:
            parent_win = self.window()
            dlg = AddTextDialog(parent_win)
            dlg.set_initial_data(t)
            init = (t.get("text",""), t.get("font_family","Arial"), t.get("font_size",48),
                    t.get("color", QColor(255,255,255)), t.get("bold",False), t.get("italic",False),
                    t.get("underline",False), t.get("outline_color"), t.get("bg_color"), t.get("bg_outline_color"),
                    t.get("bg_outline_thickness", 2), t.get("outline_thickness", 0), t.get("line_spacing", 100))
            dlg.set_edit_callbacks(lambda r: self._apply_text_from_result(ti, r), init)
            dlg.exec_()
        elif action == elim:
            self._texts.pop(ti)
            self._selected = None
            self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() != Qt.LeftButton:
            return
        cx, cy = self._widget_to_canvas(event.x(), event.y())
        handle = self._hit_resize_handle(cx, cy)
        if handle:
            self._resize_handle = handle
            self._drag_start = (cx, cy)
            return
        oi = self._hit_overlay(cx, cy)
        if oi >= 0:
            self._selected = ("overlay", oi)
            self._resize_handle = None
            self._drag_start = (cx, cy)
            self.update()
            return
        ti = self._hit_text(cx, cy)
        if ti >= 0:
            self._selected = ("text", ti)
            self._resize_handle = None
            self._drag_start = (cx, cy)
            self.update()
            return
        self._selected = None
        self._resize_handle = None
        self._drag_start = None
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self._drag_start:
            return
        cx, cy = self._widget_to_canvas(event.x(), event.y())
        dx = cx - self._drag_start[0]
        dy = cy - self._drag_start[1]
        self._drag_start = (cx, cy)
        if self._resize_handle and self._selected and self._selected[0] == "overlay":
            idx = self._selected[1]
            o = self._overlays[idx]
            x, y, w, h = o["x"], o["y"], o["w"], o["h"]
            if "w" in self._resize_handle: x += dx; w -= dx
            if "e" in self._resize_handle: w += dx
            if "n" in self._resize_handle: y += dy; h -= dy
            if "s" in self._resize_handle: h += dy
            if w < 20: w = 20
            if h < 20: h = 20
            o["x"], o["y"], o["w"], o["h"] = x, y, w, h
        elif self._selected:
            t, idx = self._selected
            if t == "overlay":
                self._overlays[idx]["x"] += dx
                self._overlays[idx]["y"] += dy
            elif t == "text":
                self._texts[idx]["x"] += dx
                self._texts[idx]["y"] += dy
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_start = None
            self._resize_handle = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and self._selected:
            t, idx = self._selected
            if t == "overlay" and 0 <= idx < len(self._overlays):
                self._overlays.pop(idx)
                self._selected = None
            elif t == "text" and 0 <= idx < len(self._texts):
                self._texts.pop(idx)
                self._selected = None
            self.update()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        scale = min(w / CANVAS_W, h / CANVAS_H)
        img = self._render_to_image()
        if img.isNull():
            return
        scaled = img.scaled(int(CANVAS_W * scale), int(CANVAS_H * scale), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pw, ph = scaled.width(), scaled.height()
        off_x = (w - pw) // 2
        off_y = (h - ph) // 2
        p = QPainter(self)
        p.drawImage(off_x, off_y, scaled)
        if self._selected:
            t, idx = self._selected
            p.setPen(QPen(QColor(0, 200, 255), 2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            if t == "overlay" and 0 <= idx < len(self._overlays):
                o = self._overlays[idx]
                rx = off_x + int(o["x"] * scale)
                ry = off_y + int(o["y"] * scale)
                rw = max(int(o["w"] * scale), 20)
                rh = max(int(o["h"] * scale), 20)
                p.drawRect(rx, ry, rw, rh)
                hs = max(int(HANDLE_SIZE * scale), 6)
                for dx in [0, 1, 2]:
                    for dy in [0, 1, 2]:
                        if dx == 1 and dy == 1:
                            continue
                        hx = rx + (dx * rw // 2) - hs // 2
                        hy = ry + (dy * rh // 2) - hs // 2
                        p.fillRect(hx, hy, hs, hs, QColor(0, 200, 255))
        p.end()

    def _render_to_image(self) -> QImage:
        img = QImage(CANVAS_W, CANVAS_H, QImage.Format_RGB32)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if self._bg_image_path:
            pix = QPixmap(self._bg_image_path)
            if not pix.isNull():
                p.drawPixmap(0, 0, CANVAS_W, CANVAS_H, pix.scaled(CANVAS_W, CANVAS_H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
            else:
                p.fillRect(0, 0, CANVAS_W, CANVAS_H, QBrush(self._bg_color))
        else:
            brush = _make_gradient(
                self._gradient_type,
                self._bg_color,
                self._bg_color2,
                self._gradient_angle,
                CANVAS_W, CANVAS_H
            )
            p.fillRect(0, 0, CANVAS_W, CANVAS_H, brush)
        for o in self._overlays:
            pix = QPixmap(o["path"])
            if not pix.isNull():
                p.drawPixmap(o["x"], o["y"], o["w"], o["h"], pix.scaled(o["w"], o["h"], Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        for t in self._texts:
            c = t.get("color", QColor(255, 255, 255))
            col = c if hasattr(c, "red") else QColor(c.get("r", 255), c.get("g", 255), c.get("b", 255))
            font = QFont(t.get("font_family", "Arial"), t.get("font_size", 48))
            font.setBold(t.get("bold", False))
            font.setItalic(t.get("italic", False))
            font.setUnderline(t.get("underline", False))
            p.setFont(font)
            x, y = t["x"], t["y"]
            txt = (t["text"] or "").replace("\r\n", "\n").replace("\r", "\n")
            path = QPainterPath()
            lines = txt.split("\n")
            fm = QFontMetrics(font)
            lh_base = fm.height()
            line_spacing = t.get("line_spacing", 100)
            lh = int(lh_base * line_spacing / 100)
            for i, line in enumerate(lines):
                if line:
                    path.addText(x, y + i * lh, font, line)
            br = path.boundingRect()
            bg_col = t.get("bg_color")
            bg_outline = t.get("bg_outline_color")
            fs = t.get("font_size", 48)
            margin = max(6, fs // 6)
            pad = QRectF(br).adjusted(-margin, -margin, margin, margin)
            r = pad.toRect()
            if bg_col is not None and hasattr(bg_col, "red"):
                p.fillRect(r, QBrush(bg_col))
            if bg_outline is not None and hasattr(bg_outline, "red"):
                bw = max(1, t.get("bg_outline_thickness", 2))
                p.setPen(QPen(bg_outline, bw, Qt.SolidLine))
                p.setBrush(Qt.NoBrush)
                p.drawRect(r)
            outline = t.get("outline_color")
            if outline is not None and hasattr(outline, "red"):
                ow = t.get("outline_thickness", 0)
                stroke_w = max(6, fs // 5) if ow <= 0 else max(1, ow)
                stroker = QPainterPathStroker()
                stroker.setWidth(stroke_w)
                stroker.setCapStyle(Qt.RoundCap)
                stroker.setJoinStyle(Qt.RoundJoin)
                outline_path = stroker.createStroke(path)
                p.fillPath(outline_path, QBrush(outline))
            p.fillPath(path, QBrush(col))
        p.end()
        return img

    def render_final(self) -> QImage:
        return self._render_to_image()


class HighlightImageCreatorDialog(QDialog):
    """Dialog per creare immagini: template predefiniti o personalizzabile con canvas interattivo."""

    def __init__(self, parent=None, match_metadata=None):
        super().__init__(parent)
        self._image_path = None
        self._duration_sec = 3
        self._match_metadata = match_metadata or {}
        self._title_text = ""
        self._subtitle_text = ""
        self._imported_image_path = None
        self._gradient_type = GRADIENT_LINEARE
        self._bg_color2 = QColor(12, 24, 36)
        self._gradient_angle = 90
        self._build_ui()
        self._apply_match_metadata()

    TEMPLATE_SIMPLE = "semplice"
    TEMPLATE_COPERTINA = "copertina_match"
    TEMPLATE_PERSONALIZZABILE = "personalizzabile"

    def _build_ui(self):
        self.setWindowTitle("Crea Immagine")
        self.setMinimumSize(560, 480)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        row0 = QHBoxLayout()
        row0.addWidget(QLabel("Template:"))
        self._combo_template = QComboBox()
        self._combo_template.addItem("Copertina Match", self.TEMPLATE_COPERTINA)
        self._combo_template.addItem("Semplice", self.TEMPLATE_SIMPLE)
        self._combo_template.addItem("Personalizzabile", self.TEMPLATE_PERSONALIZZABILE)
        self._combo_template.currentIndexChanged.connect(self._on_template_changed)
        row0.addWidget(self._combo_template, 1)
        layout.addLayout(row0)

        row_btns = QHBoxLayout()
        self._btn_testo = QPushButton("Testo")
        self._btn_testo.clicked.connect(self._open_text_dialog)
        row_btns.addWidget(self._btn_testo)
        self._btn_import_bg = QPushButton("Importa immagine sfondo")
        self._btn_import_bg.clicked.connect(self._import_bg_image)
        row_btns.addWidget(self._btn_import_bg)
        self._btn_overlay = QPushButton("Aggiungi logo/immagine")
        self._btn_overlay.clicked.connect(self._add_overlay_image)
        self._btn_overlay.setToolTip("Aggiungi stemmi o immagini sopra lo sfondo (spostabili e ridimensionabili)")
        row_btns.addWidget(self._btn_overlay)
        row_btns.addStretch(1)
        layout.addLayout(row_btns)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Sfondo:"))
        self._btn_bg = QPushButton("Colore 1")
        self._bg_color = QColor(24, 48, 72)
        self._btn_bg.setStyleSheet(
            f"background-color: rgb({self._bg_color.red()},{self._bg_color.green()},{self._bg_color.blue()});"
            "color: white; padding: 6px 12px; border-radius: 4px;"
        )
        self._btn_bg.clicked.connect(self._pick_background)
        row3.addWidget(self._btn_bg)
        self._combo_gradient = QComboBox()
        self._combo_gradient.addItem("Lineare", GRADIENT_LINEARE)
        self._combo_gradient.addItem("Radiale", GRADIENT_RADIALE)
        self._combo_gradient.addItem("Conico", GRADIENT_CONICO)
        self._combo_gradient.currentIndexChanged.connect(self._on_gradient_changed)
        row3.addWidget(QLabel("Sfumatura:"))
        row3.addWidget(self._combo_gradient)
        self._btn_bg2 = QPushButton("Colore 2")
        self._btn_bg2.setStyleSheet(
            f"background-color: rgb({self._bg_color2.red()},{self._bg_color2.green()},{self._bg_color2.blue()});"
            "color: white; padding: 6px 12px; border-radius: 4px;"
        )
        self._btn_bg2.clicked.connect(self._pick_background2)
        row3.addWidget(self._btn_bg2)
        row3.addWidget(QLabel("Angolo:"))
        self._spin_angle = QSpinBox()
        self._spin_angle.setRange(0, 360)
        self._spin_angle.setValue(90)
        self._spin_angle.valueChanged.connect(self._on_gradient_changed)
        self._spin_angle.setSuffix("°")
        row3.addWidget(self._spin_angle)
        row3.addWidget(QLabel("Colore testo:"))
        self._text_color = QColor(255, 255, 255)
        self._btn_text = QPushButton("Scegli")
        self._btn_text.setStyleSheet(
            "background-color: rgb(255,255,255); color: #333; padding: 6px 12px; border-radius: 4px;"
        )
        self._btn_text.clicked.connect(self._pick_text_color)
        row3.addWidget(QLabel("Durata (sec):"))
        self._spin_duration = QSpinBox()
        self._spin_duration.setRange(1, 60)
        self._spin_duration.setValue(3)
        row3.addWidget(self._spin_duration)
        row3.addStretch(1)
        layout.addLayout(row3)

        self._stack = QStackedWidget()
        self._preview = QLabel()
        self._preview.setMinimumHeight(200)
        self._preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setFrameStyle(QFrame.Box)
        self._preview.setStyleSheet("background: #1a1a1a; border: 1px solid #444;")
        self._stack.addWidget(self._preview)

        self._canvas = EditableImageCanvas(self)
        self._canvas.set_background_color(self._bg_color)
        self._stack.addWidget(self._canvas)

        layout.addWidget(self._stack, 1)

        self._hint_label = QLabel("Personalizzabile: trascina per spostare, tasto destro: Modifica / Elimina, Canc per eliminare")
        self._hint_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._hint_label)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel_btn = QPushButton("Annulla")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Salva e aggiungi")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_and_accept)
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)
        layout.addLayout(btns)

        self._on_template_changed()

    def _on_template_changed(self):
        is_pers = self._current_template() == self.TEMPLATE_PERSONALIZZABILE
        self._stack.setCurrentWidget(self._canvas if is_pers else self._preview)
        self._btn_testo.setEnabled(True)
        self._btn_import_bg.setEnabled(True)
        self._btn_overlay.setVisible(is_pers)
        self._hint_label.setVisible(is_pers)
        if is_pers:
            self._apply_gradient_to_canvas()
            self._canvas.set_background_image(self._imported_image_path)
            self._canvas.update()
        else:
            self._redraw_preview()

    def _current_template(self) -> str:
        return self._combo_template.currentData() or self.TEMPLATE_SIMPLE

    def _apply_match_metadata(self):
        md = self._match_metadata
        team_home = str(md.get("team_home", "") or "").strip()
        team_away = str(md.get("team_away", "") or "").strip()
        sh = md.get("score_home")
        sa = md.get("score_away")
        if team_home or team_away:
            self._title_text = f"{team_home} vs {team_away}" if team_home and team_away else (team_home or team_away)
        if sh is not None and sa is not None:
            self._subtitle_text = f"{int(sh)} - {int(sa)}"

    def _open_text_dialog(self):
        if self._current_template() == self.TEMPLATE_PERSONALIZZABILE:
            dlg = AddTextDialog(self)
            if dlg.exec_() == QDialog.Accepted:
                r = dlg.get_result()
                if r[0]:
                    self._canvas.add_text(r[0], r[1], r[2], r[3],
                        bold=r[4], italic=r[5], underline=r[6],
                        outline_color=r[7], bg_color=r[8], bg_outline_color=r[9] if len(r) >= 10 else None,
                        bg_outline_thickness=r[10] if len(r) >= 11 else 2,
                        outline_thickness=r[11] if len(r) >= 12 else 0,
                        line_spacing=r[12] if len(r) >= 13 else 100)
                    self._canvas.setFocus()
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Aggiungi testo")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Titolo:"))
        edit_text = QLineEdit()
        edit_text.setText(self._title_text)
        edit_text.setPlaceholderText("es. Squadra A vs Squadra B")
        lay.addWidget(edit_text)
        lay.addWidget(QLabel("Sottotitolo (opzionale):"))
        edit_sub = QLineEdit()
        edit_sub.setText(self._subtitle_text)
        edit_sub.setPlaceholderText("es. 2 - 1")
        lay.addWidget(edit_sub)
        btns = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn = QPushButton("Annulla")
        cancel_btn.clicked.connect(dlg.reject)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        lay.addLayout(btns)
        if dlg.exec_() == QDialog.Accepted:
            self._title_text = edit_text.text().strip()
            self._subtitle_text = edit_sub.text().strip()
            self._redraw_preview()

    def _import_bg_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importa immagine sfondo", "",
            "Image Files (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*.*)"
        )
        if path:
            self._imported_image_path = path
            self._canvas.set_background_image(path)
            self._redraw_preview()

    def _add_overlay_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Aggiungi logo/immagine", "",
            "Image Files (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*.*)"
        )
        if path:
            self._canvas.add_overlay(path)
            self._canvas.setFocus()

    def _pick_text_color(self):
        c = QColorDialog.getColor(self._text_color, self, "Colore testo")
        if c.isValid():
            self._text_color = c
            self._btn_text.setStyleSheet(
                f"background-color: rgb({c.red()},{c.green()},{c.blue()});"
                f"color: {'white' if c.lightness() < 128 else '#333'}; padding: 6px 12px; border-radius: 4px;"
            )
            if self._current_template() == self.TEMPLATE_PERSONALIZZABILE and self._canvas._selected and self._canvas._selected[0] == "text":
                self._canvas._update_text_color(self._canvas._selected[1], c)
            else:
                self._redraw_preview()

    def _pick_background(self):
        c = QColorDialog.getColor(self._bg_color, self, "Colore sfondo 1")
        if c.isValid():
            self._bg_color = c
            self._btn_bg.setStyleSheet(
                f"background-color: rgb({c.red()},{c.green()},{c.blue()});"
                "color: white; padding: 6px 12px; border-radius: 4px;"
            )
            self._apply_gradient_to_canvas()
            self._redraw_preview()

    def _pick_background2(self):
        c = QColorDialog.getColor(self._bg_color2, self, "Colore sfondo 2")
        if c.isValid():
            self._bg_color2 = c
            self._btn_bg2.setStyleSheet(
                f"background-color: rgb({c.red()},{c.green()},{c.blue()});"
                "color: white; padding: 6px 12px; border-radius: 4px;"
            )
            self._apply_gradient_to_canvas()
            self._redraw_preview()

    def _on_gradient_changed(self):
        self._gradient_type = self._combo_gradient.currentData() or GRADIENT_LINEARE
        self._gradient_angle = self._spin_angle.value()
        self._apply_gradient_to_canvas()
        self._redraw_preview()

    def _apply_gradient_to_canvas(self):
        self._canvas.set_background_gradient(
            self._combo_gradient.currentData() or GRADIENT_LINEARE,
            self._bg_color,
            self._bg_color2,
            self._spin_angle.value()
        )

    def _render_image(self) -> QImage:
        if self._current_template() == self.TEMPLATE_PERSONALIZZABILE:
            return self._canvas.render_final()
        if self._current_template() == self.TEMPLATE_COPERTINA:
            return self._render_copertina_match()
        return self._render_simple()

    def _render_copertina_match(self) -> QImage:
        img = QImage(CANVAS_W, CANVAS_H, QImage.Format_RGB32)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if self._imported_image_path:
            pix = QPixmap(self._imported_image_path)
            if not pix.isNull():
                p.drawPixmap(0, 0, CANVAS_W, CANVAS_H, pix.scaled(CANVAS_W, CANVAS_H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
            else:
                p.fillRect(0, 0, CANVAS_W, CANVAS_H, QBrush(self._bg_color))
        else:
            brush = _make_gradient(
                self._gradient_type,
                self._bg_color,
                self._bg_color2,
                self._gradient_angle,
                CANVAS_W, CANVAS_H
            )
            p.fillRect(0, 0, CANVAS_W, CANVAS_H, brush)
        overlay = QLinearGradient(0, 0, 0, CANVAS_H)
        overlay.setColorAt(0.0, QColor(0, 0, 0, 0))
        overlay.setColorAt(0.35, QColor(0, 0, 0, 120))
        overlay.setColorAt(0.65, QColor(0, 0, 0, 120))
        overlay.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, CANVAS_W, CANVAS_H, overlay)
        title = (self._title_text or "Squadra Casa vs Squadra Ospiti").strip()
        subtitle = (self._subtitle_text or "2 - 1").strip()
        p.setPen(QPen(self._text_color))
        if title:
            font = QFont()
            font.setPointSize(64)
            font.setBold(True)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
            p.setFont(font)
            p.drawText(100, 380, CANVAS_W - 200, 100, Qt.AlignCenter | Qt.TextWordWrap, title)
        if subtitle:
            font = QFont()
            font.setPointSize(80)
            font.setBold(True)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 8)
            p.setFont(font)
            p.drawText(100, 520, CANVAS_W - 200, 100, Qt.AlignCenter, subtitle)
        p.end()
        return img

    def _render_simple(self) -> QImage:
        img = QImage(CANVAS_W, CANVAS_H, QImage.Format_RGB32)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if self._imported_image_path:
            pix = QPixmap(self._imported_image_path)
            if not pix.isNull():
                p.drawPixmap(0, 0, CANVAS_W, CANVAS_H, pix.scaled(CANVAS_W, CANVAS_H, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
            else:
                p.fillRect(0, 0, CANVAS_W, CANVAS_H, QBrush(self._bg_color))
        else:
            brush = _make_gradient(
                self._gradient_type,
                self._bg_color,
                self._bg_color2,
                self._gradient_angle,
                CANVAS_W, CANVAS_H
            )
            p.fillRect(0, 0, CANVAS_W, CANVAS_H, brush)
        title = (self._title_text or "Titolo").strip()
        subtitle = (self._subtitle_text or "").strip()
        p.setPen(QPen(self._text_color))
        if title:
            font = QFont()
            font.setPointSize(72)
            font.setBold(True)
            p.setFont(font)
            p.drawText(80, 400, CANVAS_W - 160, 120, Qt.AlignCenter | Qt.TextWordWrap, title)
        if subtitle:
            font = QFont()
            font.setPointSize(48)
            p.setFont(font)
            p.drawText(80, 520, CANVAS_W - 160, 80, Qt.AlignCenter, subtitle)
        p.end()
        return img

    def _redraw_preview(self):
        if self._current_template() == self.TEMPLATE_PERSONALIZZABILE:
            self._canvas.update()
            return
        img = self._render_image()
        pw = min(640, self._preview.width() or 480)
        ph = int(pw * CANVAS_H / CANVAS_W)
        scaled = img.scaled(pw, ph, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._preview.setPixmap(QPixmap.fromImage(scaled))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._redraw_preview()

    def _save_and_accept(self):
        img = self._render_image()
        highlights_dir = Path(__file__).resolve().parent.parent / "Highlights"
        highlights_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = highlights_dir / f"creata_{ts}.png"
        if img.save(str(out_path)):
            self._image_path = str(out_path)
            self._duration_sec = self._spin_duration.value()
            self.accept()
        else:
            QMessageBox.warning(self, "Errore", "Impossibile salvare l'immagine.")
