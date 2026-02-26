"""Icone SVG 18x18 per strumenti disegno - stroke uniforme."""
from PyQt5.QtGui import QIcon, QPixmap, QPainter
from PyQt5.QtCore import Qt, QByteArray, QSize
from PyQt5.QtSvg import QSvgRenderer

# Colore icone (TEXT_PRIMARY del tema scuro)
_ICON_COLOR = "#F0F6FC"


def _svg_to_icon(svg: str, size: int = 18, color: str = None) -> QIcon:
    """Converte SVG string in QIcon alla dimensione specificata."""
    c = color or _ICON_COLOR
    svg_final = svg.replace("currentColor", c)
    data = QByteArray(svg_final.encode("utf-8"))
    renderer = QSvgRenderer(data)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


# SVGs 18x18, stroke-width 2, viewBox 0 0 18 18, colore inherit
_STROKE = 'stroke="currentColor" stroke-width="2" fill="none"'
_STROKE_DASHED = 'stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="3 2"'
# Frecce: punta 4-5px, angolo 40°, linecap/linejoin round, curve fluide
_STROKE_ARROW = 'stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"'

SVG_CIRCLE = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><circle cx="9" cy="9" r="6" {_STROKE}/></svg>'

# Freccia: linea + punta 5px, angolo 40° (tan20°≈0.36 → half-width 1.8)
SVG_ARROW = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><path d="M3 9 L11 9" {_STROKE_ARROW}/><path d="M11 7.2 L16 9 L11 10.8" {_STROKE_ARROW}/></svg>'

SVG_LINE = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><line x1="2" y1="9" x2="16" y2="9" {_STROKE}/></svg>'

SVG_RECTANGLE = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><rect x="3" y="4" width="12" height="10" rx="1" {_STROKE}/></svg>'

# T disegnato con path/stroke come le altre icone - riempie meglio il viewBox
SVG_TEXT = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><path d="M4 3 L14 3 M9 3 L9 15" {_STROKE}/></svg>'

SVG_CONE = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><path d="M9 3 L14 15 L4 15 Z" {_STROKE}/><ellipse cx="9" cy="15" rx="5" ry="1.5" {_STROKE}/></svg>'

SVG_ZOOM = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><circle cx="8" cy="8" r="5" {_STROKE}/><line x1="12" y1="12" x2="16" y2="16" {_STROKE}/></svg>'

SVG_PENCIL = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><path d="M3 15 L4 12 L12 4 L14 6 L6 14 Z" {_STROKE}/><line x1="12" y1="4" x2="14" y2="6" {_STROKE}/></svg>'

SVG_CURVED_LINE = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><path d="M2 14 Q6 4 16 4" {_STROKE}/></svg>'

# Freccia curva: Bezier quadratica fluida + punta 5px, 40°
SVG_CURVED_ARROW = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><path d="M2 14 Q7 4 12 4" {_STROKE_ARROW}/><path d="M11 2.2 L16 4 L11 5.8" {_STROKE_ARROW}/></svg>'

# Parabola (passaggio alto): curva Bezier fluida + punta 5px, 40°
SVG_PARABOLA = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><path d="M2 14 Q9 2 13 14" {_STROKE_ARROW}/><path d="M13 12.2 L16 14 L13 15.8" {_STROKE_ARROW}/></svg>'

# Freccia tratteggiata: linea dash + punta 5px, 40°
_SD = 'stroke="currentColor" stroke-width="2" fill="none" stroke-dasharray="3 2" stroke-linecap="round" stroke-linejoin="round"'
SVG_DASHED_ARROW = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><path d="M2 9 L10 9" {_SD}/><path d="M10 7.2 L16 9 L10 10.8" {_STROKE_ARROW}/></svg>'

# Freccia zigzag: onda sinusoidale fluida (Bezier) + punta 5px, 40°
SVG_ZIGZAG_ARROW = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><path d="M2 9 C3.5 11 3.5 11 5 9 C6.5 7 6.5 7 8 9 C9.5 11 9.5 11 11 9" {_STROKE_ARROW}/><path d="M11 7.2 L16 9 L11 10.8" {_STROKE_ARROW}/></svg>'

# Freccia doppia punta: entrambe le punte 5px, 40°
SVG_DOUBLE_ARROW = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><path d="M5 9 L11 9" {_STROKE_ARROW}/><path d="M11 7.2 L16 9 L11 10.8" {_STROKE_ARROW}/><path d="M7 7.2 L2 9 L7 10.8" {_STROKE_ARROW}/></svg>'

# Linea tratteggiata
SVG_DASHED_LINE = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 18 18"><line x1="2" y1="9" x2="16" y2="9" {_STROKE_DASHED}/></svg>'


def get_draw_tool_icon(tool_name: str, size: int = 18) -> QIcon:
    """Ritorna QIcon per lo strumento dato."""
    mapping = {
        "circle": SVG_CIRCLE,
        "arrow": SVG_ARROW,
        "line": SVG_LINE,
        "rectangle": SVG_RECTANGLE,
        "text": SVG_TEXT,
        "cone": SVG_CONE,
        "zoom": SVG_ZOOM,
        "pencil": SVG_PENCIL,
        "curved_line": SVG_CURVED_LINE,
        "curved_arrow": SVG_CURVED_ARROW,
        "parabola_arrow": SVG_PARABOLA,
        "dashed_arrow": SVG_DASHED_ARROW,
        "zigzag_arrow": SVG_ZIGZAG_ARROW,
        "double_arrow": SVG_DOUBLE_ARROW,
        "dashed_line": SVG_DASHED_LINE,
    }
    svg = mapping.get(tool_name, SVG_CIRCLE)
    return _svg_to_icon(svg, size, _ICON_COLOR)
