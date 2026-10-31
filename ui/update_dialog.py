"""发现新版本时的更新详情对话框（复刻 ClassIsland 更新抽屉的体验）。

由「开机自动检查」发现更新后弹出（也可从设置页「查看更新日志」跳转），展示：
- 新版本号 / 当前版本号；
- Markdown 格式的更新日志；
- 后台下载（进度条 / 速度 / 剩余时间）+ 取消；
- 「稍后」/「前往下载页」/「下载并安装」/「运行安装程序」等操作。
"""
from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from qfluentwidgets import (
    BodyLabel, InfoBar, InfoBarPosition, PrimaryPushButton, ProgressBar,
    PushButton, TextBrowser,
)

from ui.fluent_dialog import FluentContentDialog
from ui.icons import FluentIcon, icon_pixmap
from ui.theme import get_accent
from utils.i18n import tr, register
from utils.updater import UpdateService, UpdateStatus
from utils.version import APP_VERSION, GITHUB_HOMEPAGE


class UpdateDialog(FluentContentDialog):
    """更新详情 / 下载对话框。"""

    def __init__(self, parent=None, info=None, service: UpdateService = None):
        super().__init__((660, 540), parent, title=tr("发现新版本"))
        self.info = info
        self.service = service or UpdateService(getattr(parent, "config", None)
                                               if parent is not None else None)
        self._downloaded_path = None

        # ---- 头部：图标 + 版本号 ----
        head = QHBoxLayout()
        head.setSpacing(14)
        icon_lbl = QLabel(self)
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setPixmap(icon_pixmap(_icon("UPDATE"), 40, QColor(get_accent())))
        head.addWidget(icon_lbl)
        ver_box = QVBoxLayout()
        ver_box.setSpacing(2)
        self._title = BodyLabel(tr("发现新版本 {}").format(
            info.version if info else "?"), self)
        self._title.setObjectName("updateDlgTitle")
        sub = BodyLabel(tr("当前版本 v{}").format(APP_VERSION), self)
        sub.setObjectName("updateDlgSub")
        ver_box.addWidget(self._title)
        ver_box.addWidget(sub)
        head.addLayout(ver_box, 1)
        self.add_layout(head)

        # ---- 更新日志（Markdown）----
        self._browser = TextBrowser(self)
        self._browser.setMarkdown(
            (info.body if info else "") or tr("该版本未提供更新说明。"))
        self.add_widget(self._browser, 1)

        # ---- 下载进度（默认隐藏）----
        self._prog = ProgressBar(self)
        self._prog.setRange(0, 0)
        self._prog.setVisible(False)
        self._prog_text = QLabel("", self)
        self._prog_text.setVisible(False)
        self._cancel = PushButton(tr("取消"), self)
        self._cancel.setVisible(False)
        self._cancel.clicked.connect(self._cancel_download)
        prog_row = QHBoxLayout()
        prog_row.setSpacing(10)
        prog_row.addWidget(self._prog, 1)
        prog_row.addWidget(self._prog_text)
        prog_row.addWidget(self._cancel)
        self.add_layout(prog_row)

        # ---- 底部按钮 ----
        self._btn_release = self.add_button(tr("前往下载页"), slot=self._open_release, right=False)
        self._btn_later = self.add_button(tr("稍后"), slot=self.reject, right=False)
        self._btn_download = self.add_button(tr("下载并安装"), primary=True, slot=self._start_download)

        # 注册随语言刷新（标题含占位符，不注册，避免切语言显示字面量 {}）
        register(self._btn_release, "前往下载页")
        register(self._btn_later, "稍后")
        register(self._btn_download, "下载并安装")

    # ------------------------------------------------------------------ #
    def _open_release(self):
        tag = getattr(self.info, "tag", "") if self.info else ""
        url = f"{GITHUB_HOMEPAGE}/releases/tag/{tag}" if tag else f"{GITHUB_HOMEPAGE}/releases"
        QDesktopServices.openUrl(QUrl(url))

    def _start_download(self):
        if self.info is None:
            return
        asset = self.info.default_asset
        if asset is None:
            try:
                InfoBar.warning(tr("无法更新"), tr("未找到可下载的更新文件。"),
                               parent=self, position=InfoBarPosition.TOP)
            except Exception:
                pass
            return
        dest = os.path.join(tempfile.gettempdir(), "BilibiliDownloaderUpdate")
        self._downloaded_path = None
        self._prog.setVisible(True)
        self._prog.setRange(0, 100)
        self._prog.setValue(0)
        self._prog_text.setVisible(True)
        self._prog_text.setText(tr("准备下载…"))
        self._cancel.setVisible(True)
        self._btn_download.setEnabled(False)
        try:
            self.service.download_asset(
                asset, dest,
                on_progress=self._on_progress,
                on_done=self._on_done,
                on_error=self._on_error)
        except Exception as e:  # noqa: BLE001
            self._on_error(e)

    def _on_progress(self, downloaded, total, speed, eta):
        if total > 0:
            self._prog.setRange(0, total)
            self._prog.setValue(downloaded)
        else:
            self._prog.setRange(0, 0)
        sp = downloaded / (1024 * 1024)
        tot = (total / (1024 * 1024)) if total else 0.0
        spd = speed / (1024 * 1024)
        self._prog_text.setText(
            tr("下载中：{:.1f} / {:.1f} MB（{:.2f} MB/s，剩余 {:.0f}s）").format(
                sp, tot, spd, eta))

    def _on_done(self, path):
        self._downloaded_path = path
        self._prog.setVisible(False)
        self._prog_text.setVisible(False)
        self._cancel.setVisible(False)
        self._btn_download.setEnabled(True)
        self._btn_download.setVisible(False)
        if path.lower().endswith(".exe"):
            self._btn_download.setText(tr("运行安装程序"))
            self._btn_download.setVisible(True)
            self._btn_download.clicked.disconnect()
            self._btn_download.clicked.connect(lambda: self._open_file())
        else:
            self._btn_download.setText(tr("打开下载文件夹"))
            self._btn_download.setVisible(True)
            self._btn_download.clicked.disconnect()
            self._btn_download.clicked.connect(lambda: self._open_file())
        try:
            InfoBar.success(tr("更新已下载"), tr("已下载到本地，点击操作完成更新。"),
                           parent=self, position=InfoBarPosition.TOP)
        except Exception:
            pass

    def _on_error(self, e):
        self._prog.setVisible(False)
        self._prog_text.setVisible(False)
        self._cancel.setVisible(False)
        self._btn_download.setEnabled(True)
        msg = str(e) or tr("未知错误")
        try:
            InfoBar.error(tr("下载失败"), msg[:200], parent=self,
                         position=InfoBarPosition.TOP)
        except Exception:
            pass

    def _cancel_download(self):
        try:
            self.service.cancel_download()
        except Exception:
            pass
        self._prog.setVisible(False)
        self._prog_text.setVisible(False)
        self._cancel.setVisible(False)
        self._btn_download.setEnabled(True)

    def _open_file(self):
        path = self._downloaded_path
        if not path or not os.path.exists(path):
            return
        if path.lower().endswith(".exe") and os.name == "nt":
            try:
                os.startfile(path)
                return
            except Exception:
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))


def _icon(name):
    return getattr(FluentIcon, name, FluentIcon.INFO)
