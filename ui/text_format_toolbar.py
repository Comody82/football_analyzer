"""Barra strumenti formattazione testo - stile foto (font, dimensioni, grassetto, colore, ecc.).
   TextFormatPopup: barra compatta che appare con tasto destro sul testo nel video."""
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QComboBox,
    QSpinBox, QLabel, QFrame, QColorDialog, QMenu, QAction,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QPoint
from PyQt5.QtGui import QFont, QColor

from .theme import BG_CARD, BORDER, TEXT_PRIMARY
from .drawing_overlay import pick_color_pes, DrawableText


_TEXT_TOOLBAR_STYLE = """
    QWidget { background: #0f1419; border-bottom: 1px solid #374151; }
    QComboBox, QSpinBox {
        background: #1a2332;
        color: #e5e7eb;
        border: 1px solid #374151;
        border-radius: 6px;
        padding: 4px 8px;
        min-height: 28px;
    }
    QComboBox:hover, QSpinBox:hover { border-color: #12a88a; }
    QPushButton {
        background: #1a2332;
        color: #e5e7eb;
        border: 1px solid #374151;
        border-radius: 6px;
        min-width: 36px;
        min-height: 28px;
    }
    QPushButton:hover { background: rgba(18, 168, 138, 0.2); border-color: #12a88a; }
    QPushButton:checked { background: rgba(18, 168, 138, 0.35); border-color: #12a88a; }
"""


class TextFormatToolbar(QWidget):
    """Toolbar formattazione testo: font, dimensione, grassetto, corsivo, allineamento,
       colore testo, colore riempimento, opacità, contorno, interlinea."""
    formatChanged = pyqtSignal(object)  # dict con font, color, bold, italic, alignment, ecc.

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_TEXT_TOOLBAR_STYLE)

        # Riga 1: Font, Dimensione, Grassetto, Corsivo, Allineamento
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self._font_combo = QComboBox()
        self._font_combo.setMinimumWidth(140)
        self._font_combo.setEditable(False)
        fonts = ["Arial", "Segoe UI", "Calibri", "Verdana", "Georgia", "Times New Roman",
                 "Courier New", "Impact", "Comic Sans MS"]
        self._font_combo.addItems(fonts)
        self._font_combo.setCurrentText("Arial")
        self._font_combo.currentTextChanged.connect(self._emit_format)
        row1.addWidget(QLabel("Font:"))
        row1.addWidget(self._font_combo)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(8, 200)
        self._size_spin.setValue(22)
        self._size_spin.setMinimumWidth(60)
        self._size_spin.valueChanged.connect(self._emit_format)
        row1.addWidget(QLabel("pt:"))
        row1.addWidget(self._size_spin)

        self._bold_btn = QPushButton("B")
        self._bold_btn.setCheckable(True)
        self._bold_btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self._bold_btn.setFixedSize(36, 28)
        self._bold_btn.toggled.connect(self._emit_format)
        row1.addWidget(self._bold_btn)

        self._italic_btn = QPushButton("I")
        self._italic_btn.setCheckable(True)
        self._italic_btn.setStyleSheet("font-style: italic; font-size: 14px; font-weight: bold;")
        self._italic_btn.setFixedSize(36, 28)
        self._italic_btn.toggled.connect(self._emit_format)
        row1.addWidget(self._italic_btn)

        self._align_combo = QComboBox()
        self._align_combo.setMinimumWidth(100)
        self._align_combo.addItems(["Sinistra", "Centro", "Destra", "Giustificato"])
        self._align_combo.currentIndexChanged.connect(self._emit_format)
        row1.addWidget(QLabel("Allinea:"))
        row1.addWidget(self._align_combo)

        row1.addStretch()

        # Riga 2: Colore testo, Colore sfondo, Opacità, Contorno, Interlinea
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self._text_color_btn = QPushButton("A ▼")
        self._text_color_btn.setMinimumWidth(60)
        self._text_color = QColor(Qt.white)
        self._text_color_btn.clicked.connect(self._pick_text_color)
        self._update_text_color_btn()
        row2.addWidget(QLabel("Colore:"))
        row2.addWidget(self._text_color_btn)

        self._fill_color_btn = QPushButton()
        self._fill_color_btn.setFixedSize(36, 28)
        self._fill_color = QColor(0, 0, 0, 0)
        self._fill_color_btn.clicked.connect(self._pick_fill_color)
        self._update_fill_color_btn()
        row2.addWidget(QLabel("Sfondo:"))
        row2.addWidget(self._fill_color_btn)

        self._opacity_spin = QSpinBox()
        self._opacity_spin.setRange(0, 100)
        self._opacity_spin.setValue(100)
        self._opacity_spin.setSuffix("%")
        self._opacity_spin.setMinimumWidth(70)
        self._opacity_spin.valueChanged.connect(self._emit_format)
        row2.addWidget(QLabel("Opacità:"))
        row2.addWidget(self._opacity_spin)

        self._outline_width_spin = QSpinBox()
        self._outline_width_spin.setRange(0, 20)
        self._outline_width_spin.setValue(0)
        self._outline_width_spin.setMinimumWidth(50)
        self._outline_width_spin.valueChanged.connect(self._emit_format)
        row2.addWidget(QLabel("Spessore:"))
        row2.addWidget(self._outline_width_spin)

        self._outline_color_btn = QPushButton()
        self._outline_color_btn.setFixedSize(36, 28)
        self._outline_color = QColor(255, 255, 255)
        self._outline_color_btn.clicked.connect(self._pick_outline_color)
        self._update_outline_color_btn()
        row2.addWidget(QLabel("Contorno:"))
        row2.addWidget(self._outline_color_btn)

        self._line_spacing_spin = QSpinBox()
        self._line_spacing_spin.setRange(50, 300)
        self._line_spacing_spin.setValue(100)
        self._line_spacing_spin.setSuffix("%")
        self._line_spacing_spin.setMinimumWidth(70)
        self._line_spacing_spin.valueChanged.connect(self._emit_format)
        row2.addWidget(QLabel("Interlinea:"))
        row2.addWidget(self._line_spacing_spin)

        row2.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        layout.addLayout(row1)
        layout.addLayout(row2)

    def _pick_text_color(self):
        c = pick_color_pes(self, self._text_color)
        if c.isValid():
            self._text_color = c
            self._update_text_color_btn()
            self._emit_format()

    def _pick_fill_color(self):
        c = pick_color_pes(self, self._fill_color if self._fill_color.alpha() > 0 else QColor(0, 0, 0))
        if c.isValid():
            self._fill_color = c
            self._update_fill_color_btn()
            self._emit_format()

    def _pick_outline_color(self):
        c = pick_color_pes(self, self._outline_color)
        if c.isValid():
            self._outline_color = c
            self._update_outline_color_btn()
            self._emit_format()

    def _update_text_color_btn(self):
        self._text_color_btn.setStyleSheet(
            f"background: {self._text_color.name()}; color: {self._contrast_color(self._text_color)}; "
            "border: 1px solid #374151; border-radius: 6px; min-width: 60px; min-height: 28px;"
        )

    def _update_fill_color_btn(self):
        if self._fill_color.alpha() == 0:
            self._fill_color_btn.setStyleSheet(
                "background: #1a2332; border: 1px dashed #374151; border-radius: 6px; min-width: 36px; min-height: 28px;"
            )
        else:
            self._fill_color_btn.setStyleSheet(
                f"background: {self._fill_color.name()}; border: 1px solid #374151; border-radius: 6px; min-width: 36px; min-height: 28px;"
            )

    def _update_outline_color_btn(self):
        self._outline_color_btn.setStyleSheet(
            f"background: transparent; border: 2px solid {self._outline_color.name()}; border-radius: 6px; min-width: 36px; min-height: 28px;"
        )

    def _contrast_color(self, bg: QColor) -> str:
        """Ritorna bianco o nero per contrasto su sfondo."""
        lum = (0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()) / 255
        return "#000000" if lum > 0.5 else "#ffffff"

    def _emit_format(self):
        self.formatChanged.emit(self.get_format())

    def get_format(self) -> dict:
        """Ritorna il formato corrente come dizionario."""
        align_map = [Qt.AlignLeft, Qt.AlignHCenter, Qt.AlignRight, Qt.AlignJustify]
        return {
            "font_family": self._font_combo.currentText(),
            "font_size": self._size_spin.value(),
            "bold": self._bold_btn.isChecked(),
            "italic": self._italic_btn.isChecked(),
            "alignment": align_map[self._align_combo.currentIndex()],
            "text_color": QColor(self._text_color),
            "fill_color": QColor(self._fill_color),
            "opacity": self._opacity_spin.value() / 100.0,
            "outline_width": self._outline_width_spin.value(),
            "outline_color": QColor(self._outline_color),
            "line_spacing_percent": self._line_spacing_spin.value(),
        }

    def set_format(self, fmt: dict):
        """Imposta il formato dalla barra (es. da item selezionato)."""
        if "font_family" in fmt:
            idx = self._font_combo.findText(fmt["font_family"])
            if idx >= 0:
                self._font_combo.setCurrentIndex(idx)
        if "font_size" in fmt:
            self._size_spin.setValue(fmt["font_size"])
        if "bold" in fmt:
            self._bold_btn.setChecked(fmt["bold"])
        if "italic" in fmt:
            self._italic_btn.setChecked(fmt["italic"])
        if "alignment" in fmt:
            align = int(fmt["alignment"]) if fmt["alignment"] is not None else Qt.AlignLeft
            idx = 0
            if align & Qt.AlignHCenter:
                idx = 1
            elif align & Qt.AlignRight:
                idx = 2
            elif align & Qt.AlignJustify:
                idx = 3
            self._align_combo.setCurrentIndex(idx)
        if "text_color" in fmt:
            self._text_color = QColor(fmt["text_color"])
            self._update_text_color_btn()
        if "fill_color" in fmt:
            self._fill_color = QColor(fmt["fill_color"])
            self._update_fill_color_btn()
        if "opacity" in fmt:
            self._opacity_spin.setValue(int(fmt["opacity"] * 100))
        if "outline_width" in fmt:
            self._outline_width_spin.setValue(fmt["outline_width"])
        if "outline_color" in fmt:
            self._outline_color = QColor(fmt["outline_color"])
            self._update_outline_color_btn()
        if "line_spacing_percent" in fmt:
            self._line_spacing_spin.setValue(fmt["line_spacing_percent"])


# Stile popup compatto (barra flottante al tasto destro sul testo)
_POPUP_STYLE = """
    QFrame {
        background: rgba(15, 20, 25, 0.96);
        border: 1px solid rgba(55, 65, 81, 0.8);
        border-radius: 8px;
    }
    QComboBox, QSpinBox {
        background: #1a2332;
        color: #e5e7eb;
        border: 1px solid #374151;
        border-radius: 4px;
        padding: 2px 6px;
        min-height: 24px;
        font-size: 11px;
    }
    QComboBox::drop-down, QSpinBox::down-button { width: 18px; }
    QPushButton {
        background: #1a2332;
        color: #e5e7eb;
        border: 1px solid #374151;
        border-radius: 4px;
        min-width: 28px;
        min-height: 24px;
        font-size: 11px;
    }
    QPushButton:hover { background: rgba(18, 168, 138, 0.2); border-color: #12a88a; }
    QPushButton:checked { background: rgba(18, 168, 138, 0.35); }
    QPushButton#btnOk { background: #12a88a; color: #0f1419; }
    QLabel { color: #8b949e; font-size: 10px; }
"""


class TextFormatPopup(QFrame):
    """Popup compatto mostrato con tasto destro sul testo nel video.
       Contiene opzioni formattazione + azioni (Conferma, Duplica, Elimina)."""
    formatApplied = pyqtSignal(object)  # formato applicato
    duplicateRequested = pyqtSignal()
    deleteRequested = pyqtSignal()

    def __init__(self, overlay, target_item: DrawableText, global_pos: QPoint, parent=None):
        super().__init__(parent)
        self._overlay = overlay
        self._target = target_item
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(_POPUP_STYLE)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Riga 1: Font, pt, B, I, Allinea
        r1 = QHBoxLayout()
        r1.setSpacing(4)
        self._font_combo = QComboBox()
        self._font_combo.setMinimumWidth(90)
        fonts = ["Arial", "Segoe UI", "Calibri", "Verdana", "Georgia", "Times New Roman",
                 "Courier New", "Impact"]
        self._font_combo.addItems(fonts)
        self._font_combo.currentTextChanged.connect(self._apply_to_target)
        r1.addWidget(self._font_combo)

        self._size_spin = QSpinBox()
        self._size_spin.setRange(8, 120)
        self._size_spin.setMinimumWidth(45)
        self._size_spin.valueChanged.connect(self._apply_to_target)
        r1.addWidget(self._size_spin)

        self._bold_btn = QPushButton("B")
        self._bold_btn.setCheckable(True)
        self._bold_btn.setFixedSize(28, 24)
        self._bold_btn.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._bold_btn.toggled.connect(self._apply_to_target)
        r1.addWidget(self._bold_btn)

        self._italic_btn = QPushButton("I")
        self._italic_btn.setCheckable(True)
        self._italic_btn.setFixedSize(28, 24)
        self._italic_btn.setStyleSheet("font-style: italic; font-weight: bold;")
        self._italic_btn.toggled.connect(self._apply_to_target)
        r1.addWidget(self._italic_btn)

        self._align_combo = QComboBox()
        self._align_combo.setMinimumWidth(70)
        self._align_combo.addItems(["◀", "●", "▶", "≡"])
        self._align_combo.currentIndexChanged.connect(self._apply_to_target)
        r1.addWidget(self._align_combo)
        layout.addLayout(r1)

        # Riga 2: Colore, Sfondo, Opacità, Contorno
        r2 = QHBoxLayout()
        r2.setSpacing(4)
        self._text_color_btn = QPushButton("A")
        self._text_color_btn.setFixedSize(28, 24)
        self._text_color = QColor(Qt.white)
        self._text_color_btn.clicked.connect(self._pick_text_color)
        self._update_text_color_btn()
        r2.addWidget(self._text_color_btn)

        self._fill_color_btn = QPushButton("▣")
        self._fill_color_btn.setFixedSize(28, 24)
        self._fill_color = QColor(0, 0, 0, 0)
        self._fill_color_btn.clicked.connect(self._pick_fill_color)
        self._update_fill_color_btn()
        r2.addWidget(self._fill_color_btn)

        self._opacity_spin = QSpinBox()
        self._opacity_spin.setRange(0, 100)
        self._opacity_spin.setSuffix("%")
        self._opacity_spin.setMinimumWidth(50)
        self._opacity_spin.valueChanged.connect(self._apply_to_target)
        r2.addWidget(self._opacity_spin)

        self._outline_spin = QSpinBox()
        self._outline_spin.setRange(0, 20)
        self._outline_spin.setMinimumWidth(40)
        self._outline_spin.valueChanged.connect(self._apply_to_target)
        r2.addWidget(self._outline_spin)

        self._outline_color_btn = QPushButton()
        self._outline_color_btn.setFixedSize(28, 24)
        self._outline_color = QColor(255, 255, 255)
        self._outline_color_btn.clicked.connect(self._pick_outline_color)
        self._update_outline_color_btn()
        r2.addWidget(self._outline_color_btn)
        layout.addLayout(r2)

        # Pulsanti azione
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        ok_btn = QPushButton("✓")
        ok_btn.setObjectName("btnOk")
        ok_btn.setFixedSize(32, 26)
        ok_btn.setToolTip("Conferma e chiudi")
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(ok_btn)

        dup_btn = QPushButton("⧉")
        dup_btn.setFixedSize(32, 26)
        dup_btn.setToolTip("Duplica")
        dup_btn.clicked.connect(self._on_duplicate)
        btn_row.addWidget(dup_btn)

        del_btn = QPushButton("🗑")
        del_btn.setFixedSize(32, 26)
        del_btn.setToolTip("Elimina")
        del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.set_format(target_item.get_format())
        self.adjustSize()

        # Posiziona vicino al cursore, senza uscire dallo schermo
        screen_geo = self.screen().availableGeometry() if self.screen() else None
        x, y = global_pos.x(), global_pos.y()
        w, h = self.size().width(), self.size().height()
        if screen_geo:
            if x + w > screen_geo.right():
                x = screen_geo.right() - w
            if y + h > screen_geo.bottom():
                y = screen_geo.bottom() - h
            if x < screen_geo.left():
                x = screen_geo.left()
            if y < screen_geo.top():
                y = screen_geo.top()
        self.move(x, y)

    def set_format(self, fmt: dict):
        """Imposta i controlli dal formato dell'item."""
        if "font_family" in fmt:
            idx = self._font_combo.findText(fmt["font_family"])
            if idx >= 0:
                self._font_combo.setCurrentIndex(idx)
        if "font_size" in fmt:
            self._size_spin.setValue(fmt["font_size"])
        if "bold" in fmt:
            self._bold_btn.setChecked(fmt["bold"])
        if "italic" in fmt:
            self._italic_btn.setChecked(fmt["italic"])
        if "alignment" in fmt:
            align = int(fmt["alignment"]) if fmt["alignment"] is not None else Qt.AlignLeft
            idx = 0
            if align & Qt.AlignHCenter:
                idx = 1
            elif align & Qt.AlignRight:
                idx = 2
            elif align & Qt.AlignJustify:
                idx = 3
            self._align_combo.setCurrentIndex(idx)
        if "text_color" in fmt:
            self._text_color = QColor(fmt["text_color"])
            self._update_text_color_btn()
        if "fill_color" in fmt:
            self._fill_color = QColor(fmt["fill_color"])
            self._update_fill_color_btn()
        if "opacity" in fmt:
            self._opacity_spin.setValue(int(fmt["opacity"] * 100))
        if "outline_width" in fmt:
            self._outline_spin.setValue(fmt["outline_width"])
        if "outline_color" in fmt:
            self._outline_color = QColor(fmt["outline_color"])
            self._update_outline_color_btn()

    def _get_format(self) -> dict:
        align_map = [Qt.AlignLeft, Qt.AlignHCenter, Qt.AlignRight, Qt.AlignJustify]
        return {
            "font_family": self._font_combo.currentText(),
            "font_size": self._size_spin.value(),
            "bold": self._bold_btn.isChecked(),
            "italic": self._italic_btn.isChecked(),
            "alignment": align_map[self._align_combo.currentIndex()],
            "text_color": QColor(self._text_color),
            "fill_color": QColor(self._fill_color),
            "opacity": self._opacity_spin.value() / 100.0,
            "outline_width": self._outline_spin.value(),
            "outline_color": QColor(self._outline_color),
            "line_spacing_percent": 100,
        }

    def _apply_to_target(self):
        if self._target and self._overlay:
            fmt = self._get_format()
            self._target.apply_format(fmt)
            self._target.update()

    def _pick_text_color(self):
        c = pick_color_pes(self, self._text_color)
        if c.isValid():
            self._text_color = c
            self._update_text_color_btn()
            self._apply_to_target()

    def _pick_fill_color(self):
        c = pick_color_pes(self, self._fill_color if self._fill_color.alpha() > 0 else QColor(0, 0, 0))
        if c.isValid():
            self._fill_color = c
            self._update_fill_color_btn()
            self._apply_to_target()

    def _pick_outline_color(self):
        c = pick_color_pes(self, self._outline_color)
        if c.isValid():
            self._outline_color = c
            self._update_outline_color_btn()
            self._apply_to_target()

    def _update_text_color_btn(self):
        lum = (0.299 * self._text_color.red() + 0.587 * self._text_color.green() + 0.114 * self._text_color.blue()) / 255
        fg = "#000000" if lum > 0.5 else "#ffffff"
        self._text_color_btn.setStyleSheet(
            f"background: {self._text_color.name()}; color: {fg}; border: 1px solid #374151; border-radius: 4px;"
        )

    def _update_fill_color_btn(self):
        if self._fill_color.alpha() == 0:
            self._fill_color_btn.setStyleSheet("background: #1a2332; border: 1px dashed #374151; border-radius: 4px;")
        else:
            self._fill_color_btn.setStyleSheet(f"background: {self._fill_color.name()}; border: 1px solid #374151; border-radius: 4px;")

    def _update_outline_color_btn(self):
        self._outline_color_btn.setStyleSheet(
            f"background: transparent; border: 2px solid {self._outline_color.name()}; border-radius: 4px;"
        )

    def _on_ok(self):
        fmt = self._get_format()
        self.formatApplied.emit(fmt)
        self.close()

    def _on_duplicate(self):
        self.duplicateRequested.emit()

    def _on_delete(self):
        self.deleteRequested.emit()
        self.close()
