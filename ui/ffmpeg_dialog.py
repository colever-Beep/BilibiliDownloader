"""缺 FFmpeg 时的一次性选择弹窗（启动检测 / 任务触发时复用）。

设计：应用只用到 ffmpeg 这一个可执行文件（utils/ffmpeg_provider 仅取 ffmpeg.exe），
但安装版不再内置 ffmpeg，首次使用时需要用户明确选择「联网下载」或「手动放入」。
本模块提供：
- FFmpegMissingDialog：Fluent 风格对话框，给出目标路径与「打开文件夹」入口。
- prompt_ffmpeg_missing(parent)：返回用户选择（CHOICE_DOWNLOAD / CHOICE_MANUAL / None）。
- ensure_ffmpeg_prompted(logger, on_done, parent)：统一入口——已存在直接回调；
  缺失则弹窗，下载走现有后台下载流程，手动则等待用户放入（不自动下载、不误报失败）。
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QApplication,
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from qfluentwidgets import PushButton, BodyLabel, StrongBodyLabel
from utils.i18n import tr
from utils import ffmpeg_provider as fp

CHOICE_DOWNLOAD = "download"
CHOICE_MANUAL = "manual"


class FFmpegMissingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("缺少 FFmpeg"))
        self.setMinimumWidth(440)
        self.choice = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 说明
        tip = BodyLabel(
            tr("本程序需要 FFmpeg 才能合并 / 处理音视频。\n请选择获取方式：")
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        # 目标路径（用户手动放入时用的目录）
        dir_path = fp.get_ffmpeg_dir()
        path_label = StrongBodyLabel(tr("FFmpeg 将放置于："))
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(path_label)
        dir_label = BodyLabel(dir_path)
        dir_label.setWordWrap(True)
        dir_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(dir_label)

        # 打开文件夹按钮（方便用户直接把 ffmpeg.exe 拖进去）
        open_btn = PushButton(tr("打开该文件夹"))
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(dir_path))
        )
        layout.addWidget(open_btn)

        # 操作按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        manual_btn = PushButton(tr("稍后手动放入"))
        download_btn = PushButton(tr("联网下载（推荐）"))
        download_btn.setDefault(True)
        manual_btn.clicked.connect(self._choose_manual)
        download_btn.clicked.connect(self._choose_download)
        btn_row.addWidget(manual_btn)
        btn_row.addWidget(download_btn)
        layout.addLayout(btn_row)

    def _choose_download(self):
        self.choice = CHOICE_DOWNLOAD
        self.accept()

    def _choose_manual(self):
        self.choice = CHOICE_MANUAL
        self.accept()


def prompt_ffmpeg_missing(parent=None):
    """弹窗询问用户如何获取 FFmpeg。返回 CHOICE_DOWNLOAD / CHOICE_MANUAL / None（关闭）。"""
    dlg = FFmpegMissingDialog(parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.choice
    return None


def ensure_ffmpeg_prompted(logger=None, on_done=None, parent=None):
    """缺失时先弹窗让用户选择；存在则直接回调 on_done(path)。

    返回 True 表示已开始/已就绪（下载中或已存在），False 表示用户选择手动（任务应挂起等待）。
    """
    if fp.is_available():
        if on_done:
            on_done(fp.get_ffmpeg_path())
        return True
    # 已有下载在进行：直接复用现有后台下载，不再弹窗
    if fp._in_progress:
        fp.ensure_ffmpeg(logger, on_done)
        return True

    choice = prompt_ffmpeg_missing(parent)
    if choice == CHOICE_DOWNLOAD:
        fp.ensure_ffmpeg(logger, on_done)
        return True
    # 手动 / 关闭对话框：不自动下载，等待用户放入后重试
    return False
