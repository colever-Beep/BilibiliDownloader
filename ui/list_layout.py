"""全局列表布局模式（详细 / 精简）—— 供所有视频/选择类列表共享。

设计要点
--------
- 模式：``detailed``（详细，参照视频选择窗口）/ ``compact``（精简，仅 标题 + UP + 时长）。
- 持久化到 ``settings.json`` 的 ``list_layout``（通过注入的 ``ConfigManager``）。
- 任何列表构造时读 ``get_mode()`` 决定初始绘制，并通过 ``connect()`` 订阅模式变更，
  从而在主窗口切换后，所有已打开的列表窗口（选择弹窗 / 下载队列 / 搜索结果…）实时同步刷新。
- 不依赖 ``QObject``/``Signal``，避免某些导入时机（``QApplication`` 之前）下创建信号对象的隐患；
  用纯回调集合实现广播，天然线程安全（订阅回调内部自行保证切回主线程）。
"""
from __future__ import annotations

_DETAILED = "detailed"
_COMPACT = "compact"
_MODES = (_DETAILED, _COMPACT)


class ListLayoutManager:
    """列表布局模式单例（模块级 ``manager``）。

    用法::

        from ui.list_layout import manager, is_compact, set_config

        set_config(config)                       # 启动时注入，用于持久化
        mode = manager.get_mode()               # "detailed" / "compact"
        manager.set_mode("compact")             # 切换（自动落盘 + 广播）
        unsub = manager.connect(lambda m: repaint())   # 订阅变更
        unsub()                                 # 取消订阅
    """

    def __init__(self):
        self._mode = _DETAILED
        self._config = None
        self._callbacks = set()

    # ------------------------------------------------------------------ #
    # 配置 / 持久化
    # ------------------------------------------------------------------ #
    def set_config(self, config):
        self._config = config
        m = _DETAILED
        try:
            v = self._config.get("list_layout", _DETAILED)
            if v in _MODES:
                m = v
        except Exception:
            m = _DETAILED
        self._mode = m

    # ------------------------------------------------------------------ #
    # 读写
    # ------------------------------------------------------------------ #
    def get_mode(self):
        return self._mode

    def is_compact(self):
        return self._mode == _COMPACT

    def set_mode(self, mode):
        if mode not in _MODES or mode == self._mode:
            return
        self._mode = mode
        if self._config is not None:
            try:
                self._config.set("list_layout", mode)
            except Exception:
                pass
        for cb in list(self._callbacks):
            try:
                cb(mode)
            except Exception:
                # 单个订阅异常不应阻断其它订阅；销毁后的控件回调会自动抛错，忽略即可
                pass

    # ------------------------------------------------------------------ #
    # 订阅
    # ------------------------------------------------------------------ #
    def connect(self, callback):
        """订阅模式变更，返回取消订阅的 callable。"""
        self._callbacks.add(callback)
        return lambda: self._callbacks.discard(callback)

    def disconnect(self, callback):
        self._callbacks.discard(callback)


# 模块级单例：导入即用，无需显式构造
manager = ListLayoutManager()


# --------------------------------------------------------------------------- #
# 便捷函数
# --------------------------------------------------------------------------- #
def get_mode():
    return manager.get_mode()


def is_compact():
    return manager.is_compact()


def set_mode(mode):
    manager.set_mode(mode)


def set_config(config):
    manager.set_config(config)


def connect(callback):
    return manager.connect(callback)


# --------------------------------------------------------------------------- #
# 水平导航控件：仅用图标切换 详细 / 精简（参照 bili23 的列表密度切换）
# --------------------------------------------------------------------------- #
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QIcon  # noqa: E402
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton  # noqa: E402

from qfluentwidgets import FluentIcon  # noqa: E402

from utils.i18n import tr  # noqa: E402
from ui.theme import palette, get_accent  # noqa: E402
from ui.icons import icon_pixmap  # noqa: E402


class LayoutModeToggle(QWidget):
    """窗口左下方的水平导航控件：仅用图标切换 详细 / 精简 布局。

    - 详细：``FluentIcon.LIBRARY``（信息丰富，参照视频选择窗口）。
    - 精简：``FluentIcon.APPLICATION``（紧凑，仅标题 + UP + 时长）。
    激活态以强调色背景 + 白色图标高亮；未激活为透明底 + 次级色图标。
    通过 ``ui.list_layout.manager`` 广播，与全局模式实时同步。
    """

    _BTN_SIZE = 30
    _ICON = 17

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.detailed_btn = QPushButton(self)
        self.compact_btn = QPushButton(self)
        for b in (self.detailed_btn, self.compact_btn):
            b.setFixedSize(self._BTN_SIZE, self._BTN_SIZE)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.detailed_btn.setToolTip(tr("详细布局"))
        self.compact_btn.setToolTip(tr("精简布局"))
        self.detailed_btn.clicked.connect(lambda: manager.set_mode(_DETAILED))
        self.compact_btn.clicked.connect(lambda: manager.set_mode(_COMPACT))

        lay.addWidget(self.detailed_btn)
        lay.addWidget(self.compact_btn)

        self._unsub = manager.connect(self._on_mode)
        self.destroyed.connect(lambda: self._unsub())
        try:
            from qfluentwidgets import qconfig
            qconfig.themeChanged.connect(self._refresh)
            qconfig.accentColorChanged.connect(self._refresh)
        except Exception:
            pass
        self._refresh()

    # ------------------------------------------------------------------ #
    def _on_mode(self, _mode=None):
        # 模式 / 主题（明暗/强调色）变化时调色板会变，也需重绘图标与背景
        self._refresh()

    def _refresh(self):
        try:
            pal = palette()
            accent = QColor(get_accent())
            sub = QColor(pal["sub"])
            mode = manager.get_mode()
            self._paint_btn(self.detailed_btn, FluentIcon.LIBRARY,
                            mode == _DETAILED, accent, sub)
            self._paint_btn(self.compact_btn, FluentIcon.APPLICATION,
                            mode == _COMPACT, accent, sub)
        except Exception:
            # 控件已销毁或调色板暂不可用时静默跳过
            pass

    @staticmethod
    def _paint_btn(btn, icon, active, accent, sub):
        qss = "QPushButton{{border:none;border-radius:6px;background:{bg};}}"
        if active:
            btn.setStyleSheet(qss.format(bg=accent.name()))
            btn.setIcon(QIcon(icon_pixmap(icon, LayoutModeToggle._ICON, "#ffffff")))
        else:
            btn.setStyleSheet(qss.format(bg="transparent"))
            btn.setIcon(QIcon(icon_pixmap(icon, LayoutModeToggle._ICON, sub.name())))
