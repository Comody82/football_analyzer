"""Overlay per disegnare sul video: cerchi, frecce, testo, zoom - stile Kinovea."""
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsLineItem, QGraphicsTextItem, QGraphicsRectItem,
    QGraphicsPolygonItem, QGraphicsPathItem, QApplication,
    QInputDialog, QColorDialog, QFontDialog, QMenu, QShortcut,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QFrame, QWidget,
    QGraphicsOpacityEffect, QCheckBox, QComboBox,
)
from PyQt5.QtGui import (
    QPen, QBrush, QColor, QPainter, QPolygonF, QFont,
    QLinearGradient, QPainterPath, QPainterPathStroker, QWheelEvent,
    QKeySequence, QTransform, QRegion, QPolygon,
    QTextDocument, QTextOption, QTextBlockFormat, QTextCharFormat, QTextCursor,
)
from PyQt5.QtCore import (
    Qt, QPointF, QRectF, QLineF, QPoint, QObject, pyqtSignal, QEvent,
    QPropertyAnimation, QEasingCurve, QTimer, QSize, QRect,
)
from PyQt5.QtCore import QParallelAnimationGroup
from typing import Optional, List, Tuple, Dict, Any
from enum import Enum
import math


class DrawTool(Enum):
    NONE = "none"
    CIRCLE = "circle"
    ARROW = "arrow"
    LINE = "line"
    RECTANGLE = "rectangle"
    TEXT = "text"
    CONE = "cone"  # cono di luce
    ZOOM = "zoom"  # area zoom (rettangolo tratteggiato)
    PENCIL = "pencil"  # disegno a mano libera
    CURVED_LINE = "curved_line"  # linea curva con punto di controllo
    CURVED_ARROW = "curved_arrow"  # freccia curva
    PARABOLA_ARROW = "parabola_arrow"  # freccia parabolica (passaggio alto)
    DASHED_ARROW = "dashed_arrow"  # freccia tratteggiata
    ZIGZAG_ARROW = "zigzag_arrow"  # freccia zigzag
    DOUBLE_ARROW = "double_arrow"  # freccia doppia punta
    DASHED_LINE = "dashed_line"  # linea tratteggiata
    POLYGON = "polygon"


class PolygonFillStyle(Enum):
    """Stile riempimento poligono."""
    SOLID = "solid"      # trasparente con opacità
    STRIPES = "stripes"  # righe diagonali (match analysis)


class ArrowLineStyle(Enum):
    """Stili per frecce e linee."""
    STRAIGHT = "Freccia/Linea"
    DASHED = "Freccia/Linea - Trattino"
    ZIGZAG = "Freccia/Linea - A zig zag"


def _get_arrow_line_tool_params(tool: DrawTool, current_style: ArrowLineStyle) -> Tuple[ArrowLineStyle, bool, bool]:
    """(style, is_arrow, head_at_start) per strumenti freccia/linea."""
    if tool == DrawTool.DASHED_ARROW:
        return ArrowLineStyle.DASHED, True, False
    if tool == DrawTool.ZIGZAG_ARROW:
        return ArrowLineStyle.ZIGZAG, True, False
    if tool == DrawTool.DOUBLE_ARROW:
        return ArrowLineStyle.STRAIGHT, True, True
    if tool == DrawTool.DASHED_LINE:
        return ArrowLineStyle.DASHED, False, False
    if tool == DrawTool.ARROW:
        return current_style, True, False
    if tool == DrawTool.LINE:
        return current_style, False, False
    return ArrowLineStyle.STRAIGHT, True, False


def _zigzag_segment(path: QPainterPath, pa: QPointF, pb: QPointF, zig_amt: float = 12) -> None:
    """Onda sinusoidale con tratto finale retto prima della punta (per direzione chiara)."""
    dx = pb.x() - pa.x()
    dy = pb.y() - pa.y()
    length = math.sqrt(dx * dx + dy * dy) or 1
    perp_x = -dy / length
    perp_y = dx / length
    straight_len = max(10, length * 0.06)
    n_cycles = max(4, int((length - straight_len) / 28))
    # Termina l'onda dove sin=0 (sulla linea base) per unire bene al tratto retto
    k_end = max(1, int((1 - straight_len / length) * n_cycles))
    t_wave_end = k_end / n_cycles
    n_pts = max(30, n_cycles * 10)
    for i in range(1, n_pts + 1):
        t = (i / n_pts) * t_wave_end
        offset = zig_amt * math.sin(t * n_cycles * 2 * math.pi)
        pt = QPointF(pa.x() + dx * t, pa.y() + dy * t)
        pt = QPointF(pt.x() + perp_x * offset, pt.y() + perp_y * offset)
        path.lineTo(pt)
    # L'ultimo punto è sull'asse (sin=0). Tratto retto finale verso la punta.
    path.lineTo(pb)


def _build_arrow_line_path(style: ArrowLineStyle, p1: QPointF, p2: QPointF,
                          trim_end: float = 0, trim_start: float = 0) -> QPainterPath:
    """Costruisce il path per lo stile dato e i due punti.
    trim_end/trim_start: accorcia il path dalla punta (per lasciare spazio alle frecce)."""
    path = QPainterPath()
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    length = math.sqrt(dx * dx + dy * dy) or 1
    ux, uy = dx / length, dy / length
    p1_eff = QPointF(p1.x() + ux * trim_start, p1.y() + uy * trim_start) if trim_start > 0 else p1
    p2_eff = QPointF(p2.x() - ux * trim_end, p2.y() - uy * trim_end) if trim_end > 0 else p2
    path.moveTo(p1_eff)
    len_eff = math.sqrt((p2_eff.x() - p1_eff.x()) ** 2 + (p2_eff.y() - p1_eff.y()) ** 2) or 1
    zig_amt = max(4, min(8, len_eff * 0.04))

    if style == ArrowLineStyle.STRAIGHT or style == ArrowLineStyle.DASHED:
        path.lineTo(p2_eff)
    elif style == ArrowLineStyle.ZIGZAG:
        _zigzag_segment(path, p1_eff, p2_eff, zig_amt)
    return path


def _is_dashed_style(style: ArrowLineStyle) -> bool:
    return style == ArrowLineStyle.DASHED


def _arrow_tip_angle(p1: QPointF, p2: QPointF) -> float:
    """Angolo (radianti) della direzione da p1 verso p2."""
    return math.atan2(p2.y() - p1.y(), p2.x() - p1.x())


def _arrow_head_polygon(tip: QPointF, angle: float, length: float,
                        base_width: float) -> QPolygonF:
    """Triangolo punta freccia: tip = vertice, base perpendicolare alla direzione."""
    half = base_width / 2
    cx = tip.x() - length * math.cos(angle)
    cy = tip.y() - length * math.sin(angle)
    perp_x = -math.sin(angle)
    perp_y = math.cos(angle)
    a = QPointF(cx - perp_x * half, cy - perp_y * half)
    b = QPointF(cx + perp_x * half, cy + perp_y * half)
    return QPolygonF([a, tip, b])


def _make_bevel_gradient(p_light: QPointF, p_dark: QPointF, base_color: QColor) -> QLinearGradient:
    """Gradiente con 4+ color stop per effetto bevel/estrusione 3D."""
    grad = QLinearGradient(p_light, p_dark)
    light = QColor(min(255, base_color.red() + 80), min(255, base_color.green() + 80), min(255, base_color.blue() + 80))
    light_mid = QColor(min(255, base_color.red() + 35), min(255, base_color.green() + 35), min(255, base_color.blue() + 35))
    dark_mid = QColor(max(0, base_color.red() - 35), max(0, base_color.green() - 35), max(0, base_color.blue() - 35))
    dark = QColor(max(0, base_color.red() - 80), max(0, base_color.green() - 80), max(0, base_color.blue() - 80))
    grad.setColorAt(0.0, light)      # bordo superiore
    grad.setColorAt(0.25, light_mid) # transizione
    grad.setColorAt(0.5, base_color)  # centro
    grad.setColorAt(0.75, dark_mid)  # transizione
    grad.setColorAt(1.0, dark)        # bordo inferiore
    return grad


def _make_body_only_shape(body_path: QPainterPath, body_width: float) -> QPainterPath:
    """Solo corpo stroked, senza punte (per ombra)."""
    stroker = QPainterPathStroker()
    stroker.setWidth(body_width)
    stroker.setCurveThreshold(0.5)
    stroker.setCapStyle(Qt.FlatCap)
    stroker.setJoinStyle(Qt.RoundJoin)
    return stroker.createStroke(body_path)


def _make_volumetric_arrow_shape(body_path: QPainterPath, p1: QPointF, p2: QPointF,
                                  body_width: float, head_length: float,
                                  head_width_factor: float = 2.5,
                                  head_at_start: bool = False) -> QPainterPath:
    """Path riempito: corpo stroked (FlatCap) + punte triangolari."""
    result = QPainterPath(_make_body_only_shape(body_path, body_width))
    result.setFillRule(Qt.WindingFill)
    angle = _arrow_tip_angle(p1, p2)
    head_poly = _arrow_head_polygon(p2, angle, head_length, body_width * head_width_factor)
    hp = QPainterPath()
    hp.addPolygon(head_poly)
    result.addPath(hp)
    if head_at_start:
        angle_s = angle + math.pi
        head_poly_s = _arrow_head_polygon(p1, angle_s, head_length, body_width * head_width_factor)
        hp2 = QPainterPath()
        hp2.addPolygon(head_poly_s)
        result.addPath(hp2)
    return result


class ResizeHandle(QGraphicsRectItem):
    """Maniglia per il ridimensionamento - visuale only, il drag è gestito dall'overlay."""
    HANDLE_SIZE = 20

    def __init__(self, overlay, parent_item, handle_index: int):
        super().__init__(-self.HANDLE_SIZE/2, -self.HANDLE_SIZE/2, self.HANDLE_SIZE, self.HANDLE_SIZE)
        self._overlay = overlay
        self._parent_item = parent_item
        self._handle_index = handle_index
        self.setBrush(QBrush(QColor(255, 255, 255)))  # Bianco
        self.setPen(QPen(QColor(80, 80, 80), 1))
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(self.GraphicsItemFlag.ItemIgnoresTransformations)  # Dimensione fissa sullo schermo
        self.setZValue(9999)


def _stroke_shape_for_rect_ellipse(item_rect: QRectF, pen_width: int, min_tol: int = 12) -> QPainterPath:
    """Path solo sul bordo per hit detection (clic sul bordo, non area interna)."""
    path = QPainterPath()
    path.addEllipse(item_rect)  # usa ellipse per cerchio/rect (ellisse su rect = ovale)
    stroker = QPainterPathStroker()
    stroker.setWidth(max(min_tol, pen_width + 8))
    return stroker.createStroke(path)


class DrawableCircle(QGraphicsEllipseItem):
    """Cerchio disegnabile. Selezione solo sul bordo."""
    def __init__(self, rect: QRectF, color: QColor = Qt.red, pen_width: int = 3):
        super().__init__(rect)
        self.setPen(QPen(color, pen_width))
        self.setBrush(QBrush(Qt.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)
        self._color = color

    def shape(self):
        return _stroke_shape_for_rect_ellipse(self.rect(), self.pen().width())

    def setDrawColor(self, c: QColor):
        self._color = c
        self.setPen(QPen(c, self.pen().width()))

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(self.rect())


class DrawableRectangle(QGraphicsRectItem):
    """Rettangolo disegnabile. Selezione solo sul bordo."""
    def __init__(self, rect: QRectF, color: QColor = Qt.red, pen_width: int = 3):
        super().__init__(rect)
        self.setPen(QPen(color, pen_width))
        self.setBrush(QBrush(Qt.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)
        self._color = color

    def shape(self):
        path = QPainterPath()
        path.addRect(self.rect())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(12, self.pen().width() + 8))
        return stroker.createStroke(path)

    def setDrawColor(self, c: QColor):
        self._color = c
        self.setPen(QPen(c, self.pen().width()))

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.rect())


class DrawableArrow(QGraphicsPathItem):
    """Frecce volumetriche 3D: corpo poligonale + punta triangolare piena, effetto bevel, ombra solo su corpo."""
    HEAD_WIDTH_FACTOR = 2.5
    SHADOW_OFFSET_PX = 3
    HIGHLIGHT_OPACITY = 0.2

    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 color: QColor = Qt.red, width: int = 4,
                 style: ArrowLineStyle = ArrowLineStyle.STRAIGHT,
                 head_at_start: bool = False):
        super().__init__()
        self._p1 = QPointF(x1, y1)
        self._p2 = QPointF(x2, y2)
        self._color = color
        self._width = max(2, width)
        self._style = style
        self._arrow_size = max(12, self._width * 3)
        self._head_at_start = head_at_start
        self._update_path()

    def _update_path(self):
        trim_end = float(self._arrow_size)
        trim_start = float(self._arrow_size) if self._head_at_start else 0
        body_path = _build_arrow_line_path(
            self._style, self._p1, self._p2, trim_end=trim_end, trim_start=trim_start
        )
        self._centerline_path = _build_arrow_line_path(self._style, self._p1, self._p2)
        self._highlight_centerline_path = body_path  # accorciato, senza punte
        self._body_path_for_shadow = _make_body_only_shape(body_path, float(self._width))
        vol_path = _make_volumetric_arrow_shape(
            body_path, self._p1, self._p2,
            float(self._width), float(self._arrow_size),
            self.HEAD_WIDTH_FACTOR, self._head_at_start
        )
        self.setPath(vol_path)
        self.setPen(QPen(Qt.NoPen))
        self.setBrush(QBrush(Qt.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)

    def shape(self):
        s = QPainterPathStroker()
        s.setWidth(max(8, self._width + 6))
        return s.createStroke(self.path())

    def line(self):
        return QLineF(self._p1, self._p2)

    def setLine(self, x1: float, y1: float, x2: float, y2: float):
        self._p1 = QPointF(x1, y1)
        self._p2 = QPointF(x2, y2)
        self._update_path()

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.HighQualityAntialiasing, True)
        path = self.path()
        angle = _arrow_tip_angle(self._p1, self._p2)
        perp_x, perp_y = -math.sin(angle), math.cos(angle)
        cx = (self._p1.x() + self._p2.x()) / 2
        cy = (self._p1.y() + self._p2.y()) / 2
        half_len = math.sqrt((self._p2.x() - self._p1.x()) ** 2 + (self._p2.y() - self._p1.y()) ** 2) / 2 or 1
        head_polys = [
            _arrow_head_polygon(self._p2, angle, self._arrow_size, self._width * self.HEAD_WIDTH_FACTOR)
        ]
        if self._head_at_start:
            head_polys.append(
                _arrow_head_polygon(self._p1, angle + math.pi, self._arrow_size, self._width * self.HEAD_WIDTH_FACTOR)
            )
        # 1. Ombra solo sul corpo (senza punta)
        tr_shadow = QTransform().translate(self.SHADOW_OFFSET_PX, self.SHADOW_OFFSET_PX)
        painter.setPen(QPen(Qt.NoPen))
        painter.setBrush(QBrush(QColor(0, 0, 0, 100)))
        painter.drawPath(tr_shadow.map(self._body_path_for_shadow))
        # 2. Corpo e punte: poligono pieno con gradiente bevel (4+ color stop)
        p_light = QPointF(cx - perp_x * half_len, cy - perp_y * half_len)
        p_dark = QPointF(cx + perp_x * half_len, cy + perp_y * half_len)
        grad = _make_bevel_gradient(p_light, p_dark, self._color)
        painter.setPen(QPen(Qt.NoPen))
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)
        for poly in head_polys:
            painter.drawPolygon(poly)
        # 3. Highlight centrale: shape più stretta, accorciato (non sotto la punta)
        hl_w = max(1, int(self._width * 0.35))
        up_x, up_y = perp_x * (self._width * 0.3), perp_y * (self._width * 0.3)
        tr_hl = QTransform().translate(up_x, up_y)
        stroker_hl = QPainterPathStroker()
        stroker_hl.setWidth(hl_w)
        stroker_hl.setCapStyle(Qt.RoundCap)
        stroker_hl.setCurveThreshold(0.5)
        hl_path = stroker_hl.createStroke(tr_hl.map(self._highlight_centerline_path))
        painter.setBrush(QBrush(QColor(255, 255, 255, int(255 * self.HIGHLIGHT_OPACITY))))
        painter.drawPath(hl_path)
        # 4. Selezione
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

    def setDrawColor(self, c: QColor):
        self._color = c
        self._update_path()

    @property
    def style(self):
        return self._style

    def setStyle(self, s: ArrowLineStyle):
        self._style = s
        self._update_path()


class DrawableLine(QGraphicsPathItem):
    """Linee con vari stili (senza punte)."""
    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 color: QColor = Qt.red, width: int = 4,
                 style: ArrowLineStyle = ArrowLineStyle.STRAIGHT):
        super().__init__()
        self._p1 = QPointF(x1, y1)
        self._p2 = QPointF(x2, y2)
        self._color = color
        self._width = width
        self._style = style
        self._update_path()

    def _update_path(self):
        path = _build_arrow_line_path(self._style, self._p1, self._p2)
        self.setPath(path)
        pen = QPen(self._color, self._width)
        if _is_dashed_style(self._style):
            pen.setStyle(Qt.DashLine)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)

    def shape(self):
        s = QPainterPathStroker()
        s.setWidth(max(20, self._width + 12))
        return s.createStroke(self.path())

    def line(self):
        return QLineF(self._p1, self._p2)

    def setLine(self, x1: float, y1: float, x2: float, y2: float):
        self._p1 = QPointF(x1, y1)
        self._p2 = QPointF(x2, y2)
        self._update_path()

    def setDrawColor(self, c: QColor):
        self._color = c
        self._update_path()

    @property
    def style(self):
        return self._style

    def setStyle(self, s: ArrowLineStyle):
        self._style = s
        self._update_path()

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(self.path())


def _quadratic_curve_path(p1: QPointF, ctrl: QPointF, p2: QPointF) -> QPainterPath:
    """Path curva quadratica Bezier da p1 a p2 con punto di controllo ctrl."""
    path = QPainterPath()
    path.moveTo(p1)
    path.quadTo(ctrl, p2)
    return path


def _bezier_tangent_at_end(p1: QPointF, ctrl: QPointF, p2: QPointF) -> float:
    """Angolo tangente (radianti) alla curva Bezier quadratica all'estremità t=1."""
    return math.atan2(p2.y() - ctrl.y(), p2.x() - ctrl.x())


def _quadratic_curve_path_trimmed(p1: QPointF, ctrl: QPointF, p2: QPointF,
                                  trim_from_end: float) -> QPainterPath:
    """Curva Bezier quadratica accorciata di trim_from_end dalla fine (approssimazione)."""
    if trim_from_end <= 0:
        return _quadratic_curve_path(p1, ctrl, p2)
    dist = math.sqrt((p2.x() - ctrl.x()) ** 2 + (p2.y() - ctrl.y()) ** 2) or 1
    t_trim = max(0.0, 1.0 - trim_from_end / (2.0 * dist))
    u = 1 - t_trim
    p2_eff = QPointF(
        u * u * p1.x() + 2 * u * t_trim * ctrl.x() + t_trim * t_trim * p2.x(),
        u * u * p1.y() + 2 * u * t_trim * ctrl.y() + t_trim * t_trim * p2.y()
    )
    path = QPainterPath()
    path.moveTo(p1)
    path.quadTo(ctrl, p2_eff)
    return path


class DrawableCurvedLine(QGraphicsPathItem):
    """Linea curva con punto di controllo (quadratic Bezier)."""
    def __init__(self, p1: QPointF, ctrl: QPointF, p2: QPointF,
                 color: QColor = Qt.red, pen_width: int = 4):
        super().__init__()
        self._p1 = QPointF(p1)
        self._ctrl = QPointF(ctrl)
        self._p2 = QPointF(p2)
        self._color = color
        self._pen_width = pen_width
        self._update_path()

    def _update_path(self):
        self.setPath(_quadratic_curve_path(self._p1, self._ctrl, self._p2))
        self.setPen(QPen(self._color, self._pen_width))
        self.setBrush(QBrush(Qt.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)

    def shape(self):
        s = QPainterPathStroker()
        s.setWidth(max(20, self._pen_width + 12))
        return s.createStroke(self.path())

    def getPoints(self) -> List[QPointF]:
        return [self._p1, self._ctrl, self._p2]

    def setPoints(self, p1: QPointF, ctrl: QPointF, p2: QPointF):
        self._p1 = QPointF(p1)
        self._ctrl = QPointF(ctrl)
        self._p2 = QPointF(p2)
        self._update_path()

    def setDrawColor(self, c: QColor):
        self._color = c
        self._update_path()

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(self.path())


class DrawableCurvedArrow(QGraphicsPathItem):
    """Freccia curva volumetrica 3D: corpo Bezier + punta, effetto bevel, ombra solo su corpo."""
    HEAD_WIDTH_FACTOR = 2.5
    SHADOW_OFFSET_PX = 3
    HIGHLIGHT_OPACITY = 0.2

    def __init__(self, p1: QPointF, ctrl: QPointF, p2: QPointF,
                 color: QColor = Qt.red, pen_width: int = 4):
        super().__init__()
        self._p1 = QPointF(p1)
        self._ctrl = QPointF(ctrl)
        self._p2 = QPointF(p2)
        self._color = color
        self._pen_width = max(2, pen_width)
        self._arrow_size = max(12, self._pen_width * 3)
        self._update_path()

    def _update_path(self):
        body_path = _quadratic_curve_path_trimmed(
            self._p1, self._ctrl, self._p2, float(self._arrow_size)
        )
        self._centerline_path = _quadratic_curve_path(self._p1, self._ctrl, self._p2)
        self._highlight_centerline_path = body_path  # accorciato, senza punta
        self._body_path_for_shadow = _make_body_only_shape(body_path, float(self._pen_width))
        angle = _bezier_tangent_at_end(self._p1, self._ctrl, self._p2)
        vol_path = _make_volumetric_arrow_shape(
            body_path,
            self._p2 - QPointF(math.cos(angle), math.sin(angle)),
            self._p2,
            float(self._pen_width), float(self._arrow_size),
            self.HEAD_WIDTH_FACTOR, False
        )
        self.setPath(vol_path)
        self.setPen(QPen(Qt.NoPen))
        self.setBrush(QBrush(Qt.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)

    def shape(self):
        s = QPainterPathStroker()
        s.setWidth(max(8, self._pen_width + 6))
        return s.createStroke(self.path())

    def getPoints(self) -> List[QPointF]:
        return [self._p1, self._ctrl, self._p2]

    def setPoints(self, p1: QPointF, ctrl: QPointF, p2: QPointF):
        self._p1 = QPointF(p1)
        self._ctrl = QPointF(ctrl)
        self._p2 = QPointF(p2)
        self._update_path()

    def setDrawColor(self, c: QColor):
        self._color = c
        self._update_path()

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.HighQualityAntialiasing, True)
        path = self.path()
        angle = _bezier_tangent_at_end(self._p1, self._ctrl, self._p2)
        perp_x, perp_y = -math.sin(angle), math.cos(angle)
        cx, cy = (self._p1.x() + self._p2.x()) / 2, (self._p1.y() + self._p2.y()) / 2
        half_len = math.sqrt((self._p2.x() - self._p1.x()) ** 2 + (self._p2.y() - self._p1.y()) ** 2) / 2 or 1
        head_poly = _arrow_head_polygon(
            self._p2, angle, self._arrow_size,
            float(self._pen_width) * self.HEAD_WIDTH_FACTOR
        )
        tr_shadow = QTransform().translate(self.SHADOW_OFFSET_PX, self.SHADOW_OFFSET_PX)
        painter.setPen(QPen(Qt.NoPen))
        painter.setBrush(QBrush(QColor(0, 0, 0, 100)))
        painter.drawPath(tr_shadow.map(self._body_path_for_shadow))
        p_light = QPointF(cx - perp_x * half_len, cy - perp_y * half_len)
        p_dark = QPointF(cx + perp_x * half_len, cy + perp_y * half_len)
        grad = _make_bevel_gradient(p_light, p_dark, self._color)
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)
        painter.drawPolygon(head_poly)
        hl_w = max(1, int(self._pen_width * 0.35))
        up_x, up_y = perp_x * (self._pen_width * 0.3), perp_y * (self._pen_width * 0.3)
        tr_hl = QTransform().translate(up_x, up_y)
        stroker_hl = QPainterPathStroker()
        stroker_hl.setWidth(hl_w)
        stroker_hl.setCapStyle(Qt.RoundCap)
        stroker_hl.setCurveThreshold(0.5)
        hl_path = stroker_hl.createStroke(tr_hl.map(self._highlight_centerline_path))
        painter.setBrush(QBrush(QColor(255, 255, 255, int(255 * self.HIGHLIGHT_OPACITY))))
        painter.drawPath(hl_path)
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)


class DrawableParabolaArrow(QGraphicsPathItem):
    """Freccia parabolica volumetrica 3D: curva + punta, effetto bevel, ombra corpo + linea p1-p2 sotto."""
    HEAD_WIDTH_FACTOR = 2.5
    SHADOW_OFFSET_PX = 3
    HIGHLIGHT_OPACITY = 0.2
    SHADOW_LINE_OPACITY = 0.35  # opacità ridotta per linea ombra p1-p2

    def __init__(self, p1: QPointF, ctrl: QPointF, p2: QPointF,
                 color: QColor = Qt.red, pen_width: int = 4):
        super().__init__()
        self._p1 = QPointF(p1)
        self._ctrl = QPointF(ctrl)
        self._p2 = QPointF(p2)
        self._color = color
        self._pen_width = max(2, pen_width)
        self._arrow_size = max(12, self._pen_width * 3)
        self._update_path()

    def _update_path(self):
        body_path = _quadratic_curve_path_trimmed(
            self._p1, self._ctrl, self._p2, float(self._arrow_size)
        )
        self._centerline_path = _quadratic_curve_path(self._p1, self._ctrl, self._p2)
        self._highlight_centerline_path = body_path  # accorciato, senza punta
        self._body_path_for_shadow = _make_body_only_shape(body_path, float(self._pen_width))
        angle = _bezier_tangent_at_end(self._p1, self._ctrl, self._p2)
        back = QPointF(math.cos(angle), math.sin(angle))
        vol_path = _make_volumetric_arrow_shape(
            body_path, self._p2 - back, self._p2,
            float(self._pen_width), float(self._arrow_size),
            self.HEAD_WIDTH_FACTOR, False
        )
        self.setPath(vol_path)
        self.setPen(QPen(Qt.NoPen))
        self.setBrush(QBrush(Qt.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)

    def shape(self):
        s = QPainterPathStroker()
        s.setWidth(max(8, self._pen_width + 6))
        return s.createStroke(self.path())

    def getPoints(self) -> List[QPointF]:
        return [self._p1, self._ctrl, self._p2]

    def setPoints(self, p1: QPointF, ctrl: QPointF, p2: QPointF):
        self._p1 = QPointF(p1)
        self._ctrl = QPointF(ctrl)
        self._p2 = QPointF(p2)
        self._update_path()

    def setDrawColor(self, c: QColor):
        self._color = c
        self._update_path()

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.HighQualityAntialiasing, True)
        path = self.path()
        angle = _bezier_tangent_at_end(self._p1, self._ctrl, self._p2)
        perp_x, perp_y = -math.sin(angle), math.cos(angle)
        cx, cy = (self._p1.x() + self._p2.x()) / 2, (self._p1.y() + self._p2.y()) / 2
        half_len = math.sqrt((self._p2.x() - self._p1.x()) ** 2 + (self._p2.y() - self._p1.y()) ** 2) / 2 or 1
        head_poly = _arrow_head_polygon(
            self._p2, angle, self._arrow_size,
            float(self._pen_width) * self.HEAD_WIDTH_FACTOR
        )
        # 1. Ombra linea retta p1-p2 sotto la curva (grigio scuro, opacità ridotta)
        shadow_line = QLineF(self._p1, self._p2)
        shadow_line_tr = QLineF(
            shadow_line.p1().x() + self.SHADOW_OFFSET_PX, shadow_line.p1().y() + self.SHADOW_OFFSET_PX,
            shadow_line.p2().x() + self.SHADOW_OFFSET_PX, shadow_line.p2().y() + self.SHADOW_OFFSET_PX
        )
        shadow_gray = QColor(50, 50, 50, int(255 * self.SHADOW_LINE_OPACITY))
        painter.setPen(QPen(shadow_gray, max(2, self._pen_width)))
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(shadow_line_tr)
        # 2. Ombra corpo (senza punta)
        tr_shadow = QTransform().translate(self.SHADOW_OFFSET_PX, self.SHADOW_OFFSET_PX)
        painter.setPen(QPen(Qt.NoPen))
        painter.setBrush(QBrush(QColor(0, 0, 0, 100)))
        painter.drawPath(tr_shadow.map(self._body_path_for_shadow))
        p_light = QPointF(cx - perp_x * half_len, cy - perp_y * half_len)
        p_dark = QPointF(cx + perp_x * half_len, cy + perp_y * half_len)
        grad = _make_bevel_gradient(p_light, p_dark, self._color)
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)
        painter.drawPolygon(head_poly)
        hl_w = max(1, int(self._pen_width * 0.35))
        up_x, up_y = perp_x * (self._pen_width * 0.3), perp_y * (self._pen_width * 0.3)
        tr_hl = QTransform().translate(up_x, up_y)
        stroker_hl = QPainterPathStroker()
        stroker_hl.setWidth(hl_w)
        stroker_hl.setCapStyle(Qt.RoundCap)
        stroker_hl.setCurveThreshold(0.5)
        hl_path = stroker_hl.createStroke(tr_hl.map(self._highlight_centerline_path))
        painter.setBrush(QBrush(QColor(255, 255, 255, int(255 * self.HIGHLIGHT_OPACITY))))
        painter.drawPath(hl_path)
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)


class DrawableText(QGraphicsTextItem):
    """Testo disegnabile: selezionabile, trascinabile, doppio clic per modificare.
       Supporta formato: font, colore, sfondo, contorno, allineamento, interlinea."""
    def __init__(self, text: str = "", color: QColor = Qt.white):
        super().__init__(text)
        self.setDefaultTextColor(color)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(self.GraphicsItemFlag.ItemIsFocusable)
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        font = QFont("Segoe UI", 24, QFont.Bold)
        self.setFont(font)
        self._color = color
        self._fill_color = QColor(0, 0, 0, 0)
        self._outline_color = QColor(255, 255, 255)
        self._outline_width = 0  # 0 = nessun contorno

    def apply_format(self, fmt: dict):
        """Applica formato da TextFormatToolbar."""
        if "font_family" in fmt or "font_size" in fmt or "bold" in fmt or "italic" in fmt:
            font = self.font()
            if "font_family" in fmt:
                font.setFamily(fmt["font_family"])
            if "font_size" in fmt:
                font.setPointSize(fmt["font_size"])
            if "bold" in fmt:
                font.setBold(fmt["bold"])
            if "italic" in fmt:
                font.setItalic(fmt["italic"])
            if "underline" in fmt:
                font.setUnderline(fmt["underline"])
            self.setFont(font)
        if "text_color" in fmt:
            c = fmt["text_color"]
            self._color = QColor(c)
            self.setDefaultTextColor(self._color)
        if "fill_color" in fmt:
            self._fill_color = QColor(fmt["fill_color"])
        if "opacity" in fmt:
            self.setOpacity(fmt["opacity"])
        if "outline_width" in fmt:
            self._outline_width = int(fmt["outline_width"])
        if "outline_color" in fmt:
            self._outline_color = QColor(fmt["outline_color"])
            if self._outline_width == 0 and "outline_width" not in fmt:
                self._outline_width = 1
        if "alignment" in fmt:
            opt = self.document().defaultTextOption()
            opt.setAlignment(Qt.AlignmentFlag(fmt["alignment"]))
            self.document().setDefaultTextOption(opt)
        if "line_spacing_percent" in fmt:
            pct = fmt["line_spacing_percent"]
            block_fmt = QTextBlockFormat()
            block_fmt.setLineHeight(pct, QTextBlockFormat.ProportionalHeight)
            cursor = QTextCursor(self.document())
            cursor.select(QTextCursor.Document)
            cursor.mergeBlockFormat(block_fmt)

    def get_format(self) -> dict:
        """Ritorna il formato corrente."""
        f = self.font()
        opt = self.document().defaultTextOption()
        align = opt.alignment()
        return {
            "font_family": f.family(),
            "font_size": f.pointSize(),
            "bold": f.bold(),
            "italic": f.italic(),
            "underline": f.underline(),
            "alignment": align,
            "text_color": QColor(self._color),
            "fill_color": QColor(self._fill_color),
            "opacity": self.opacity(),
            "outline_width": self._outline_width,
            "outline_color": QColor(self._outline_color),
            "line_spacing_percent": 100,
        }

    def setDrawColor(self, c: QColor):
        self._color = c
        self.setDefaultTextColor(c)

    def focusOutEvent(self, event):
        """Terminata modifica: torna selezionabile/trascinabile."""
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        cb = getattr(self, "_confirm_callback", None)
        if callable(cb):
            cb()
        super().focusOutEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Doppio clic: abilita modifica testo."""
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus(Qt.MouseFocusReason)
        super().mouseDoubleClickEvent(event)

    def sceneEvent(self, event):
        """Tasto destro: inoltra alla view per mostrare menu Personalizzazione/Duplica/Elimina."""
        if event.type() == QEvent.GraphicsSceneContextMenu:
            views = self.scene().views() if self.scene() else []
            if views:
                overlay = views[0]
                if hasattr(overlay, "_show_context_menu"):
                    sp = event.screenPos()
                    global_pos = QPoint(int(sp.x()), int(sp.y()))
                    overlay._show_context_menu(global_pos, self)
                    event.accept()
                    return True
        return super().sceneEvent(event)

    def paint(self, painter, option, widget):
        br = self.boundingRect()
        # Sfondo riempimento (se colore con alpha > 0)
        if self._fill_color.alpha() > 0:
            painter.fillRect(br, QBrush(self._fill_color))
        # Contorno testo (outline): disegna il documento più volte con offset
        if self._outline_width > 0:
            old_color = self.defaultTextColor()
            self.setDefaultTextColor(self._outline_color)
            offsets = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
            for dx, dy in offsets:
                sx = dx * self._outline_width
                sy = dy * self._outline_width
                painter.save()
                painter.translate(sx, sy)
                self.document().drawContents(painter, br.adjusted(-20, -20, 20, 20))
                painter.restore()
            self.setDefaultTextColor(old_color)
        super().paint(painter, option, widget)
        if self.isSelected() and self.textInteractionFlags() == Qt.NoTextInteraction:
            painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(br)


class DrawableFreehand(QGraphicsPathItem):
    """Disegno a mano libera (matita). Oggetto con bounding box dinamico, selezionabile e manipolabile."""
    def __init__(self, path: QPainterPath, color: QColor = Qt.red, pen_width: int = 4):
        # Path in coordinate scene → normalizza in coord locali (pos = top-left del bounding rect)
        br = path.controlPointRect()
        if br.width() < 1 and br.height() < 1:
            br = path.boundingRect()
        if br.width() < 1 and br.height() < 1:
            br = QRectF(0, 0, 1, 1)
        tr = QTransform()
        tr.translate(-br.left(), -br.top())
        local_path = tr.map(path)
        super().__init__(local_path)
        self.setPen(QPen(color, pen_width))
        self.setBrush(QBrush(Qt.NoBrush))
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)
        self._color = color
        self._path = QPainterPath(local_path)
        self.setPos(br.left(), br.top())

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(max(16, self.pen().width() + 10))
        return stroker.createStroke(self.path())

    def setDrawColor(self, c: QColor):
        self._color = c
        self.setPen(QPen(c, self.pen().width()))

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(self.path())

    def setPathToBounds(self, new_local_rect: QRectF):
        """Ridimensiona il path per adattarlo al nuovo bounding box (coord locali, origine 0,0)."""
        old_br = self.path().boundingRect()
        if old_br.width() < 0.01 or old_br.height() < 0.01:
            return
        tr = QTransform()
        tr.translate(-old_br.left(), -old_br.top())
        tr.scale(new_local_rect.width() / old_br.width(),
                 new_local_rect.height() / old_br.height())
        tr.translate(new_local_rect.left(), new_local_rect.top())
        self.setPath(tr.map(self.path()))


class DrawableCone(QGraphicsPolygonItem):
    """Cono di luce (triangolo gradiente). Selezione solo sul bordo."""
    def __init__(self, points: List[QPointF], color: QColor = Qt.yellow):
        poly = QPolygonF(points)
        super().__init__(poly)
        self.setPen(QPen(Qt.NoPen))
        grad = QLinearGradient(points[0], points[1])
        grad.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 180))
        grad.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 30))
        self.setBrush(QBrush(grad))
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)
        self._color = color

    def shape(self):
        path = QPainterPath()
        path.addPolygon(self.polygon())
        stroker = QPainterPathStroker()
        stroker.setWidth(16)
        return stroker.createStroke(path)

    def paint(self, painter, option, widget):
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(self.polygon())


class DrawablePolygon(QGraphicsPolygonItem):
    """Poligono per zone (match analysis). Fill trasparente o a righe diagonali."""
    def __init__(self, points: List[QPointF], color: QColor = Qt.yellow,
                 fill_style: PolygonFillStyle = PolygonFillStyle.SOLID, opacity: float = 0.4):
        poly = QPolygonF(points)
        super().__init__(poly)
        self._color = color
        self._fill_style = fill_style
        self._opacity = max(0.2, min(0.6, opacity))
        self.setPen(QPen(color, 2))
        self._update_brush()
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)

    def _update_brush(self):
        alpha = int(self._opacity * 255)
        if self._fill_style == PolygonFillStyle.SOLID:
            fill_color = QColor(self._color.red(), self._color.green(), self._color.blue(), alpha)
            self.setBrush(QBrush(fill_color))
        else:
            self.setBrush(QBrush(Qt.NoBrush))

    def paint(self, painter, option, widget):
        if self._fill_style == PolygonFillStyle.SOLID:
            super().paint(painter, option, widget)
        else:
            painter.setPen(self.pen())
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(self.polygon())
            self._paint_stripes(painter)
        if self.isSelected():
            painter.setPen(QPen(QColor(255, 255, 255), 3, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawPolygon(self.polygon())

    def _paint_stripes(self, painter):
        """Righe diagonali 45° (stile match analysis)."""
        painter.save()
        poly = self.polygon()
        br = poly.boundingRect()
        alpha = int(self._opacity * 255)
        stripe_color = QColor(self._color.red(), self._color.green(), self._color.blue(), alpha)
        painter.setPen(QPen(stripe_color, 2))
        path = QPainterPath()
        path.addPolygon(poly)
        painter.setClipPath(path)
        step = 10
        diag = math.sqrt(br.width()**2 + br.height()**2)
        n = int(diag / step) + 2
        for i in range(-n, n + 1):
            off = i * step
            p1 = QPointF(br.left() - diag, br.top() + off)
            p2 = QPointF(br.right() + diag, br.top() + off + diag)
            painter.drawLine(p1, p2)
        painter.restore()

    def setDrawColor(self, c: QColor):
        self._color = c
        self.setPen(QPen(c, self.pen().width()))
        self._update_brush()

    def setFillStyle(self, style: PolygonFillStyle):
        self._fill_style = style
        self._update_brush()

    def setOpacity(self, opacity: float):
        self._opacity = max(0.2, min(0.6, opacity))
        self._update_brush()


def _serialize_point(p: QPointF) -> Dict[str, float]:
    return {"x": float(p.x()), "y": float(p.y())}


def _deserialize_point(d: dict) -> QPointF:
    return QPointF(d.get("x", 0), d.get("y", 0))


def _serialize_rect(r: QRectF) -> Dict[str, float]:
    return {"x": float(r.x()), "y": float(r.y()), "w": float(r.width()), "h": float(r.height())}


def _deserialize_rect(d: dict) -> QRectF:
    return QRectF(d.get("x", 0), d.get("y", 0), d.get("w", 0), d.get("h", 0))


def _serialize_color(c: QColor) -> str:
    return c.name()


def _deserialize_color(s: str) -> QColor:
    return QColor(s)


def _serialize_path(path: QPainterPath) -> list:
    """Serializza QPainterPath come lista di comandi JSON-serializzabili."""
    out = []
    for i in range(path.elementCount()):
        el = path.elementAt(i)
        if el.isMoveTo():
            out.append({"t": "M", "x": el.x, "y": el.y})
        elif el.isLineTo():
            out.append({"t": "L", "x": el.x, "y": el.y})
        elif el.isCurveTo():
            out.append({"t": "C", "x": el.x, "y": el.y})
        else:
            out.append({"t": "D", "x": el.x, "y": el.y})
    return out


def _deserialize_path(cmds: list) -> QPainterPath:
    path = QPainterPath()
    ctrl_pts = []
    for cmd in cmds:
        t, x, y = cmd.get("t"), cmd.get("x", 0), cmd.get("y", 0)
        if t == "M":
            path.moveTo(x, y)
            ctrl_pts = []
        elif t == "L":
            path.lineTo(x, y)
            ctrl_pts = []
        elif t == "C":
            ctrl_pts.append(QPointF(x, y))
            if len(ctrl_pts) == 3:
                path.cubicTo(ctrl_pts[0], ctrl_pts[1], ctrl_pts[2])
                ctrl_pts = []
        elif t == "D":
            ctrl_pts.append(QPointF(x, y))
    return path


def _serialize_font(f: QFont) -> dict:
    return {"family": f.family(), "pointSize": f.pointSize(), "weight": f.weight()}


def _deserialize_font(d: dict) -> QFont:
    font = QFont(d.get("family", "Segoe UI"), d.get("pointSize", 24), d.get("weight", QFont.Bold))
    return font


# Pulsante X: contorno rotondo, sfondo teal molto sfumato
_TITLE_BAR_CLOSE_BTN_STYLE = """
    QPushButton#titleBarCloseBtn {
        background: qradialgradient(cx:0.5, cy:0.5, radius:0.6, fx:0.5, fy:0.5,
            stop:0 rgba(0, 255, 200, 0.12),
            stop:0.6 rgba(0, 255, 200, 0.04),
            stop:1 rgba(0, 255, 200, 0));
        color: #E6F1FF;
        border: 1px solid rgba(0, 255, 200, 0.4);
        border-radius: 16px;
        font-size: 22px;
        font-weight: 700;
    }
    QPushButton#titleBarCloseBtn:hover {
        background: qradialgradient(cx:0.5, cy:0.5, radius:0.6, fx:0.5, fy:0.5,
            stop:0 rgba(0, 255, 200, 0.12),
            stop:0.6 rgba(0, 255, 200, 0.04),
            stop:1 rgba(0, 255, 200, 0));
        color: #FFFFFF;
        border: 1px solid rgba(0, 255, 200, 0.4);
    }
"""


class _CloseButtonWithHover(QPushButton):
    """Pulsante X con animazione scale 1.05 su hover (150ms)."""
    _SIZE_NORMAL = 32
    _SIZE_HOVER = 34  # ~1.06x per effetto scale

    def __init__(self, parent=None):
        super().__init__("×", parent)
        self.setMinimumSize(self._SIZE_NORMAL, self._SIZE_NORMAL)
        self.setMaximumSize(self._SIZE_NORMAL, self._SIZE_NORMAL)
        self.setObjectName("titleBarCloseBtn")
        self.setStyleSheet(_TITLE_BAR_CLOSE_BTN_STYLE)
        self.setCursor(Qt.PointingHandCursor)
        self._anim_min = QPropertyAnimation(self, b"minimumSize")
        self._anim_max = QPropertyAnimation(self, b"maximumSize")
        for a in (self._anim_min, self._anim_max):
            a.setDuration(150)
            a.setEasingCurve(QEasingCurve.OutCubic)
        self._scale_group = QParallelAnimationGroup(self)
        self._scale_group.addAnimation(self._anim_min)
        self._scale_group.addAnimation(self._anim_max)

    def enterEvent(self, event):
        super().enterEvent(event)
        s = QSize(self._SIZE_NORMAL, self._SIZE_NORMAL)
        e = QSize(self._SIZE_HOVER, self._SIZE_HOVER)
        self._anim_min.setStartValue(s)
        self._anim_min.setEndValue(e)
        self._anim_max.setStartValue(s)
        self._anim_max.setEndValue(e)
        self._scale_group.start()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        s = QSize(self._SIZE_HOVER, self._SIZE_HOVER)
        e = QSize(self._SIZE_NORMAL, self._SIZE_NORMAL)
        self._anim_min.setStartValue(s)
        self._anim_min.setEndValue(e)
        self._anim_max.setStartValue(s)
        self._anim_max.setEndValue(e)
        self._scale_group.start()


class GradientTitleBar(QWidget):
    """Barra titolo con pulsante chiudi - sfondo uniforme al contenuto."""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._parent_dialog = parent
        self._drag_pos = None
        self.setFixedHeight(42)
        self.setCursor(Qt.ArrowCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(8)
        self._label = QLabel(title)
        self._label.setStyleSheet("color: #e5e7eb; font-size: 14px; font-weight: 600;")
        layout.addWidget(self._label)
        layout.addStretch()
        close_btn = _CloseButtonWithHover(self)
        close_btn.clicked.connect(lambda: parent.reject() if parent else None)
        layout.addWidget(close_btn)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(15, 20, 25))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.LeftButton and self._parent_dialog:
            delta = event.globalPos() - self._drag_pos
            self._parent_dialog.move(self._parent_dialog.pos() + delta)
            self._drag_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = None


def _set_rounded_mask(widget: QWidget, radius: int = 12):
    """Applica angoli arrotondati alla finestra."""
    try:
        path = QPainterPath()
        path.addRoundedRect(QRectF(widget.rect()), radius, radius)
        polyf = path.toFillPolygon()
        poly = QPolygon()
        for i in range(polyf.size()):
            pt = polyf.at(i)
            poly.append(QPoint(int(pt.x()), int(pt.y())))
        widget.setMask(QRegion(poly))
    except Exception:
        pass


class _RoundedDialogFilter(QObject):
    """Event filter per applicare mask angoli arrotondati su Show/Resize."""
    def __init__(self, radius=12):
        super().__init__()
        self._radius = radius

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show or event.type() == QEvent.Resize:
            try:
                path = QPainterPath()
                path.addRoundedRect(QRectF(obj.rect()), self._radius, self._radius)
                polyf = path.toFillPolygon()
                poly = QPolygon()
                for i in range(polyf.size()):
                    pt = polyf.at(i)
                    poly.append(QPoint(int(pt.x()), int(pt.y())))
                obj.setMask(QRegion(poly))
            except Exception:
                pass
        return False


class _DialogFadeInFilter(QObject):
    """Event filter per fade-in 150ms quando il dialog si apre."""
    def __init__(self, dialog: QDialog):
        self._dialog = dialog
        self._done = False
        super().__init__(dialog)

    def eventFilter(self, obj, event):
        dialog = getattr(self, "_dialog", None)
        if dialog is not None and obj is dialog and event.type() == QEvent.Show and not self._done:
            self._done = True
            eff = QGraphicsOpacityEffect(dialog)
            eff.setOpacity(0.0)
            dialog.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity")
            anim.setDuration(150)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)

            def on_finished():
                dialog.setGraphicsEffect(None)

            anim.finished.connect(on_finished)
            anim.start()
            self._fade_anim = anim  # keep ref
        return False


def _apply_pes_title_bar(dialog: QDialog, title: str):
    """Aggiunge header, angoli arrotondati e fade-in a un dialog."""
    dialog.setWindowFlags(dialog.windowFlags() | Qt.FramelessWindowHint)
    layout = dialog.layout()
    if layout is not None:
        bar = GradientTitleBar(title, dialog)
        layout.insertWidget(0, bar)
    dialog._round_filter = _RoundedDialogFilter()
    dialog.installEventFilter(dialog._round_filter)
    dialog._fade_filter = _DialogFadeInFilter(dialog)
    dialog.installEventFilter(dialog._fade_filter)


class _TransparentSwatchButton(QPushButton):
    """Quadretto a scacchi per selezionare colore trasparente nel color picker."""
    def __init__(self, dialog: QColorDialog, parent=None):
        super().__init__(parent)
        self._dialog = dialog
        self.setFixedSize(36, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Sfondo trasparente")
        self.clicked.connect(self._on_click)

    def _on_click(self):
        self._dialog.setCurrentColor(QColor(0, 0, 0, 0))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        sq = 4
        for i in range(0, self.width(), sq):
            for j in range(0, self.height(), sq):
                light = ((i // sq) + (j // sq)) % 2 == 0
                p.fillRect(i, j, sq, sq, QColor(255, 255, 255) if light else QColor(200, 200, 200))
        p.setPen(QPen(QColor(0x37, 0x41, 0x51)))
        p.drawRect(0, 0, self.width() - 1, self.height() - 1)


def pick_color_pes(parent, initial: QColor, allow_alpha: bool = False) -> QColor:
    """Apre QColorDialog con stile PES. Ritorna il colore selezionato o QColor invalido se annullato.
    Se allow_alpha=True, mostra il selettore alpha e un quadretto a scacchi per sfondo trasparente."""
    cd = QColorDialog(initial, parent)
    if allow_alpha:
        cd.setOption(QColorDialog.ShowAlphaChannel)
    cd.setStyleSheet("""
        QColorDialog { background: #0f1419; border-radius: 12px; border: 1px solid rgba(55, 65, 81, 0.8); }
        QColorDialog QWidget { background: #0f1419; color: #e5e7eb; }
        QPushButton { background: #1a2332; color: #e5e7eb; border: 1px solid #374151;
            border-radius: 6px; padding: 6px 14px; }
        QPushButton:hover { background: rgba(18, 168, 138, 0.2); border-color: #12a88a; }
        QPushButton#titleBarCloseBtn {
            background: rgba(0, 255, 200, 0.15); color: #E6F1FF; border: 1px solid rgba(0, 255, 200, 0.4);
            border-radius: 50%; font-size: 22px; font-weight: 700; padding: 0;
        }
        QPushButton#titleBarCloseBtn:hover { color: #FFFFFF; }
    """)
    _apply_pes_title_bar(cd, "Scegli colore")
    if allow_alpha:
        lay = cd.layout()
        if lay is not None:
            row = QHBoxLayout()
            row.addWidget(QLabel("Trasparente:"))
            swatch = _TransparentSwatchButton(cd, cd)
            swatch.setStyleSheet("background: transparent; border: none;")
            row.addWidget(swatch)
            row.addStretch()
            row_w = QWidget()
            row_w.setLayout(row)
            row_w.setStyleSheet("background: #0f1419; color: #e5e7eb;")
            lay.insertWidget(1, row_w)
    if cd.exec_() == QDialog.Accepted:
        c = cd.selectedColor()
        if c.isValid():
            return c
    return QColor()


class StyledIntDialog(QDialog):
    """Dialog per numero intero con header PES (sostituisce QInputDialog.getInt)."""
    def __init__(self, title: str, label: str, value: int, min_val: int, max_val: int, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setStyleSheet(_DIALOG_STYLE)
        self.setWindowTitle(title)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(GradientTitleBar(title, self))

        content = QWidget()
        content.setStyleSheet("background: #0f1419;")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(20, 16, 20, 20)
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        self._spin = QSpinBox()
        self._spin.setRange(min_val, max_val)
        self._spin.setValue(value)
        row.addWidget(self._spin)
        row.addStretch()
        c_layout.addLayout(row)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Annulla")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("btnAccent")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        c_layout.addLayout(btn_row)
        layout.addWidget(content)
        self._round_filter = _RoundedDialogFilter()
        self.installEventFilter(self._round_filter)
        self._fade_filter = _DialogFadeInFilter(self)
        self.installEventFilter(self._fade_filter)

    def value(self) -> int:
        return self._spin.value()


# Stile PES per dialog colore/spessore
_DIALOG_STYLE = """
    QDialog {
        background: #0f1419;
        border-radius: 12px;
        border: 1px solid rgba(55, 65, 81, 0.8);
    }
    QLabel {
        color: #e5e7eb;
        font-size: 13px;
        font-weight: 500;
    }
    QPushButton {
        background: #1a2332;
        color: #e5e7eb;
        border: 1px solid #374151;
        border-radius: 8px;
        padding: 10px 20px;
        font-size: 13px;
        font-weight: 500;
    }
    QPushButton:hover {
        background: rgba(18, 168, 138, 0.2);
        border-color: #12a88a;
        color: #19e6c1;
    }
    QPushButton#btnAccent {
        background: #12a88a;
        color: white;
        border-color: #12a88a;
    }
    QPushButton#btnAccent:hover {
        background: #0f9378;
    }
    QPushButton#titleBarCloseBtn {
        background: rgba(0, 255, 200, 0.15); color: #E6F1FF; border: 1px solid rgba(0, 255, 200, 0.4);
        border-radius: 50%; font-size: 22px; font-weight: 700; padding: 0;
    }
    QPushButton#titleBarCloseBtn:hover { color: #FFFFFF; }
    QSpinBox {
        background: #1a2332;
        color: #e5e7eb;
        border: 1px solid #374151;
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 13px;
        min-width: 60px;
    }
    QSpinBox:focus {
        border-color: #12a88a;
    }
"""


class ColorAndThicknessDialog(QDialog):
    """Dialog unificato colore + spessore - stile Pro Evolution Soccer."""
    def __init__(self, initial_color: QColor, initial_thickness: int, has_thickness: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Colore e spessore")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(_DIALOG_STYLE)
        self.setFixedSize(320, has_thickness and 220 or 180)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header con sfumatura
        self._title_bar = GradientTitleBar("Colore e spessore", self)
        layout.addWidget(self._title_bar)

        # Contenuto
        content = QWidget()
        content.setStyleSheet("background: #0f1419;")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(16)
        content_layout.setContentsMargins(20, 16, 20, 20)

        # Riga colore
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Colore:"))
        self._color_btn = QPushButton()
        self._color_btn.setFixedSize(40, 32)
        self._color_btn.setCursor(Qt.PointingHandCursor)
        self._color_btn.clicked.connect(self._pick_color)
        self._color = initial_color
        self._update_color_btn()
        color_row.addWidget(self._color_btn)
        color_row.addStretch()
        content_layout.addLayout(color_row)

        # Riga spessore (solo se ha linea)
        self._thickness_spin = None
        if has_thickness:
            thick_row = QHBoxLayout()
            thick_row.addWidget(QLabel("Spessore (px):"))
            self._thickness_spin = QSpinBox()
            self._thickness_spin.setRange(1, 20)
            self._thickness_spin.setValue(initial_thickness)
            thick_row.addWidget(self._thickness_spin)
            thick_row.addStretch()
            content_layout.addLayout(thick_row)

        # Pulsanti
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Annulla")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("btnAccent")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        content_layout.addLayout(btn_row)

        layout.addWidget(content)
        self._round_filter = _RoundedDialogFilter()
        self.installEventFilter(self._round_filter)
        self._fade_filter = _DialogFadeInFilter(self)
        self.installEventFilter(self._fade_filter)

    def _pick_color(self):
        cd = QColorDialog(self._color, self)
        cd.setWindowTitle("Scegli colore")
        cd.setStyleSheet("""
            QColorDialog { background: #0f1419; border-radius: 12px; border: 1px solid rgba(55, 65, 81, 0.8); }
            QColorDialog QWidget { background: #0f1419; color: #e5e7eb; }
            QPushButton { background: #1a2332; color: #e5e7eb; border: 1px solid #374151;
                border-radius: 6px; padding: 6px 14px; }
            QPushButton:hover { background: rgba(18, 168, 138, 0.2); border-color: #12a88a; }
            QPushButton#titleBarCloseBtn {
                background: rgba(0, 255, 200, 0.15); color: #E6F1FF; border: 1px solid rgba(0, 255, 200, 0.4);
                border-radius: 50%; font-size: 22px; font-weight: 700; padding: 0;
            }
            QPushButton#titleBarCloseBtn:hover { color: #FFFFFF; }
        """)
        _apply_pes_title_bar(cd, "Scegli colore")
        if cd.exec_() == QDialog.Accepted:
            c = cd.selectedColor()
            if c.isValid():
                self._color = c
                self._update_color_btn()

    def _update_color_btn(self):
        self._color_btn.setStyleSheet(
            f"background: {self._color.name()}; border: 2px solid #374151; border-radius: 6px;"
        )

    def get_color(self) -> QColor:
        return self._color

    def get_thickness(self) -> int:
        return self._thickness_spin.value() if self._thickness_spin else 8


class TextPersonalizeDialog(QDialog):
    """Dialog Personalizzazione testo: colore, sfondo, font, grassetto, corsivo, sottolineato."""
    def __init__(self, target: "DrawableText", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Personalizzazione testo")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setStyleSheet(_DIALOG_STYLE)
        self.setFixedSize(400, 400)
        self._target = target

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(GradientTitleBar("Personalizzazione testo", self))

        content = QWidget()
        content.setStyleSheet("background: #0f1419;")
        c = QVBoxLayout(content)
        c.setSpacing(12)
        c.setContentsMargins(20, 16, 20, 20)

        # Colore testo
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Colore testo:"))
        self._text_color_btn = QPushButton()
        self._text_color_btn.setFixedSize(40, 28)
        self._text_color_btn.setCursor(Qt.PointingHandCursor)
        self._text_color_btn.clicked.connect(self._pick_text_color)
        self._text_color = QColor(target._color)
        self._update_text_color_btn()
        r1.addWidget(self._text_color_btn)
        r1.addStretch()
        c.addLayout(r1)

        # Colore sfondo cella
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Colore sfondo cella:"))
        self._fill_color_btn = QPushButton()
        self._fill_color_btn.setFixedSize(40, 28)
        self._fill_color_btn.setCursor(Qt.PointingHandCursor)
        self._fill_color_btn.clicked.connect(self._pick_fill_color)
        self._fill_color = QColor(target._fill_color)
        self._update_fill_color_btn()
        r2.addWidget(self._fill_color_btn)
        r2.addStretch()
        c.addLayout(r2)

        # Font
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Font:"))
        self._font_combo = QComboBox()
        self._font_combo.setMinimumWidth(240)
        self._font_combo.setStyleSheet("""
            QComboBox {
                background: #1a2332;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 6px 12px;
                min-height: 24px;
            }
            QComboBox:hover { border-color: #12a88a; }
            QComboBox::drop-down {
                border: none;
                padding-right: 8px;
            }
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #1a2332;
                selection-background-color: #e5e7eb;
                selection-color: #0f1419;
                padding: 4px;
                min-width: 180px;
            }
        """)
        fonts = ["Arial", "Segoe UI", "Calibri", "Verdana", "Georgia", "Times New Roman", "Courier New", "Impact"]
        self._font_combo.addItems(fonts)
        f = target.font()
        idx = self._font_combo.findText(f.family())
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)
        else:
            self._font_combo.setCurrentIndex(0)
        r3.addWidget(self._font_combo, 1)
        r3.addStretch()
        c.addLayout(r3)

        # Dimensione
        r3b = QHBoxLayout()
        r3b.addWidget(QLabel("Dimensione:"))
        self._size_spin = QSpinBox()
        self._size_spin.setRange(8, 200)
        self._size_spin.setValue(f.pointSize())
        self._size_spin.setMinimumWidth(70)
        r3b.addWidget(self._size_spin)
        r3b.addStretch()
        c.addLayout(r3b)

        # Grassetto, Corsivo, Sottolineato
        r4 = QHBoxLayout()
        self._bold_cb = QCheckBox("Grassetto")
        self._bold_cb.setChecked(f.bold())
        self._bold_cb.setStyleSheet("color: #e5e7eb;")
        r4.addWidget(self._bold_cb)
        self._italic_cb = QCheckBox("Corsivo")
        self._italic_cb.setChecked(f.italic())
        self._italic_cb.setStyleSheet("color: #e5e7eb;")
        r4.addWidget(self._italic_cb)
        self._underline_cb = QCheckBox("Sottolineato")
        self._underline_cb.setChecked(f.underline())
        self._underline_cb.setStyleSheet("color: #e5e7eb;")
        r4.addWidget(self._underline_cb)
        r4.addStretch()
        c.addLayout(r4)

        # Pulsanti
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Annulla")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("btnAccent")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        c.addLayout(btn_row)

        layout.addWidget(content)
        self._round_filter = _RoundedDialogFilter()
        self.installEventFilter(self._round_filter)

    def _pick_text_color(self):
        c = pick_color_pes(self, self._text_color)
        if c.isValid():
            self._text_color = c
            self._update_text_color_btn()

    def _pick_fill_color(self):
        initial = self._fill_color if self._fill_color.alpha() > 0 else QColor(128, 128, 128, 0)
        c = pick_color_pes(self, initial, allow_alpha=True)
        if c.isValid():
            self._fill_color = c
            self._update_fill_color_btn()

    def _update_text_color_btn(self):
        self._text_color_btn.setStyleSheet(
            f"background: {self._text_color.name()}; border: 2px solid #374151; border-radius: 6px;"
        )

    def _update_fill_color_btn(self):
        if self._fill_color.alpha() == 0:
            self._fill_color_btn.setStyleSheet(
                "background: #1a2332; border: 1px dashed #374151; border-radius: 6px;"
            )
        else:
            self._fill_color_btn.setStyleSheet(
                f"background: {self._fill_color.name()}; border: 2px solid #374151; border-radius: 6px;"
            )

    def get_format(self) -> dict:
        """Ritorna il formato selezionato."""
        return {
            "text_color": QColor(self._text_color),
            "fill_color": QColor(self._fill_color),
            "font_family": self._font_combo.currentText(),
            "font_size": self._size_spin.value(),
            "bold": self._bold_cb.isChecked(),
            "italic": self._italic_cb.isChecked(),
            "underline": self._underline_cb.isChecked(),
        }


class DrawingOverlay(QGraphicsView):
    """Widget overlay trasparente per disegnare sul video - stile Kinovea."""
    drawingAdded = pyqtSignal(object)
    drawingConfirmed = pyqtSignal(object)  # Emesso quando annotazione confermata (da salvare come evento)
    drawingStarted = pyqtSignal()  # Emesso quando inizia il disegno (per freeze video)
    zoomRequested = pyqtSignal(int, int, int)  # delta, mouse_x, mouse_y (in coords overlay)
    annotationDeleted = pyqtSignal(str, int)  # event_id, ann_index (per displayed items)
    annotationModified = pyqtSignal(str, int, object)  # event_id, ann_index, new_data (dopo move/resize)
    emptyAreaLeftClicked = pyqtSignal(int, int)  # x, y - quando tool=NONE e click fuori dalle forme (per Web UI)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        # Event filter su view e viewport per intercettare right-click
        self.viewport().installEventFilter(self)
        self.installEventFilter(self)

        self._tool = DrawTool.NONE
        self._color = QColor("#FFFF00")
        self._pen_width = 8
        self._arrow_line_style = ArrowLineStyle.STRAIGHT
        self._start_pos: Optional[QPointF] = None
        self._current_item = None
        self._items: List[object] = []
        self._displayed_items: List[object] = []  # disegni caricati da project per timestamp corrente
        self._resize_handles: List[ResizeHandle] = []
        self._resize_target_item = None
        self._resize_drag_handle_index: Optional[int] = None
        self._resize_freehand_start_rect: Optional[QRectF] = None  # BBox originale al drag start
        self._resize_freehand_start_path: Optional[QPainterPath] = None  # Path originale al drag start
        self._pencil_path: Optional[QPainterPath] = None  # per disegno mano libera
        self._polygon_points: List[QPointF] = []  # vertici in costruzione (strumento Poligono)
        self._polygon_preview_item: Optional[QGraphicsPathItem] = None  # preview durante costruzione
        self._polygon_fill_style = PolygonFillStyle.SOLID
        self._polygon_opacity = 0.4
        self._selected_shape = None  # forma selezionata (mostra maniglie e bordo)
        self._clipboard_item = None  # dati per Copia/Incolla
        self._is_moving = False
        self._move_start_scene = None
        self._move_start_item_pos = None
        self._move_target_item = None  # item in trascinamento (testo o forma con maniglie)
        self._default_text_format: dict = {}  # formato per nuovo testo da TextFormatToolbar

        sc_copy = QShortcut(QKeySequence.Copy, self, self._copy_selected)
        sc_paste = QShortcut(QKeySequence.Paste, self, self._paste)
        sc_copy.setContext(Qt.ApplicationShortcut)
        sc_paste.setContext(Qt.ApplicationShortcut)

    def setSceneRectFromView(self, rect: QRectF):
        self.setSceneRect(rect)
        self.fitInView(rect, Qt.KeepAspectRatio)

    def _safe_remove_item(self, item):
        if item and item.scene() is self.scene():
            self.scene().removeItem(item)

    def _clear_resize_handles(self):
        if self._resize_target_item:
            self._resize_target_item.setSelected(False)
            self._resize_target_item.setZValue(0)
        for h in self._resize_handles:
            self._safe_remove_item(h)
        self._resize_handles.clear()
        self._resize_target_item = None
        self._resize_freehand_start_rect = None
        self._resize_freehand_start_path = None
        self._selected_shape = None

    def _select_shape(self, item):
        """Seleziona una forma: mostra maniglie e bordo di selezione."""
        if item not in self._items:
            return
        self._clear_resize_handles()
        self._selected_shape = item
        self._enter_resize_mode(item)

    def _deselect_shape(self):
        """Deseleziona: nasconde maniglie."""
        self._clear_resize_handles()

    def _copy_selected(self):
        """Copia la forma selezionata negli appunti (Ctrl+C)."""
        if self._selected_shape is None or self._selected_shape not in self._items:
            return
        self._clipboard_item = self._item_to_copy_data(self._selected_shape)

    def _paste(self):
        """Incolla la forma dagli appunti (Ctrl+V). Nessun effetto se nulla in clipboard."""
        if self._clipboard_item is None:
            return
        new_item = self._copy_data_to_item(self._clipboard_item, offset_x=15, offset_y=15)
        if new_item is not None:
            self.scene().addItem(new_item)
            self._items.append(new_item)
            self.drawingAdded.emit(new_item)
            self._select_shape(new_item)

    def item_to_serializable_data(self, item) -> Optional[dict]:
        """Converte item overlay in dict JSON-serializzabile per DrawingItem.data."""
        raw = self._item_to_copy_data(item)
        if not raw:
            return None
        return self._copy_data_to_serializable(raw)

    def _copy_data_to_serializable(self, data: dict) -> dict:
        """Converte copy_data (Qt types) in dict serializzabile."""
        out = {}
        for k, v in data.items():
            if isinstance(v, QPointF):
                out[k] = _serialize_point(v)
            elif isinstance(v, QRectF):
                out[k] = _serialize_rect(v)
            elif isinstance(v, QColor):
                out[k] = _serialize_color(v)
            elif isinstance(v, QFont):
                out[k] = _serialize_font(v)
            elif isinstance(v, QPainterPath):
                out[k] = _serialize_path(v)
            elif isinstance(v, (list, tuple)) and v and isinstance(v[0], QPointF):
                out[k] = [_serialize_point(p) for p in v]
            elif hasattr(v, "value"):  # ArrowLineStyle enum
                out[k] = v.value if hasattr(v, "value") else str(v)
            else:
                out[k] = v
        return out

    def _serializable_to_copy_data(self, data: dict) -> dict:
        """Converte dict serializzato in copy_data (Qt types) per _copy_data_to_item."""
        out = {}
        for k, v in data.items():
            if k in ("pos", "p1", "p2", "ctrl") and isinstance(v, dict):
                out[k] = _deserialize_point(v)
            elif k == "rect" and isinstance(v, dict):
                out[k] = _deserialize_rect(v)
            elif k == "color" and isinstance(v, str):
                out[k] = _deserialize_color(v)
            elif k == "font" and isinstance(v, dict):
                out[k] = _deserialize_font(v)
            elif k == "path" and isinstance(v, list):
                out[k] = _deserialize_path(v)
            elif k == "points" and isinstance(v, list):
                out[k] = [_deserialize_point(p) if isinstance(p, dict) else p for p in v]
            elif k == "style" and isinstance(v, str):
                out[k] = next((s for s in ArrowLineStyle if s.value == v), ArrowLineStyle.STRAIGHT)
            elif k == "fill_style" and isinstance(v, str):
                out[k] = PolygonFillStyle(v) if v in (e.value for e in PolygonFillStyle) else PolygonFillStyle.SOLID
            else:
                out[k] = v
        return out

    def _item_to_copy_data(self, item) -> Optional[dict]:
        """Estrae dati serializzabili dalla forma per la clipboard."""
        pos = item.scenePos()
        if isinstance(item, DrawableCircle):
            return {"type": "circle", "rect": item.rect(), "pos": pos, "color": item._color,
                    "pen_width": item.pen().width()}
        if isinstance(item, DrawableRectangle):
            return {"type": "rectangle", "rect": item.rect(), "pos": pos, "color": item._color,
                    "pen_width": item.pen().width()}
        if isinstance(item, DrawableArrow):
            p1_scene = QPointF(pos.x() + item.line().p1().x(), pos.y() + item.line().p1().y())
            p2_scene = QPointF(pos.x() + item.line().p2().x(), pos.y() + item.line().p2().y())
            return {"type": "arrow", "p1": p1_scene, "p2": p2_scene,
                    "color": item._color, "width": item._width, "style": item._style,
                    "head_start": item._head_at_start}
        if isinstance(item, DrawableLine):
            p1_scene = QPointF(pos.x() + item.line().p1().x(), pos.y() + item.line().p1().y())
            p2_scene = QPointF(pos.x() + item.line().p2().x(), pos.y() + item.line().p2().y())
            return {"type": "line", "p1": p1_scene, "p2": p2_scene,
                    "color": item._color, "width": item._width, "style": item._style}
        if isinstance(item, DrawableCone):
            poly = [QPointF(p) for p in item.polygon()]
            return {"type": "cone", "points": poly, "pos": pos, "color": item._color}
        if isinstance(item, DrawablePolygon):
            poly = [QPointF(p) for p in item.polygon()]
            return {"type": "polygon", "points": poly, "pos": pos, "color": item._color,
                    "fill_style": item._fill_style.value, "opacity": item._opacity}
        if isinstance(item, DrawableText):
            fmt = item.get_format()
            fc = fmt.get("fill_color")
            fill_hex = fc.name() if isinstance(fc, QColor) and fc.alpha() > 0 else None
            oc = fmt.get("outline_color")
            outline_hex = oc.name() if isinstance(oc, QColor) else None
            return {"type": "text", "text": item.toPlainText(), "pos": pos, "color": item._color,
                    "font": item.font(), "fill_color": fill_hex, "opacity": fmt.get("opacity", 1.0),
                    "outline_width": fmt.get("outline_width", 0), "outline_color": outline_hex}
        if isinstance(item, DrawableFreehand):
            return {"type": "freehand", "path": QPainterPath(item.path()), "pos": pos,
                    "color": item._color, "pen_width": item.pen().width()}
        if isinstance(item, (DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow)):
            pts = item.getPoints()
            pts_scene = [item.mapToScene(p) for p in pts]
            tname = "curved_line" if isinstance(item, DrawableCurvedLine) else (
                "curved_arrow" if isinstance(item, DrawableCurvedArrow) else "parabola_arrow")
            return {"type": tname, "p1": pts_scene[0], "ctrl": pts_scene[1], "p2": pts_scene[2],
                    "pos": item.scenePos(), "color": item._color, "pen_width": item._pen_width}
        return None

    def _copy_data_to_item(self, data: dict, offset_x: float = 0, offset_y: float = 0):
        """Crea una nuova forma dai dati con offset."""
        if not data:
            return None
        pos = data.get("pos", QPointF(0, 0))
        new_pos = QPointF(pos.x() + offset_x, pos.y() + offset_y)
        t = data.get("type")
        if t == "circle":
            item = DrawableCircle(data["rect"], data["color"], data.get("pen_width", 8))
            item.setPos(new_pos)
            return item
        if t == "rectangle":
            item = DrawableRectangle(data["rect"], data["color"], data.get("pen_width", 8))
            item.setPos(new_pos)
            return item
        if t == "arrow":
            p1, p2 = data["p1"], data["p2"]
            # p1, p2 sono in scene; con offset
            np1 = QPointF(p1.x() + offset_x, p1.y() + offset_y)
            np2 = QPointF(p2.x() + offset_x, p2.y() + offset_y)
            item = DrawableArrow(np1.x(), np1.y(), np2.x(), np2.y(), data["color"],
                                data.get("width", 8), data.get("style", ArrowLineStyle.STRAIGHT),
                                data.get("head_start", False))
            item.setPos(0, 0)
            return item
        if t == "line":
            p1, p2 = data["p1"], data["p2"]
            np1 = QPointF(p1.x() + offset_x, p1.y() + offset_y)
            np2 = QPointF(p2.x() + offset_x, p2.y() + offset_y)
            item = DrawableLine(np1.x(), np1.y(), np2.x(), np2.y(), data["color"],
                               data.get("width", 8), data.get("style", ArrowLineStyle.STRAIGHT))
            item.setPos(0, 0)
            return item
        if t == "cone":
            item = DrawableCone(data["points"], data["color"])
            item.setPos(new_pos)
            return item
        if t == "polygon":
            pts = data.get("points", [])
            if pts and isinstance(pts[0], dict):
                pts = [_deserialize_point(p) for p in pts]
            pts = [QPointF(p.x() + offset_x, p.y() + offset_y) for p in pts]
            style = PolygonFillStyle(data.get("fill_style", "solid"))
            item = DrawablePolygon(pts, data["color"], style, data.get("opacity", 0.4))
            item.setPos(0, 0)
            return item
        if t == "text":
            item = DrawableText(data.get("text", ""), data["color"])
            if "font" in data and data["font"]:
                item.setFont(data["font"])
            if "fill_color" in data and data["fill_color"]:
                item._fill_color = QColor(str(data["fill_color"]))
            if "opacity" in data:
                item.setOpacity(float(data["opacity"]))
            if "outline_width" in data and data["outline_width"]:
                item._outline_width = int(data["outline_width"])
            if "outline_color" in data and data["outline_color"]:
                item._outline_color = QColor(str(data["outline_color"]))
            item.setPos(new_pos)
            return item
        if t == "freehand":
            item = DrawableFreehand(data["path"], data["color"], data.get("pen_width", 8))
            item.setPos(new_pos)
            return item
        if t == "curved_line":
            p1 = QPointF(data["p1"].x() + offset_x, data["p1"].y() + offset_y)
            ctrl = QPointF(data["ctrl"].x() + offset_x, data["ctrl"].y() + offset_y)
            p2 = QPointF(data["p2"].x() + offset_x, data["p2"].y() + offset_y)
            item = DrawableCurvedLine(p1, ctrl, p2, data["color"], data.get("pen_width", 8))
            item.setPos(0, 0)
            return item
        if t == "curved_arrow":
            p1 = QPointF(data["p1"].x() + offset_x, data["p1"].y() + offset_y)
            ctrl = QPointF(data["ctrl"].x() + offset_x, data["ctrl"].y() + offset_y)
            p2 = QPointF(data["p2"].x() + offset_x, data["p2"].y() + offset_y)
            item = DrawableCurvedArrow(p1, ctrl, p2, data["color"], data.get("pen_width", 8))
            item.setPos(0, 0)
            return item
        if t == "parabola_arrow":
            p1 = QPointF(data["p1"].x() + offset_x, data["p1"].y() + offset_y)
            ctrl = QPointF(data["ctrl"].x() + offset_x, data["ctrl"].y() + offset_y)
            p2 = QPointF(data["p2"].x() + offset_x, data["p2"].y() + offset_y)
            item = DrawableParabolaArrow(p1, ctrl, p2, data["color"], data.get("pen_width", 8))
            item.setPos(0, 0)
            return item
        return None

    def _get_item_at_border(self, scene_pos: QPointF):
        """Ritorna l'item disegnabile sotto scene_pos (usa shape per hit su bordo)."""
        item = self.scene().itemAt(scene_pos, self.transform())
        return self._find_drawable_item(item)

    def setTool(self, tool: DrawTool):
        self._tool = tool
        self._start_pos = None
        self._pencil_path = None
        self._polygon_points = []
        self._remove_polygon_preview()
        self._safe_remove_item(self._current_item)
        self._current_item = None
        self._clear_resize_handles()

    def setColor(self, color: QColor):
        self._color = color

    def setPenWidth(self, w: int):
        self._pen_width = w

    def penWidth(self) -> int:
        return self._pen_width

    def set_default_text_format(self, fmt: dict):
        """Formato predefinito per nuovo testo (da TextFormatToolbar)."""
        self._default_text_format = dict(fmt) if fmt else {}

    def apply_format_to_selected_text(self, fmt: dict):
        """Applica formato al testo selezionato (se presente)."""
        item = self.get_selected_text_item()
        if item:
            item.apply_format(fmt)
            item.update()

    def get_selected_text_item(self) -> Optional["DrawableText"]:
        """Ritorna il DrawableText selezionato o con focus, se presente."""
        fi = self.scene().focusItem()
        if isinstance(fi, DrawableText):
            return fi
        sel = self.scene().selectedItems()
        for it in sel:
            if isinstance(it, DrawableText):
                return it
        return None

    def setArrowLineStyle(self, style: ArrowLineStyle):
        self._arrow_line_style = style

    def _start_freeze(self):
        """Notifica l'inizio del disegno per il freeze del video."""
        self.drawingStarted.emit()

    def _emit_text_confirmed(self, item):
        """Chiamato da DrawableText.focusOutEvent quando la modifica è terminata."""
        if item in self._items:
            self.drawingConfirmed.emit(item)

    def wheelEvent(self, event: QWheelEvent):
        """Con strumento Zoom attivo: zoom continuo (max 5x) via rotella verso il puntatore."""
        if self._tool == DrawTool.ZOOM:
            pos = event.pos()
            self.zoomRequested.emit(event.angleDelta().y(), int(pos.x()), int(pos.y()))
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            # Se clicchi su una maniglia di resize: inizia drag ridimensionamento
            handle_idx = self._get_resize_handle_index_at(scene_pos)
            if handle_idx is not None:
                self._resize_drag_handle_index = handle_idx
                self._is_moving = False
                # Per freehand: memorizza bbox e path originali al drag start (come rettangolo/cerchio)
                if isinstance(self._resize_target_item, DrawableFreehand):
                    self._resize_freehand_start_rect = QRectF(self._resize_target_item.sceneBoundingRect())
                    self._resize_freehand_start_path = QPainterPath(self._resize_target_item.path())
                else:
                    self._resize_freehand_start_rect = None
                    self._resize_freehand_start_path = None
                event.accept()
                return
            # Se clicchi sul bordo di una forma
            hit_item = self._get_item_at_border(scene_pos)
            if hit_item is not None and (hit_item in self._items or hit_item in self._displayed_items):
                # Forma già selezionata: inizia trascinamento per spostare
                is_selected_for_move = (
                    hit_item == self._resize_target_item or
                    (isinstance(hit_item, DrawableText) and hit_item == self._selected_shape)
                )
                if is_selected_for_move:
                    self._is_moving = True
                    self._move_start_scene = scene_pos
                    self._move_start_item_pos = hit_item.scenePos()
                    self._move_target_item = hit_item
                    event.accept()
                    return
                # Altra forma: seleziona
                self._select_shape(hit_item)
                event.accept()
                return
            # Clic fuori: deseleziona (ma non se stiamo costruendo un poligono)
            if self._tool != DrawTool.POLYGON or not self._polygon_points:
                self._deselect_shape()
                self._resize_drag_handle_index = None
                self._is_moving = False
                self._move_target_item = None
                # Tool NONE + click su area vuota: segnale per Web UI (video click)
                if self._tool == DrawTool.NONE:
                    scene_pos = self.mapToScene(event.pos())
                    self.emptyAreaLeftClicked.emit(int(scene_pos.x()), int(scene_pos.y()))
                    event.accept()
                    return
        if event.button() == Qt.LeftButton and self._tool == DrawTool.POLYGON:
            scene_pos = self.mapToScene(event.pos())
            self._start_freeze()
            CLOSE_TOLERANCE = 15
            if len(self._polygon_points) >= 3:
                first = self._polygon_points[0]
                dist = math.sqrt((scene_pos.x() - first.x())**2 + (scene_pos.y() - first.y())**2)
                if dist <= CLOSE_TOLERANCE:
                    self._finish_polygon()
                    event.accept()
                    return
            self._polygon_points.append(QPointF(scene_pos))
            self._update_polygon_preview(None)  # senza cursore; linea al cursore in mouseMove
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._tool == DrawTool.TEXT:
            scene_pos = self.mapToScene(event.pos())
            self._clear_resize_handles()
            self._start_freeze()
            fmt = self._default_text_format
            color = fmt.get("text_color", QColor(Qt.white)) if fmt else QColor(Qt.white)
            item = DrawableText("", color)
            if fmt:
                item.apply_format(fmt)
            item.setPos(scene_pos)
            item.setTextInteractionFlags(Qt.TextEditorInteraction)
            item._confirm_callback = lambda it=item: self._emit_text_confirmed(it)
            self.scene().addItem(item)
            self._items.append(item)
            self.drawingAdded.emit(item)
            self.scene().setFocusItem(item)
            self.setFocus()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._tool not in (DrawTool.NONE, DrawTool.ZOOM, DrawTool.POLYGON):
            scene_pos = self.mapToScene(event.pos())
            self._clear_resize_handles()
            self._start_pos = scene_pos
            self._start_freeze()
            if self._tool == DrawTool.PENCIL:
                self._pencil_path = QPainterPath()
                self._pencil_path.moveTo(scene_pos)
        super().mousePressEvent(event)

    def eventFilter(self, obj, event):
        """Intercetta right-click per menu contestuale sul testo."""
        if obj not in (self, self.viewport()):
            return super().eventFilter(obj, event)
        # ContextMenu oppure MouseButtonPress con destro (prima che la view lo converta in scene event)
        is_right_click = (
            event.type() == QEvent.ContextMenu or
            (event.type() == QEvent.MouseButtonPress and event.button() == Qt.RightButton)
        )
        if is_right_click:
            import logging
            logging.debug(f"[DRAW] Right-click ricevuto: obj={type(obj).__name__} event={event.type()}")
            # event.pos() è relativo a obj; converti in coordinate view
            view_pos = obj.mapTo(self, event.pos()) if obj is self.viewport() else event.pos()
            scene_pos = self.mapToScene(view_pos)
            tol = 25
            r = QRectF(scene_pos.x() - tol, scene_pos.y() - tol, tol * 2, tol * 2)
            target = None
            for it in self.scene().items(r, Qt.IntersectsItemShape, Qt.DescendingOrder):
                if it in self._items or it in self._displayed_items:
                    target = it
                    break
                t = self._find_drawable_item(it)
                if t is not None:
                    target = t
                    break
            gp = event.globalPos()
            global_pt = QPoint(gp.x(), gp.y()) if hasattr(gp, 'x') else self.mapToGlobal(event.pos())
            self._show_context_menu(global_pt, target)
            event.accept()
            return True  # Consuma l'evento, impedisce elaborazione successiva
        return super().eventFilter(obj, event)

    def _on_context_menu_requested(self, view_pos):
        """Chiamato su tasto destro. view_pos è in coordinate della view."""
        scene_pos = self.mapToScene(view_pos)
        tol = 20
        r = QRectF(scene_pos.x() - tol, scene_pos.y() - tol, tol * 2, tol * 2)
        target = None
        for it in self.scene().items(r, Qt.IntersectsItemShape, Qt.DescendingOrder):
            if it in self._items or it in self._displayed_items:
                target = it
                break
            t = self._find_drawable_item(it)
            if t is not None:
                target = t
                break
        global_pos = self.mapToGlobal(view_pos)
        self._show_context_menu(global_pos, target)

    def mouseDoubleClickEvent(self, event):
        """Doppio clic con strumento Poligono: chiude il poligono."""
        if event.button() == Qt.LeftButton and self._tool == DrawTool.POLYGON and len(self._polygon_points) >= 3:
            self._finish_polygon()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _remove_polygon_preview(self):
        """Rimuove l'item di preview del poligono dalla scena."""
        self._safe_remove_item(self._polygon_preview_item)
        self._polygon_preview_item = None

    def _update_polygon_preview(self, mouse_scene_pos: Optional[QPointF] = None):
        """Aggiorna la preview: linee tra i vertici e linea fino al cursore (se fornito)."""
        self._remove_polygon_preview()
        if not self._polygon_points:
            return
        path = QPainterPath()
        path.moveTo(self._polygon_points[0])
        for i in range(1, len(self._polygon_points)):
            path.lineTo(self._polygon_points[i])
        if mouse_scene_pos is not None:
            path.lineTo(mouse_scene_pos)
        self._polygon_preview_item = QGraphicsPathItem(path)
        self._polygon_preview_item.setPen(QPen(self._color, self._pen_width))
        self._polygon_preview_item.setBrush(QBrush(Qt.NoBrush))
        self._polygon_preview_item.setZValue(-1)  # sotto gli altri elementi
        self.scene().addItem(self._polygon_preview_item)

    def _finish_polygon(self):
        """Chiude il poligono in costruzione e lo salva come annotazione."""
        if len(self._polygon_points) < 3:
            self._polygon_points = []
            self._remove_polygon_preview()
            return
        self._remove_polygon_preview()
        pts = [QPointF(p) for p in self._polygon_points]
        poly = DrawablePolygon(pts, self._color)
        poly.setFillStyle(self._polygon_fill_style)
        poly.setOpacity(self._polygon_opacity)
        poly.setPos(0, 0)  # punti già in coordinate scena
        self.scene().addItem(poly)
        self._items.append(poly)
        self.drawingAdded.emit(poly)
        self.drawingConfirmed.emit(poly)
        self._polygon_points = []
        self._remove_polygon_preview()

    # Stile menu contestuale (tipo Pro Evolution Soccer: elegante, scuro, arrotondato)
    _CONTEXT_MENU_STYLE = """
        QMenu {
            background: rgba(15, 20, 25, 0.96);
            border: 1px solid rgba(55, 65, 81, 0.8);
            border-radius: 10px;
            padding: 6px 2px;
            min-width: 200px;
            font-size: 13px;
            font-weight: 500;
        }
        QMenu::item {
            padding: 10px 20px;
            color: #e5e7eb;
            border-radius: 6px;
            margin: 1px 6px;
        }
        QMenu::item:selected {
            background: rgba(18, 168, 138, 0.25);
            color: #19e6c1;
        }
        QMenu::item:disabled {
            color: #6b7280;
        }
        QMenu::separator {
            height: 1px;
            background: rgba(55, 65, 81, 0.6);
            margin: 6px 12px;
        }
    """

    def _show_context_menu(self, pos, item):
        """Menu contestuale sul tasto destro."""
        target = self._find_drawable_item(item)
        if target is None or (target not in self._items and target not in self._displayed_items):
            return
        is_text = isinstance(target, DrawableText)

        # Testo: menu Personalizzazione, Duplica, Elimina
        if is_text:
            menu = QMenu(self)
            menu.setStyleSheet(self._CONTEXT_MENU_STYLE)
            personalizza_action = menu.addAction("Personalizzazione")
            menu.addSeparator()
            duplica_action = menu.addAction("Duplica")
            menu.addSeparator()
            elimina_action = menu.addAction("Elimina")
            action = menu.exec_(pos)
            if action == personalizza_action:
                dlg = TextPersonalizeDialog(target, self)
                if dlg.exec_() == QDialog.Accepted:
                    fmt = dlg.get_format()
                    target.apply_format(fmt)
                    target.update()
                    self.set_default_text_format(fmt)
                    self._persist_displayed_item_if_needed(target)
            elif action == duplica_action:
                data = self._item_to_copy_data(target)
                if data:
                    new_item = self._copy_data_to_item(data, offset_x=15, offset_y=15)
                    if new_item:
                        self.scene().addItem(new_item)
                        self._items.append(new_item)
                        self.drawingAdded.emit(new_item)
                        self._select_shape(new_item)
            elif action == elimina_action:
                ref = target.data(Qt.UserRole) if hasattr(target, "data") else None
                if isinstance(ref, dict) and "event_id" in ref and "ann_index" in ref:
                    self.annotationDeleted.emit(ref["event_id"], ref["ann_index"])
                if target in self._items:
                    self._items.remove(target)
                if target in self._displayed_items:
                    self._displayed_items.remove(target)
                self._safe_remove_item(target)
                self._clear_resize_handles()
            return

        menu = QMenu(self)
        menu.setStyleSheet(self._CONTEXT_MENU_STYLE)
        has_line = isinstance(target, (DrawableCircle, DrawableRectangle, DrawableArrow,
                                       DrawableLine, DrawableFreehand,
                                       DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow))
        has_thickness = has_line or isinstance(target, DrawablePolygon)
        style_action = menu.addAction("Colore e spessore") if has_thickness else menu.addAction("Modifica colore")
        is_polygon = isinstance(target, DrawablePolygon)
        fill_solid_action = menu.addAction("Fill pieno trasparente") if is_polygon else None
        fill_stripes_action = menu.addAction("Fill a righe") if is_polygon else None
        opacity_action = menu.addAction("Opacità...") if is_polygon else None
        menu.addSeparator()
        duplica_action = menu.addAction("Duplica")
        menu.addSeparator()
        delete_action = menu.addAction("Elimina")
        action = menu.exec_(pos)
        if action == fill_solid_action and is_polygon:
            target.setFillStyle(PolygonFillStyle.SOLID)
            target.update()
            self._persist_displayed_item_if_needed(target)
        elif action == fill_stripes_action and is_polygon:
            target.setFillStyle(PolygonFillStyle.STRIPES)
            target.update()
            self._persist_displayed_item_if_needed(target)
        elif action == opacity_action and is_polygon:
            cur = int(target._opacity * 100)
            dlg = StyledIntDialog("Opacità", "Opacità (20-60%):", cur, 20, 60, self)
            if dlg.exec_() == QDialog.Accepted:
                v = dlg.value()
                target.setOpacity(v / 100.0)
                target.update()
                self._persist_displayed_item_if_needed(target)
        elif action == style_action:
            current_color = target._color if hasattr(target, "_color") else target.pen().color()
            if isinstance(target, (DrawableArrow, DrawableLine)):
                current_thick = target._width
            elif isinstance(target, (DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow)):
                current_thick = target._pen_width
            elif isinstance(target, DrawablePolygon):
                current_thick = int(target.pen().widthF()) if target.pen().widthF() > 0 else 2
            else:
                current_thick = int(target.pen().widthF()) if target.pen().widthF() > 0 else 8
            dlg = ColorAndThicknessDialog(current_color, current_thick, has_thickness, self)
            if dlg.exec_() == QDialog.Accepted:
                c = dlg.get_color()
                target.setDrawColor(c)
                if hasattr(target, "_color"):
                    target._color = c
                if has_thickness:
                    w = dlg.get_thickness()
                    if isinstance(target, (DrawableArrow, DrawableLine)):
                        target._width = w
                        target._update_path()
                    elif isinstance(target, (DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow)):
                        target._pen_width = w
                        target._update_path()
                    else:
                        target.setPen(QPen(c, w))
                target.update()
                self._persist_displayed_item_if_needed(target)
        elif action == delete_action:
            ref = target.data(Qt.UserRole) if hasattr(target, "data") else None
            if isinstance(ref, dict) and "event_id" in ref and "ann_index" in ref:
                self.annotationDeleted.emit(ref["event_id"], ref["ann_index"])
            if target in self._items:
                self._items.remove(target)
            if target in self._displayed_items:
                self._displayed_items.remove(target)
            self._safe_remove_item(target)
            self._clear_resize_handles()
        elif action == duplica_action:
            data = self._item_to_copy_data(target)
            if data:
                new_item = self._copy_data_to_item(data, offset_x=15, offset_y=15)
                if new_item:
                    self.scene().addItem(new_item)
                    self._items.append(new_item)
                    self.drawingAdded.emit(new_item)
                    self._select_shape(new_item)

    def _persist_displayed_item_if_needed(self, item):
        """Salva modifiche nell'evento se l'item è un'annotazione caricata (displayed)."""
        if item not in self._displayed_items:
            return
        ref = item.data(Qt.UserRole) if hasattr(item, "data") else None
        if isinstance(ref, dict) and "event_id" in ref and "ann_index" in ref:
            new_data = self.item_to_serializable_data(item)
            if new_data:
                self.annotationModified.emit(ref["event_id"], ref["ann_index"], new_data)

    def is_editing_text(self) -> bool:
        """True se l'utente sta modificando un DrawableText (non intercettare Space, ecc.)."""
        fi = self.scene().focusItem() if self.scene() else None
        return (
            fi is not None
            and isinstance(fi, DrawableText)
            and fi.textInteractionFlags() == Qt.TextEditorInteraction
        )

    def _find_drawable_item(self, item):
        """Trova l'item disegnabile (può essere sotto altri o un figlio)."""
        if item is None:
            return None
        while item is not None:
            if item in self._items or item in self._displayed_items:
                return item
            item = item.parentItem()
        return None

    def _get_resize_handle_index_at(self, scene_pos) -> Optional[int]:
        """Ritorna l'indice della maniglia sotto scene_pos, o None."""
        item = self.scene().itemAt(scene_pos, self.transform())
        if isinstance(item, ResizeHandle):
            return item._handle_index
        return None

    def _get_arrow_line_handle_scene_positions(self, item):
        """Posizioni maniglie in coordinate scena per frecce/linee."""
        line = item.line()
        pos = item.scenePos()
        p1 = QPointF(pos.x() + line.p1().x(), pos.y() + line.p1().y())
        p2 = QPointF(pos.x() + line.p2().x(), pos.y() + line.p2().y())
        return [p1, p2]

    def _enter_resize_mode(self, item):
        """Attiva modalità ridimensionamento con maniglie (angoli + lati). Testo: solo selezione."""
        if isinstance(item, DrawableText):
            self._resize_target_item = None
            item.setSelected(True)
            self._selected_shape = item
            return
        if not isinstance(item, (QGraphicsEllipseItem, QGraphicsRectItem, DrawableCircle, DrawableRectangle,
                                 DrawableArrow, DrawableLine, DrawableCone, DrawableFreehand,
                                 DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow,
                                 DrawablePolygon)):
            return
        self._resize_target_item = item
        item.setZValue(9998)  # sopra altri item, sotto le maniglie
        self._resize_handles = []
        if isinstance(item, (DrawableArrow, DrawableLine)):
            handles_pos = self._get_arrow_line_handle_scene_positions(item)
        elif isinstance(item, (DrawableCone, DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow)):
            handles_pos = self._get_three_point_handle_scene_positions(item)
        elif isinstance(item, DrawablePolygon):
            handles_pos = self._get_polygon_handle_scene_positions(item)
        else:
            handles_pos = self._get_rect_ellipse_handle_scene_positions(item)
        for i, hp in enumerate(handles_pos):
            h = ResizeHandle(self, item, i)
            h.setPos(hp)
            self.scene().addItem(h)
            self._resize_handles.append(h)
        self._resize_target_item.setSelected(True)
        self.scene().invalidate()
        self.update()

    def _get_rect_ellipse_handle_scene_positions(self, item):
        """8 maniglie: angoli + punti medi dei lati."""
        br = item.sceneBoundingRect()
        cx = br.center().x()
        cy = br.center().y()
        return [
            br.topLeft(), QPointF(cx, br.top()),
            br.topRight(), QPointF(br.right(), cy),
            br.bottomRight(), QPointF(cx, br.bottom()),
            br.bottomLeft(), QPointF(br.left(), cy)
        ]

    def _get_cone_handle_scene_positions(self, item):
        """3 maniglie ai vertici del cono."""
        poly = item.polygon()
        pos = item.scenePos()
        return [QPointF(pos.x() + p.x(), pos.y() + p.y()) for p in poly]

    def _get_polygon_handle_scene_positions(self, item: DrawablePolygon):
        """Una maniglia per ogni vertice del poligono (pos = 0,0)."""
        poly = item.polygon()
        return [item.mapToScene(QPointF(p.x(), p.y())) for p in poly]

    def _get_three_point_handle_scene_positions(self, item):
        """3 maniglie per forme con 3 punti (cono, linea curva, freccia curva, parabola)."""
        if isinstance(item, DrawableCone):
            poly = item.polygon()
            pos = item.scenePos()
            return [QPointF(pos.x() + p.x(), pos.y() + p.y()) for p in poly]
        if isinstance(item, (DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow)):
            pts = item.getPoints()
            return [item.mapToScene(p) for p in pts]
        return []

    def _reposition_resize_handles(self):
        """Riposiziona le maniglie sull'item target."""
        item = self._resize_target_item
        if not item or not self._resize_handles:
            return
        if isinstance(item, (DrawableArrow, DrawableLine)):
            handles_pos = self._get_arrow_line_handle_scene_positions(item)
        elif isinstance(item, (DrawableCone, DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow)):
            handles_pos = self._get_three_point_handle_scene_positions(item)
        elif isinstance(item, DrawablePolygon):
            handles_pos = self._get_polygon_handle_scene_positions(item)
        elif isinstance(item, DrawableFreehand):
            handles_pos = self._get_rect_ellipse_handle_scene_positions(item)
        else:
            handles_pos = self._get_rect_ellipse_handle_scene_positions(item)
        for h, hp in zip(self._resize_handles, handles_pos):
            h.setPos(hp)

    def _scale_freehand_path_to_bounds(self, item: DrawableFreehand, original_path: QPainterPath, new_local_rect: QRectF):
        """Scala il path originale al nuovo bounding box. Usa la bbox originale del path, scale factor può essere < 1."""
        old_br = original_path.boundingRect()
        if old_br.width() < 0.01 or old_br.height() < 0.01:
            return
        tr = QTransform()
        tr.translate(-old_br.left(), -old_br.top())
        tr.scale(new_local_rect.width() / old_br.width(), new_local_rect.height() / old_br.height())
        tr.translate(new_local_rect.left(), new_local_rect.top())
        item.setPath(tr.map(original_path))

    def _get_freehand_new_rect_from_anchor_and_drag(self, drag_handle_index: int, scene_pos: QPointF) -> Optional[QRectF]:
        """Calcola il nuovo rect in scene basandosi sulla bbox ORIGINALE (anchor fissa) e sulla posizione del drag.
        Come rettangolo/cerchio: l'angolo/bordo opposto resta fisso, scale factor può essere < 1."""
        if self._resize_freehand_start_rect is None:
            return None
        r = self._resize_freehand_start_rect
        # 0:TL 1:top 2:TR 3:right 4:BR 5:bottom 6:BL 7:left
        if drag_handle_index == 0:    # TopLeft: anchor = BR
            new_rect = QRectF(scene_pos, QPointF(r.right(), r.bottom()))
        elif drag_handle_index == 1:  # Top: anchor = bottom
            new_rect = QRectF(QPointF(r.left(), scene_pos.y()), QPointF(r.right(), r.bottom()))
        elif drag_handle_index == 2:  # TopRight: anchor = BL
            new_rect = QRectF(QPointF(r.left(), scene_pos.y()), QPointF(scene_pos.x(), r.bottom()))
        elif drag_handle_index == 3:  # Right: anchor = left
            new_rect = QRectF(QPointF(r.left(), r.top()), QPointF(scene_pos.x(), r.bottom()))
        elif drag_handle_index == 4:  # BottomRight: anchor = TL
            new_rect = QRectF(r.topLeft(), scene_pos)
        elif drag_handle_index == 5:  # Bottom: anchor = top
            new_rect = QRectF(QPointF(r.left(), r.top()), QPointF(r.right(), scene_pos.y()))
        elif drag_handle_index == 6:  # BottomLeft: anchor = TR
            new_rect = QRectF(QPointF(scene_pos.x(), r.top()), QPointF(r.right(), scene_pos.y()))
        elif drag_handle_index == 7:  # Left: anchor = right
            new_rect = QRectF(QPointF(scene_pos.x(), r.top()), QPointF(r.right(), r.bottom()))
        else:
            return None
        return new_rect.normalized()

    def _apply_resize(self, scene_pos: QPointF):
        """Applica il ridimensionamento trascinando la maniglia verso scene_pos."""
        item = self._resize_target_item
        if not item or self._resize_drag_handle_index is None:
            return
        i = self._resize_drag_handle_index
        if isinstance(item, (DrawableArrow, DrawableLine)):
            local = item.mapFromScene(scene_pos)
            line = item.line()
            if i == 0:
                item.setLine(local.x(), local.y(), line.p2().x(), line.p2().y())
            else:
                item.setLine(line.p1().x(), line.p1().y(), local.x(), local.y())
            self._reposition_resize_handles()
        elif isinstance(item, DrawableCone):
            local = item.mapFromScene(scene_pos)
            poly = item.polygon()
            if 0 <= i < len(poly):
                poly[i] = local
                item.setPolygon(poly)
            self._reposition_resize_handles()
        elif isinstance(item, DrawablePolygon):
            local = item.mapFromScene(scene_pos)
            poly = QPolygonF(item.polygon())
            if 0 <= i < len(poly):
                poly[i] = local
                item.setPolygon(poly)
            self._reposition_resize_handles()
        elif isinstance(item, (DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow)):
            local = item.mapFromScene(scene_pos)
            pts = item.getPoints()
            if 0 <= i < len(pts):
                pts = list(pts)
                pts[i] = local
                item.setPoints(pts[0], pts[1], pts[2])
            self._reposition_resize_handles()
        elif isinstance(item, (QGraphicsEllipseItem, QGraphicsRectItem, DrawableCircle, DrawableRectangle)):
            local = item.mapFromScene(scene_pos)
            rect = item.rect()
            # 0:TL 1:top 2:TR 3:right 4:BR 5:bottom 6:BL 7:left
            if i == 0:
                rect.setTopLeft(local)
            elif i == 1:
                rect.setTop(local.y())
            elif i == 2:
                rect.setTopRight(local)
            elif i == 3:
                rect.setRight(local.x())
            elif i == 4:
                rect.setBottomRight(local)
            elif i == 5:
                rect.setBottom(local.y())
            elif i == 6:
                rect.setBottomLeft(local)
            elif i == 7:
                rect.setLeft(local.x())
            rect = rect.normalized()
            if rect.width() > 15 and rect.height() > 15:
                item.setRect(rect)
                self._reposition_resize_handles()
        elif isinstance(item, DrawableFreehand) and self._resize_freehand_start_path is not None:
            new_scene_rect = self._get_freehand_new_rect_from_anchor_and_drag(i, scene_pos)
            if new_scene_rect and new_scene_rect.width() > 5 and new_scene_rect.height() > 5:
                # Scala il path ORIGINALE al nuovo rect (anchor fissa, scale può essere < 1)
                item.setPos(new_scene_rect.topLeft())
                new_local = QRectF(0, 0, new_scene_rect.width(), new_scene_rect.height())
                self._scale_freehand_path_to_bounds(item, self._resize_freehand_start_path, new_local)
                self._reposition_resize_handles()

    def mouseMoveEvent(self, event):
        # Trascinamento per spostare la forma (o il testo)
        if self._is_moving and self._move_target_item:
            scene_pos = self.mapToScene(event.pos())
            delta = scene_pos - self._move_start_scene
            new_pos = self._move_start_item_pos + delta
            self._move_target_item.setPos(new_pos)
            self._move_start_scene = scene_pos
            self._move_start_item_pos = new_pos
            if self._resize_target_item:
                self._reposition_resize_handles()
            event.accept()
            return
        # Ridimensionamento in corso: aggiorna l'oggetto
        if self._resize_drag_handle_index is not None:
            scene_pos = self.mapToScene(event.pos())
            self._apply_resize(scene_pos)
            event.accept()
            return
        # Poligono: preview con linea fino al cursore
        if self._tool == DrawTool.POLYGON and self._polygon_points:
            pos = self.mapToScene(event.pos())
            self._update_polygon_preview(pos)
        # Matita: disegno a mano libera continuo
        elif self._tool == DrawTool.PENCIL and self._pencil_path is not None:
            pos = self.mapToScene(event.pos())
            self._pencil_path.lineTo(pos)
            self._safe_remove_item(self._current_item)
            self._current_item = QGraphicsPathItem(self._pencil_path)
            self._current_item.setPen(QPen(self._color, self._pen_width))
            self._current_item.setBrush(QBrush(Qt.NoBrush))
            self.scene().addItem(self._current_item)
        elif self._start_pos and self._tool in (DrawTool.CIRCLE, DrawTool.ARROW, DrawTool.LINE, DrawTool.RECTANGLE, DrawTool.CONE,
                                               DrawTool.CURVED_LINE, DrawTool.CURVED_ARROW, DrawTool.PARABOLA_ARROW,
                                               DrawTool.DASHED_ARROW, DrawTool.ZIGZAG_ARROW, DrawTool.DOUBLE_ARROW, DrawTool.DASHED_LINE):
            pos = self.mapToScene(event.pos())
            self._safe_remove_item(self._current_item)
            style, is_arrow, _ = _get_arrow_line_tool_params(self._tool, self._arrow_line_style)
            if self._tool in (DrawTool.ARROW, DrawTool.LINE, DrawTool.DASHED_ARROW, DrawTool.ZIGZAG_ARROW,
                             DrawTool.DOUBLE_ARROW, DrawTool.DASHED_LINE):
                path = _build_arrow_line_path(style, self._start_pos, pos)
                self._current_item = QGraphicsPathItem(path)
                pen = QPen(self._color, self._pen_width)
                if _is_dashed_style(style):
                    pen.setStyle(Qt.DashLine)
                self._current_item.setPen(pen)
                self._current_item.setBrush(QBrush(Qt.NoBrush))
            elif self._tool == DrawTool.RECTANGLE:
                r = QRectF(self._start_pos, pos).normalized()
                self._current_item = QGraphicsRectItem(r)
                pen = QPen(self._color, self._pen_width)
                self._current_item.setPen(pen)
                self._current_item.setBrush(QBrush(Qt.NoBrush))
            elif self._tool == DrawTool.CIRCLE:
                r = QRectF(self._start_pos, pos).normalized()
                self._current_item = QGraphicsEllipseItem(r)
                self._current_item.setPen(QPen(self._color, self._pen_width))
                self._current_item.setBrush(QBrush(Qt.NoBrush))
            elif self._tool in (DrawTool.CURVED_LINE, DrawTool.CURVED_ARROW, DrawTool.PARABOLA_ARROW):
                # Curva: control=midpoint (linea/freccia) o sopra il midpoint (parabola)
                p1, p2 = self._start_pos, pos
                ctrl = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                if self._tool == DrawTool.PARABOLA_ARROW:
                    dist = math.sqrt((p2.x()-p1.x())**2 + (p2.y()-p1.y())**2) or 1
                    curve_ht = dist * 0.45  # Altezza parabola
                    ctrl = QPointF(ctrl.x(), min(p1.y(), p2.y()) - curve_ht)
                path = _quadratic_curve_path(p1, ctrl, p2)
                self._current_item = QGraphicsPathItem(path)
                self._current_item.setPen(QPen(self._color, self._pen_width))
                self._current_item.setBrush(QBrush(Qt.NoBrush))
            elif self._tool == DrawTool.CONE:
                dx = pos.x() - self._start_pos.x()
                dy = pos.y() - self._start_pos.y()
                dist = math.sqrt(dx*dx + dy*dy) or 1
                perp_x = -dy / dist * 40
                perp_y = dx / dist * 40
                p1 = QPointF(self._start_pos.x(), self._start_pos.y())
                p2 = QPointF(pos.x() + perp_x, pos.y() + perp_y)
                p3 = QPointF(pos.x() - perp_x, pos.y() - perp_y)
                self._current_item = DrawableCone([p1, p2, p3], self._color)
            if self._current_item:
                self.scene().addItem(self._current_item)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._move_target_item is not None or self._resize_target_item is not None:
                modified_item = self._move_target_item or self._resize_target_item
                if modified_item in self._displayed_items:
                    ref = modified_item.data(Qt.UserRole) if hasattr(modified_item, "data") else None
                    if isinstance(ref, dict) and "event_id" in ref and "ann_index" in ref:
                        new_data = self.item_to_serializable_data(modified_item)
                        if new_data:
                            self.annotationModified.emit(ref["event_id"], ref["ann_index"], new_data)
            self._resize_drag_handle_index = None
            self._resize_freehand_start_rect = None
            self._resize_freehand_start_path = None
            self._is_moving = False
            self._move_target_item = None
        if event.button() == Qt.LeftButton and self._start_pos:
            pos = self.mapToScene(event.pos())
            style, is_arrow, head_at_start = _get_arrow_line_tool_params(self._tool, self._arrow_line_style)
            if self._tool in (DrawTool.ARROW, DrawTool.DASHED_ARROW, DrawTool.ZIGZAG_ARROW, DrawTool.DOUBLE_ARROW) and self._current_item:
                item = DrawableArrow(
                    self._start_pos.x(), self._start_pos.y(),
                    pos.x(), pos.y(),
                    self._color, self._pen_width,
                    style, head_at_start
                )
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
                self.drawingConfirmed.emit(item)
                self._current_item = None
            elif self._tool in (DrawTool.LINE, DrawTool.DASHED_LINE) and self._current_item:
                item = DrawableLine(
                    self._start_pos.x(), self._start_pos.y(),
                    pos.x(), pos.y(),
                    self._color, self._pen_width,
                    style
                )
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
                self.drawingConfirmed.emit(item)
                self._current_item = None
            elif self._tool == DrawTool.CIRCLE and self._current_item:
                r = QRectF(self._start_pos, pos).normalized()
                item = DrawableCircle(r, self._color, self._pen_width)
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
                self.drawingConfirmed.emit(item)
                self._current_item = None
            elif self._tool == DrawTool.RECTANGLE and self._current_item:
                r = QRectF(self._start_pos, pos).normalized()
                item = DrawableRectangle(r, self._color, self._pen_width)
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
                self.drawingConfirmed.emit(item)
                self._current_item = None
            elif self._tool == DrawTool.CONE and self._current_item:
                self._items.append(self._current_item)
                self.drawingAdded.emit(self._current_item)
                self.drawingConfirmed.emit(self._current_item)
                self._current_item = None
            elif self._tool == DrawTool.CURVED_LINE and self._current_item:
                p1, p2 = self._start_pos, pos
                ctrl = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                item = DrawableCurvedLine(p1, ctrl, p2, self._color, self._pen_width)
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
                self.drawingConfirmed.emit(item)
                self._current_item = None
            elif self._tool == DrawTool.CURVED_ARROW and self._current_item:
                p1, p2 = self._start_pos, pos
                ctrl = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                item = DrawableCurvedArrow(p1, ctrl, p2, self._color, self._pen_width)
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
                self.drawingConfirmed.emit(item)
                self._current_item = None
            elif self._tool == DrawTool.PARABOLA_ARROW and self._current_item:
                p1, p2 = self._start_pos, pos
                ctrl = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                dist = math.sqrt((p2.x()-p1.x())**2 + (p2.y()-p1.y())**2) or 1
                curve_ht = dist * 0.45
                ctrl = QPointF(ctrl.x(), min(p1.y(), p2.y()) - curve_ht)
                item = DrawableParabolaArrow(p1, ctrl, p2, self._color, self._pen_width)
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
                self.drawingConfirmed.emit(item)
                self._current_item = None
            elif self._tool == DrawTool.PENCIL and self._pencil_path is not None and self._pencil_path.length() > 2:
                item = DrawableFreehand(QPainterPath(self._pencil_path), self._color, self._pen_width)
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
                self.drawingConfirmed.emit(item)
                self._current_item = None
                self._pencil_path = None
            else:
                self._safe_remove_item(self._current_item)
                self._current_item = None
            self._start_pos = None
            self._pencil_path = None
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Fallback: se il sistema invia contextMenuEvent alla view."""
        self._on_context_menu_requested(event.pos())
        event.accept()

    def _update_resize_rect_item(self, item, new_rect: QRectF):
        """Aggiorna rect per ellipse/rect."""
        if isinstance(item, (QGraphicsEllipseItem, DrawableCircle)):
            item.setRect(new_rect)
        elif isinstance(item, QGraphicsRectItem):
            item.setRect(new_rect)

    def clearDrawings(self):
        self._clear_resize_handles()
        for item in self._items[:]:
            self._safe_remove_item(item)
            self._items.remove(item)
        self._clear_displayed_items()

    def _clear_displayed_items(self):
        """Rimuove i disegni caricati da project (layer salvato)."""
        for item in self._displayed_items[:]:
            if item in self._items:
                self._items.remove(item)
            self._safe_remove_item(item)
            self._displayed_items.remove(item)

    def setDrawingsVisibility(self, visible: bool):
        """Mostra/nascondi tutti i disegni (working + displayed) - usato quando video in play."""
        for item in self._items + self._displayed_items:
            item.setVisible(visible)

    def loadDrawingsFromProject(self, drawings_list):
        """Carica i disegni da lista di DrawingItem o dict (annotazioni) per il timestamp corrente.
        Gli item sono editabili (selectable, movable) quando video in pausa.
        drawings_list può contenere: dict con type, oppure dict con data/event_id/ann_index."""
        self._clear_displayed_items()
        for d in drawings_list:
            event_id, ann_index = None, None
            if hasattr(d, "data") and d.data:
                raw = d.data
            elif isinstance(d, dict):
                raw = d.get("data") or d
                event_id = d.get("event_id")
                ann_index = d.get("ann_index")
                if not raw or not raw.get("type"):
                    continue
            else:
                continue
            data = self._serializable_to_copy_data(raw)
            data["pos"] = data.get("pos", _deserialize_point({"x": 0, "y": 0}))
            item = self._copy_data_to_item(data, offset_x=0, offset_y=0)
            if item:
                if event_id is not None and ann_index is not None:
                    item.setData(Qt.UserRole, {"event_id": event_id, "ann_index": ann_index})
                item.setFlag(item.GraphicsItemFlag.ItemIsMovable, True)
                item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True)
                self.scene().addItem(item)
                self._displayed_items.append(item)
                self._items.append(item)

    def removeItemForSave(self, item):
        """Rimuove item da _items dopo averlo salvato in project (verrà mostrato da loadDrawingsFromProject)."""
        if item in self._items:
            self._items.remove(item)
            self._safe_remove_item(item)
            self._clear_resize_handles()

    def removeSelected(self):
        for item in self.scene().selectedItems():
            if item in self._items:
                self._items.remove(item)
            self._safe_remove_item(item)
        self._clear_resize_handles()

    def chooseColor(self) -> QColor:
        cd = QColorDialog(self._color, self)
        cd.setWindowTitle("Scegli colore")
        cd.setStyleSheet("""
            QColorDialog { background: #0f1419; border-radius: 12px; border: 1px solid rgba(55, 65, 81, 0.8); }
            QColorDialog QWidget { background: #0f1419; color: #e5e7eb; }
            QPushButton { background: #1a2332; color: #e5e7eb; border: 1px solid #374151;
                border-radius: 6px; padding: 6px 14px; }
            QPushButton:hover { background: rgba(18, 168, 138, 0.2); border-color: #12a88a; }
            QPushButton#titleBarCloseBtn {
                background: rgba(0, 255, 200, 0.15); color: #E6F1FF; border: 1px solid rgba(0, 255, 200, 0.4);
                border-radius: 50%; font-size: 22px; font-weight: 700; padding: 0;
            }
            QPushButton#titleBarCloseBtn:hover { color: #FFFFFF; }
        """)
        _apply_pes_title_bar(cd, "Scegli colore")
        if cd.exec_() == QDialog.Accepted:
            c = cd.selectedColor()
            if c.isValid():
                self._color = c
        return self._color
