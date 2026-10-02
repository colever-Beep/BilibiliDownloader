"""设置窗口（qfluentwidgets MSFluentWindow）。

- 左侧：垂直导航（图标 + 文字），对应 bili23 的「垂直布局管理器」。
- 右侧：每个分类一个可滚动卡片组（SettingCardGroup + SettingCard）；切换分类时由
  MSFluentWindow 自带的抽屉式滑入动画呈现，对应 bili23 的「抽屉样式选项模式」。

与旧的 QTabWidget 版等价：保留全部 settings.json 键，并把「外观 / 强调色 / 语言」
的变化实时同步给主窗口（通过构造时传入的回调）。

i18n 约定：可见静态文本一律用 tr() 包裹；配置值 / 选项（"dark" / "1080p" /
"mp4" / "auto_rename" 等）只作为内部存储值，绝不在界面上翻译。
"""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import QFileDialog, QScrollArea, QWidget, QVBoxLayout

from utils.i18n import tr, LANGUAGES, register
from ui.icons import FluentIcon
from ui.theme import get_accent, is_dark, set_accent, resolve_appearance

# qfluentwidgets 是本窗口的必需依赖；缺失时本窗口不可用（与 ui.icons 的降级策略一致）。
from qfluentwidgets import (
    MSFluentWindow, NavigationItemPosition, SettingCard, SettingCardGroup,
    SwitchButton, ComboBox, PushButton, SpinBox, LineEdit, ColorPickerButton,
    PushSettingCard, ExpandGroupSettingCard, setTheme, setThemeColor, Theme,
)
from qfluentwidgets.components.settings.expand_setting_card import GroupWidget


class _ExpandCard(ExpandGroupSettingCard):
    """可展开分组卡（参照 bili23 的 ExpandGroupSettingCard 封装）。

    把一组相关设置收进一张卡片，展开后逐行呈现——替代整页平铺，
    用于「代理设置」这类多字段聚合场景。
    """

    def __init__(self, icon_name, title_key, content_key, parent=None):
        super().__init__(_icon(icon_name), tr(title_key),
                         tr(content_key) if content_key else None, parent)
        self._title_key = title_key
        self._content_key = content_key
        self._rows = []  # (GroupWidget, title_key, content_key)

    def add_row(self, icon_name, title_key, content_key, widget, stretch=0):
        g = GroupWidget(_icon(icon_name), tr(title_key),
                        tr(content_key) if content_key else "", widget, stretch)
        self.addGroupWidget(g)
        self._rows.append((g, title_key, content_key))
        return g

    def retranslate(self):
        _set_title(self, tr(self._title_key))
        if self._content_key:
            _set_content(self, tr(self._content_key))
        for g, tk, ck in self._rows:
            _set_title(g, tr(tk))
            if ck:
                _set_content(g, tr(ck))


def _icon(name):
    """取 FluentIcon 成员，缺失时回退到 SETTING，保证导航/卡片都有图标。"""
    return getattr(FluentIcon, name, FluentIcon.SETTING)


def _set_title(obj, text):
    """按「接口兜底链」设置标题。

    qfluentwidgets 同类部件的接口并不一致：``SettingCard`` 只有 ``setTitle``，
    ``SettingCardGroup`` 只有 ``titleLabel``，``ExpandGroupSettingCard`` 的标题在
    内层 ``card`` 上，``GroupWidget`` 又只有 ``setTitle``。只写其中一种，语言切换
    后就会有一部分标题停留在旧语言（且异常被 try/except 吞掉，表面看不出问题）。
    """
    for attempt in (
        lambda: obj.setTitle(text),
        lambda: obj.titleLabel.setText(text),
        lambda: obj.card.setTitle(text),
    ):
        try:
            attempt()
            return True
        except Exception:
            continue
    return False


def _set_content(obj, text):
    """内容副标题的兜底链（同上：setContent -> contentLabel -> card.contentLabel）。"""
    for attempt in (
        lambda: obj.setContent(text),
        lambda: obj.contentLabel.setText(text),
        lambda: obj.card.contentLabel.setText(text),
    ):
        try:
            attempt()
            return True
        except Exception:
            continue
    return False


class _SubInterface(QScrollArea):
    """右侧可滚动子界面容器（每个分类一个）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view = QWidget()
        self.vbox = QVBoxLayout(self.view)
        self.vbox.setSpacing(16)
        self.vbox.setContentsMargins(26, 16, 26, 16)
        self.vbox.setAlignment(Qt.AlignTop)
        self.setWidget(self.view)

    def add_group(self, group):
        self.vbox.addWidget(group)


class SettingsWindow(MSFluentWindow):

    def __init__(self, parent, config, on_language_change, on_settings_changed, preview_theme,
                 on_open_logs=None, on_stay_on_top=None):
        super().__init__(parent)
        self.config = config
        self.on_language_change = on_language_change
        self.on_settings_changed = on_settings_changed
        self._preview_theme = preview_theme
        self.on_open_logs = on_open_logs          # 「查看日志」卡片回调（主窗口注入）
        self.on_stay_on_top = on_stay_on_top      # 置顶开关即时生效回调（主窗口注入）

        self._cards = []        # (card, title_key, content_key)
        self._groups = []       # (group, title_key)
        self._expand_cards = [] # _ExpandCard（可展开分组卡，多语言刷新）
        self._nav = []          # (routeKey, title_key)
        self._lang_rev = {v: k for k, v in LANGUAGES.items()}

        # 同步 Fluent 主题（明暗 + 强调色）与主程序一致
        try:
            setTheme(Theme.DARK if is_dark() else Theme.LIGHT)
            setThemeColor(QColor(get_accent()))
        except Exception:
            pass

        self.setWindowTitle(tr("设置"))
        self.resize(900, 640)
        self.setMinimumSize(760, 560)

        # 构建四个分类子界面
        self._basic = self._build_basic()
        self._download = self._build_download()
        self._options = self._build_options()
        self._advanced = self._build_advanced()

        # MSFluentWindow 用 interface.objectName() 作为导航项的 routeKey，
        # 因此必须在 addSubInterface 之前设置好。
        self._basic.setObjectName("basic")
        self._download.setObjectName("download")
        self._options.setObjectName("options")
        self._advanced.setObjectName("advanced")

        self.addSubInterface(self._basic, _icon("SETTING"), tr("基本设置"),
                             position=NavigationItemPosition.SCROLL)
        self.addSubInterface(self._download, _icon("DOWNLOAD"), tr("下载"),
                             position=NavigationItemPosition.SCROLL)
        self.addSubInterface(self._options, _icon("DOCUMENT"), tr("附加文件"),
                             position=NavigationItemPosition.SCROLL)
        self.addSubInterface(self._advanced, _icon("DEVELOPER_TOOLS"), tr("高级"),
                             position=NavigationItemPosition.SCROLL)

        self._nav.extend([
            ("basic", "基本设置"), ("download", "下载"),
            ("options", "附加文件"), ("advanced", "高级"),
        ])

        try:
            self.navigationInterface.setCurrentItem("basic")
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 构造辅助
    # ------------------------------------------------------------------ #
    def _group(self, title_key):
        g = SettingCardGroup(tr(title_key), self)
        self._groups.append((g, title_key))
        return g

    def _register_card(self, card, title_key, content_key):
        self._cards.append((card, title_key, content_key))

    def _display_for(self, options, value_map, cur):
        if isinstance(value_map, dict):
            inv = {v: k for k, v in value_map.items()}
            return inv.get(cur, cur)
        return cur if cur in options else (options[0] if options else "")

    def _value_for(self, options, value_map, text):
        if isinstance(value_map, dict):
            return value_map.get(text, text)
        return text

    def _combo_card(self, group, icon_name, title_key, content_key, config_key,
                    options, value_map=None, default=None, on_change=None):
        card = SettingCard(_icon(icon_name), tr(title_key), tr(content_key), self)
        cb = ComboBox()
        cb.addItems(options)
        cur = self.config.get(config_key, default)
        cb.setCurrentText(self._display_for(options, value_map, cur))
        if on_change is not None:
            cb.currentTextChanged.connect(lambda t: on_change(self._value_for(options, value_map, t)))
        else:
            cb.currentTextChanged.connect(
                lambda t: self._set(config_key, self._value_for(options, value_map, t)))
        cb.setMinimumWidth(150)
        card.hBoxLayout.addStretch(1)
        card.hBoxLayout.addWidget(cb)
        group.addSettingCard(card)
        self._register_card(card, title_key, content_key)
        return card, cb

    def _switch_card(self, group, icon_name, title_key, content_key, config_key,
                     default=False, on_change=None, val_true=None, val_false=None):
        card = SettingCard(_icon(icon_name), tr(title_key), tr(content_key), self)
        sw = SwitchButton()
        init = self.config.get(config_key, default)
        checked = (init == val_true) if val_true is not None else bool(init)
        sw.setChecked(checked)
        if on_change is not None:
            sw.checkedChanged.connect(lambda v: on_change(v))
        else:
            sw.checkedChanged.connect(lambda v: self._set(config_key, v))
        card.hBoxLayout.addStretch(1)
        card.hBoxLayout.addWidget(sw)
        group.addSettingCard(card)
        self._register_card(card, title_key, content_key)
        return card, sw

    def _spin_card(self, group, icon_name, title_key, content_key, config_key,
                   minv, maxv, default):
        card = SettingCard(_icon(icon_name), tr(title_key), tr(content_key), self)
        sp = SpinBox()
        sp.setRange(minv, maxv)
        sp.setValue(int(self.config.get(config_key, default) or default))
        sp.valueChanged.connect(lambda v: self._set(config_key, v))
        sp.setMinimumWidth(110)
        card.hBoxLayout.addStretch(1)
        card.hBoxLayout.addWidget(sp)
        group.addSettingCard(card)
        self._register_card(card, title_key, content_key)
        return card

    def _path_card(self, group, icon_name, title_key, content_key, config_key,
                   file_mode=False, filter_text=""):
        card = SettingCard(_icon(icon_name), tr(title_key), tr(content_key), self)
        le = LineEdit()
        le.setText(self.config.get(config_key, "") or "")
        le.setMinimumWidth(240)
        le.setReadOnly(True)
        browse = PushButton(tr("浏览"))
        browse.clicked.connect(lambda: self._browse(browse, le, config_key, file_mode, filter_text))
        open_btn = PushButton(tr("打开"))
        open_btn.clicked.connect(lambda: self._open_target(le.text()))
        le.textChanged.connect(lambda t: self._set(config_key, t, callback=False))
        card.hBoxLayout.addStretch(1)
        card.hBoxLayout.addWidget(le)
        card.hBoxLayout.addWidget(browse)
        card.hBoxLayout.addWidget(open_btn)
        group.addSettingCard(card)
        self._register_card(card, title_key, content_key)
        register(browse, "浏览")
        register(open_btn, "打开")
        return card

    def _accent_card(self, group):
        card = SettingCard(_icon("PALETTE"), tr("强调色"),
                           tr("主题强调色，应用于按钮与高亮"), self)
        self._accent_picker = ColorPickerButton(QColor(get_accent()), tr("选择颜色"), self)
        self._accent_picker.colorChanged.connect(self._on_accent)
        # 跟随系统：开启后强调色取 Windows 系统强调色，取色器禁用
        self._accent_sys_sw = SwitchButton(tr("跟随系统"))
        follow = self.config.get("accent_color", "") == "system"
        self._accent_sys_sw.setChecked(follow)
        self._accent_picker.setEnabled(not follow)
        self._accent_sys_sw.checkedChanged.connect(self._on_accent_follow)
        card.hBoxLayout.addStretch(1)
        card.hBoxLayout.addWidget(self._accent_sys_sw)
        card.hBoxLayout.addWidget(self._accent_picker)
        group.addSettingCard(card)
        self._register_card(card, "强调色", "主题强调色，应用于按钮与高亮")
        register(self._accent_sys_sw, "跟随系统")

    def _on_accent_follow(self, v):
        try:
            if v:
                cur = self.config.get("accent_color", "")
                if cur and cur != "system":
                    self.config.set("accent_color_custom", cur)
                self.config.set("accent_color", "system")
            else:
                self.config.set(
                    "accent_color",
                    self.config.get("accent_color_custom", "") or "#1f8a4c")
        except Exception:
            pass
        try:
            set_accent(self.config.get("accent_color"))  # set_accent 内部解析 "system"
        except Exception:
            pass
        try:
            self._accent_picker.setEnabled(not v)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # 分类构建
    # ------------------------------------------------------------------ #
    def _build_basic(self):
        w = _SubInterface(self)
        g = self._group("基本设置")
        w.add_group(g)

        # 界面语言
        card = SettingCard(_icon("LANGUAGE"), tr("界面语言"), tr("选择界面显示语言"), self)
        cb = ComboBox()
        cb.addItems(list(LANGUAGES.values()))
        cb.setCurrentText(LANGUAGES.get(self.config.get("language", "zh_CN"), "简体中文"))
        cb.currentTextChanged.connect(self._on_language)
        cb.setMinimumWidth(150)
        card.hBoxLayout.addStretch(1)
        card.hBoxLayout.addWidget(cb)
        g.addSettingCard(card)
        self._register_card(card, "界面语言", "选择界面显示语言")

        # 外观（明暗，支持跟随系统）
        self._combo_card(
            g, "BRUSH", "外观", "明暗主题", "appearance",
            [tr("跟随系统"), tr("深色"), tr("浅色")],
            {tr("跟随系统"): "system", tr("深色"): "dark", tr("浅色"): "light"},
            "dark", on_change=self._on_appearance)

        # 强调色
        self._accent_card(g)

        # 关闭行为
        def _on_tray(v):
            self._set("close_behavior", "tray" if v else "quit")
        self._switch_card(
            g, "SYNC", "关闭时最小化到托盘", "关闭窗口时最小化到系统托盘而非退出",
            "close_behavior", default=(self.config.get("close_behavior", "") == "tray"),
            on_change=_on_tray, val_true="tray", val_false="quit")

        # 窗口置顶（参照 bili23 WindowBehaviorSettingCard 的 stay_on_top）
        def _on_top(v):
            try:
                self.config.set("stay_on_top", v)
            except Exception:
                pass
            if callable(self.on_stay_on_top):
                try:
                    self.on_stay_on_top(v)
                except Exception:
                    pass
        self._switch_card(
            g, "PIN", "窗口置顶", "主窗口始终显示在其他窗口最前",
            "stay_on_top", default=bool(self.config.get("stay_on_top", False)),
            on_change=_on_top)

        # 显示下载选项对话框
        self._switch_card(
            g, "APPLICATION", "选择后弹出下载选项", "勾选视频后弹出下载选项对话框",
            "show_download_options_dialog", default=True)

        # 下载完成后打开目录
        self._switch_card(
            g, "FOLDER", "下载后打开目录", "下载完成后自动打开输出文件夹",
            "open_download_dir", default=True)
        return w

    def _build_download(self):
        w = _SubInterface(self)
        g = self._group("下载")
        w.add_group(g)

        # 下载路径
        self._path_card(g, "FOLDER", "下载路径", "视频与音频的保存目录", "download_path")

        # 同时下载数
        self._spin_card(g, "SPEED_HIGH" if hasattr(FluentIcon, "SPEED_HIGH") else "DOWNLOAD",
                        "同时下载数", "最大并行下载任务数", "max_workers", 1, 8, 3)

        # 画质
        self._combo_card(g, "VIDEO", "画质", "优先下载的清晰度", "quality",
                         ["8K", "4K", "1080p", "720p", "480p", "360p"], None, "1080p")

        # 视频编码
        self._combo_card(g, "VIDEO", "视频编码", "视频流编码格式", "video_codec",
                         ["H.264 (兼容性好)", "H.265 (体积更小)", "AV1 (实验性)"], None,
                         "H.264 (兼容性好)")

        # 合并格式
        self._combo_card(g, "DOCUMENT", "合并格式", "音视频合并后的封装格式", "merge_format",
                         ["mp4", "mkv", "mov", "webm"], None, "mp4")

        # 分离音视频
        self._switch_card(g, "MUSIC", "分离音视频", "不合并，分别保存音频与视频",
                          "audio_video_separate", default=False)

        # 仅音频
        self._switch_card(g, "MUSIC", "仅下载音频", "只下载音频流，不下载视频",
                          "audio_only", default=False)

        # 音频格式
        self._combo_card(g, "MUSIC", "音频格式", "音频流封装格式", "audio_format",
                         ["原始（不转换）", "m4a", "mp3", "aac", "flac", "wav", "opus"], None,
                         "原始（不转换）")

        # 音频码率
        self._combo_card(g, "MUSIC", "音频码率", "有损音频的目标码率", "audio_bitrate",
                         ["128k", "192k", "256k", "320k"], None, "192k")

        # 下载限速
        self._spin_card(g, "SPEED_HIGH" if hasattr(FluentIcon, "SPEED_HIGH") else "DOWNLOAD",
                        "下载限速", "0 表示不限速（KB/s）", "download_limit", 0, 102400, 0)

        # 建文件夹
        self._switch_card(g, "FOLDER", "按视频种类分文件夹", "按类型（视频/番剧/直播/音频…）自动归类到子目录保存",
                          "create_folder", default=True)

        # 同名处理
        self._combo_card(g, "DOCUMENT", "同名文件处理", "遇到同名文件时的策略",
                         "file_conflict_resolution",
                         [tr("自动重命名"), tr("覆盖")],
                         {tr("自动重命名"): "auto_rename", tr("覆盖"): "overwrite"},
                         "auto_rename")

        # 直播录制编码（B 站高清直播流常为 HEVC/AV1，直接封装 mp4 部分播放器无法解码）
        self._combo_card(g, "VIDEO", "直播录制编码", "转码可提升兼容性，但增加 CPU 占用",
                         "live_record_codec",
                         [tr("原始流（不转码）"), tr("H.264（兼容性好）"), tr("H.265（体积更小）")],
                         {tr("原始流（不转码）"): "copy",
                          tr("H.264（兼容性好）"): "h264",
                          tr("H.265（体积更小）"): "h265"},
                         "copy")
        return w

    def _build_options(self):
        w = _SubInterface(self)
        g = self._group("弹幕 / 字幕 / 封面 / 元数据")
        w.add_group(g)

        # 弹幕
        self._switch_card(g, "APPLICATION", "下载弹幕", "同时下载弹幕文件",
                          "download_danmaku", default=True)
        self._combo_card(g, "APPLICATION", "弹幕格式", "弹幕文件格式", "danmaku_format",
                         ["xml", "ass", "json"], None, "xml")

        # 封面
        self._switch_card(g, "PHOTO", "下载封面", "同时下载视频封面图",
                          "download_cover", default=True)
        self._switch_card(g, "PHOTO", "内嵌封面", "把封面写入视频元数据",
                          "embed_cover", default=False)
        self._switch_card(g, "PHOTO", "内嵌后删除封面", "内嵌成功后删除单独的封面文件",
                          "delete_cover_after_attach", default=False)
        self._combo_card(g, "PHOTO", "封面格式", "封面文件格式", "cover_type",
                         ["jpg", "png", "webp", "avif"], None, "jpg")

        # 字幕
        self._switch_card(g, "APPLICATION", "下载字幕", "同时下载字幕文件",
                          "download_subtitle", default=False)
        self._combo_card(g, "APPLICATION", "字幕格式", "字幕文件格式", "subtitle_format",
                         ["srt", "ass", "lrc", "txt", "json"], None, "srt")
        self._combo_card(g, "APPLICATION", "字幕语言", "需要下载的字幕语言", "subtitle_lang",
                         ["全部语言", "仅中文", "仅英文"], None, "全部语言")

        # 元数据
        self._switch_card(g, "APPLICATION", "下载元数据", "同时下载视频元数据",
                          "download_metadata", default=False)
        self._combo_card(g, "APPLICATION", "元数据格式", "元数据保存格式", "metadata_format",
                         ["json", "nfo", "内嵌到视频"], None, "json")
        return w

    def _build_advanced(self):
        w = _SubInterface(self)
        g = self._group("网络 / 代理 / FFmpeg")
        w.add_group(g)

        # ---- 代理设置（聚合为一张可展开卡片，参照 bili23 ProxySettingCard）----
        g.addSettingCard(self._build_proxy_expand())

        # FFmpeg 路径
        self._path_card(g, "APPLICATION", "FFmpeg 路径", "自定义 ffmpeg.exe（留空用内置）",
                        "ffmpeg_path", file_mode=True, filter_text="ffmpeg.exe")

        # 查看日志（参照 bili23 的 log_card：PushSettingCard 直接打开日志窗口）
        log_card = PushSettingCard(tr("查看"), _icon("HISTORY"), tr("日志"),
                                   tr("查看应用运行日志"), self)
        log_card.clicked.connect(self._on_open_logs)
        g.addSettingCard(log_card)
        self._register_card(log_card, "日志", "查看应用运行日志")

        # ---- 百宝箱：娱乐功能，与下载主流程无关（懒加载弹窗，避免拖慢设置窗口）----
        g2 = self._group("百宝箱")
        w.add_group(g2)

        dl_card = PushSettingCard(
            tr("打开"), _icon("DOWNLOAD"), tr("自定义链接下载"),
            tr("用 yt-dlp 下载任意链接（支持非 B 站站点）"), self)
        dl_card.clicked.connect(self._open_custom_download)
        g2.addSettingCard(dl_card)
        self._register_card(dl_card, "自定义链接下载", "用 yt-dlp 下载任意链接（支持非 B 站站点）")

        luck_card = PushSettingCard(
            tr("打开"), _icon("HEART"), tr("今日人品"),
            tr("测一测今天的手气（纯娱乐）"), self)
        luck_card.clicked.connect(self._open_luck)
        g2.addSettingCard(luck_card)
        self._register_card(luck_card, "今日人品", "测一测今天的手气（纯娱乐）")

        dnc_card = PushSettingCard(
            tr("打开"), _icon("FINGERPRINT"), tr("千万别点"),
            tr("一个不该点的按钮"), self)
        dnc_card.clicked.connect(self._open_dnc)
        g2.addSettingCard(dnc_card)
        self._register_card(dnc_card, "千万别点", "一个不该点的按钮")
        return w

    # ------------------------------------------------------------------ #
    # 百宝箱（娱乐功能）入口：全部懒加载，未使用时零开销
    # ------------------------------------------------------------------ #
    def _open_custom_download(self):
        from ui.toolbox import CustomDownloadDialog
        CustomDownloadDialog(self, self.config).exec()

    def _open_luck(self):
        from ui.toolbox import LuckDialog
        LuckDialog(self, self.config).exec()

    def _open_dnc(self):
        from ui.toolbox import DoNotClickDialog
        DoNotClickDialog(self, self.config).exec()

    def _build_proxy_expand(self):
        """代理设置展开卡：类型 / 地址 / 端口 / 用户名 / 密码 收进一张卡片。"""
        card = _ExpandCard("LINK", "代理设置", "下载使用的代理服务器", self)
        self._expand_cards.append(card)

        cb = ComboBox()
        cb.addItem(tr("不使用"), userData="none")
        cb.addItem("HTTP", userData="http")
        cb.addItem("HTTPS", userData="https")
        cb.addItem("SOCKS5", userData="socks5")
        cur = self.config.get("proxy_type", "none")
        idx = cb.findData(cur)
        cb.setCurrentIndex(idx if idx >= 0 else 0)
        cb.setMinimumWidth(150)
        cb.currentTextChanged.connect(
            lambda: self._set("proxy_type", cb.currentData()))
        card.add_row("LINK", "代理类型", "下载使用的代理类型", cb)

        le_host = LineEdit()
        le_host.setPlaceholderText("127.0.0.1")
        le_host.setText(self.config.get("proxy_host", "") or "")
        le_host.setMinimumWidth(220)
        le_host.textChanged.connect(lambda t: self._set("proxy_host", t))
        card.add_row("LINK", "代理地址", "代理服务器主机名或 IP", le_host)

        le_port = LineEdit()
        le_port.setPlaceholderText("7890")
        le_port.setText(str(self.config.get("proxy_port", "") or ""))
        le_port.setMinimumWidth(220)
        le_port.textChanged.connect(lambda t: self._set("proxy_port", t))
        card.add_row("LINK", "代理端口", "代理服务器端口", le_port)

        le_user = LineEdit()
        le_user.setPlaceholderText(tr("需要认证时填写"))
        le_user.setText(self.config.get("proxy_user", "") or "")
        le_user.setMinimumWidth(220)
        le_user.textChanged.connect(lambda t: self._set("proxy_user", t))
        card.add_row("LINK", "代理用户名", "需要认证时填写", le_user)

        le_pass = LineEdit()
        le_pass.setEchoMode(LineEdit.EchoMode.Password)
        le_pass.setPlaceholderText(tr("需要认证时填写"))
        le_pass.setText(self.config.get("proxy_pass", "") or "")
        le_pass.setMinimumWidth(220)
        le_pass.textChanged.connect(lambda t: self._set("proxy_pass", t))
        card.add_row("LINK", "代理密码", "需要认证时填写", le_pass)

        return card

    def _on_open_logs(self):
        if callable(self.on_open_logs):
            try:
                self.on_open_logs()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # 交互回调
    # ------------------------------------------------------------------ #
    def _set(self, key, val, callback=True):
        try:
            self.config.set(key, val)
        except Exception:
            pass
        if callback:
            try:
                self.on_settings_changed()
            except Exception:
                pass

    def _on_appearance(self, val):
        # 持久化外观选择（此前只预览不保存，重启后会回退旧主题）
        try:
            self.config.set("appearance", val)
        except Exception:
            pass
        try:
            self._preview_theme({"appearance": val})
        except Exception:
            pass
        try:
            resolved = resolve_appearance(val)
            setTheme(Theme.DARK if resolved == "dark" else Theme.LIGHT)
        except Exception:
            pass

    def _on_accent(self, color: QColor):
        hexv = color.name()
        try:
            self.config.set("accent_color", hexv)
            self.config.set("accent_color_custom", hexv)
        except Exception:
            pass
        try:
            # set_accent 内部已同步 qfluentwidgets setThemeColor（值未变时自动跳过），
            # 这里不再重复调用，避免二次全量 re-polish。
            set_accent(hexv)
        except Exception:
            pass

    def _on_language(self, display):
        code = self._lang_rev.get(display, display)
        try:
            self.on_language_change(code)
        except Exception:
            pass
        self._retranslate()

    def _browse(self, btn, le, config_key, file_mode, filter_text):
        if file_mode:
            path, _ = QFileDialog.getOpenFileName(self, tr("选择 FFmpeg 可执行文件"),
                                                  le.text() or os.path.expanduser("~"),
                                                  f"FFmpeg (*{filter_text})" if filter_text else "")
        else:
            path = QFileDialog.getExistingDirectory(self, tr("选择下载目录"),
                                                    le.text() or os.path.expanduser("~"))
        if path:
            le.setText(path)
            self._set(config_key, path, callback=False)

    def _open_target(self, path):
        if path and os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ------------------------------------------------------------------ #
    # 多语言刷新（导航 / 卡片组 / 卡片标题）
    # ------------------------------------------------------------------ #
    @staticmethod
    def _set_card_title(card, text):
        try:
            card.setTitle(text)
            return
        except Exception:
            pass
        try:
            card.titleLabel.setText(text)
        except Exception:
            pass

    @staticmethod
    def _set_card_content(card, text):
        try:
            card.setContent(text)
            return
        except Exception:
            pass
        try:
            card.contentLabel.setText(text)
        except Exception:
            pass

    def _retranslate(self):
        for card, tk, ck in self._cards:
            if tk:
                self._set_card_title(card, tr(tk))
            if ck:
                self._set_card_content(card, tr(ck))
        for g, tk in self._groups:
            if tk:
                # SettingCardGroup 没有 setTitle（标题只在 titleLabel 上），
                # 走 _set_title 的兜底链，否则语言切换后分组标题不刷新。
                _set_title(g, tr(tk))
        for ec in self._expand_cards:
            try:
                ec.retranslate()
            except Exception:
                pass
        for rk, key in self._nav:
            try:
                self.navigationInterface.widget(rk).setText(tr(key))
            except Exception:
                pass
