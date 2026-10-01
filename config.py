import json
import os


def get_bundled_ffmpeg_path():
    """返回同目录（程序根目录）下 bin/ffmpeg.exe 的绝对路径。

    仅在「FFmpeg 路径」设置留空时使用，作为内置 ffmpeg 的回退来源；
    返回的路径不保证一定存在，调用方需自行判断文件是否存在。
    """
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "bin", "ffmpeg.exe")


def _default_videos_path():
    """自动寻找用户电脑中的视频文件夹：Windows 用 Known Folder ID（兼容中文系统
    的「视频」文件夹），其他系统回退到 ~/Videos，并确保目录存在。"""
    try:
        import ctypes
        from ctypes import wintypes
        # FOLDERID_Videos = {18989B1D-99B5-455B-841C-AB7C74E4DDFC}
        fid = ctypes.create_unicode_buffer("{18989B1D-99B5-455B-841C-AB7C74E4DDFC}")
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        SHGetKnownFolderPath = shell32.SHGetKnownFolderPath
        SHGetKnownFolderPath.argtypes = [
            ctypes.c_wchar_p, wintypes.DWORD, wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p)
        ]
        SHGetKnownFolderPath.restype = ctypes.HRESULT
        p_path = ctypes.c_wchar_p()
        hr = SHGetKnownFolderPath(fid, 0, None, ctypes.byref(p_path))
        if hr == 0 and p_path.value:
            path = p_path.value
            try:
                ole32.CoTaskMemFree(p_path)
            except Exception:
                pass
            if path:
                try:
                    os.makedirs(path, exist_ok=True)
                except Exception:
                    pass
                if os.path.isdir(path):
                    return path
    except Exception:
        pass
    # 回退：~/Videos
    fallback = os.path.join(os.path.expanduser("~"), "Videos")
    try:
        os.makedirs(fallback, exist_ok=True)
    except Exception:
        pass
    return fallback


def normalize_download_path(raw):
    """校验并归一化下载路径，确保最终返回一个真实存在、可写入的目录。

    典型失效场景：程序被打包分发到「用户名不同的电脑」后，settings.json 里
    残留了旧机器的绝对路径（如 ``C:/Users/旧用户名/Downloads``），该目录在新
    电脑上不存在也不存在写入权限，直接交给下载器会导致下载失败。

    规则：
    1. 保存的路径存在且可写 -> 直接使用（尊重用户自定义目录）。
    2. 否则尝试创建该路径 -> 创建成功且可写则使用。
    3. 前述都失败 -> 自动寻找当前登录用户的「视频」文件夹作为兜底
       （Windows 用 Known Folder ID，天然跟随当前用户，不会写死旧用户名）。
    """
    raw = (raw or "").strip()
    if raw:
        # 1. 已存在且可写
        if os.path.isdir(raw) and os.access(raw, os.W_OK):
            return raw
        # 2. 尝试创建（合法但尚未创建的自定义目录）
        try:
            os.makedirs(raw, exist_ok=True)
            if os.path.isdir(raw) and os.access(raw, os.W_OK):
                return raw
        except Exception:
            pass
    # 3. 兜底：当前用户的视频文件夹（一定存在且可写）
    return _default_videos_path()


DEFAULT_CONFIG = {
    "open_download_dir": True,
    "download_path": _default_videos_path(),
    "max_workers": 3,
    # 下载队列列宽（像素，用户可在表头拖拽调整；旧版为 list，遇到非 dict 会回落默认值）
    "column_widths": {
        "cover": 96, "num": 36, "title": 280, "dur": 70, "pub": 96,
        "view": 74, "like": 74, "fav": 74, "status": 70, "actions": 112,
    },
    "download_danmaku": True,
    "download_cover": True,
    "embed_cover": False,
    "delete_cover_after_attach": False,  # 内嵌封面后是否删除原封面文件（需开启 embed_cover）
    "cover_type": "jpg",                # 封面文件格式：jpg / png / webp / avif
    "audio_video_separate": False,
    "live_record_codec": "copy",      # 直播录制编码：copy（原始流，不转码）/ h264 / h265
                                      # B 站直播高清流常为 HEVC/AV1，-c copy 封装 mp4 后
                                      # 部分播放器提示「解码不受支持」，可切换 h264 实时转码
    "live_record_format": "mp4",      # 直播录制封装格式：mp4 / mkv / flv / ts
    "live_record_qn": 10000,          # 直播录制清晰度（B 站 qn 码）：10000 原画 / 40000 4K
                                      # / 30000 杜比 / 250 超清 / 150 高清 / 80 流畅
    "live_record_auto_reconnect": True,   # 直播断流后自动重连并分段保存
    "live_record_options_dialog": True,   # 开始录制前是否弹出「直播录制选项」对话框
    "quality": "1080p",
    "merge_format": "mp4",
    "appearance": "dark",
    "video_codec": "H.264 (兼容性好)",
    # ---- 音频 ----
    "audio_only": False,              # 仅下载音频（不下载视频流）
    "audio_format": "原始（不转换）",   # 原始 / m4a / mp3 / aac / flac / wav / opus
    "audio_bitrate": "192k",          # 有损格式的目标码率
    # ---- 弹幕 ----
    "danmaku_format": "xml",          # xml / ass / json
    # ---- 字幕 ----
    "download_subtitle": False,
    "subtitle_format": "srt",         # srt / ass / lrc / txt / json
    "subtitle_lang": "全部语言",        # 全部语言 / 仅中文 / 仅英文
    # ---- 元数据 ----
    "download_metadata": False,
    "metadata_format": "json",        # json / nfo / 内嵌到视频
    "download_limit": 0,
    "overwrite": False,               # 旧字段（兼容）：True 等价 file_conflict_resolution=overwrite
    "file_conflict_resolution": "auto_rename",  # 同名文件处理：auto_rename（自动重命名）/ overwrite（覆盖）
    "show_download_options_dialog": True,       # 选择视频后是否弹出「下载选项」对话框
    "create_folder": True,            
    "proxy_type": "none",            
    "proxy_host": "",
    "proxy_port": "",
    "proxy_user": "",
    "proxy_pass": "",
    # ---- 关闭行为 / 登录提示 ----
    "close_behavior": "",            # 首次关闭时询问："" 未设置 / "tray" 最小化到托盘 / "quit" 直接关闭
    "stay_on_top": False,            # 主窗口置顶（参照 bili23 WindowBehaviorSettingCard）
    "login_api_warned": False,       # 是否已展示过登录后 API 限制警告（仅首次登录展示）
    "accepted_terms": False,         # 是否已接受《用户协议》（首次启动弹窗，不接受则退出）

    "language": "zh_CN",             # 界面语言：zh_CN / zh_TW / en / ja

    # ---- 列表布局（详细 / 精简）----
    "list_layout": "detailed",       # 所有视频/选择类列表的密度：detailed（详细）/ compact（精简，仅标题+UP+时长）

    # ---- 主题 ----
    "accent_color": "#1f8a4c",       # 强调色（主题色）；"system" 表示跟随 Windows 系统强调色
    "accent_color_custom": "#1f8a4c",  # 上一次自定义强调色（跟随系统开关关闭时恢复用）

    # ---- 百宝箱（设置 → 高级）娱乐功能，与下载主流程无关 ----
    "toolbox_download_dir": "",           # 自定义链接下载的保存目录（空 = 跟随 download_path）
    "toolbox_download_quality": "best",   # best / 1080p / 720p / audio
    "toolbox_luck_seed": "",              # 今日人品的名字 / 种子（空 = 当前系统用户名）
    "toolbox_luck_bonus": 0,              # 今日人品彩蛋加成（「千万别点」每次 +5，上限 20）
    "toolbox_dnc_clicks": 0,              # 「千万别点」累计点击次数

    "quality_rules": {
        "8K":  "bestvideo[height<=4320][vcodec^=avc]+bestaudio[acodec^=mp4a]/best[height<=4320]",
        "4K":  "bestvideo[height<=2160][vcodec^=avc]+bestaudio[acodec^=mp4a]/best[height<=2160]",
        "1080p": "bestvideo[height<=1080][vcodec^=avc]+bestaudio[acodec^=mp4a]/best[height<=1080]",
        "720p": "bestvideo[height<=720][vcodec^=avc]+bestaudio[acodec^=mp4a]/best[height<=720]",
        "480p": "bestvideo[height<=480][vcodec^=avc]+bestaudio[acodec^=mp4a]/best[height<=480]",
        "360p": "bestvideo[height<=360][vcodec^=avc]+bestaudio[acodec^=mp4a]/best[height<=360]"
    }
}

class ConfigManager:
    def __init__(self, config_file="settings.json"):
        self.config_file = config_file
        self.config = self._load()

    def _load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                # 合并默认值
                result = {**DEFAULT_CONFIG, **user_config}
                # 确保 quality_rules 存在
                if "quality_rules" not in result or not result["quality_rules"]:
                    result["quality_rules"] = DEFAULT_CONFIG["quality_rules"]
                # ---- 下载路径自愈 ----
                # 跨电脑/跨用户时 settings.json 可能残留旧用户名路径，这里自动
                # 归一到当前用户真正可用、可写的视频文件夹（仅在确有损坏时回写，
                # 避免每次启动都无谓写盘）。
                raw_path = result.get("download_path")
                safe_path = normalize_download_path(raw_path)
                result["download_path"] = safe_path
                if safe_path != raw_path:
                    try:
                        with open(self.config_file, "w", encoding="utf-8") as f:
                            json.dump(result, f, indent=2, ensure_ascii=False)
                    except Exception:
                        pass
                return result
            except:
                return DEFAULT_CONFIG.copy()
        return DEFAULT_CONFIG.copy()

    def save(self):
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def get_quality_rule(self, quality_label=None):
        if quality_label is None:
            quality_label = self.get("quality", "1080p")
        rules = self.get("quality_rules", DEFAULT_CONFIG["quality_rules"])
        rule = rules.get(quality_label)
        if not rule:
            # 如果找不到对应清晰度，返回 H.264 优先的通用规则
            return "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[acodec^=mp4a]/best[ext=mp4]/best"
        return rule