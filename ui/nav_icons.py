"""导航栏单色矢量图标集（纯 PySide6 自绘，无外部资源依赖）。

每个图标在 24x24 的设计坐标系内用 QPainter 描边绘制，调用方传入一个
``QColor`` 作为描边/填充色，因此可以随主题（明暗 / 强调色）自动着色。
参照 bili23 的导航图标风格：线性单色、统一线宽、留白居中。
"""
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPainterPath, QPolygonF,
)

_LINE = 1.8


def _pen(color):
    p = QPen(color)
    p.setWidthF(_LINE)
    p.setCapStyle(Qt.RoundCap)
    p.setJoinStyle(Qt.RoundJoin)
    return p


def _draw_folder(p):
    path = QPainterPath()
    path.moveTo(3, 7)
    path.lineTo(9, 7)
    path.lineTo(11.5, 10)
    path.lineTo(21, 10)
    path.lineTo(21, 19)
    path.lineTo(3, 19)
    path.closeSubpath()
    p.drawPath(path)


def _draw_clock(p):
    p.drawEllipse(4, 4, 16, 16)
    p.drawLine(12, 12, 12, 6.5)
    p.drawLine(12, 12, 16, 13)


def _draw_history(p):
    p.drawEllipse(4, 4, 16, 16)
    p.drawLine(12, 12, 12, 6.5)
    p.drawLine(12, 12, 16, 13)
    # 逆时针小箭头（环上）
    p.drawArc(2.5, 2.5, 19, 19, 220 * 16, 80 * 16)


def _draw_heart(p):
    path = QPainterPath()
    path.moveTo(12, 20)
    path.cubicTo(4, 14, 4, 8, 8.5, 6)
    path.cubicTo(10.5, 5, 12, 7, 12, 7)
    path.cubicTo(12, 7, 13.5, 5, 15.5, 6)
    path.cubicTo(20, 8, 20, 14, 12, 20)
    path.closeSubpath()
    p.drawPath(path)


def _draw_star(p):
    pts = []
    import math
    for i in range(5):
        ang = -math.pi / 2 + i * 2 * math.pi / 5
        pts.append(QPointF(12 + 9 * math.cos(ang), 12 + 9 * math.sin(ang)))
        ang2 = ang + math.pi / 5
        pts.append(QPointF(12 + 3.8 * math.cos(ang2), 12 + 3.8 * math.sin(ang2)))
    poly = QPolygonF(pts)
    p.drawPolygon(poly)


def _draw_fire(p):
    path = QPainterPath()
    path.moveTo(12, 3)
    path.cubicTo(18, 9, 15.5, 15, 12, 21)
    path.cubicTo(8.5, 16, 6, 11, 9.5, 8)
    path.cubicTo(10.5, 9, 11, 7.5, 12, 3)
    path.closeSubpath()
    p.drawPath(path)


def _draw_trophy(p):
    p.drawRoundedRect(7, 4, 10, 9, 1.5, 1.5)
    p.drawLine(7, 7, 3.5, 9)
    p.drawLine(17, 7, 20.5, 9)
    p.drawLine(12, 13, 12, 17)
    p.drawLine(8, 17, 16, 17)
    p.drawLine(9.5, 17, 9.5, 19)
    p.drawLine(14.5, 17, 14.5, 19)


def _draw_search(p):
    p.drawEllipse(5, 5, 12, 12)
    p.drawLine(13.5, 13.5, 20, 20)


def _draw_music(p):
    p.drawEllipse(6, 15, 6.5, 6.5)
    p.drawEllipse(15.5, 13, 5.5, 5.5)
    p.drawLine(9.25, 15, 9.25, 6)
    p.drawLine(18.25, 13, 18.25, 4)
    p.drawLine(9.25, 7, 18.25, 5)


def _draw_live(p):
    p.drawEllipse(3.5, 3.5, 17, 17)
    p.drawEllipse(10, 10, 4, 4)
    p.drawArc(3, 3, 18, 18, 35 * 16, 110 * 16)
    p.drawArc(3, 3, 18, 18, 215 * 16, 110 * 16)


def _draw_settings(p):
    p.drawEllipse(7.5, 7.5, 9, 9)
    p.drawEllipse(10.5, 10.5, 3, 3)
    import math
    for i in range(8):
        ang = i * math.pi / 4
        x1 = 12 + 5.8 * math.cos(ang)
        y1 = 12 + 5.8 * math.sin(ang)
        x2 = 12 + 8.2 * math.cos(ang)
        y2 = 12 + 8.2 * math.sin(ang)
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _draw_info(p):
    p.drawEllipse(4, 4, 16, 16)
    p.drawLine(12, 7, 12, 10.5)
    p.drawEllipse(11.6, 13.2, 0.8, 0.8)


def _draw_user(p):
    p.drawEllipse(8, 4, 8, 8)
    path = QPainterPath()
    path.moveTo(5, 20)
    path.cubicTo(5, 14.5, 19, 14.5, 19, 20)
    p.drawPath(path)


_DRAW = {
    "folder": _draw_folder,
    "toview": _draw_clock,
    "history": _draw_history,
    "following": _draw_heart,
    "season": _draw_star,
    "popular": _draw_fire,
    "ranking": _draw_trophy,
    "search": _draw_search,
    "music": _draw_music,
    "live": _draw_live,
    "settings": _draw_settings,
    "about": _draw_info,
    "user": _draw_user,
}


def draw_nav_icon(painter, name, rect, color):
    """在 ``rect`` 内居中以 ``color`` 描边绘制名为 ``name`` 的导航图标。

    ``painter`` 必须是已经开启 Antialiasing 的 QPainter；本函数会
    save/restore 其状态，调用方无需关心坐标变换。
    """
    fn = _DRAW.get(name)
    if fn is None:
        return
    s = min(rect.width(), rect.height())
    if s <= 0:
        return
    painter.save()
    painter.setPen(_pen(color))
    painter.setBrush(Qt.NoBrush)
    # 把 24x24 设计盒缩放到可用正方形并居中
    off_x = rect.x() + (rect.width() - s) / 2.0
    off_y = rect.y() + (rect.height() - s) / 2.0
    painter.translate(off_x, off_y)
    painter.scale(s / 24.0, s / 24.0)
    fn(painter)
    painter.restore()
