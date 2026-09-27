"""下载队列视图（PySide6 版，参照 bili23 主界面列表优化）。

用 QListView + QAbstractListModel + QStyledItemDelegate 实现「整行自定义绘制 + 原生虚拟化」：
- 哪怕队列有几万条，屏幕上永远只绘制可见的那十几行 —— 彻底告别旧版手搓的
  VirtualList（Canvas + 对象池 + 滚轮全局分发 + 快速滚动降级那 330 行 hack）。
- 列：封面 / # / 标题(类型徽标+UP主) / 时长 / 发布 / 播放 / 点赞 / 收藏 / 状态 / 操作。
- 行内进度条随下载实时刷新（只重绘单行，不重建列表）。

参照 bili23 的视觉语言做的优化（本次重构重点）：
- 封面改为圆角矩形（bili23 风格），无图时显示占位图而非 emoji 📺。
- 操作按钮改为矢量图标（暂停/继续/重试/删除/打开文件位置），替代 emoji 字形，
  并在鼠标悬停时高亮（bili23 的 ActionButtonHoveredRow 行为）。
- 整行悬停背景叠加（bili23 的 _drawBackground）。
- 进度条按状态着色：下载中=蓝、已暂停=黄、失败=红（bili23 的 _drawProgressBar）。
- 完成态操作按钮变为「打开文件位置」文件夹图标（bili23 行为）。
- 右键上下文菜单：打开文件位置 / 重试 / 暂停·继续 / 删除 / 复制链接。
"""
import os
import threading
import webbrowser
import queue as pyq
from io import BytesIO

import requests
from PIL import Image

from PySide6.QtCore import (
    Qt, QAbstractListModel, QModelIndex, QSize, QRect, QPoint, QByteArray, Signal,
    QEvent, QUrl, QObject, QTimer,
)
from PySide6.QtGui import (QPixmap, QImage, QPainter, QColor, QFont, QPen,
                           QBrush, QFontMetrics, QDesktopServices)
from PySide6.QtWidgets import (
    QListView, QWidget, QAbstractItemView, QStyledItemDelegate,
    QVBoxLayout, QHBoxLayout, QMenu, QStyle, QApplication,
)
from qfluentwidgets import InfoBadge, Pivot

from utils.helpers import optimize_thumbnail_url, format_duration, format_count
from utils.i18n import tr
from utils.main_thread import run_on_main
from ui.theme import palette, is_dark, get_accent
from ui.list_icons import (
    draw_pause, draw_play, draw_retry, draw_delete, draw_folder,
    draw_placeholder, category_badge_color,
)
from ui.list_layout import manager

# --------------------------------------------------------------------------- #
# 列定义 + 列宽管理
# --------------------------------------------------------------------------- #
# 每列：key / 表头文案（翻译键） / 默认宽 / 最小宽 / 最大宽 / 与后一列的间距 gap。
# gap 计入布局总宽，保证列与列之间恒有留白、永不互相覆盖。
# 「标题」列 stretch=1：窗口变宽时吃掉多余空间，窗口变窄时最先被压缩。
_COLUMNS = [
    {"key": "cover",   "label": "封面", "default": 96,  "min": 56,  "max": 220, "gap": 6},
    {"key": "num",     "label": "#",    "default": 36,  "min": 26,  "max": 72,  "gap": 4},
    {"key": "title",   "label": "标题", "default": 280, "min": 150, "max": 900, "gap": 8, "stretch": 1},
    {"key": "dur",     "label": "时长", "default": 70,  "min": 48,  "max": 160, "gap": 0},
    {"key": "pub",     "label": "发布", "default": 96,  "min": 64,  "max": 180, "gap": 0},
    {"key": "view",    "label": "播放", "default": 74,  "min": 46,  "max": 160, "gap": 0},
    {"key": "like",    "label": "点赞", "default": 74,  "min": 46,  "max": 160, "gap": 0},
    {"key": "fav",     "label": "收藏", "default": 74,  "min": 46,  "max": 160, "gap": 0},
    {"key": "status",  "label": "状态", "default": 70,  "min": 54,  "max": 160, "gap": 0},
    {"key": "actions", "label": "",     "default": 112, "min": 84,  "max": 240, "gap": 0},
]
_PAD = 8          # 行左右留白
_COLUMN_KEYS = [c["key"] for c in _COLUMNS]


def _spec(key):
    for c in _COLUMNS:
        if c["key"] == key:
            return c
    return _COLUMNS[0]


class ColumnLayout(QObject):
    """下载队列列宽管理：默认宽 + 用户拖拽 + 持久化 + 自动收窄防重叠。

    - 列宽以像素存储（dict），可写入 settings.json 的 ``column_widths``。
    - 「标题」列 stretch=1 吸收多余空间：窗口变宽 -> 标题变宽；窗口变窄 -> 先压标题。
    - 宽度不足时收缩顺序：标题（到 min） -> 其余列按可压缩量等比收缩 -> 硬缩放下限。
      保证**任何窗口宽度下列都不会越界重叠**（旧实现为固定列宽 + 标题最小 140，
      窄窗口下右侧几列会被挤出可视区、文字互相覆盖）。
    """

    changed = Signal()

    def __init__(self, saved=None, parent=None):
        super().__init__(parent)
        self._w = {}
        self._hidden = set()      # 精简布局下隐藏的列（不参与布局/绘制）
        for c in _COLUMNS:
            raw = saved.get(c["key"]) if isinstance(saved, dict) else None
            try:
                raw = int(raw)
            except (TypeError, ValueError):
                raw = None
            if not raw or raw <= 0:
                raw = c["default"]
            self._w[c["key"]] = max(c["min"], min(raw, c["max"]))

    # ------------------------------------------------------------------ #
    # 隐藏列（精简布局）
    # ------------------------------------------------------------------ #
    def set_hidden(self, keys):
        keys = set(keys or set())
        if keys == self._hidden:
            return
        self._hidden = keys
        self.changed.emit()

    def hidden(self):
        return set(self._hidden)

    def active_columns(self):
        """当前参与布局与绘制的列（排除隐藏列）。"""
        return [c for c in _COLUMNS if c["key"] not in self._hidden]

    # ------------------------------------------------------------------ #
    # 读写
    # ------------------------------------------------------------------ #
    def width(self, key):
        return self._w.get(key, _spec(key)["default"])

    def as_dict(self):
        return dict(self._w)

    def gaps_total(self):
        return sum(c["gap"] for c in self.active_columns())

    def max_width_for(self, key, total_width):
        """在给定容器宽度下该列允许的最大宽（保证其它列都能保持最小宽）。"""
        spec = _spec(key)
        if total_width and total_width > 0:
            avail = max(0, total_width - 2 * _PAD - self.gaps_total())
            others_min = sum(c["min"] for c in self.active_columns() if c["key"] != key)
            return max(spec["min"], min(spec["max"], avail - others_min))
        return spec["max"]

    def set_width(self, key, w, total_width=None):
        spec = _spec(key)
        lo = spec["min"]
        hi = self.max_width_for(key, total_width)
        v = max(lo, min(int(w), hi))
        if v == self._w.get(key):
            return False
        self._w[key] = v
        self.changed.emit()
        return True

    def reset(self, key=None):
        """恢复默认列宽：指定 key 只重置该列，None 重置全部。"""
        changed = False
        for c in _COLUMNS:
            if key and c["key"] != key:
                continue
            if self._w.get(c["key"]) != c["default"]:
                self._w[c["key"]] = c["default"]
                changed = True
        if changed:
            self.changed.emit()
        return changed

    # ------------------------------------------------------------------ #
    # 布局计算
    # ------------------------------------------------------------------ #
    def widths(self, total_width):
        """按可用宽度求出每列实际宽度（不足时自动收缩，绝不溢出）。"""
        active = self.active_columns()
        inner = max(0, total_width - 2 * _PAD - self.gaps_total())
        base = {c["key"]: self._w[c["key"]] for c in active}
        total = sum(base.values())
        if total <= inner:
            extra = inner - total
            for c in active:
                if c.get("stretch"):
                    base[c["key"]] += extra
                    break
            return base
        deficit = total - inner
        # 1) 先压缩 stretch 列（标题）
        for c in sorted(active, key=lambda c: -c.get("stretch", 0)):
            slack = base[c["key"]] - c["min"]
            if slack <= 0:
                continue
            take = min(slack, deficit)
            base[c["key"]] -= take
            deficit -= take
            if deficit <= 0:
                break
        if deficit > 0:
            # 2) 其余列按可压缩量等比收缩到各自 min
            others = [c for c in active if not c.get("stretch")]
            slack_total = sum(base[c["key"]] - c["min"] for c in others)
            if slack_total > 0:
                f = min(1.0, deficit / slack_total)
                for c in others:
                    s = base[c["key"]] - c["min"]
                    take = int(s * f)
                    base[c["key"]] -= take
                    deficit -= take
        if deficit > 0:
            # 3) 兜底：整体等比硬缩放（保留一个很小的下限，避免列被压成 0）
            scale = max(0.0, inner / max(1, sum(base.values())))
            for c in active:
                base[c["key"]] = max(24, int(base[c["key"]] * scale))
        return base

    def rects(self, rect):
        """按行/表头矩形计算各列矩形（仅含活动列）。"""
        ws = self.widths(rect.width())
        out = {}
        x = rect.x() + _PAD
        for c in self.active_columns():
            w = ws.get(c["key"], 0)
            if c["key"] == "cover":
                h = max(36, min(rect.height() - 16, int(w * 9 / 16)))
                out["cover"] = QRect(x, rect.y() + (rect.height() - h) // 2, w, h)
            else:
                out[c["key"]] = QRect(x, rect.y(), w, rect.height())
            x += w + c["gap"]
        return out


_default_layout = None


def _column_rects(rect, layout=None):
    """兼容旧调用：不传 layout 时用模块级默认布局。"""
    global _default_layout
    if layout is None:
        if _default_layout is None:
            _default_layout = ColumnLayout()
        layout = _default_layout
    return layout.rects(rect)


def _status_info(status):
    return {
        "waiting": (tr("等待"), "#cccccc"),
        "downloading": (tr("下载中"), "#42a5f5"),
        "paused": (tr("已暂停"), "#f39c12"),
        "completed": (tr("完成"), "#66bb6a"),
        "cancelled": (tr("已取消"), "#ffca28"),
        "failed": (tr("失败"), "#ef5350"),
    }.get(status, (tr("未知"), "#ffffff"))


def _action_buttons(rect, status):
    """返回该状态行「操作列」内的按钮列表 [(action, QRect)]。

    完成态为「打开文件位置」(open)，其余为 pause/resume/retry/del。
    按钮组在列内**水平居中**（旧实现固定从左侧 +6 排布，列宽变化时右侧会留空/溢出）。
    """
    acts = {
        "downloading": ["pause"],
        "paused": ["resume", "del"],
        "failed": ["retry", "del"],
        "cancelled": ["retry", "del"],
        "completed": ["open", "del"],
        "waiting": ["del"],
    }.get(status, [])
    if not acts:
        return []
    bw, bh, gap = 32, 30, 6
    total = len(acts) * bw + (len(acts) - 1) * gap
    x = rect.x() + max(2, (rect.width() - total) // 2)
    y = rect.y() + (rect.height() - bh) // 2
    res = []
    for a in acts:
        res.append((a, QRect(x, y, bw, bh)))
        x += bw + gap
    return res


def _draw_cell(painter, rect, text, align=Qt.AlignCenter, pad=4):
    """单元格文本绘制：宽度不足时省略号截断，绝不越界写到相邻列上。"""
    fm = QFontMetrics(painter.font())
    tw = max(0, rect.width() - 2 * pad)
    painter.drawText(rect, align, fm.elidedText(str(text), Qt.ElideRight, tw))


def _progress_bar_width(bar_width, progress):
    """把任务进度比例（0~1）转换为进度条像素宽度。"""
    fraction = max(0.0, min(1.0, float(progress or 0)))
    return max(2, int(bar_width * fraction))



class TaskListModel(QAbstractListModel):
    def __init__(self, tasks=None):
        super().__init__()
        self._tasks = list(tasks or [])

    def set_tasks(self, tasks):
        self.beginResetModel()
        self._tasks = list(tasks)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._tasks)

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.UserRole:
            return self._tasks[index.row()]
        return None

    def task_at(self, row):
        if 0 <= row < len(self._tasks):
            return self._tasks[row]
        return None

    def row_of_url(self, url):
        for i, t in enumerate(self._tasks):
            if t.get("url") == url:
                return i
        return -1


def _mouse_x(ev):
    """Qt6 用 position()，Qt5 用 pos()；统一取相对本控件的 x。"""
    try:
        return int(ev.position().x())
    except AttributeError:
        return int(ev.pos().x())


class HeaderBar(QWidget):
    """列标题栏：与 delegate 共用 ColumnLayout，保证表头与行严格对齐。

    交互：
    - 鼠标移到列分隔线（±5px）出现左右箭头光标，按住拖拽即可调整该列宽度；
    - 双击分隔线：该列恢复默认宽度；
    - 右键：弹出「恢复默认列宽」，一键还原所有列。
    """

    GRAB = 5        # 分隔线命中半径
    H = 30

    def __init__(self, layout):
        super().__init__()
        self._layout = layout
        self.setFixedHeight(self.H)
        self.setMouseTracking(True)
        self._off_l = 0        # 左侧偏移（列表边框），用于与 viewport 对齐
        self._off_r = 0        # 右侧偏移（垂直滚动条宽度）
        self._drag = None      # {"key","x0","w0"}
        self._hover_edge = None
        layout.changed.connect(self.update)

    # ------------------------------------------------------------------ #
    # 与列表 viewport 对齐（滚动条出现/消失、窗口缩放时同步）
    # ------------------------------------------------------------------ #
    def set_offsets(self, left, right):
        left, right = max(0, int(left)), max(0, int(right))
        if (left, right) != (self._off_l, self._off_r):
            self._off_l, self._off_r = left, right
            self.update()

    def inner_rect(self):
        return self.rect().adjusted(self._off_l, 0, -self._off_r, 0)

    # ------------------------------------------------------------------ #
    # 分隔线几何
    # ------------------------------------------------------------------ #
    def _edges(self):
        """[(列 key, 分隔线 x)]，取相邻两列之间的中点。"""
        active = self._layout.active_columns()
        cols = self._layout.rects(self.inner_rect())
        out = []
        for i in range(len(active) - 1):
            a = cols.get(active[i]["key"])
            b = cols.get(active[i + 1]["key"])
            if a is None or b is None:
                continue
            out.append((active[i]["key"], (a.right() + b.x()) // 2))
        return out

    def _edge_at(self, x):
        hit, best = None, 1 << 30
        for key, ex in self._edges():
            d = abs(x - ex)
            if d <= self.GRAB and d < best:
                hit, best = key, d
        return hit

    # ------------------------------------------------------------------ #
    # 鼠标交互
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            key = self._edge_at(_mouse_x(ev))
            if key:
                self._drag = {"key": key, "x0": _mouse_x(ev),
                              "w0": self._layout.width(key)}
                ev.accept()
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        x = _mouse_x(ev)
        if self._drag:
            total = self.inner_rect().width()
            self._layout.set_width(self._drag["key"],
                                   self._drag["w0"] + (x - self._drag["x0"]),
                                   total)
            ev.accept()
            return
        key = self._edge_at(x)
        if key != self._hover_edge:
            self._hover_edge = key
            self.setCursor(Qt.CursorShape.SplitHCursor if key else Qt.CursorShape.ArrowCursor)
            self.update()
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._drag:
            self._drag = None
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        key = self._edge_at(_mouse_x(ev))
        if key:
            self._layout.reset(key)      # 双击分隔线：该列恢复默认宽
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)

    def contextMenuEvent(self, ev):
        menu = QMenu(self)
        act = menu.addAction(tr("恢复默认列宽"))
        act.triggered.connect(lambda: self._layout.reset())
        menu.exec(ev.globalPos())

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #
    def paintEvent(self, ev):
        p = QPainter(self)
        pal = palette()
        p.fillRect(self.rect(), QColor(pal["panel2"]))
        inner = self.inner_rect()
        cols = self._layout.rects(inner)
        p.setPen(QColor(pal["sub"]))
        p.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        for c in self._layout.active_columns():
            label = tr(c["label"]) if c["label"] else ""
            if not label:
                continue
            r = cols.get(c["key"])
            if r is None:
                continue
            if c["key"] == "title":
                p.drawText(r.adjusted(4, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft,
                           QFontMetrics(p.font()).elidedText(label, Qt.ElideRight,
                                                             max(10, r.width() - 8)))
            else:
                p.drawText(r, Qt.AlignCenter,
                           QFontMetrics(p.font()).elidedText(label, Qt.ElideRight,
                                                             max(10, r.width() - 4)))
        # 分隔线（悬停/拖拽中高亮为强调色）
        accent = QColor(get_accent())
        for key, ex in self._edges():
            active = (key == self._hover_edge) or (self._drag and self._drag["key"] == key)
            p.setPen(QPen(accent if active else QColor(pal["border"]), 2 if active else 1))
            p.drawLine(ex, inner.y() + 5, ex, inner.bottom() - 5)
        p.setPen(QColor(pal["border"]))
        p.drawLine(self.rect().left(), self.rect().bottom(),
                   self.rect().right(), self.rect().bottom())
        p.end()


class TaskDelegate(QStyledItemDelegate):
    ROW_H = 92

    def __init__(self, list_view, owner, layout=None):
        super().__init__()
        # list_view: 内层 QListView —— 提供 viewport() / visualRect() / model()；
        # owner:     外层 QueueView  —— 提供 do_action() / show_context_menu() / thumbnail_for()。
        # 二者职责不同，早前把 owner 直接当 _view 传入，导致 viewport() 不存在而崩溃。
        self._view = list_view
        self._owner = owner
        self._cols = layout or getattr(owner, "column_layout", None)
        self._hover_row = -1
        self._hover_btn = None

    def rects(self, rect):
        """当前列宽下的各列矩形（表头与行共用同一份 ColumnLayout）。"""
        if self._cols is not None:
            return self._cols.rects(rect)
        return _column_rects(rect)

    # ------------------------------------------------------------------ #
    # 鼠标交互：悬停高亮、点击操作按钮、右键菜单（均走标准 editorEvent）
    # ------------------------------------------------------------------ #
    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseMove:
            self._track_hover(option, index, event.pos())
            return False
        if event.type() == QEvent.Type.Leave:
            self._clear_hover()
            return False
        if event.type() == QEvent.Type.MouseButtonRelease:
            task = index.data(Qt.UserRole)
            if task is None:
                return False
            cols = self.rects(option.rect)
            for action, br in _action_buttons(cols["actions"], task["status"]):
                if br.contains(event.pos()):
                    self._owner.do_action(action, task.get("url"))
                    return True
            return False
        if event.type() == QEvent.Type.MouseButtonPress and \
                event.button() == Qt.MouseButton.RightButton:
            self._owner.show_context_menu(index, event.globalPos())
            return True
        return False

    def _track_hover(self, option, index, pos):
        task = index.data(Qt.UserRole)
        hb = None
        if task is not None:
            cols = self.rects(option.rect)
            for action, br in _action_buttons(cols["actions"], task["status"]):
                if br.contains(pos):
                    hb = action
                    break
        if self._hover_row != index.row() or self._hover_btn != hb:
            prev = self._hover_row
            self._hover_row = index.row()
            self._hover_btn = hb
            self._view.viewport().update(self._view.visualRect(index))
            if prev != -1 and prev != index.row():
                prev_index = self._view.model().index(prev, 0)
                self._view.viewport().update(self._view.visualRect(prev_index))

    def _clear_hover(self):
        prev = self._hover_row
        self._hover_row = -1
        self._hover_btn = None
        if prev != -1:
            prev_index = self._view.model().index(prev, 0)
            self._view.viewport().update(self._view.visualRect(prev_index))

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #
    def paint(self, painter, option, index):
        task = index.data(Qt.UserRole)
        if task is None:
            return
        rect = option.rect
        pal = palette()
        bg = QColor(pal["panel"] if (index.row() % 2 == 0) else pal["panel2"])
        if option.state & QStyle.State_Selected:
            bg = QColor(get_accent())
            bg.setAlpha(60)
        painter.fillRect(rect, bg)

        # 整行悬停叠加（bili23 _drawBackground）
        if self._hover_row == index.row():
            painter.save()
            painter.setPen(Qt.NoPen)
            c = 255 if is_dark() else 0
            painter.setBrush(QColor(c, c, c, 18 if is_dark() else 12))
            painter.drawRoundedRect(rect.adjusted(4, 2, -4, -2), 5, 5)
            painter.restore()

        cols = self.rects(rect)
        fg = QColor(pal["fg"])
        sub = QColor(pal["sub"])

        # 封面（圆角 + 占位图）—— 精简布局下 cover 列被隐藏
        cr = cols.get("cover")
        if cr is not None and cr.width() > 0:
            pm = self._owner.thumbnail_for(task)
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            path = QPainterPath_rrect(cr, 6)
            painter.setClipPath(path)
            if pm is not None:
                # 按 16:9 填满并裁切（封面临界窄列时也不会变形拉伸到列外）
                painter.drawPixmap(cr, pm.scaled(cr.size(),
                                                 Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                                 Qt.TransformationMode.SmoothTransformation))
            else:
                draw_placeholder(painter, cr, QColor(pal["sub"]))
            painter.restore()
            # 封面描边
            painter.save()
            painter.setPen(QPen(QColor(pal["border"]), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(cr, 6, 6)
            painter.restore()

        # 序号
        painter.setFont(QFont("Microsoft YaHei UI", 13))
        if "num" in cols:
            _draw_cell(painter, cols["num"], str(index.row() + 1), pad=2)

        # 标题 + 徽标 + UP主
        tr_ = cols.get("title")
        if tr_ is not None:
            title = task.get("title", tr("未知"))
            painter.setFont(QFont("Microsoft YaHei UI", 13, QFont.Bold))
            title_y = tr_.y() + 8
            badge, badge_color = category_badge_color(task.get("category", ""))
            if badge:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(badge_color))
                bw = min(painter.fontMetrics().horizontalAdvance(badge) + 12,
                         max(0, tr_.width() - 4))
                painter.drawRoundedRect(tr_.x() + 2, title_y, bw, 18, 4, 4)
                painter.setPen(QColor("#ffffff"))
                painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
                painter.drawText(tr_.x() + 8, title_y + 13, badge)
                painter.setPen(fg)
                painter.setFont(QFont("Microsoft YaHei UI", 13, QFont.Bold))
                tx = tr_.x() + 2 + bw + 6
            else:
                tx = tr_.x() + 2
            painter.setPen(fg)
            painter.setFont(QFont("Microsoft YaHei UI", 13, QFont.Bold))
            title_w = max(10, tr_.right() - tx - 4)
            painter.drawText(QRect(tx, title_y, title_w, 22),
                             Qt.AlignLeft | Qt.AlignTop,
                             QFontMetrics(painter.font()).elidedText(
                                 title, Qt.ElideRight, title_w))
            # UP主（精简布局下仍保留，作为「标题 + UP + 时长」的一部分）
            uploader = task.get("uploader", "")
            if uploader:
                painter.setPen(sub)
                painter.setFont(QFont("Microsoft YaHei UI", 10))
                up_w = max(10, tr_.width() - 6)
                painter.drawText(QRect(tr_.x() + 2, title_y + 26, up_w, 18),
                                 Qt.AlignLeft | Qt.AlignVCenter,
                                 QFontMetrics(painter.font()).elidedText(
                                     uploader, Qt.ElideRight, up_w))

        # 时长 / 发布 / 播放 / 点赞 / 收藏（精简布局隐藏 pub/view/like/fav）
        painter.setPen(fg)
        painter.setFont(QFont("Microsoft YaHei UI", 12))
        if "dur" in cols:
            _draw_cell(painter, cols["dur"], format_duration(task.get("duration", 0)))
        if "pub" in cols:
            _draw_cell(painter, cols["pub"], str(task.get("publish_time", ""))[:10])
        if "view" in cols:
            _draw_cell(painter, cols["view"], format_count(task.get("view_count", 0)))
        if "like" in cols:
            _draw_cell(painter, cols["like"], format_count(task.get("like_count", 0)))
        if "fav" in cols:
            _draw_cell(painter, cols["fav"], format_count(task.get("favorite_count", 0)))

        # 状态
        stat_text, color = _status_info(task["status"])
        painter.setPen(QColor(color))
        if "status" in cols:
            _draw_cell(painter, cols["status"], stat_text)

        # 操作按钮（矢量 + 悬停高亮）
        actions_rect = cols.get("actions")
        if actions_rect is not None:
            hovered_row = (self._hover_row == index.row())
            for action, br in _action_buttons(actions_rect, task["status"]):
                self._draw_action(painter, br, action,
                                  hovered_row and self._hover_btn == action, pal)

        # 行内进度条（底部整行，按状态着色）
        pb = 0 if task["status"] == "waiting" else (task.get("progress", 0) or 0)
        if pb > 0:
            bar = QRect(rect.x() + 6, rect.bottom() - 5, rect.width() - 12, 4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(pal["border"]))
            painter.drawRoundedRect(bar, 2, 2)
            if task["status"] == "failed":
                bcol = QColor("#ef5350")
            elif task["status"] == "paused":
                bcol = QColor("#f39c12")
            else:
                bcol = QColor(get_accent())
            painter.setBrush(bcol)
            w = _progress_bar_width(bar.width(), pb)
            painter.drawRoundedRect(QRect(bar.x(), bar.y(), w, bar.height()), 2, 2)

    def _draw_action(self, painter, br, action, hovered, pal):
        icon_color = QColor(pal["fg"])
        if hovered:
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(get_accent()))
            painter.drawRoundedRect(br, 6, 6)
            painter.restore()
            icon_color = QColor("#ffffff")
        if action == "pause":
            draw_pause(painter, br, icon_color)
        elif action == "resume":
            draw_play(painter, br, icon_color)
        elif action == "retry":
            draw_retry(painter, br, icon_color)
        elif action == "del":
            draw_delete(painter, br, icon_color)
        elif action == "open":
            draw_folder(painter, br, icon_color)

    def sizeHint(self, option, index):
        return QSize(0, self.ROW_H)


def QPainterPath_rrect(rect, r):
    """构造圆角矩形 QPainterPath（避免直接依赖 QPainterPath 导入位置）。"""
    from PySide6.QtGui import QPainterPath
    p = QPainterPath()
    p.addRoundedRect(rect, r, r)
    return p


def _set_progress_bar(prog, value):
    """兼容 main_window 总进度条（QProgressBar，`value` 为 0~1 比例）。"""
    try:
        prog.setValue(int((value or 0) * 100))
    except Exception:
        pass


class QueueView(QWidget):
    thumb_loaded = Signal(str, QByteArray)

    def __init__(self, master, engine, config):
        super().__init__(master)
        self.engine = engine
        self.config = config
        self._closed = False
        self._thumbs = {}            # url -> QPixmap
        self._pending = set()        # 正在加载的 url
        self._thumb_q = pyq.Queue()
        self._tasks = []
        self._current_group = "active"
        self._task_groups = {}
        self._queue_initialized = False
        self._unread_counts = {"active": 0, "cancelled": 0, "completed": 0}
        self._model = TaskListModel([])
        self._model.set_tasks(engine.queue)

        # 列宽：从 settings.json 恢复（旧版残留的 list 结构会被忽略，回落到默认宽）
        saved = None
        try:
            saved = self.config.get("column_widths") if self.config else None
        except Exception:
            saved = None
        self.column_layout = ColumnLayout(saved, self)
        self.column_layout.changed.connect(self._on_layout_changed)
        # 全局列表布局模式（详细/精简）切换：精简隐藏 封面/发布/播放/点赞/收藏
        # （实际套用放到 __init__ 末尾，确保 _header / _list 已建好后再触发重绘）
        self._unsub_layout = manager.connect(self._on_layout_mode)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self._save_layout)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._tabs = Pivot(self)
        self._tabs.addItem("active", tr("正在下载"))
        self._tabs.addItem("cancelled", tr("已取消"))
        self._tabs.addItem("completed", tr("下载完成"))
        self._tab_badges = {
            key: InfoBadge.error(
                "1", parent=self._tabs, target=self._tabs.widget(key))
            for key in self._unread_counts
        }
        for badge in self._tab_badges.values():
            badge.hide()
        self._tabs.currentItemChanged.connect(self._on_tab_changed)
        self._tabs.setCurrentItem("active")
        # 水平布局：Pivot 左对齐（与视频下载设置顶部导航一致），右侧留白
        pivot_row = QHBoxLayout()
        pivot_row.setContentsMargins(10, 6, 10, 2)
        pivot_row.addWidget(self._tabs)
        pivot_row.addStretch(1)
        lay.addLayout(pivot_row)

        self._header = HeaderBar(self.column_layout)
        lay.addWidget(self._header)
        self._list = QListView()
        self._view = self._list
        self.view = self._list
        self._list.setModel(self._model)
        # delegate 需要两个引用：内层 QListView（绘制/命中几何）+ 外层 QueueView（业务操作）
        self._delegate = TaskDelegate(self._list, self, self.column_layout)
        self._list.setItemDelegate(self._delegate)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._list.setSpacing(0)
        self._list.setMouseTracking(True)
        self._list.installEventFilter(self)
        lay.addWidget(self._list, 1)
        # 滚动条出现/消失会让 viewport 变窄，需同步表头右侧偏移，保证列对齐
        try:
            self._list.verticalScrollBar().rangeChanged.connect(
                lambda *_: self._sync_header_geometry())
        except Exception:
            pass

        self.thumb_loaded.connect(self._on_thumb_loaded)
        self._start_loaders()
        self.update_view(engine.queue)
        # 套用持久化的布局模式（详细/精简）—— 此时 _header/_list 已就绪
        self._on_layout_mode()
        QTimer.singleShot(0, self._sync_header_geometry)

    # ---------- 列宽：变更重绘 + 防抖落盘 ----------
    def _on_layout_changed(self):
        if not (hasattr(self, "_header") and hasattr(self, "_list")):
            return
        self._header.update()
        self._list.viewport().update()
        self._save_timer.start()

    # ---------- 布局模式（详细/精简）----------
    def _on_layout_mode(self, _mode=None):
        """精简布局隐藏 封面/发布/播放/点赞/收藏 列，仅保留 序号/标题(含UP)/时长/状态/操作。"""
        hidden = {"cover", "pub", "view", "like", "fav"} if manager.is_compact() else set()
        self.column_layout.set_hidden(hidden)
        self._sync_header_geometry()

    def retranslate(self):
        """语言切换时刷新表头与单元格文案。

        HeaderBar 用 paintEvent 绘制 tr(c["label"])，列名不缓存，但没有任何
        信号在语言切换时通知它重绘，所以必须主动 update()；列表 viewport 同理
        （单元格状态文字由 delegate 绘制，依赖重绘才重新 tr()）。
        """
        self._tabs.setItemText("active", tr("正在下载"))
        self._tabs.setItemText("cancelled", tr("已取消"))
        self._tabs.setItemText("completed", tr("下载完成"))
        self._header.update()
        self._list.viewport().update()

    def _save_layout(self):
        try:
            if self.config is not None:
                self.config.set("column_widths", self.column_layout.as_dict())
        except Exception:
            pass

    # ---------- 表头与列表 viewport 对齐 ----------
    def _sync_header_geometry(self):
        """把表头左右各缩进列表边框 / 滚动条的宽度，使表头列与行严格对齐。"""
        if self._closed:
            return
        try:
            vp = self._list.viewport()
            left = vp.mapTo(self, QPoint(0, 0)).x() - self._header.x()
            right = self._header.width() - (left + vp.width())
            self._header.set_offsets(left, max(0, right))
        except Exception:
            pass

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._sync_header_geometry()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._sync_header_geometry()

    def reset_column_widths(self):
        """恢复默认列宽（供设置/菜单调用）。"""
        self.column_layout.reset()

    # ---------- 事件过滤：列表离开时清除悬停 ----------
    def eventFilter(self, obj, ev):
        if obj is self._list and ev.type() == QEvent.Type.Leave:
            self._delegate._clear_hover()
            return False
        return super().eventFilter(obj, ev)

    # ---------- 数据更新 ----------
    @staticmethod
    def _group_for_status(status):
        if status == "cancelled":
            return "cancelled"
        if status == "completed":
            return "completed"
        return "active"

    @staticmethod
    def _task_identity(task):
        return task.get("id") or task.get("url")

    def _on_tab_changed(self, route_key):
        if route_key not in self._unread_counts:
            return
        self._current_group = route_key
        self._unread_counts[self._current_group] = 0
        self._update_tab_badges()
        self._refresh_filtered_tasks()

    def _update_tab_badges(self):
        for group, badge in self._tab_badges.items():
            count = self._unread_counts[group]
            if count:
                badge.setText(str(count) if count < 100 else "99+")
                badge.adjustSize()
                manager = getattr(badge, "manager", None)
                if manager is not None:
                    badge.move(manager.position())
                badge.show()
            else:
                badge.hide()

    def _refresh_filtered_tasks(self):
        visible = [
            task for task in self._tasks
            if self._group_for_status(task.get("status")) == self._current_group
        ]
        self._model.set_tasks(visible)
        QTimer.singleShot(0, self._sync_header_geometry)

    def update_view(self, queue):
        """结构/内容整体刷新（主线程调用，来自引擎回调）。"""
        if self._closed:
            return
        self._tasks = list(queue)
        current_groups = {}
        for task in self._tasks:
            identity = self._task_identity(task)
            if identity is None:
                continue
            group = self._group_for_status(task.get("status"))
            current_groups[identity] = group
            previous = self._task_groups.get(identity)
            if (self._queue_initialized and group != previous
                    and group != self._current_group):
                self._unread_counts[group] += 1
        self._task_groups = current_groups
        self._queue_initialized = True
        self._update_tab_badges()
        self._refresh_filtered_tasks()

    def update_task_progress(self, url, percent, speed=None):
        """高频进度回调：只刷新匹配 URL 的那一行（dataChanged），不重建列表。"""
        if self._closed:
            return
        task = next((t for t in self._tasks if t.get("url") == url), None)
        if task is None:
            return
        task["progress"] = percent
        row = self._model.row_of_url(url)
        if row >= 0:
            idx = self._model.index(row, 0)
            self._model.dataChanged.emit(idx, idx)

    # ---------- 缩略图异步加载 ----------
    def thumbnail_for(self, task):
        url = task.get("thumbnail", "")
        if not url:
            return None
        pm = self._thumbs.get(url)
        if pm is not None:
            return pm
        if url not in self._pending:
            self._pending.add(url)
            self._thumb_q.put(url)
        return None

    def _start_loaders(self):
        for _ in range(4):
            threading.Thread(target=self._loader, daemon=True).start()

    def _loader(self):
        while not self._closed:
            try:
                url = self._thumb_q.get(timeout=1)
            except pyq.Empty:
                continue
            try:
                thumb = optimize_thumbnail_url(url)
                resp = requests.get(thumb, timeout=4)
                img = Image.open(BytesIO(resp.content)).convert("RGB")
                img.thumbnail((120, 120))
                ba = QByteArray()
                buf = BytesIO()
                img.save(buf, format="PNG")
                ba.append(buf.getvalue())
                self.thumb_loaded.emit(url, ba)
            except Exception:
                self._pending.discard(url)

    def _on_thumb_loaded(self, url, ba):
        pm = QPixmap()
        if pm.loadFromData(ba):
            self._thumbs[url] = pm
        self._pending.discard(url)
        for i, t in enumerate(self._tasks):
            if t.get("thumbnail") == url:
                idx = self._model.index(i, 0)
                self._model.dataChanged.emit(idx, idx)

    # ---------- 操作按钮命中（由 delegate editorEvent 调用）----------
    def do_action(self, action, url):
        if action == "del":
            with getattr(self.engine, "_lock", _Null()):
                for i, item in enumerate(self.engine.queue):
                    if item.get("url") == url:
                        del self.engine.queue[i]
                        break
            try:
                self.engine.save_tasks()
            except Exception:
                pass
            self.update_view(self.engine.queue)
        elif action == "pause":
            self.engine.pause_task(url)
        elif action == "resume":
            self.engine.resume_task(url)
        elif action == "retry":
            self.engine.retry_task(url)
        elif action == "open":
            self._open_location(url)

    def _open_location(self, url):
        """打开任务下载目录（bili23 完成态文件夹按钮行为）。"""
        task = None
        for t in self._tasks:
            if t.get("url") == url:
                task = t
                break
        if not task:
            return
        d = task.get("download_path") or self.config.get("download_path") if self.config else None
        folder = task.get("folder")
        target = d
        if folder:
            target = os.path.join(d, folder) if d else folder
        try:
            if target and os.path.isdir(target):
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(target)))
            elif d:
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(d)))
        except Exception:
            pass

    # ---------- 右键上下文菜单 ----------
    def show_context_menu(self, index, pos):
        task = index.data(Qt.UserRole)
        if task is None:
            return
        url = task.get("url", "")
        status = task.get("status", "")
        menu = QMenu(self)
        if status == "completed":
            a = menu.addAction(tr("打开文件位置"))
            a.triggered.connect(lambda: self._open_location(url))
        if status == "downloading":
            a = menu.addAction(tr("暂停"))
            a.triggered.connect(lambda: self.engine.pause_task(url))
        elif status == "paused":
            a = menu.addAction(tr("继续"))
            a.triggered.connect(lambda: self.engine.resume_task(url))
        if status in ("failed", "cancelled"):
            a = menu.addAction(tr("重试"))
            a.triggered.connect(lambda: self.engine.retry_task(url))
        a = menu.addAction(tr("删除"))
        a.triggered.connect(lambda: self.do_action("del", url))
        a = menu.addAction(tr("复制链接"))
        a.triggered.connect(lambda: self._copy(url))
        menu.exec(pos)

    def _copy(self, url):
        try:
            import pyperclip
            pyperclip.copy(url)
        except Exception:
            pass

    def closeEvent(self, ev):
        self._closed = True
        try:
            if getattr(self, "_unsub_layout", None) is not None:
                self._unsub_layout()
        except Exception:
            pass
        super().closeEvent(ev)


class _Null:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False
