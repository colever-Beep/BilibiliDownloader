"""图标绘制：封装 bili23 同款的 qfluentwidgets FluentIcon 矢量图标体系。

动作按钮（play/pause/retry/delete/folder/select_all）与封面占位图均使用 FluentIcon；
勾选框保留手绘（填充强调色 + 白色对勾，标准 checkbox 观感）。所有图标颜色由调用方传入
QColor，随明暗主题 / 强调色自适应。

对外暴露的函数签名保持稳定，供 queue_view.py / select_list_view.py 直接调用：
    draw_pause / draw_play / draw_retry / draw_delete / draw_folder / draw_select_all
    draw_check / draw_placeholder / category_badge_color / paint_option_background
"""
from PySide6.QtCore import Qt, QRect, QPointF
from PySide6.QtGui import QPainter, QColor, QPen

from ui.icons import FluentIcon, AppFluentIcon, draw_icon


def _pad(rect, p):
    return QRect(rect.x() + p, rect.y() + p, rect.width() - 2 * p, rect.height() - 2 * p)


def draw_pause(painter, rect, color):
    draw_icon(painter, rect, FluentIcon.PAUSE, color)


def draw_play(painter, rect, color):
    draw_icon(painter, rect, FluentIcon.PLAY, color)


def draw_retry(painter, rect, color):
    draw_icon(painter, rect, AppFluentIcon.RETRY, color)


def draw_delete(painter, rect, color):
    draw_icon(painter, rect, FluentIcon.DELETE, color)


def draw_folder(painter, rect, color):
    draw_icon(painter, rect, FluentIcon.FOLDER, color)


def draw_select_all(painter, rect, color):
    draw_icon(painter, rect, AppFluentIcon.SELECT_ALL, color)


def draw_check(painter, rect, checked, color, sub_color):
    """勾选框：checked=填充强调色 + 白色对勾；unchecked=描边占位。

    ``rect`` 为单元格矩形，内部自动取正方形。
    """
    side = rect.height()
    box = QRect(rect.x() + (rect.width() - side) // 2, rect.y(), side, side)
    pad = max(2, int(side * 0.16))
    inner = box.adjusted(pad, pad, -pad, -pad)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if checked:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(inner, 4, 4)
        pen = QPen(QColor("#ffffff"))
        pen.setWidthF(max(2.0, inner.width() * 0.13))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        x0, y0 = inner.left() + inner.width() * 0.22, inner.center().y()
        x1, y1 = inner.left() + inner.width() * 0.44, inner.bottom() - inner.height() * 0.22
        x2, y2 = inner.right() - inner.width() * 0.18, inner.top() + inner.height() * 0.24
        painter.drawLine(QPointF(x0, y0), QPointF(x1, y1))
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    else:
        pen = QPen(QColor(sub_color))
        pen.setWidthF(max(1.5, inner.width() * 0.09))
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(inner, 4, 4)
    painter.restore()


def draw_placeholder(painter, rect, sub_color):
    """无封面时的占位图（圆角灰底 + Fluent 视频图标），替代 emoji 📺。"""
    r = _pad(rect, max(2, int(rect.width() * 0.04)))
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(sub_color))
    painter.setOpacity(0.20)
    painter.drawRoundedRect(r, 5, 5)
    painter.setOpacity(1.0)
    painter.restore()
    draw_icon(painter, r, FluentIcon.VIDEO, sub_color, scale=0.50)


def category_badge_color(category):
    """类型徽标配色（与 queue_view 保持一致）。"""
    cat = (category or "").strip()
    if not cat or cat == "视频":
        return None, None
    table = {
        "歌单": "#8e44ad", "课程": "#f39c12", "音频": "#9b59b6",
        "每周必看": "#e67e22", "动态": "#16a085", "搜索": "#2980b9",
        "番剧": "#c0392b", "影视": "#c0392b",
    }
    return cat, table.get(cat, "#607d8b")


def paint_option_background(painter, option, index, hover_row):
    """绘制行悬停/选中背景叠加层（参照 bili23 的 _drawBackground）。

    hover 行叠一层半透明白/黑，使整行在明/暗主题下都有清晰的悬停反馈。
    """
    if hover_row != index.row():
        return
    try:
        from ui.theme import is_dark as _is_dark
        dark = _is_dark()
    except Exception:
        dark = False
    c = 255 if dark else 0
    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(c, c, c, 18 if dark else 12))
    painter.drawRoundedRect(option.rect.adjusted(4, 2, -4, -2), 5, 5)
    painter.restore()
