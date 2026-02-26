"""Overlay per disegnare sul video: cerchi, frecce, testo, zoom - stile Kinovea."""
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsLineItem, QGraphicsTextItem, QGraphicsRectItem,
    QGraphicsPolygonItem, QGraphicsPathItem, QApplication,
    QInputDialog, QColorDialog, QMenu, QShortcut
)
from PyQt5.QtGui import (
    QPen, QBrush, QColor, QPainter, QPolygonF, QFont,
    QLinearGradient, QPainterPath, QPainterPathStroker, QWheelEvent,
    QKeySequence, QTransform
)
from PyQt5.QtCore import Qt, QPointF, QRectF, QLineF, pyqtSignal
from typing import Optional, List, Tuple
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
    """Testo disegnabile: QGraphicsTextItem, editabile subito, 24px, bianco."""
    def __init__(self, text: str = "", color: QColor = Qt.white):
        super().__init__(text)
        self.setDefaultTextColor(color)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(self.GraphicsItemFlag.ItemIsFocusable)
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        font = QFont("Segoe UI", 24, QFont.Bold)
        self.setFont(font)
        self._color = color

    def setDrawColor(self, c: QColor):
        self._color = c
        self.setDefaultTextColor(c)


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


class DrawingOverlay(QGraphicsView):
    """Widget overlay trasparente per disegnare sul video - stile Kinovea."""
    drawingAdded = pyqtSignal(object)
    drawingStarted = pyqtSignal()  # Emesso quando inizia il disegno (per freeze video)
    zoomRequested = pyqtSignal(int, int, int)  # delta, mouse_x, mouse_y (in coords overlay)

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

        self._tool = DrawTool.NONE
        self._color = QColor("#FFFF00")
        self._pen_width = 8
        self._arrow_line_style = ArrowLineStyle.STRAIGHT
        self._start_pos: Optional[QPointF] = None
        self._current_item = None
        self._items: List[object] = []
        self._resize_handles: List[ResizeHandle] = []
        self._resize_target_item = None
        self._resize_drag_handle_index: Optional[int] = None
        self._resize_freehand_start_rect: Optional[QRectF] = None  # BBox originale al drag start
        self._resize_freehand_start_path: Optional[QPainterPath] = None  # Path originale al drag start
        self._pencil_path: Optional[QPainterPath] = None  # per disegno mano libera
        self._selected_shape = None  # forma selezionata (mostra maniglie e bordo)
        self._clipboard_item = None  # dati per Copia/Incolla
        self._is_moving = False
        self._move_start_scene = None
        self._move_start_item_pos = None

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
        if isinstance(item, DrawableText):
            return {"type": "text", "text": item.toPlainText(), "pos": pos, "color": item._color}
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
        if t == "text":
            item = DrawableText(data.get("text", ""), data["color"])
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
        self._safe_remove_item(self._current_item)
        self._current_item = None
        self._clear_resize_handles()

    def setColor(self, color: QColor):
        self._color = color

    def setPenWidth(self, w: int):
        self._pen_width = w

    def penWidth(self) -> int:
        return self._pen_width

    def setArrowLineStyle(self, style: ArrowLineStyle):
        self._arrow_line_style = style

    def _start_freeze(self):
        """Notifica l'inizio del disegno per il freeze del video."""
        self.drawingStarted.emit()

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
            if hit_item is not None and hit_item in self._items:
                if hit_item == self._resize_target_item:
                    # Forma già selezionata: inizia trascinamento per spostare
                    self._is_moving = True
                    self._move_start_scene = scene_pos
                    self._move_start_item_pos = hit_item.scenePos()
                    event.accept()
                    return
                # Altra forma: seleziona
                self._select_shape(hit_item)
                event.accept()
                return
            # Clic fuori: deseleziona
            self._deselect_shape()
            self._resize_drag_handle_index = None
            self._is_moving = False
        if event.button() == Qt.LeftButton and self._tool == DrawTool.TEXT:
            scene_pos = self.mapToScene(event.pos())
            self._clear_resize_handles()
            self._start_freeze()
            item = DrawableText("", QColor(Qt.white))
            item.setPos(scene_pos)
            self.scene().addItem(item)
            self._items.append(item)
            self.drawingAdded.emit(item)
            self.scene().setFocusItem(item)
            self.setFocus()
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._tool not in (DrawTool.NONE, DrawTool.ZOOM):
            scene_pos = self.mapToScene(event.pos())
            self._clear_resize_handles()
            self._start_pos = scene_pos
            self._start_freeze()
            if self._tool == DrawTool.PENCIL:
                self._pencil_path = QPainterPath()
                self._pencil_path.moveTo(scene_pos)
        elif event.button() == Qt.RightButton:
            item = self.scene().itemAt(self.mapToScene(event.pos()), self.transform())
            self._show_context_menu(event.globalPos(), item)
            return
        super().mousePressEvent(event)

    def _show_context_menu(self, pos, item):
        """Menu contestuale sul tasto destro."""
        target = self._find_drawable_item(item)
        if target is None or target not in self._items:
            return
        menu = QMenu(self)
        color_action = menu.addAction("Modifica colore")
        has_line = isinstance(target, (DrawableCircle, DrawableRectangle, DrawableArrow,
                                       DrawableLine, DrawableFreehand,
                                       DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow))
        thickness_action = menu.addAction("Modifica spessore linea")
        if not has_line:
            thickness_action.setEnabled(False)
        menu.addSeparator()
        duplica_action = menu.addAction("Duplica")
        menu.addSeparator()
        delete_action = menu.addAction("Elimina")
        action = menu.exec_(pos)
        if action == delete_action:
            if target in self._items:
                self._items.remove(target)
            self._safe_remove_item(target)
            self._clear_resize_handles()
        elif action == color_action:
            c = QColorDialog.getColor(target._color, self, "Modifica colore")
            if c.isValid():
                target.setDrawColor(c)
                target._color = c
                target.update()
        elif action == thickness_action and has_line:
            if isinstance(target, (DrawableArrow, DrawableLine)):
                current = target._width
            elif isinstance(target, (DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow)):
                current = target._pen_width
            else:
                current = int(target.pen().widthF()) if target.pen().widthF() > 0 else 8
            w, ok = QInputDialog.getInt(self, "Modifica spessore", "Spessore (px):", current, 1, 20)
            if ok:
                if isinstance(target, (DrawableArrow, DrawableLine)):
                    target._width = w
                    target._update_path()
                elif isinstance(target, (DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow)):
                    target._pen_width = w
                    target._update_path()
                else:
                    color = target._color if hasattr(target, "_color") else target.pen().color()
                    target.setPen(QPen(color, w))
                target.update()
        elif action == duplica_action:
            data = self._item_to_copy_data(target)
            if data:
                new_item = self._copy_data_to_item(data, offset_x=15, offset_y=15)
                if new_item:
                    self.scene().addItem(new_item)
                    self._items.append(new_item)
                    self.drawingAdded.emit(new_item)
                    self._select_shape(new_item)

    def _find_drawable_item(self, item):
        """Trova l'item disegnabile (può essere sotto altri o un figlio)."""
        if item is None:
            return None
        while item is not None:
            if item in self._items:
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
        """Attiva modalità ridimensionamento con maniglie (angoli + lati)."""
        if not isinstance(item, (QGraphicsEllipseItem, QGraphicsRectItem, DrawableCircle, DrawableRectangle,
                                 DrawableArrow, DrawableLine, DrawableCone, DrawableFreehand,
                                 DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow)):
            return
        self._resize_target_item = item
        item.setZValue(9998)  # sopra altri item, sotto le maniglie
        self._resize_handles = []
        if isinstance(item, (DrawableArrow, DrawableLine)):
            handles_pos = self._get_arrow_line_handle_scene_positions(item)
        elif isinstance(item, (DrawableCone, DrawableCurvedLine, DrawableCurvedArrow, DrawableParabolaArrow)):
            handles_pos = self._get_three_point_handle_scene_positions(item)
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
        # Trascinamento per spostare la forma
        if self._is_moving and self._resize_target_item:
            scene_pos = self.mapToScene(event.pos())
            delta = scene_pos - self._move_start_scene
            new_pos = self._move_start_item_pos + delta
            self._resize_target_item.setPos(new_pos)
            self._move_start_scene = scene_pos
            self._move_start_item_pos = new_pos
            self._reposition_resize_handles()
            event.accept()
            return
        # Ridimensionamento in corso: aggiorna l'oggetto
        if self._resize_drag_handle_index is not None:
            scene_pos = self.mapToScene(event.pos())
            self._apply_resize(scene_pos)
            event.accept()
            return
        # Matita: disegno a mano libera continuo
        if self._tool == DrawTool.PENCIL and self._pencil_path is not None:
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
            self._resize_drag_handle_index = None
            self._resize_freehand_start_rect = None
            self._resize_freehand_start_path = None
            self._is_moving = False
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
                self._current_item = None
            elif self._tool == DrawTool.CIRCLE and self._current_item:
                r = QRectF(self._start_pos, pos).normalized()
                item = DrawableCircle(r, self._color, self._pen_width)
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
                self._current_item = None
            elif self._tool == DrawTool.RECTANGLE and self._current_item:
                r = QRectF(self._start_pos, pos).normalized()
                item = DrawableRectangle(r, self._color, self._pen_width)
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
                self._current_item = None
            elif self._tool == DrawTool.CONE and self._current_item:
                self._items.append(self._current_item)
                self.drawingAdded.emit(self._current_item)
                self._current_item = None
            elif self._tool == DrawTool.CURVED_LINE and self._current_item:
                p1, p2 = self._start_pos, pos
                ctrl = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                item = DrawableCurvedLine(p1, ctrl, p2, self._color, self._pen_width)
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
                self._current_item = None
            elif self._tool == DrawTool.CURVED_ARROW and self._current_item:
                p1, p2 = self._start_pos, pos
                ctrl = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                item = DrawableCurvedArrow(p1, ctrl, p2, self._color, self._pen_width)
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
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
                self._current_item = None
            elif self._tool == DrawTool.PENCIL and self._pencil_path is not None and self._pencil_path.length() > 2:
                item = DrawableFreehand(QPainterPath(self._pencil_path), self._color, self._pen_width)
                self._safe_remove_item(self._current_item)
                self.scene().addItem(item)
                self._items.append(item)
                self.drawingAdded.emit(item)
                self._current_item = None
                self._pencil_path = None
            else:
                self._safe_remove_item(self._current_item)
                self._current_item = None
            self._start_pos = None
            self._pencil_path = None
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Gestione tasto destro - menu contestuale sugli oggetti."""
        scene_pos = self.mapToScene(event.pos())
        # Cerca in un'area attorno al punto per gestire percorsi sottili
        tol = 15
        r = QRectF(scene_pos.x() - tol, scene_pos.y() - tol, tol * 2, tol * 2)
        items_at = self.scene().items(r, Qt.IntersectsItemShape, Qt.DescendingOrder)
        target = None
        for it in items_at:
            if it in self._items:
                target = it
                break
            t = self._find_drawable_item(it)
            if t is not None:
                target = t
                break
        if target is not None:
            event.accept()
            self._show_context_menu(event.globalPos(), target)
        else:
            event.accept()  # Non mostrare menu fuori dalle forme

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

    def removeSelected(self):
        for item in self.scene().selectedItems():
            if item in self._items:
                self._items.remove(item)
            self._safe_remove_item(item)
        self._clear_resize_handles()

    def chooseColor(self) -> QColor:
        c = QColorDialog.getColor(self._color, self, "Scegli colore")
        if c.isValid():
            self._color = c
        return self._color
