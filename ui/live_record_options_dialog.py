"""直播录制选项对话框 —— 开始录制前弹出（参照 ui/download_options_dialog.py）。

用户在录制窗口点「开始录制」（或从直播中心一键录制自动开始）后，先弹出本窗口
供本次录制选择设置；结构与下载选项对话框同款：
  - 顶部 `Pivot` 导航（单页：录制设置）；
  - `SettingCardGroup` / `SettingCard` Fluent 卡片组；
  - 底部 `PrimaryPushButton` 开始录制 + `PushButton` 取消。

对外契约：
    LiveRecordOptionsDialog(parent, config, on_confirm=None).exec()
  `exec()` 返回真值表示确认开始录制；`.result` 亦保留（True=确认, False=取消）。

确认后把本次设置写回全局 config（与设置窗口共享同一套键），由录制窗口按
新值拉流（清晰度）并启动 LiveRecorder（编码 / 封装格式 / 断流重连）。
"""
from __future__ import annotations

from PySide6.QtWidgets import QFileDialog

from ui.download_options_dialog import (
    _add_combo, _add_path, _add_switch, _combo_value, _icon, _new_page,
)
from ui.fluent_dialog import TopNavigationDialog
from utils.i18n import tr
from config import normalize_download_path

# 录制编码（存储值必须是不翻译的配置值，与设置窗口 / live_recorder 同源）
LIVE_CODEC_OPTIONS = [
    ("copy", "原始流（不转码）"),
    ("h264", "H.264（兼容性好）"),
    ("h265", "H.265（体积更小）"),
]
LIVE_FORMAT_OPTIONS = ["mp4", "mkv", "flv", "ts"]
# B 站直播清晰度 qn 码（存储值为 int，不翻译）
LIVE_QN_OPTIONS = [
    (10000, "原画"),
    (40000, "4K"),
    (30000, "杜比"),
    (250, "超清"),
    (150, "高清"),
    (80, "流畅"),
]


class LiveRecordOptionsDialog(TopNavigationDialog):
    """「本次录制设置」窗口（开始直播录制前弹出）。"""

    def __init__(self, parent, config, on_confirm=None, room_hint=""):
        super().__init__((640, 540), parent, title=tr("直播录制选项"),
                         ok_text=tr("开始录制"), cancel_text=tr("取消"))
        self.config = config
        self.on_confirm = on_confirm
        self.result = None      # None=未关闭, True=确认, False=取消

        tip = tr("本次录制设置（确认后生效）")
        if room_hint:
            tip = tr("直播间：{} · 本次录制设置").format(room_hint)
        self.set_tip(tip)

        page, lay = _new_page()
        from PySide6.QtWidgets import QVBoxLayout  # noqa: E402  局部导入保持页头简洁
        from qfluentwidgets import SettingCardGroup  # noqa: E402
        g = SettingCardGroup(tr("录制设置"), page)
        lay.addWidget(g)

        c = config
        _, self.codec_combo = _add_combo(
            g, "VIDEO", "录制编码", "HEVC/AV1 源转 H.264 可提升播放兼容性",
            LIVE_CODEC_OPTIONS, c.get("live_record_codec", "copy"))

        _, self.format_combo = _add_combo(
            g, "DOCUMENT", "封装格式", "录制文件的容器格式",
            LIVE_FORMAT_OPTIONS, c.get("live_record_format", "mp4"))

        _, self.quality_combo = _add_combo(
            g, "SPEED_HIGH" if _has_icon("SPEED_HIGH") else "VIDEO",
            "清晰度", "优先录制的直播清晰度",
            LIVE_QN_OPTIONS, int(c.get("live_record_qn", 10000) or 10000))

        _, self.reconnect_sw = _add_switch(
            g, "LINK", "断流自动重连", "直播中断后自动重连并分段保存",
            c.get("live_record_auto_reconnect", True))

        _, self.path_edit = _add_path(
            g, "FOLDER", "保存路径", "录制文件的保存目录",
            c.get("download_path", ""), self._browse_path)

        _, self.show_again_sw = _add_switch(
            g, "SETTING", "以后每次录制都弹出此对话框", "关闭后可在设置窗口重新开启",
            c.get("live_record_options_dialog", True))

        self.add_page("record", tr("录制设置"), _icon("VIDEO"), page)
        self.show_page("record")
        self.stackedWidget.setCurrentWidget(page)

    # ====================== 浏览 ======================
    def _browse_path(self, le):
        path = QFileDialog.getExistingDirectory(self, tr("浏览"), le.text() or "")
        if path:
            le.setText(path)

    # ====================== 确认 / 取消 ======================
    def accept(self):
        self._apply()
        self.result = True
        if callable(self.on_confirm):
            self.on_confirm()
        super().accept()

    def reject(self):
        self.result = False
        super().reject()

    def _apply(self):
        c = self.config
        c.set("live_record_codec", _combo_value(self.codec_combo))
        c.set("live_record_format", self.format_combo.currentText())
        qn = _combo_value(self.quality_combo)
        try:
            qn = int(qn)
        except (TypeError, ValueError):
            qn = 10000
        c.set("live_record_qn", qn)
        c.set("live_record_auto_reconnect", self.reconnect_sw.isChecked())
        c.set("download_path", normalize_download_path(self.path_edit.text()))
        c.set("live_record_options_dialog", self.show_again_sw.isChecked())


def _has_icon(name):
    from ui.icons import FluentIcon  # noqa: E402
    return hasattr(FluentIcon, name)
