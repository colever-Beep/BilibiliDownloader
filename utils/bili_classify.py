"""B 站链接 / 来源标签 -> 视频种类文件夹名。

用于『按视频种类自动分文件夹』功能：把下载内容按类型归入
视频 / 番剧 / 直播 / 音频 / 歌单 / 收藏夹 / UP主 / 合集 / 课程 等子目录。

设计要点：
- 目录名直接落盘，**不做翻译**（避免切换界面语言后文件散落到不同目录）。
- URL 判定优先（最可靠）；b23.tv 短链等无法从 URL 判断时，用来源 category
  标签兜底；两者都失败再回落到『视频』。
"""
from __future__ import annotations

KIND_VIDEO = "视频"
KIND_BANGUMI = "番剧"
KIND_LIVE = "直播"
KIND_AUDIO = "音频"
KIND_PLAYLIST = "歌单"
KIND_FAV = "收藏夹"
KIND_UP = "UP主"
KIND_COLLECTION = "合集"
KIND_COURSE = "课程"

# 非法路径字符（Windows），用于兜底校验
_ILLEGAL_CHARS = '\\/:*?"<>|'


def classify_bili_kind(url, category=""):
    """返回该链接应当归属的种类目录名（中文，落盘用）。"""
    u = (url or "").strip().lower()
    cat = (category or "").strip().lower()

    # 1) 优先按 URL 主机 / 路径判定（最可靠）
    if "live.bilibili.com" in u:
        return KIND_LIVE
    if "bangumi" in u:
        return KIND_BANGUMI
    if "audio/menu" in u or "music.bilibili.com" in u or "/music/" in u:
        return KIND_PLAYLIST
    if "bilibili.com/audio" in u:
        return KIND_AUDIO
    if "favlist" in u or "medialist" in u:
        return KIND_FAV
    if "channel" in u or "series" in u or "collection" in u:
        return KIND_COLLECTION
    if "space.bilibili.com" in u:
        return KIND_UP
    if "bilibili.com/video" in u or "/bv" in u or "/av" in u:
        return KIND_VIDEO

    # 2) URL 无法判定（如 b23.tv 短链），用来源 category 标签兜底
    pairs = (
        ("番剧", KIND_BANGUMI), ("影视", KIND_BANGUMI),
        ("直播", KIND_LIVE),
        ("音频", KIND_AUDIO), ("音乐", KIND_AUDIO),
        ("歌单", KIND_PLAYLIST),
        ("收藏", KIND_FAV),
        ("up", KIND_UP), ("空间", KIND_UP),
        ("合集", KIND_COLLECTION), ("频道", KIND_COLLECTION),
        ("课程", KIND_COURSE),
    )
    for kw, name in pairs:
        if kw in cat:
            return name

    # 3) 兜底：普通视频
    return KIND_VIDEO


def safe_kind(kind):
    """兜底防御：确保种类名合法且非空，避免异常标签污染路径。"""
    kind = (kind or "").strip()
    if not kind or any(ch in kind for ch in _ILLEGAL_CHARS):
        return KIND_VIDEO
    return kind
