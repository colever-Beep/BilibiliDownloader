# -*- coding: utf-8 -*-
"""附加内容（弹幕 / 字幕 / 元数据 / 音频）格式转换工具。

设计说明
--------
下载环节统一交给 yt-dlp：
  * 弹幕  -> yt-dlp 的 ``danmaku`` 字幕轨，产物为 B 站原始 XML；
  * 字幕  -> yt-dlp 已把 B 站 JSON 字幕转成 SRT，产物为 ``*.<lang>.srt``；
  * 元数据 -> ``writeinfojson`` 产出 ``*.info.json``，或用 FFmpegMetadata 内嵌。

本模块只负责“落盘之后”的二次转换，全部为纯 Python 实现（NFO / ASS / LRC /
JSON / TXT），只有音频转码需要调用 ffmpeg。这样即使用户没装 protobuf 之类的
依赖，也能拿到多种格式。
"""

import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from html import escape as _xml_escape

# ---------------------------------------------------------------------------
# 通用
# ---------------------------------------------------------------------------

AUDIO_EXTS = {"m4a", "mp3", "aac", "opus", "flac", "wav", "ogg", "webm", "mka"}

#: 界面展示名 -> 实际扩展名。"原始" 表示不做任何转码
AUDIO_FORMATS = ["原始（不转换）", "m4a", "mp3", "aac", "flac", "wav", "opus"]
DANMAKU_FORMATS = ["xml", "ass", "json"]
SUBTITLE_FORMATS = ["srt", "ass", "lrc", "txt", "json"]
METADATA_FORMATS = ["json", "nfo", "内嵌到视频"]
SUBTITLE_LANGS = ["全部语言", "仅中文", "仅英文"]


def audio_format_ext(label):
    """把界面上的音频格式选项转成扩展名；'原始' 返回 None 表示不转码。"""
    if not label or label.startswith("原始"):
        return None
    return label.strip().lower()


def _fmt_ass_time(seconds):
    """秒 -> ASS 时间戳 H:MM:SS.cc"""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _fmt_srt_time(seconds):
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _text_width(text, font_size):
    """粗略估算文本像素宽度：CJK 占一个字宽，ASCII 约 0.55 字宽。"""
    width = 0.0
    for ch in text:
        width += font_size if ord(ch) > 0x2E80 else font_size * 0.55
    return int(width)


# ---------------------------------------------------------------------------
# 弹幕：B 站 XML -> dict 列表 / JSON / ASS
# ---------------------------------------------------------------------------

def parse_danmaku_xml(xml_text):
    """解析 B 站弹幕 XML，返回标准化后的 dict 列表。

    ``<d p="stime,mode,fontsize,color,ctime,pool,uid_hash,dmid">文本</d>``
    """
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    for node in root.iter("d"):
        attr = (node.get("p") or "").split(",")
        text = (node.text or "").strip()
        if not text or len(attr) < 4:
            continue
        try:
            stime = float(attr[0])
            mode = int(attr[1])
            font_size = int(attr[2])
            color = int(attr[3])
        except (ValueError, TypeError):
            continue
        items.append({
            "stime": stime,
            "mode": mode,
            "font_size": font_size,
            "color": color,
            "timestamp": attr[4] if len(attr) > 4 else "",
            "pool": attr[5] if len(attr) > 5 else "",
            "uid_hash": attr[6] if len(attr) > 6 else "",
            "dmid": attr[7] if len(attr) > 7 else "",
            "text": text,
        })
    items.sort(key=lambda x: x["stime"])
    return items


def danmaku_to_json(xml_text):
    return json.dumps(parse_danmaku_xml(xml_text), ensure_ascii=False, indent=2)


_ASS_TEMPLATE = """[Script Info]
; 由 B站下载器 生成
Title: {title}
ScriptType: v4.00+
WrapStyle: 2
Collisions: Normal
ScaledBorderAndShadow: yes
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Danmaku,{font},{size},&H{alpha}FFFFFF,&H{alpha}FFFFFF,&H{alpha}000000,&H{alpha}000000,0,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{dialogues}
"""


class _ScrollTrack:
    """滚动弹幕轨道：保证同轨相邻弹幕不追尾。"""

    def __init__(self, screen_width, min_gap):
        self.screen_width = screen_width
        self.min_gap = min_gap
        self.last_stime = None
        self.last_duration = 0.0
        self.last_width = 0
        self.last_speed = 1.0

    def can_fit(self, stime, speed):
        if self.last_stime is None:
            return True
        # 前一条尾部已离开右边缘并留出间距
        cond1 = stime >= self.last_stime + (self.last_width + self.min_gap) / max(self.last_speed, 1e-6)
        # 前一条离屏时，当前这条还没追上它
        cond2 = stime >= self.last_stime + self.last_duration - (self.screen_width - self.min_gap) / max(speed, 1e-6)
        return cond1 and cond2

    def push(self, stime, duration, width, speed):
        self.last_stime = stime
        self.last_duration = duration
        self.last_width = width
        self.last_speed = speed


class _StaticTrack:
    def __init__(self):
        self.end_time = -1.0

    def can_fit(self, stime):
        return stime >= self.end_time

    def push(self, end_time):
        self.end_time = end_time


def danmaku_to_ass(xml_text, title="", width=1920, height=1080,
                   font="微软雅黑", font_size=38, opacity=0.85, display_area=0.6):
    """把 B 站弹幕 XML 转成 ASS 字幕（滚动 / 顶部 / 底部三类，自动分轨防重叠）。"""
    items = parse_danmaku_xml(xml_text)
    line_height = font_size + 4
    max_scroll_rows = max(1, int(height * display_area / line_height))
    max_static_rows = max(1, int(height * display_area / line_height))
    min_gap = 20

    scroll_tracks = [_ScrollTrack(width, min_gap) for _ in range(max_scroll_rows)]
    top_tracks = [_StaticTrack() for _ in range(max_static_rows)]
    bottom_tracks = [_StaticTrack() for _ in range(max_static_rows)]

    scroll_duration = 10.0   # 滚动弹幕存活秒数
    static_duration = 5.0    # 顶/底部弹幕存活秒数

    dialogues = []
    for item in items:
        text = item["text"].replace("\n", " ").replace("{", "\\{").replace("}", "\\}")
        mode = item["mode"]
        stime = item["stime"]
        tw = _text_width(text, font_size)

        row = None
        tag = ""
        if mode in (1, 2, 3):  # 滚动
            duration = scroll_duration
            speed = (width + tw) / duration
            for idx, track in enumerate(scroll_tracks):
                if track.can_fit(stime, speed):
                    track.push(stime, duration, tw, speed)
                    row = idx
                    break
            if row is not None:
                y = row * line_height
                tag = f"\\move({width},{y},{-tw},{y})"
        elif mode == 5:  # 顶部
            duration = static_duration
            for idx, track in enumerate(top_tracks):
                if track.can_fit(stime):
                    track.push(stime + duration)
                    row = idx
                    break
            if row is not None:
                tag = f"\\an8\\pos({width // 2},{row * line_height})"
        elif mode == 4:  # 底部
            duration = static_duration
            for idx, track in enumerate(bottom_tracks):
                if track.can_fit(stime):
                    track.push(stime + duration)
                    row = idx
                    break
            if row is not None:
                tag = f"\\an2\\pos({width // 2},{height - row * line_height})"
        else:
            continue

        if row is None:  # 满屏，丢弃以免重叠
            continue

        color_tag = ""
        if item["color"] != 16777215:
            c = item["color"] & 0xFFFFFF
            bgr = ((c & 0xFF) << 16) | (c & 0xFF00) | ((c >> 16) & 0xFF)
            color_tag = f"\\c&H{bgr:06X}&"

        dialogues.append(
            "Dialogue: 0,{start},{end},Danmaku,,0,0,0,,{{{tags}}}{text}".format(
                start=_fmt_ass_time(stime),
                end=_fmt_ass_time(stime + duration),
                tags=tag + color_tag,
                text=text,
            )
        )

    alpha = f"{int((1.0 - opacity) * 255):02X}"
    return _ASS_TEMPLATE.format(
        title=title or "Danmaku",
        width=width,
        height=height,
        font=font,
        size=font_size,
        alpha=alpha,
        dialogues="\n".join(dialogues),
    )


# ---------------------------------------------------------------------------
# 字幕：SRT -> ASS / LRC / TXT / JSON
# ---------------------------------------------------------------------------

_SRT_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)


def parse_srt(srt_text):
    """解析 SRT，返回 [{'start': 秒, 'end': 秒, 'content': 文本}, ...]"""
    blocks = re.split(r"\n\s*\n", srt_text.replace("\r\n", "\n").strip())
    result = []
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        time_idx = None
        for i, line in enumerate(lines):
            if _SRT_TIME_RE.search(line):
                time_idx = i
                break
        if time_idx is None:
            continue
        m = _SRT_TIME_RE.search(lines[time_idx])
        start = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4).ljust(3, "0")) / 1000
        end = int(m.group(5)) * 3600 + int(m.group(6)) * 60 + int(m.group(7)) + int(m.group(8).ljust(3, "0")) / 1000
        content = "\n".join(lines[time_idx + 1:]).strip()
        if content:
            result.append({"start": start, "end": end, "content": content})
    return result


_SUB_ASS_TEMPLATE = """[Script Info]
; 由 B站下载器 生成
Title: {title}
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,20,20,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{dialogues}
"""


def srt_to_ass(srt_text, title="", font="微软雅黑", font_size=54):
    lines = []
    for item in parse_srt(srt_text):
        text = item["content"].replace("\n", "\\N")
        lines.append(
            f"Dialogue: 0,{_fmt_ass_time(item['start'])},{_fmt_ass_time(item['end'])},Default,,0,0,0,,{text}"
        )
    return _SUB_ASS_TEMPLATE.format(
        title=title or "Subtitle", font=font, size=font_size, dialogues="\n".join(lines)
    )


def srt_to_lrc(srt_text):
    lines = []
    for item in parse_srt(srt_text):
        minute = int(item["start"] // 60)
        second = item["start"] % 60
        text = item["content"].replace("\n", " ")
        lines.append(f"[{minute:02d}:{second:05.2f}]{text}")
    return "\n".join(lines)


def srt_to_txt(srt_text):
    return "\n".join(item["content"].replace("\n", " ") for item in parse_srt(srt_text))


def srt_to_json(srt_text):
    return json.dumps(parse_srt(srt_text), ensure_ascii=False, indent=2)


def convert_subtitle(srt_text, target_format, title=""):
    """按目标格式转换字幕，返回 (内容, 扩展名)。"""
    target = (target_format or "srt").lower()
    if target == "ass":
        return srt_to_ass(srt_text, title), "ass"
    if target == "lrc":
        return srt_to_lrc(srt_text), "lrc"
    if target == "txt":
        return srt_to_txt(srt_text), "txt"
    if target == "json":
        return srt_to_json(srt_text), "json"
    return srt_text, "srt"


# ---------------------------------------------------------------------------
# 元数据：NFO（Kodi / Jellyfin / Emby 通用）
# ---------------------------------------------------------------------------

def _nfo_node(tag, value):
    if value in (None, "", 0):
        return ""
    return f"  <{tag}>{_xml_escape(str(value), quote=False)}</{tag}>\n"


def build_nfo(task, info=None):
    """由队列任务信息（可选叠加 yt-dlp 的 info.json）生成 NFO 文本。"""
    info = info or {}
    title = task.get("title") or info.get("title") or ""
    uploader = task.get("uploader") or info.get("uploader") or ""
    publish = str(task.get("publish_time") or "")
    # 只保留 YYYY-MM-DD，Kodi 的 <aired> 需要标准日期
    aired = publish[:10] if len(publish) >= 10 else ""
    plot = info.get("description") or ""
    duration = task.get("duration") or info.get("duration") or 0
    thumb = task.get("thumbnail") or info.get("thumbnail") or ""

    body = ["<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"yes\"?>\n<episodedetails>\n"]
    body.append(_nfo_node("title", title))
    body.append(_nfo_node("showtitle", title))
    body.append(_nfo_node("plot", plot))
    body.append(_nfo_node("aired", aired))
    body.append(_nfo_node("premiered", aired))
    body.append(_nfo_node("studio", "bilibili"))
    if uploader:
        body.append(f"  <director>{_xml_escape(uploader, quote=False)}</director>\n")
        body.append("  <actor>\n")
        body.append(f"    <name>{_xml_escape(uploader, quote=False)}</name>\n")
        body.append("    <role>UP主</role>\n")
        body.append("  </actor>\n")
    if thumb:
        body.append(f"  <thumb>{_xml_escape(thumb, quote=False)}</thumb>\n")
    if duration:
        try:
            body.append("  <fileinfo>\n    <streamdetails>\n      <video>\n")
            body.append(f"        <durationinseconds>{int(duration)}</durationinseconds>\n")
            body.append("      </video>\n    </streamdetails>\n  </fileinfo>\n")
        except (TypeError, ValueError):
            pass
    for tag in (info.get("tags") or [])[:15]:
        body.append(f"  <tag>{_xml_escape(str(tag), quote=False)}</tag>\n")
    body.append(_nfo_node("source", task.get("url", "")))
    body.append("</episodedetails>\n")
    return "".join(x for x in body if x)


# ---------------------------------------------------------------------------
# 音频转码
# ---------------------------------------------------------------------------

_AUDIO_ENCODER = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "aac": ["-c:a", "aac", "-b:a", "192k"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "opus": ["-c:a", "libopus", "-b:a", "160k"],
    "flac": ["-c:a", "flac"],
    "wav": ["-c:a", "pcm_s16le"],
}


def convert_audio(src_path, target_ext, ffmpeg_path=None, bitrate=None):
    """把音频文件转成目标格式，成功后删除源文件并返回新路径；失败返回 None。"""
    if not src_path or not os.path.isfile(src_path) or not target_ext:
        return None
    target_ext = target_ext.lower()
    if src_path.lower().endswith("." + target_ext):
        return src_path

    dst_path = os.path.splitext(src_path)[0] + "." + target_ext
    args = list(_AUDIO_ENCODER.get(target_ext, ["-c:a", "copy"]))
    if bitrate and target_ext in ("mp3", "aac", "m4a", "opus"):
        # 用户指定码率时覆盖默认值
        for flag in ("-q:a", "-b:a"):
            while flag in args:
                i = args.index(flag)
                del args[i:i + 2]
        args += ["-b:a", str(bitrate)]

    cmd = [ffmpeg_path or "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-i", src_path, "-vn"] + args + [dst_path]
    creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              creationflags=creationflags)
    except Exception:
        return None
    if proc.returncode != 0 or not os.path.isfile(dst_path):
        if os.path.isfile(dst_path):
            try:
                os.remove(dst_path)
            except OSError:
                pass
        return None
    if os.path.abspath(dst_path) != os.path.abspath(src_path):
        try:
            os.remove(src_path)
        except OSError:
            pass
    return dst_path


# ---------------------------------------------------------------------------
# 文件辅助
# ---------------------------------------------------------------------------

def read_text(path):
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            with open(path, "r", encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
        except OSError:
            return None
    return None


def write_text(path, content):
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except OSError:
        return False


def list_outputs(out_dir, base_name):
    """列出以 ``base_name.`` 开头的所有产物文件（绝对路径）。"""
    prefix = base_name + "."
    try:
        names = os.listdir(out_dir)
    except OSError:
        return []
    return [os.path.join(out_dir, n) for n in names if n.startswith(prefix)]
