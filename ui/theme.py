"""Tema e stili per Football Analyzer - Design pulito e moderno."""
from PyQt5.QtGui import QPalette, QColor, QFont
from PyQt5.QtCore import Qt


# Palette scura elegante
BG_DARK = "#0F1419"
BG_CARD = "#1A2332"
BG_HOVER = "#243447"
ACCENT = "#00D9A5"
ACCENT_HOVER = "#00F5B8"
ACCENT_DIM = "#00A87A"
TEXT_PRIMARY = "#F0F6FC"
TEXT_SECONDARY = "#8B949E"
BORDER = "#30363D"
ERROR = "#F85149"
WARNING = "#D29922"

# Font
FONT_FAMILY = "Segoe UI"
FONT_FAMILY_MONO = "Consolas"


def get_stylesheet() -> str:
    return f"""
    QMainWindow, QWidget {{
        background-color: {BG_DARK};
        color: {TEXT_PRIMARY};
    }}

    QLabel {{
        color: {TEXT_PRIMARY};
        font-family: {FONT_FAMILY};
    }}

    QPushButton {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 10px 16px;
        font-size: 13px;
        font-weight: 500;
    }}

    QPushButton:hover {{
        background-color: {BG_HOVER};
        border-color: {ACCENT_DIM};
    }}

    QPushButton:pressed {{
        background-color: {ACCENT_DIM};
        color: {BG_DARK};
    }}

    QPushButton[accent="true"] {{
        background-color: {ACCENT};
        color: {BG_DARK};
        border-color: {ACCENT};
    }}

    QPushButton[accent="true"]:hover {{
        background-color: {ACCENT_HOVER};
    }}

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 8px 12px;
        selection-background-color: {ACCENT};
    }}

    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border-color: {ACCENT};
    }}

    QListWidget, QTreeWidget {{
        background-color: {BG_CARD};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 4px;
    }}

    QListWidget::item, QTreeWidget::item {{
        padding: 8px;
        border-radius: 4px;
    }}

    QListWidget::item:hover, QTreeWidget::item:hover {{
        background-color: {BG_HOVER};
    }}

    QListWidget::item:selected, QTreeWidget::item:selected {{
        background-color: {ACCENT_DIM};
    }}

    QSlider::groove:horizontal {{
        background: {BORDER};
        height: 6px;
        border-radius: 3px;
    }}

    QSlider::handle:horizontal {{
        background: {ACCENT};
        width: 16px;
        margin: -5px 0;
        border-radius: 8px;
    }}

    QSlider::handle:horizontal:hover {{
        background: {ACCENT_HOVER};
    }}

    QScrollBar:vertical {{
        background: {BG_CARD};
        width: 10px;
        border-radius: 5px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background: {BORDER};
        min-height: 30px;
        border-radius: 5px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {TEXT_SECONDARY};
    }}

    QGroupBox {{
        font-weight: bold;
        border: 1px solid {BORDER};
        border-radius: 8px;
        margin-top: 12px;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {ACCENT};
    }}

    QTabWidget::pane {{
        border: 1px solid {BORDER};
        border-radius: 8px;
        top: -1px;
    }}

    QTabBar::tab {{
        background: {BG_CARD};
        padding: 10px 20px;
        margin-right: 4px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
    }}

    QTabBar::tab:selected {{
        background: {BG_DARK};
        border-bottom: 2px solid {ACCENT};
    }}

    QToolTip {{
        background-color: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        padding: 6px;
        border-radius: 4px;
    }}

    QProgressBar {{
        background: {BG_CARD};
        border: none;
        border-radius: 4px;
        height: 8px;
    }}

    QProgressBar::chunk {{
        background: {ACCENT};
        border-radius: 4px;
    }}
    """


def apply_palette(app):
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG_DARK))
    palette.setColor(QPalette.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.Base, QColor(BG_CARD))
    palette.setColor(QPalette.AlternateBase, QColor(BG_HOVER))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor(BG_DARK))
    app.setPalette(palette)
