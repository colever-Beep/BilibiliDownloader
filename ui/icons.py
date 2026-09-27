"""Fluent 图标门面（与 bili23 同款的 qfluentwidgets FluentIcon 体系）。

优先使用 ``qfluentwidgets`` 的 ``FluentIcon`` / ``FluentIconBase`` 渲染矢量图标；若该包未安装
（例如用未装依赖的解释器直接 ``python main.py``），自动降级为内置的手绘矢量图标，保证导入链
绝不崩溃、界面仍可正常显示。

- 内置图标：``FluentIcon``（PLAY / PAUSE / DELETE / FOLDER / ACCEPT / VIDEO / PHOTO …）。
- 自定义图标：``AppFluentIcon`` —— 资源来自 ``res/`` 下编译的 ``resources_rc.py``
  （前缀 ``/bili``，dark/light 双主题，随 ``set_fluent_theme()`` 切换）。

图标均为单色，渲染时按调用方传入的 QColor 重新着色，随明暗主题 / 强调色自适应。
"""
from enum import Enum

from PySide6.QtCore import QSize, QRect, QRectF, QPointF, Qt
from PySide6.QtGui import QColor, QPixmap, QIcon, QPainter, QPen, QPolygonF

try:
    from qfluentwidgets import FluentIcon as _QFluentIcon, FluentIconBase, Theme, qconfig
    FLUENT_AVAILABLE = True
except Exception:  # noqa: BLE001 —— 依赖缺失时优雅降级，不阻塞导入
    FLUENT_AVAILABLE = False
    _QFluentIcon = FluentIconBase = Theme = qconfig = None

if FLUENT_AVAILABLE:
    # 注册 Qt 资源（:/bili/icon/{dark,light}/*.svg 等）
    import res.resources_rc  # noqa: F401,F403


def set_fluent_theme(dark: bool):
    """把当前明暗主题同步给 qfluentwidgets 控件与图标资源。

    在 ``ui.theme.apply_appearance`` 或主窗口切换主题后调用，保持图标与界面同色系。
    依赖缺失时为空操作。
    """
    if not FLUENT_AVAILABLE:
        return
    theme = Theme.DARK if dark else Theme.LIGHT
    if qconfig.theme != theme:
        from qfluentwidgets import setTheme
        setTheme(theme)


# ---------------------------------------------------------------------------
# 自定义扩展图标（Fluent 可用时指向 res 资源；缺失时用同名手绘降级）
# ---------------------------------------------------------------------------
if FLUENT_AVAILABLE:

    class AppFluentIcon(FluentIconBase, Enum):
        """项目自定义图标，对应 ``res/icon/{dark,light}/*.svg``。"""

        RETRY = "retry"
        SELECT_ALL = "select_all"
        CLEAR = "clear"
        REMOVE = "remove"
        ADD = "add"
        SORT = "sort"
        CHOOSE_PAGE = "choose_page"
        APPLICATION_WINDOW = "application_window"

        def path(self, theme=Theme.AUTO):
            theme = qconfig.theme if theme == Theme.AUTO else theme
            return f":/bili/icon/{theme.value.lower()}/{self.value}.svg"

    FluentIcon = _QFluentIcon

else:
    # 降级：用命名空间对象返回「手绘图标占位」，名字即原 SVG 文件名 / Fluent 成员名。
    class _FallbackIcon:
        def __init__(self, name):
            self.name = name
            self.value = name

        def icon(self, color=None, theme=None):
            size = 64
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            c = QColor(color) if color is not None else QColor(0, 0, 0)
            _HANDDRAWN.get(self.name, _draw_unknown)(p, QRect(0, 0, size, size), c)
            p.end()
            return QIcon(pm)

    class _FallbackIconNamespace:
        def __getattr__(self, name):
            return _FallbackIcon(name)

    FluentIcon = _FallbackIconNamespace()
    AppFluentIcon = _FallbackIconNamespace()


def icon_pixmap(icon, size, color=None):
    """渲染为 ``size×size`` 的 QPixmap。

    ``color`` 为 None 时用 Fluent 默认主题色（黑/白，随 qconfig.theme）。
    """
    if color is not None:
        ic = icon.icon(color=QColor(color))
    else:
        ic = icon.icon()
    return ic.pixmap(QSize(size, size))


def draw_icon(painter, rect, icon, color=None, scale=0.60):
    """把图标绘制到 ``rect`` 中心（按 ``scale`` 留白）。

    调用方传入 ``FluentIcon.*`` 或 ``AppFluentIcon.*``；颜色由 ``color`` 指定。
    """
    if rect.width() <= 0 or rect.height() <= 0:
        return
    s = max(8, int(min(rect.width(), rect.height()) * scale))
    pm = icon_pixmap(icon, s, color)
    x = rect.x() + (rect.width() - s) // 2
    y = rect.y() + (rect.height() - s) // 2
    painter.drawPixmap(QRect(x, y, s, s), pm)


# ---------------------------------------------------------------------------
# 降级手绘图标（仅在 qfluentwidgets 缺失时使用）
# ---------------------------------------------------------------------------
def _pen_brush(p, c):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(c))


def _draw_play(p, r, c):
    _pen_brush(p, c)
    tri = QPolygonF([
        QPointF(r.x() + r.width() * 0.34, r.y() + r.height() * 0.20),
        QPointF(r.x() + r.width() * 0.34, r.y() + r.height() * 0.80),
        QPointF(r.x() + r.width() * 0.78, r.y() + r.height() * 0.50),
    ])
    p.drawPolygon(tri)


def _draw_pause(p, r, c):
    _pen_brush(p, c)
    w = r.width() * 0.20
    gap = r.width() * 0.12
    h = r.height() * 0.56
    y = r.y() + r.height() * 0.22
    x1 = r.x() + r.width() * 0.29
    x2 = x1 + w + gap
    p.drawRoundedRect(QRectF(x1, y, w, h), 3, 3)
    p.drawRoundedRect(QRectF(x2, y, w, h), 3, 3)


def _draw_delete(p, r, c):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(c))
    x = r.x() + r.width() * 0.24
    y = r.y() + r.height() * 0.38
    w = r.width() * 0.52
    h = r.height() * 0.40
    # 桶身
    p.drawRoundedRect(QRectF(x, y, w, h), 4, 4)
    # 盖 + 把手
    p.setBrush(QColor(c))
    lid_w = w * 0.62
    p.drawRoundedRect(QRectF(r.x() + r.width() * 0.5 - lid_w / 2, y - r.height() * 0.10, lid_w, r.height() * 0.10), 2, 2)
    hw = w * 0.16
    p.drawRoundedRect(QRectF(r.x() + r.width() * 0.5 - hw / 2, y - r.height() * 0.16, hw, r.height() * 0.08), 2, 2)


def _draw_folder(p, r, c):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(c))
    x = r.x() + r.width() * 0.16
    y = r.y() + r.height() * 0.34
    w = r.width() * 0.68
    h = r.height() * 0.42
    tab = r.width() * 0.18
    # 底部主体
    p.drawRoundedRect(QRectF(x, y + r.height() * 0.10, w, h - r.height() * 0.10), 4, 4)
    # 顶部标签
    p.drawRoundedRect(QRectF(x, y, tab, r.height() * 0.12), 2, 2)


def _draw_retry(p, r, c):
    p.setPen(QPen(QColor(c), max(3.0, r.width() * 0.07), Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    cx, cy = r.x() + r.width() * 0.5, r.y() + r.height() * 0.5
    rad = r.width() * 0.30
    # 圆角环形箭头（留口），从 30° 起画 280°
    p.drawArc(QRectF(cx - rad, cy - rad, rad * 2, rad * 2), 30 * 16, 280 * 16)
    # 箭头头部：指向弧线末端（30° + 280° = 310°）
    import math
    ang = math.radians(310)
    ax = cx + rad * math.cos(ang)
    ay = cy - rad * math.sin(ang)  # Qt y 轴向下，故取负
    s = r.width() * 0.14
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(c))
    head = QPolygonF([
        QPointF(ax, ay),
        QPointF(ax - s * 0.9, ay - s * 0.5),
        QPointF(ax - s * 0.2, ay + s * 0.9),
    ])
    p.drawPolygon(head)


def _draw_video(p, r, c):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(c))
    x = r.x() + r.width() * 0.20
    y = r.y() + r.height() * 0.26
    w = r.width() * 0.60
    h = r.height() * 0.48
    p.drawRoundedRect(QRectF(x, y, w, h), 6, 6)
    # 内部播放三角（反色）
    p.setBrush(QColor(255, 255, 255, 230))
    tri = QPolygonF([
        QPointF(x + w * 0.40, y + h * 0.28),
        QPointF(x + w * 0.40, y + h * 0.72),
        QPointF(x + w * 0.72, y + h * 0.50),
    ])
    p.drawPolygon(tri)


def _draw_check(p, r, c):
    p.setPen(QPen(QColor(c), max(3.0, r.width() * 0.08), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    x0 = r.x() + r.width() * 0.28
    y0 = r.y() + r.height() * 0.52
    x1 = r.x() + r.width() * 0.44
    y1 = r.y() + r.height() * 0.68
    x2 = r.x() + r.width() * 0.74
    y2 = r.y() + r.height() * 0.32
    p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _draw_unknown(p, r, c):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(c))
    p.drawEllipse(QRectF(r.x() + r.width() * 0.42, r.y() + r.height() * 0.42,
                         r.width() * 0.16, r.height() * 0.16))


_HANDDRAWN = {
    "PLAY": _draw_play,
    "PAUSE": _draw_pause,
    "DELETE": _draw_delete,
    "FOLDER": _draw_folder,
    "RETRY": _draw_retry,
    "VIDEO": _draw_video,
    "SELECT_ALL": _draw_check,
    "ACCEPT": _draw_check,
    "CHECK": _draw_check,
    "ADD": _draw_check,
    "REMOVE": _draw_delete,
}


# ---------------------------------------------------------------------------
# 侧边栏导航图标（语义名 -> 图标）
# ---------------------------------------------------------------------------
# 优先用 FluentIcon 内置成员（清晰填充 SVG）；Fluent 没有的成员（STAR / FIRE /
# TROPHY 等）回退到 ui.nav_icons 的手绘描边图标，保证每一项都有图标且风格接近。
_NAV_FLUENT = {
    "folder": "FOLDER",
    "toview": "CALENDAR",     # 稍后再看：Fluent 无 CLOCK，用 CALENDAR 最贴切
    "history": "HISTORY",
    "following": "HEART",
    "season": "STAR",         # 缺失 -> 手绘兜底
    "popular": "FIRE",        # 缺失 -> 手绘兜底
    "ranking": "TROPHY",      # 缺失 -> 手绘兜底
    "search": "SEARCH",
    "music": "MUSIC",
    "live_center": "VIDEO",
    "settings": "SETTING",
    "about": "INFO",
}


def draw_nav_icon(painter, name, rect, color):
    """侧边栏导航项图标：FluentIcon 优先，缺失回退手绘，保证每项都显示。

    签名与旧 ``ui.nav_icons.draw_nav_icon`` 完全一致，侧边栏仅需改 import 来源。
    """
    if rect.width() <= 0 or rect.height() <= 0:
        return
    fluent_name = _NAV_FLUENT.get(name)
    if FLUENT_AVAILABLE and fluent_name and hasattr(FluentIcon, fluent_name):
        draw_icon(painter, rect, getattr(FluentIcon, fluent_name), color)
        return
    # 手绘兜底（含 live_center -> live 的名字修正）
    nav_name = {"live_center": "live"}.get(name, name)
    try:
        from ui import nav_icons
        drawer = nav_icons._DRAW.get(nav_name)
        if drawer is not None:
            nav_icons.draw_nav_icon(painter, nav_name, rect, color)
    except Exception:
        pass
