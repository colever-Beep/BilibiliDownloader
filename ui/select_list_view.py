"""可复用的「勾选选择」列表组件（参照 bili23 的 CheckListView / EntryListItem 风格）。

供「视频选择对话框」(SelectDialog / PaginatedSelectDialog) 与「分集选择对话框」
(EpisodeSelectDialog) 共用，统一视觉与交互：

- 每行：圆角封面（异步加载，无图显示占位图）+ 勾选框 + 标题 + 副信息
  （UP主 · 时长 · 播放 · 点赞 · 收藏）+ 类型徽标。
- 没有封面 / 统计字段时（如分集）自动进入紧凑模式：仅显示 # / 标题 / 时长。
- 整行悬停高亮（bili23 的 _drawBackground）。
- 点击整行即切换勾选（bili23 CheckListView 行为），勾选态由调用方持有的
  `checked_keys` 集合驱动，因此跨翻页 / 过滤天然保持一致。
- 原生虚拟化（QListView + QAbstractListModel），几千条也不卡。

使用方只需：构造 `SelectListView(checked_keys, parent)`，连接 `rowClicked` 信号，
调用 `set_items(...)`；勾选态读取 `checked_keys` 集合即可，列表只负责绘制与交互。
"""
import threading
import queue as pyq
from io import BytesIO

import requests
from PIL import Image

from PySide6.QtCore import (
    Qt, QAbstractListModel, QModelIndex, QSize, QRect, QByteArray, Signal, QEvent,
)
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QFontMetrics, QPainterPath
from PySide6.QtWidgets import (
    QListView, QAbstractItemView, QStyledItemDelegate, QStyleOptionViewItem,
)

from utils.helpers import optimize_thumbnail_url, format_duration, format_count
from utils.i18n import tr
from ui.theme import palette, is_dark, get_accent
from ui.list_icons import (
    draw_check, draw_placeholder, category_badge_color,
)
from ui.list_layout import manager, is_compact


def _key_of(item):
    if not item:
        return None
    return item.get("url") or item.get("bvid") or id(item)


class SelectListModel(QAbstractListModel):
    def __init__(self, checked_keys):
        super().__init__()
        self._items = []
        self._checked_keys = checked_keys  # 调用方持有的 set，作为唯一勾选真值源

    def set_items(self, items):
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.UserRole:
            return self._items[index.row()]
        return None

    def item_at(self, row):
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def is_checked(self, index):
        it = self.item_at(index.row())
        key = _key_of(it)
        return key in self._checked_keys


class SelectItemDelegate(QStyledItemDelegate):
    ROW_H = 70

    def __init__(self, view):
        super().__init__()
        self._view = view
        self._hover_row = -1

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #
    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseMove:
            if self._hover_row != index.row():
                prev = self._hover_row
                self._hover_row = index.row()
                self._view.viewport().update(self._view.visualRect(index))
                if prev != -1:
                    prev_index = self._view.model().index(prev, 0)
                    self._view.viewport().update(self._view.visualRect(prev_index))
            return False
        if event.type() == QEvent.Type.Leave:
            prev = self._hover_row
            self._hover_row = -1
            if prev != -1:
                prev_index = self._view.model().index(prev, 0)
                self._view.viewport().update(self._view.visualRect(prev_index))
            return False
        if event.type() == QEvent.Type.MouseButtonRelease and \
                event.button() == Qt.MouseButton.LeftButton:
            self._view.rowClicked.emit(index)
            return True
        return False

    # ------------------------------------------------------------------ #
    # 绘制
    # ------------------------------------------------------------------ #
    def paint(self, painter, option, index):
        item = index.data(Qt.UserRole)
        if item is None:
            return
        rect = option.rect
        pal = palette()
        bg = QColor(pal["panel"] if (index.row() % 2 == 0) else pal["panel2"])
        painter.fillRect(rect, bg)

        if self._hover_row == index.row():
            painter.save()
            painter.setPen(Qt.NoPen)
            c = 255 if is_dark() else 0
            painter.setBrush(QColor(c, c, c, 18 if is_dark() else 12))
            painter.drawRoundedRect(rect.adjusted(4, 2, -4, -2), 5, 5)
            painter.restore()

        checked = self._view.model().is_checked(index)
        fg = QColor(pal["fg"])
        sub = QColor(pal["sub"])
        accent = QColor(get_accent())

        x = rect.x() + 10
        # 勾选框
        cb = QRect(x, rect.center().y() - 11, 22, 22)
        draw_check(painter, cb, checked, accent, QColor(pal["sub"]))
        x += 30

        # ---- 精简布局：仅展示 标题 + UP + 时长（隐藏封面 / 徽标 / 统计）----
        if is_compact():
            self._paint_compact(painter, item, rect, x, fg, sub)
            return

        has_thumb = bool(item.get("thumbnail"))
        if has_thumb:
            is_user = item.get("type") == "user"
            cover_size = 56
            cover_width = cover_size if is_user else 100
            cover = QRect(x, rect.y() + (rect.height() - cover_size) // 2,
                          cover_width, cover_size)
            pm = self._view.thumbnail_for(item)
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            if is_user:
                path = QPainterPath()
                path.addEllipse(cover)
                painter.setClipPath(path)
            else:
                painter.setClipPath(QPainterPath_rrect(cover, 6))
            if pm is not None:
                painter.drawPixmap(cover, pm)
            else:
                draw_placeholder(painter, cover, sub)
            painter.restore()
            painter.save()
            painter.setPen(QPen(QColor(pal["border"]), 1))
            painter.setBrush(Qt.NoBrush)
            if is_user:
                painter.drawEllipse(cover)
            else:
                painter.drawRoundedRect(cover, 6, 6)
            painter.restore()
            x = cover.right() + 12
        else:
            # 紧凑模式：显示序号 #
            painter.setPen(sub)
            painter.setFont(QFont("Microsoft YaHei UI", 12))
            painter.drawText(QRect(x, rect.y(), 26, rect.height()),
                             Qt.AlignCenter, str(index.row() + 1))
            x += 30

        # 文本块
        tx = x
        tw = rect.right() - tx - 14
        title = item.get("title", tr("未知"))
        # 类型徽标
        badge, badge_color = category_badge_color(item.get("category", ""))
        painter.setFont(QFont("Microsoft YaHei UI", 13, QFont.Bold))
        if badge:
            bw = painter.fontMetrics().horizontalAdvance(badge) + 12
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(badge_color))
            painter.drawRoundedRect(tx + 2, rect.y() + 10, bw, 18, 4, 4)
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
            painter.drawText(tx + 8, rect.y() + 23, badge)
            painter.restore()
            title_x = tx + 2 + bw + 6
        else:
            title_x = tx + 2
        painter.setPen(fg)
        painter.setFont(QFont("Microsoft YaHei UI", 13, QFont.Bold))
        painter.drawText(QRect(title_x, rect.y() + 8, rect.right() - title_x - 6, 22),
                         Qt.AlignLeft | Qt.AlignTop,
                         QFontMetrics(painter.font()).elidedText(
                             title, Qt.ElideRight, rect.right() - title_x - 6))

        # 副信息：UP主 · 时长 · 播放 · 点赞 · 收藏
        parts = []
        up = item.get("uploader", "")
        if up:
            parts.append(up)
        dur = item.get("duration", 0)
        if dur:
            parts.append(format_duration(dur))
        vc = item.get("view_count", 0)
        if vc:
            parts.append(f"{tr('播放')} {format_count(vc)}")
        lc = item.get("like_count", 0)
        if lc:
            parts.append(f"{tr('点赞')} {format_count(lc)}")
        fc = item.get("favorite_count", 0)
        if fc:
            parts.append(f"{tr('收藏')} {format_count(fc)}")
        if parts:
            painter.setPen(sub)
            painter.setFont(QFont("Microsoft YaHei UI", 10))
            painter.drawText(QRect(tx + 2, rect.y() + 38, tw, 18),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             QFontMetrics(painter.font()).elidedText(
                                 " · ".join(parts), Qt.ElideRight, tw))
        elif has_thumb:
            # 有封面但无副信息：底部留白即可
            pass

    def sizeHint(self, option, index):
        return QSize(0, self.ROW_H)

    # ------------------------------------------------------------------ #
    # 精简布局：标题 + UP + 时长（无封面 / 徽标 / 统计）
    # ------------------------------------------------------------------ #
    def _paint_compact(self, painter, item, rect, x, fg, sub):
        tx = x
        tw = rect.right() - tx - 14
        if tw <= 0:
            return
        title = item.get("title", tr("未知"))

        # 标题（加粗，单行省略）
        painter.setPen(fg)
        painter.setFont(QFont("Microsoft YaHei UI", 13, QFont.Bold))
        painter.drawText(
            QRect(tx, rect.y() + 8, tw, 22),
            Qt.AlignLeft | Qt.AlignTop,
            QFontMetrics(painter.font()).elidedText(title, Qt.ElideRight, tw))

        # 第二行：UP · 时长（分集无 UP，仅显示时长）
        up = item.get("uploader", "")
        dur = item.get("duration", 0)
        parts = []
        if up:
            parts.append(up)
        if dur:
            parts.append(format_duration(dur))
        if parts:
            painter.setPen(sub)
            painter.setFont(QFont("Microsoft YaHei UI", 10))
            painter.drawText(
                QRect(tx, rect.y() + 38, tw, 18),
                Qt.AlignLeft | Qt.AlignVCenter,
                QFontMetrics(painter.font()).elidedText(
                    " · ".join(parts), Qt.ElideRight, tw))


def QPainterPath_rrect(rect, r):
    p = QPainterPath()
    p.addRoundedRect(rect, r, r)
    return p


class SelectListView(QListView):
    rowClicked = Signal(QModelIndex)

    def __init__(self, checked_keys, parent=None):
        super().__init__(parent)
        self._closed = False
        self._thumbs = {}
        self._pending = set()
        self._thumb_q = pyq.Queue()
        self._model = SelectListModel(checked_keys)
        self.setModel(self._model)
        self._delegate = SelectItemDelegate(self)
        self.setItemDelegate(self._delegate)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setSpacing(0)
        self.setMouseTracking(True)
        self._start_loaders()
        # 全局布局模式切换时实时重绘（跨窗口同步）
        self._unsub = manager.connect(lambda _mode: self._repaint_all())

    def _repaint_all(self):
        if getattr(self, "_closed", False):
            return
        try:
            self.viewport().update()
        except Exception:
            pass

    # ---------- 数据 ----------
    def set_items(self, items):
        self._model.set_items(items)

    def items(self):
        return self._model._items

    def refresh_row(self, index):
        self._model.dataChanged.emit(index, index)

    # ---------- 缩略图异步加载 ----------
    def thumbnail_for(self, item):
        url = item.get("thumbnail", "")
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
        for _ in range(3):
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
                img.thumbnail((200, 120))
                ba = QByteArray()
                buf = BytesIO()
                img.save(buf, format="PNG")
                ba.append(buf.getvalue())
                self._on_loaded(url, ba)
            except Exception:
                self._pending.discard(url)

    def _on_loaded(self, url, ba):
        pm = QPixmap()
        if pm.loadFromData(ba):
            self._thumbs[url] = pm
        self._pending.discard(url)
        # 通知主线程刷新所有含该封面的行
        try:
            run_on_main_safe(lambda: self._repaint_thumb(url))
        except Exception:
            self._repaint_thumb(url)

    def _repaint_thumb(self, url):
        for i, it in enumerate(self._model._items):
            if it.get("thumbnail") == url:
                idx = self._model.index(i, 0)
                self._model.dataChanged.emit(idx, idx)

    def closeEvent(self, ev):
        self._closed = True
        try:
            if getattr(self, "_unsub", None) is not None:
                self._unsub()
        except Exception:
            pass
        super().closeEvent(ev)


def run_on_main_safe(fn):
    """优先切回主线程执行 UI 刷新；若主线程辅助不可用则就地执行。"""
    try:
        from utils.main_thread import run_on_main
        run_on_main(fn)
    except Exception:
        fn()
