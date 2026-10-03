"""qfluentwidgets 模态对话框基类（参照 bili23 的 gui/component/dialog.py）。

- `FluentModalDialog`：无边框 + Fluent 标题栏的模态窗口。`FluentWidget` 是窗口而非
  `QDialog`，没有原生 `exec()`，这里用 `QEventLoop` 实现等效的模态阻塞语义
  （bili23 的 `FluentDialogBase` 同款做法），并手动在主窗口上居中。
- `TopNavigationDialog`：在基类之上加「顶部 Pivot 导航 + PopUpAniStackedWidget 翻页 +
  确定/取消」，即 bili23 的 `TopNavigationDialogBase`——下载选项窗口就是它的子类。
- `FluentContentDialog`：最常用的骨架——「标题栏 + 内容区 + 底部左右按钮排」，
  大部分功能型弹窗（关于/日志/搜索/收藏夹/直播中心…）都基于它。
- 消息框助手 `msg_info / msg_warn / msg_error / msg_confirm`：包装 qfluentwidgets 的
  `MessageBox`（遮罩式），替代散落的 `QMessageBox`；父窗口缺失时自动解析活动窗口，
  仍拿不到则退化为自绘 `_MessageDialog`，绝不抛异常。

注意：
  * `FluentWidget` 以 parent=None 创建（顶层窗口），再手动居中到调用方窗口；
  * 不启用 Mica/亚克力——窗口材料跟随**系统**主题，会和 app 内「外观」设置冲突，
    这里统一让 qfluentwidgets 主题（由 `ui.theme.apply_appearance` 同步）说了算；
  * `qfluentwidgets.MessageBox` 是**遮罩式**对话框，构造时必须有非空 parent
    （`MaskDialogBase.__init__` 会读 `parent.width()`），无父窗口场景见 `_message()`。
"""
from __future__ import annotations

import os

from PySide6.QtCore import QEventLoop, QSize, QTimer, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QVBoxLayout

from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentWidget, FluentWidgetTitleBar, MessageBox, Pivot,
    PopUpAniStackedWidget, PrimaryPushButton, PushButton,
)

from utils.i18n import tr
from utils.resources import get_app_icon_path

# --------------------------------------------------------------------------- #
# qframelesswindow 兼容性补丁
# --------------------------------------------------------------------------- #
# PySide6 6.11.x 下，FluentWidget（及其子类：主窗口 / 各种 Fluent 弹窗）在
# __init__ 阶段调用 WindowsFramelessWindowBase._initFrameless 时，偶发
# `self.windowHandle()` 返回非 QWindow 对象（表现为 PySide6.QtWidgets.QWidgetItem），
# 导致 `self.windowHandle().screenChanged.connect(...)` 抛出
#   AttributeError: '...QWidgetItem' object has no attribute 'screenChanged'
# 使所有 Fluent 弹窗（如「自定义链接下载」）一构造就崩。
#
# 根因：`updateFrameless()` 刚调用 `winId()` 创建原生句柄后，`windowHandle()`
# 取到的句柄包装类型尚未稳定。兜底方案：捕获这一次连接失败，补完剩余初始化
# （resize / titleBar.raise_），并把 screenChanged 连接延迟到事件循环首帧
# （届时句柄已稳定），功能与表现不受影响。正常路径（不崩）走原版，零副作用。
try:
    from qframelesswindow.windows import WindowsFramelessWindowBase as _FWBase
    _orig_init_frameless = _FWBase._initFrameless

    def _retry_screen_connect(w):
        wh = w.windowHandle()
        if wh is None:
            return
        slot = getattr(w, "_WindowsFramelessWindowBase__onScreenChanged", None)
        if slot is None or not hasattr(wh, "screenChanged"):
            return
        try:
            wh.screenChanged.connect(slot)
        except Exception:
            pass

    def _patched_init_frameless(self):
        try:
            _orig_init_frameless(self)
            return
        except AttributeError as _e:
            # 仅拦截 windowHandle 错类型这一种已知异常，其余 AttributeError 照常抛出
            if "screenChanged" not in str(_e) and "QWidgetItem" not in str(_e):
                raise
        # —— 兜底：原版在 windowHandle().screenChanged.connect 处崩了 ——
        # 前序步骤（windowEffect / titleBar / updateFrameless）已执行，仅缺末尾
        # 的 resize(500,500) / titleBar.raise_ 与 screenChanged 连接，这里补齐。
        try:
            self.resize(500, 500)
        except Exception:
            pass
        try:
            self.titleBar.raise_()
        except Exception:
            pass
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: _retry_screen_connect(self))
        except Exception:
            pass

    _FWBase._init_frameless = _patched_init_frameless
except Exception:
    pass

_message_dialog_active = False


def _child_window_icon(parent):
    """解析子窗口图标：优先继承父窗口图标（主窗口已加载 icon.ico），
    否则回退到根目录 icon.ico（兼容打包 _MEIPASS 与开发态）。

    返回 ``QIcon``；解析不到时返回空 ``QIcon``（调用方自行判断是否 setWindowIcon）。
    """
    if parent is not None:
        try:
            pi = parent.windowIcon()
            if not pi.isNull():
                return pi
        except Exception:
            pass
    try:
        path = get_app_icon_path()
        if path and os.path.exists(path):
            return QIcon(path)
    except Exception:
        pass
    return QIcon()


class FluentModalDialog(FluentWidget):
    """Fluent 无边框模态对话框（带标题栏，居中于调用方窗口）。"""

    def __init__(self, size, parent_window=None):
        super().__init__(None)
        self._parent_window = parent_window
        self._size = QSize(int(size[0]), int(size[1]))
        self._result = False
        self._loop = None

        self._setup_title_bar()
        try:
            self.setMicaEffectEnabled(False)
        except Exception:
            pass
        self.setWindowModality(Qt.ApplicationModal)
        self.setFixedSize(self._size)
        # 注意：不再使用 WindowStaysOnTopHint 全局置顶——那样会让弹窗盖住
        # 其它程序的窗口（用户反馈的 bug）。保持 ApplicationModal 即可让弹窗始终
        # 位于本应用窗口之上、且不挡其它应用；exec() 内再 raise_()/activateWindow()
        # 保证 Windows 下必定可点击、不被前台锁卡成「看得见点不动」。
        # 子窗口图标：继承父窗口（主窗口已加载 icon.ico），否则用根目录 icon.ico
        self.setWindowIcon(_child_window_icon(self._parent_window))

    # ------------------------------------------------------------------ #
    # 标题栏 / 居中
    # ------------------------------------------------------------------ #
    def _setup_title_bar(self):
        bar = FluentWidgetTitleBar(self)
        bar.setFixedHeight(36)
        bar.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        bar.hBoxLayout.insertSpacing(0, 12)
        for name in ("minBtn", "maxBtn"):     # 对话框不需要最小化/最大化
            btn = getattr(bar, name, None)
            if btn is not None:
                btn.hide()
        try:
            bar.setDoubleClickEnabled(False)
        except Exception:
            pass
        self.setTitleBar(bar)
        try:
            self.titleBar.raise_()
        except Exception:
            pass

    def _center_on_parent(self):
        parent = self._parent_window
        if parent is None:
            return
        try:
            rect = parent.frameGeometry()
        except Exception:
            return
        if not rect.isValid():
            return
        self.move(rect.left() + (rect.width() - self.width()) // 2,
                  rect.top() + (rect.height() - self.height()) // 2)

    def showEvent(self, e):
        self._center_on_parent()
        super().showEvent(e)

    # ------------------------------------------------------------------ #
    # 模态语义
    # ------------------------------------------------------------------ #
    def accept(self):
        self._result = True
        self.close()

    def reject(self):
        self._result = False
        self.close()

    def closeEvent(self, e):
        if self._loop is not None and self._loop.isRunning():
            self._loop.quit()
        super().closeEvent(e)

    def exec(self):
        """等效 QDialog.exec()：阻塞到窗口关闭，返回是否点了「确定」。"""
        self.show()
        # 提升并激活到本应用最前（不含 WindowStaysOnTopHint，不会盖住其它程序窗口），
        # 解决 Windows 下模态弹窗「看得见点不动」的前台锁问题。
        self.raise_()
        self.activateWindow()
        self._loop = QEventLoop(self)
        self._loop.exec()
        self._loop = None
        return self._result


class TopNavigationDialog(FluentModalDialog):
    """顶部 Pivot 导航 + 翻页堆栈 + 确定/取消（bili23 的 TopNavigationDialogBase）。"""

    def __init__(self, size, parent_window=None, title="",
                 ok_text="确定", cancel_text="取消", with_ok=True):
        super().__init__(size, parent_window)
        if title:
            self.setWindowTitle(title)

        self.pivot = Pivot(self)
        self.stackedWidget = PopUpAniStackedWidget(self)

        self._tipLabel = CaptionLabel("", self)

        if with_ok:
            self.okBtn = PrimaryPushButton(tr(ok_text) if ok_text else tr("确定"), self)
            self.okBtn.setMinimumWidth(96)
            self.okBtn.clicked.connect(self.accept)
        else:
            self.okBtn = None

        self.cancelBtn = PushButton(tr(cancel_text) if cancel_text else tr("取消"), self)
        self.cancelBtn.setMinimumWidth(96)
        self.cancelBtn.clicked.connect(self.reject)

        pivot_row = QHBoxLayout()
        pivot_row.setContentsMargins(0, 0, 0, 0)
        pivot_row.addSpacing(5)
        pivot_row.addWidget(self.pivot)
        pivot_row.addStretch(1)
        pivot_row.addWidget(self._tipLabel)
        pivot_row.addSpacing(5)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 5, 0, 0)
        button_row.setSpacing(10)
        button_row.addStretch(1)
        if self.okBtn is not None:
            button_row.addWidget(self.okBtn)
        button_row.addWidget(self.cancelBtn)

        self.vboxLayout = QVBoxLayout(self)
        # 顶部 32px 让位给 36px 的无边框标题栏
        self.vboxLayout.setContentsMargins(10, 32, 10, 10)
        self.vboxLayout.setSpacing(5)
        self.vboxLayout.addLayout(pivot_row)
        self.vboxLayout.addWidget(self.stackedWidget, 1)
        self.vboxLayout.addLayout(button_row)

    # ------------------------------------------------------------------ #
    def set_tip(self, text):
        """右上角提示文字（例如「已选择 N 个视频」）。"""
        self._tipLabel.setText(text)

    def add_page(self, route_key, text, icon, widget):
        """注册一个导航分类页（Pivot 项 + 翻页页），点击即抽屉式滑入。"""
        self.pivot.addItem(route_key, text,
                           lambda: self.stackedWidget.setCurrentWidget(widget),
                           icon=icon)
        self.stackedWidget.addWidget(widget)

    def show_page(self, route_key):
        self.pivot.setCurrentItem(route_key)


class FluentContentDialog(FluentModalDialog):
    """通用 Fluent 弹窗骨架：标题栏 + 内容区 + 底部按钮排。

    布局约定（`vboxLayout` 上边距 44 是为了让开 36px 的无边框标题栏）：

        ┌── 标题栏（关闭按钮在右上）──────────────┐
        │  内容区  self.contentLayout（竖向）      │
        │  底部    [左按钮…] ─stretch─ [右按钮…]  │
        └──────────────────────────────────────┘

    用法::

        dlg = FluentContentDialog((640, 480), parent, title=tr("日志"))
        dlg.add_widget(q.TextEdit(), 1)
        dlg.add_button(tr("刷新"), slot=self._load, right=False)
        dlg.add_ok_cancel(ok_text=tr("关闭"), on_ok=self.accept)   # 关闭不想要取消可自行加
        dlg.exec()
    """

    def __init__(self, size, parent_window=None, title=""):
        super().__init__(size, parent_window)
        if title:
            self.setWindowTitle(title)

        self.vboxLayout = QVBoxLayout(self)
        self.vboxLayout.setContentsMargins(24, 44, 24, 20)
        self.vboxLayout.setSpacing(12)

        self.contentLayout = QVBoxLayout()
        self.contentLayout.setSpacing(12)
        self.vboxLayout.addLayout(self.contentLayout, 1)

        self._leftBtns = QHBoxLayout()
        self._leftBtns.setSpacing(10)
        self._rightBtns = QHBoxLayout()
        self._rightBtns.setSpacing(10)
        self.buttonRow = QHBoxLayout()
        self.buttonRow.setSpacing(10)
        self.buttonRow.addLayout(self._leftBtns)
        self.buttonRow.addStretch(1)
        self.buttonRow.addLayout(self._rightBtns)
        self.vboxLayout.addLayout(self.buttonRow)

    # ------------------------------------------------------------------ #
    # 内容区
    # ------------------------------------------------------------------ #
    def add_widget(self, widget, stretch=0):
        self.contentLayout.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout, stretch=0):
        self.contentLayout.addLayout(layout, stretch)
        return layout

    def add_stretch(self, n=1):
        self.contentLayout.addStretch(n)

    # ------------------------------------------------------------------ #
    # 按钮
    # ------------------------------------------------------------------ #
    def add_button(self, text, primary=False, slot=None, right=True,
                   min_width=96):
        btn = PrimaryPushButton(text, self) if primary else PushButton(text, self)
        if min_width:
            btn.setMinimumWidth(min_width)
        if slot is not None:
            btn.clicked.connect(slot)
        (self._rightBtns if right else self._leftBtns).addWidget(btn)
        return btn

    def add_ok_cancel(self, ok_text=None, cancel_text=None, on_ok=None):
        """右侧加「确定 + 取消」（确定默认走 accept，取消走 reject）。"""
        self.okBtn = self.add_button(ok_text or tr("确定"), primary=True,
                                    slot=on_ok or self.accept)
        self.cancelBtn = self.add_button(cancel_text or tr("取消"),
                                        slot=self.reject)
        return self.okBtn, self.cancelBtn


# --------------------------------------------------------------------------- #
# 消息框（替代散落的 QMessageBox）
# --------------------------------------------------------------------------- #
class _MessageDialog(FluentContentDialog):
    """无父窗口时的自绘兜底消息框（qfluentwidgets.MessageBox 必须有 parent）。"""

    def __init__(self, parent, title, content, with_cancel=False,
                 ok_text=None, cancel_text=None):
        super().__init__((420, 210), parent, title)
        lab = BodyLabel(content, self)
        lab.setWordWrap(True)
        self.add_widget(lab, 1)
        self.add_button(ok_text or tr("确定"), primary=True, slot=self.accept)
        if with_cancel:
            self.add_button(cancel_text or tr("取消"), slot=self.reject)


def _resolve_parent(parent):
    """尽力为遮罩式消息框找一个非空父窗口（否则 MessageBox 构造即崩）。"""
    if parent is not None:
        return parent
    app = QApplication.instance()
    if app is None:
        return None
    win = app.activeWindow()
    if win is not None:
        return win
    for w in app.topLevelWidgets():
        try:
            if w.isWindow() and w.isVisible():
                return w
        except Exception:
            continue
    return None


def _message(parent, title, content, with_cancel=False,
             ok_text=None, cancel_text=None):
    """弹一个 Fluent 消息框，返回 1（确定 / 关闭）或 0（取消）。"""
    global _message_dialog_active
    if _message_dialog_active:
        return 0
    _message_dialog_active = True
    try:
        parent = _resolve_parent(parent)
        if parent is None:
            return int(bool(_MessageDialog(None, title, content, with_cancel).exec()))
        mb = _MaskMessageBox(title, content, parent)
        try:
            mb.yesButton.setText(ok_text or tr("确定"))
            mb.cancelButton.setText(cancel_text or tr("取消"))
            if not with_cancel:
                mb.hideCancelButton()
        except Exception:
            pass
        ret = mb.exec()
        # exec() 返回后对话框已隐藏但仍存活（QDialog 默认只 hide，不销毁），
        # 用 deleteLater() 安全销毁——既不踩 exec() 的返回语义，也避免隐藏的
        # 对话框（含 windowMask 遮罩层、淡入动画）在主窗口子树里累积残留，
        # 否则连续第二次弹窗会出现「点不动 / 异常」。绝不在 exec() 返回前/内
        # 依赖 WA_DeleteOnClose 来销毁。
        mb.deleteLater()
        return int(bool(ret))
    finally:
        _message_dialog_active = False


class _MaskMessageBox(MessageBox):
    """遮罩式消息框（qfluentwidgets 原版封装，参照 bili23 的 MessageBox）。

    保持简洁：**不重写 done()、不设 WA_DeleteOnClose**，避免与 exec() 的返回
    时序冲突——那正是「连续第二次弹窗抛 C++ 对象已销毁异常」的根因。

    关闭后在 `_message()` 里显式 `deleteLater()` 释放，既不踩 exec() 语义，也不
    会让隐藏对话框（含 windowMask 遮罩层、淡入动画）在主窗口子树里累积。

    不再使用 WindowStaysOnTopHint 全局置顶（会盖住其它程序窗口，用户反馈的 bug）；
    保持模态即可位于本应用窗口之上，showEvent 内延迟 raise_/activateWindow 保证
    Windows 下必定可点击、不被前台锁卡成「看得见点不动」。
    """

    def __init__(self, title, content, parent=None):
        super().__init__(title, content, parent)
        # 子窗口图标：遮罩式消息框覆盖在父窗口上，继承父窗口图标（避免任务栏/
        # 切换窗口时显示空白图标），父窗口无图标时回退到根目录 icon.ico。
        try:
            self.setWindowIcon(_child_window_icon(parent))
        except Exception:
            pass

    def showEvent(self, e):
        super().showEvent(e)
        # 延迟到首帧后提升并激活（不含全局置顶），避免盖住其它程序窗口的同时
        # 解决 Windows 模态弹窗「看得见点不动」的前台锁问题。
        QTimer.singleShot(0, self.raise_)
        QTimer.singleShot(0, self.activateWindow)


def msg_info(parent, content, title=None, ok_text=None):
    """提示消息框（仅「确定」）。"""
    return _message(parent, title or tr("提示"), content, ok_text=ok_text)


def msg_warn(parent, content, title=None, ok_text=None):
    """警告消息框（仅「确定」）。"""
    return _message(parent, title or tr("提示"), content, ok_text=ok_text)


def msg_error(parent, content, title=None, ok_text=None):
    """错误消息框（仅「确定」）。"""
    return _message(parent, title or tr("错误"), content, ok_text=ok_text)


def msg_confirm(parent, content, title=None, ok_text=None, cancel_text=None):
    """确认消息框，点「确定」返回 True。"""
    return _message(parent, title or tr("确认"), content, with_cancel=True,
                    ok_text=ok_text, cancel_text=cancel_text) == 1


class ChoiceDialog(FluentContentDialog):
    """自定义二选一对话框（例如「直接退出 / 最小化到托盘」）。

    options: [(显示文本, 取值), ...]，第一个为主按钮（primary）。
    关闭 / 取消时 `value` 保持 `default`。
    """

    def __init__(self, parent, title, content="", options=None, default=None,
                 cancel_text=None):
        super().__init__((470, 250), parent, title=title)
        self.value = default
        if content:
            lab = BodyLabel(content, self)
            lab.setWordWrap(True)
            self.add_widget(lab, 1)
        for i, (text, value) in enumerate(list(options or [])):
            self.add_button(text, primary=(i == 0),
                            slot=(lambda v=value: self.pick(v)))
        if cancel_text:
            self.add_button(cancel_text, slot=self.reject)

    def pick(self, value):
        self.value = value
        self.accept()
