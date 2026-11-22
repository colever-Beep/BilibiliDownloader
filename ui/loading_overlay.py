"""加载遮罩：在列表区域中央显示转圈动画 + 说明文字。

用于替代原先散落在状态栏左下角的「加载中... / 正在加载第 N 页...」纯文字提示。
用法：把需要覆盖的列表用 ``LoadingOverlay.wrap(list_widget)`` 包一层，得到
容器 + overlay；加载时 ``overlay.show()``（自动居中和置顶），完成 ``overlay.hide()``。

设计要点：
- **半透明遮罩背景**：盖住底层列表内容，避免转圈动画与已有条目文字重叠、糊成一团；
  背景色跟随明暗主题（浅色用浅灰白、深色用深灰），约 72% 不透明度——既能遮挡
  内容又透出轮廓，不会纯白/纯黑刺眼；
- 使用 qfluentwidgets 的 ``IndeterminateProgressRing``（转圈进度环），
  颜色跟随主题强调色，深浅主题自动适配；
- overlay 随容器 resize 自动居中（resizeEvent 里重定位）；
- 文字通过 tr() 包一层，切换语言时调 ``set_text()`` 更新。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from qfluentwidgets import CaptionLabel, IndeterminateProgressRing

from utils.i18n import tr
from ui.theme import is_dark


def _mask_stylesheet() -> str:
    """半透明遮罩背景色，跟随当前明暗主题。"""
    # 浅色主题：柔和浅灰白；深色主题：柔和深灰。alpha≈0.72，盖住内容但仍透出轮廓。
    return ("LoadingOverlay { background-color: rgba(245, 245, 247, 184); }"
            if not is_dark()
            else "LoadingOverlay { background-color: rgba(32, 32, 34, 190); }")


class LoadingOverlay(QFrame):
    """覆盖在目标控件上的加载动画层（带半透明遮罩）。"""

    def __init__(self, parent: QWidget, text: str | None = None):
        super().__init__(parent)
        # 允许 stylesheet 背景生效（QFrame 默认绘制，但显式声明更稳妥）
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_mask_stylesheet())
        self._ring = IndeterminateProgressRing(self)
        self._ring.setFixedSize(42, 42)
        self._label = CaptionLabel(text or tr("加载中..."), self)
        self._label.setAlignment(Qt.AlignHCenter)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        lay.addStretch(1)
        lay.addWidget(self._ring, alignment=Qt.AlignHCenter)
        lay.addWidget(self._label, alignment=Qt.AlignHCenter)
        lay.addStretch(1)

        # 默认隐藏；由调用方在加载态 show()
        self.hide()

    def refresh_theme(self):
        """主题切换后刷新遮罩底色（布局/文字由全局 QSS 自动处理，仅背景需手动同步）。"""
        self.setStyleSheet(_mask_stylesheet())

    def set_text(self, text: str):
        """更新加载说明文字（已由调用方 tr() 翻译）。"""
        self._label.setText(text or "")

    def set_ring_size(self, size: int):
        self._ring.setFixedSize(size, size)

    def resizeEvent(self, e):
        # 覆盖整个父控件区域并居中内容
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(0, 0, parent.width(), parent.height())
        super().resizeEvent(e)

    def showEvent(self, e):
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(0, 0, parent.width(), parent.height())
        # 遮罩颜色在显示时重取一次，确保主题切换后正确
        self.setStyleSheet(_mask_stylesheet())
        self.raise_()
        super().showEvent(e)


def wrap(widget: QWidget, text: str | None = None):
    """把 ``widget`` 包进一个带 LoadingOverlay 的容器。

    返回 ``(container, overlay)``。调用方把 container 加到布局中代替原 widget；
    overlay 覆盖在 widget 之上，加载时显示转圈动画 + 半透明遮罩。
    """
    container = QWidget(widget.parent())
    lay = QVBoxLayout(container)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    lay.addWidget(widget)
    overlay = LoadingOverlay(container, text)
    return container, overlay
