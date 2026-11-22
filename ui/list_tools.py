"""视频列表的公共排序 / 本地过滤工具。

独立成模块是为了让 BrowsePage（ui.content_pages）与选择对话框（ui.select_dialog）
共用同一套逻辑，又避免两者互相 import 造成循环依赖
（content_pages → dialogs → select_dialog）。

- 排序键与显示标签统一在这里维护；配置值 / 排序字段名不翻译，显示标签由调用方 tr()。
- 本地过滤只作用于「当前已加载」的列表项（一页 / 一批），语义与「我的关注」搜索框一致。
"""
from __future__ import annotations

SORT_KEYS = ("default", "pub", "view", "duration", "title")
SORT_LABELS = {
    "default": "默认排序",
    "pub": "按发布时间",
    "view": "按播放量",
    "duration": "按时长",
    "title": "按标题",
}

# 本地过滤时参与匹配的字段（视频标题 / UP主 / bvid / 简介）
_FILTER_FIELDS = ("title", "author", "up_name", "uname", "name",
                  "bvid", "desc", "description")


def _sort_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _sort_pub_key(v):
    """发布时间 → 统一的 epoch 秒数，便于混合「时间戳/日期字符串」时正确比较。"""
    from datetime import datetime
    if isinstance(v, (int, float)):
        n = float(v)
        return n / 1000 if n > 1e11 else n   # 13 位毫秒时间戳换算为秒
    s = str(v or "").strip()
    if not s:
        return 0.0
    try:                                      # 纯数字字符串按时间戳
        n = float(s)
        return n / 1000 if n > 1e11 else n
    except ValueError:
        pass
    try:                                      # ISO 日期字符串（含 Z / 纯日期）
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def sort_items(items, key):
    """按 key 返回新列表；default 或未知 key 原样返回。"""
    seq = list(items)
    if key in (None, "", "default"):
        return seq
    if key == "title":
        return sorted(seq, key=lambda it: str(it.get("title") or ""))
    if key == "view":
        return sorted(seq, key=lambda it: _sort_num(it.get("view_count")), reverse=True)
    if key == "duration":
        return sorted(seq, key=lambda it: _sort_num(it.get("duration")), reverse=True)
    if key == "pub":
        return sorted(seq, key=lambda it: _sort_pub_key(it.get("publish_time")), reverse=True)
    return seq


def filter_items(items, keyword):
    """按关键字对本批 items 做本地过滤（大小写不敏感，匹配标题/UP主/bvid/简介）。"""
    seq = list(items)
    kw = (keyword or "").strip().lower()
    if not kw:
        return seq
    out = []
    for it in seq:
        if not isinstance(it, dict):
            continue
        hay = " ".join(str(it.get(f) or "") for f in _FILTER_FIELDS).lower()
        if kw in hay:
            out.append(it)
    return out
