"""下载选项对话框 —— qfluentwidgets Fluent 版（参照 bili23 的 DownloadOptionsDialog）。

用户在「选择视频 / 选择分集」确认后弹出，结构对应 bili23：
  - 顶部 `Pivot` 导航（媒体设置 / 附加文件 / 下载设置），点击由 `PopUpAniStackedWidget`
    做抽屉式翻页；
  - 每页 = 可滚动区域 + `SettingCardGroup` / `SettingCard` 卡片组（开关 / 下拉 / 数值 /
    路径卡片），与小节内的设置窗口同一套 Fluent 视觉；
  - 底部 `PrimaryPushButton` 确认添加 + `PushButton` 取消。

对外契约（与旧 QTabWidget 版一致，main_window 零改动）：
    DownloadOptionsDialog(parent, config, selected_count=0, on_confirm=None).exec()
  `exec()` 返回真值表示确认；`.result` 亦保留。

确认后把本次设置写回全局 config（与设置窗口共享同一套键），再由调用方入队。
所有控件联动逻辑（音视频流 / 合并 / 分离 / 仅音频、封面内嵌、弹幕字幕格式）原样保留。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QVBoxLayout, QWidget

from qfluentwidgets import (
    CaptionLabel, ComboBox, LineEdit, MessageBox, PushButton, ScrollArea,
    SettingCard, SettingCardGroup, SpinBox, SwitchButton,
)

from ui.fluent_dialog import TopNavigationDialog
from ui.icons import FluentIcon
from utils.i18n import tr
from utils.media_extras import (
    AUDIO_FORMATS, DANMAKU_FORMATS, METADATA_FORMATS, SUBTITLE_FORMATS, SUBTITLE_LANGS,
)
from config import normalize_download_path

# 选项取值与设置窗口保持一致（同一批 settings.json 键，两处必须同源）
QUALITY_OPTIONS = ["8K", "4K", "1080p", "720p", "480p", "360p"]
CODEC_OPTIONS = ["H.264 (兼容性好)", "H.265 (体积更小)", "AV1 (实验性)"]
MERGE_FORMAT_OPTIONS = ["mp4", "mkv", "mov", "webm"]
COVER_FORMAT_OPTIONS = ["jpg", "png", "webp", "avif"]
BITRATE_OPTIONS = ["128k", "192k", "256k", "320k"]
# (存储值, 显示文案)：存储值必须是不翻译的配置值
CONFLICT_OPTIONS = [("auto_rename", "自动重命名"), ("overwrite", "覆盖")]
LIMIT_MAX = 102400      # KB/s
WORKERS_MAX = 16


def _icon(name):
    """取 FluentIcon 成员，缺失时回退到 SETTING（与设置窗口同策略）。"""
    return getattr(FluentIcon, name, FluentIcon.SETTING)


def _to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# 卡片构造助手（与 ui/settings_window.py 同款写法）
# --------------------------------------------------------------------------- #
def _new_card(group, icon_name, title, content=""):
    card = SettingCard(_icon(icon_name), tr(title), tr(content) if content else None, group)
    group.addSettingCard(card)
    return card


def _add_combo(group, icon_name, title, content, options, current,
               width=170, on_change=None):
    """下拉卡片。options 为 [str] 或 [(存储值, 显示文案)]。返回 (card, combo)。"""
    card = _new_card(group, icon_name, title, content)
    cb = ComboBox()
    if options and isinstance(options[0], tuple):
        for value, label in options:
            cb.addItem(tr(label), userData=value)
        idx = cb.findData(current)
        if idx >= 0:
            cb.setCurrentIndex(idx)
    else:
        cb.addItems(list(options))
        cb.setCurrentText(current if current in options else (options[0] if options else ""))
    cb.setMinimumWidth(width)
    if on_change is not None:
        cb.currentTextChanged.connect(on_change)
    card.hBoxLayout.addStretch(1)
    card.hBoxLayout.addWidget(cb)
    return card, cb


def _combo_value(cb):
    """取下拉的存储值（无 userData 时退回显示文本）。"""
    data = cb.currentData()
    return data if data is not None else cb.currentText()


def _add_switch(group, icon_name, title, content, checked, on_change=None):
    card = _new_card(group, icon_name, title, content)
    sw = SwitchButton()
    sw.setChecked(bool(checked))
    if on_change is not None:
        sw.checkedChanged.connect(on_change)
    card.hBoxLayout.addStretch(1)
    card.hBoxLayout.addWidget(sw)
    return card, sw


def _add_spin(group, icon_name, title, content, value, minv, maxv, width=110):
    card = _new_card(group, icon_name, title, content)
    sp = SpinBox()
    sp.setRange(minv, maxv)
    sp.setValue(max(minv, min(maxv, _to_int(value, minv))))
    sp.setMinimumWidth(width)
    card.hBoxLayout.addStretch(1)
    card.hBoxLayout.addWidget(sp)
    return card, sp


def _add_path(group, icon_name, title, content, value, on_browse):
    card = _new_card(group, icon_name, title, content)
    le = LineEdit()
    le.setText(value or "")
    le.setMinimumWidth(250)
    browse = PushButton(tr("浏览"))
    browse.clicked.connect(lambda: on_browse(le))
    card.hBoxLayout.addStretch(1)
    card.hBoxLayout.addWidget(le)
    card.hBoxLayout.addWidget(browse)
    return card, le


def _new_page():
    """一个可滚动页：ScrollArea（容器 + 竖向卡片布局）。返回 (page, layout)。"""
    area = ScrollArea()
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    container = QWidget()
    lay = QVBoxLayout(container)
    lay.setContentsMargins(10, 8, 10, 8)
    lay.setSpacing(14)
    lay.setAlignment(Qt.AlignTop)
    area.setWidget(container)
    try:
        area.enableTransparentBackground()
    except Exception:
        pass
    return area, lay


class DownloadOptionsDialog(TopNavigationDialog):
    """「本次下载设置」窗口（选择视频 / 分集后弹出）。"""

    def __init__(self, parent, config, selected_count=0, on_confirm=None):
        super().__init__((780, 580), parent, title=tr("下载选项"),
                         ok_text=tr("确认添加"), cancel_text=tr("取消"))
        self.config = config
        self.on_confirm = on_confirm
        self.result = None      # None=未关闭, True=确认, False=取消

        self.set_tip(tr("已选择 {} 个视频 · 本次下载设置（确认后生效）").format(selected_count))

        self.media_page = self._build_media()
        self.additional_page = self._build_additional()
        self.download_page = self._build_download()

        self.add_page("media", tr("媒体设置"), _icon("MEDIA"), self.media_page)
        self.add_page("additional", tr("附加文件"), _icon("DOCUMENT"), self.additional_page)
        self.add_page("download", tr("下载设置"), _icon("DOWNLOAD"), self.download_page)
        self.show_page("media")
        self.stackedWidget.setCurrentWidget(self.media_page)

    # ====================== 媒体设置 ======================
    def _build_media(self):
        c = self.config
        page, lay = _new_page()
        g = SettingCardGroup(tr("媒体设置"), page)
        lay.addWidget(g)

        _, self.quality_combo = _add_combo(
            g, "VIDEO", "画质", "优先下载的清晰度",
            QUALITY_OPTIONS, c.get("quality", "1080p"))

        _, self.codec_combo = _add_combo(
            g, "VIDEO", "视频编码", "视频流编码格式",
            CODEC_OPTIONS, c.get("video_codec", CODEC_OPTIONS[0]))

        _, self.format_combo = _add_combo(
            g, "DOCUMENT", "合并格式", "音视频合并后的封装格式",
            MERGE_FORMAT_OPTIONS, c.get("merge_format", "mp4"))

        _, self.video_stream_sw = _add_switch(
            g, "VIDEO", "下载视频流", "仅下载音频时可关闭",
            c.get("download_video_stream", True),
            on_change=lambda _v: self._on_stream_toggle())

        _, self.audio_stream_sw = _add_switch(
            g, "MUSIC", "下载音频流", "关闭后视频将没有声音",
            c.get("download_audio_stream", True),
            on_change=lambda _v: self._on_stream_toggle())

        _, self.merge_sw = _add_switch(
            g, "MUSIC", "合并音视频", "把视频流与音频流合并为单个文件",
            c.get("merge_video_audio", True),
            on_change=lambda _v: self._on_stream_toggle())

        _, self.separate_sw = _add_switch(
            g, "MUSIC", "分离音视频", "不合并，分别保存音频与视频",
            c.get("audio_video_separate", False),
            on_change=lambda _v: self._on_separate_toggle())

        _, self.audio_only_sw = _add_switch(
            g, "MUSIC", "仅下载音频", "只下载音频流，不下载视频",
            c.get("audio_only", False),
            on_change=lambda _v: self._on_audio_only_toggle())

        _, self.audio_format_combo = _add_combo(
            g, "MUSIC", "音频格式", "音频流封装格式",
            AUDIO_FORMATS, c.get("audio_format", AUDIO_FORMATS[0]),
            on_change=lambda _t: self._on_audio_toggle())

        _, self.audio_bitrate_combo = _add_combo(
            g, "MUSIC", "音频码率", "有损音频的目标码率",
            BITRATE_OPTIONS, c.get("audio_bitrate", "192k"))

        lay.addWidget(CaptionLabel(tr("音频格式仅在「音画分离」或「仅下载音频」时生效"), page))

        self._on_stream_toggle()
        self._on_audio_toggle()
        return page

    # ====================== 附加文件 ======================
    def _build_additional(self):
        c = self.config
        page, lay = _new_page()
        g = SettingCardGroup(tr("附加文件"), page)
        lay.addWidget(g)

        _, self.danmaku_sw = _add_switch(
            g, "APPLICATION", "下载弹幕", "同时下载弹幕文件",
            c.get("download_danmaku", True),
            on_change=lambda _v: self._on_extras_toggle())

        _, self.danmaku_format_combo = _add_combo(
            g, "APPLICATION", "弹幕格式", "弹幕文件格式",
            DANMAKU_FORMATS, c.get("danmaku_format", "xml"))

        _, self.subtitle_sw = _add_switch(
            g, "APPLICATION", "下载字幕", "同时下载字幕文件",
            c.get("download_subtitle", False),
            on_change=lambda _v: self._on_extras_toggle())

        _, self.subtitle_format_combo = _add_combo(
            g, "APPLICATION", "字幕格式", "字幕文件格式",
            SUBTITLE_FORMATS, c.get("subtitle_format", "srt"))

        _, self.subtitle_lang_combo = _add_combo(
            g, "APPLICATION", "字幕语言", "需要下载的字幕语言",
            SUBTITLE_LANGS, c.get("subtitle_lang", SUBTITLE_LANGS[0]))

        _, self.cover_sw = _add_switch(
            g, "PHOTO", "下载封面", "同时下载视频封面图",
            c.get("download_cover", True),
            on_change=lambda _v: self._on_cover_toggle())

        _, self.cover_type_combo = _add_combo(
            g, "PHOTO", "封面格式", "封面文件格式",
            COVER_FORMAT_OPTIONS, c.get("cover_type", "jpg"),
            on_change=lambda _t: self._on_cover_toggle())

        _, self.embed_cover_sw = _add_switch(
            g, "PHOTO", "内嵌封面", "把封面写入视频元数据",
            c.get("embed_cover", False),
            on_change=lambda _v: self._on_cover_toggle())

        _, self.delete_cover_sw = _add_switch(
            g, "PHOTO", "内嵌后删除封面", "内嵌成功后删除单独的封面文件",
            c.get("delete_cover_after_attach", False))

        _, self.metadata_sw = _add_switch(
            g, "APPLICATION", "下载元数据", "同时下载视频元数据",
            c.get("download_metadata", False),
            on_change=lambda _v: self._on_extras_toggle())

        _, self.metadata_format_combo = _add_combo(
            g, "APPLICATION", "元数据格式", "元数据保存格式",
            METADATA_FORMATS, c.get("metadata_format", "json"))

        self._on_cover_toggle()
        self._on_extras_toggle()
        return page

    # ====================== 下载设置 ======================
    def _build_download(self):
        c = self.config
        page, lay = _new_page()
        g = SettingCardGroup(tr("下载设置"), page)
        lay.addWidget(g)

        _, self.path_edit = _add_path(
            g, "FOLDER", "下载路径", "视频与音频的保存目录",
            c.get("download_path", ""), self._browse_path)

        _, self.limit_spin = _add_spin(
            g, "DOWNLOAD", "下载限速", "0 表示不限速（KB/s）",
            c.get("download_limit", 0), 0, LIMIT_MAX)

        _, self.workers_spin = _add_spin(
            g, "DOWNLOAD", "同时下载数", "最大并行下载任务数",
            c.get("max_workers", 3), 1, WORKERS_MAX)

        _, self.conflict_combo = _add_combo(
            g, "DOCUMENT", "同名文件处理", "遇到同名文件时的策略",
            CONFLICT_OPTIONS, c.get("file_conflict_resolution", "auto_rename"))

        _, self.folder_sw = _add_switch(
            g, "FOLDER", "为合集/多P视频创建单独文件夹", "按视频分文件夹保存",
            c.get("create_folder", True))

        _, self.show_again_sw = _add_switch(
            g, "SETTING", "以后每次选择视频都弹出此对话框", "关闭后可在设置窗口重新开启",
            c.get("show_download_options_dialog", True))

        return page

    # ====================== 联动逻辑 ======================
    def _on_stream_toggle(self):
        """视频流 / 音频流 / 合并 三者联动：仅当两路都开且非分离/仅音频时「合并」才有意义。"""
        can_merge = (self.video_stream_sw.isChecked()
                     and self.audio_stream_sw.isChecked()
                     and not self.audio_only_sw.isChecked()
                     and not self.separate_sw.isChecked())
        if not can_merge:
            self.merge_sw.setChecked(False)
        self.merge_sw.setEnabled(can_merge)

    def _on_separate_toggle(self):
        """音画分离：开启时禁用并取消「合并」（分离与合并互斥）。"""
        if self.separate_sw.isChecked():
            self.merge_sw.setChecked(False)
            self.merge_sw.setEnabled(False)
        else:
            self._on_stream_toggle()
        self._on_audio_toggle()

    def _on_audio_only_toggle(self):
        """仅下载音频：开启时禁用并取消「视频流」和「合并」。"""
        if self.audio_only_sw.isChecked():
            self.video_stream_sw.setChecked(False)
            self.video_stream_sw.setEnabled(False)
            self.merge_sw.setChecked(False)
            self.merge_sw.setEnabled(False)
            self.separate_sw.setChecked(False)
            self.separate_sw.setEnabled(False)
        else:
            self.video_stream_sw.setEnabled(True)
            self.separate_sw.setEnabled(True)
            self._on_stream_toggle()
        self._on_audio_toggle()

    def _on_cover_toggle(self):
        cover_on = self.cover_sw.isChecked()
        if not cover_on:
            self.embed_cover_sw.setChecked(False)
            self.embed_cover_sw.setEnabled(False)
        elif self.cover_type_combo.currentText() == "avif":
            # avif 无法内嵌到视频容器
            self.embed_cover_sw.setChecked(False)
            self.embed_cover_sw.setEnabled(False)
        else:
            self.embed_cover_sw.setEnabled(True)
        embed_on = self.embed_cover_sw.isChecked()
        self.delete_cover_sw.setEnabled(cover_on and embed_on)
        if not embed_on:
            self.delete_cover_sw.setChecked(False)

    def _on_audio_toggle(self):
        active = self.separate_sw.isChecked() or self.audio_only_sw.isChecked()
        self.audio_format_combo.setEnabled(active)
        lossy = self.audio_format_combo.currentText() in ("mp3", "aac", "m4a", "opus")
        self.audio_bitrate_combo.setEnabled(active and lossy)

    def _on_extras_toggle(self):
        self.danmaku_format_combo.setEnabled(self.danmaku_sw.isChecked())
        sub_on = self.subtitle_sw.isChecked()
        self.subtitle_format_combo.setEnabled(sub_on)
        self.subtitle_lang_combo.setEnabled(sub_on)
        self.metadata_format_combo.setEnabled(self.metadata_sw.isChecked())

    def _browse_path(self, le):
        path = QFileDialog.getExistingDirectory(self, tr("浏览"), le.text() or "")
        if path:
            le.setText(path)

    # ====================== 提示框（Fluent MessageBox） ======================
    def _alert(self, title, content):
        box = MessageBox(tr(title), tr(content), self)
        box.hideCancelButton()
        box.yesButton.setText(tr("确定"))
        box.exec()

    def _ask(self, title, content):
        box = MessageBox(tr(title), tr(content), self)
        box.yesButton.setText(tr("继续"))
        box.cancelButton.setText(tr("取消"))
        return bool(box.exec())

    # ====================== 确认 / 取消 ======================
    def accept(self):
        video_on = self.video_stream_sw.isChecked()
        audio_on = self.audio_stream_sw.isChecked()
        separate_on = self.separate_sw.isChecked()
        audio_only_on = self.audio_only_sw.isChecked()

        if not video_on and not audio_on:
            self._alert("无法开始", "请至少选择下载视频流或音频流之一。")
            return
        if video_on and not audio_on and not separate_on and not audio_only_on:
            if not self._ask("提示", "仅下载视频流会产生无声视频。\n如确需无音轨视频可继续，否则请同时开启音频流。"):
                return
        if video_on and audio_on and not self.merge_sw.isChecked() and not separate_on:
            if not self._ask("提示", "未开启「合并视频与音频」，将得到视频、音频两个独立文件。\n如需单个完整视频请开启合并。"):
                return

        self._apply()
        self.result = True
        # 仅在确认时回调（旧实现在取消时也会回调，会把视频误加入队列）
        if callable(self.on_confirm):
            self.on_confirm()
        super().accept()

    def reject(self):
        self.result = False
        super().reject()

    def _apply(self):
        c = self.config
        c.set("quality", self.quality_combo.currentText())
        c.set("video_codec", self.codec_combo.currentText())
        c.set("merge_format", self.format_combo.currentText())
        c.set("download_video_stream", self.video_stream_sw.isChecked())
        c.set("download_audio_stream", self.audio_stream_sw.isChecked())
        c.set("merge_video_audio", self.merge_sw.isChecked())
        c.set("audio_video_separate", self.separate_sw.isChecked())
        c.set("audio_only", self.audio_only_sw.isChecked())
        c.set("audio_format", self.audio_format_combo.currentText())
        c.set("audio_bitrate", self.audio_bitrate_combo.currentText())

        c.set("download_danmaku", self.danmaku_sw.isChecked())
        c.set("danmaku_format", self.danmaku_format_combo.currentText())
        c.set("download_subtitle", self.subtitle_sw.isChecked())
        c.set("subtitle_format", self.subtitle_format_combo.currentText())
        c.set("subtitle_lang", self.subtitle_lang_combo.currentText())
        c.set("download_cover", self.cover_sw.isChecked())
        c.set("cover_type", self.cover_type_combo.currentText())
        c.set("embed_cover", self.embed_cover_sw.isChecked())
        c.set("delete_cover_after_attach", self.delete_cover_sw.isChecked())
        c.set("download_metadata", self.metadata_sw.isChecked())
        c.set("metadata_format", self.metadata_format_combo.currentText())

        c.set("download_path", normalize_download_path(self.path_edit.text()))
        c.set("download_limit", int(self.limit_spin.value()))
        c.set("max_workers", max(1, int(self.workers_spin.value())))
        conflict = _combo_value(self.conflict_combo)
        c.set("file_conflict_resolution", conflict)
        c.set("create_folder", self.folder_sw.isChecked())
        c.set("show_download_options_dialog", self.show_again_sw.isChecked())
        c.set("overwrite", conflict == "overwrite")     # 兼容旧字段
