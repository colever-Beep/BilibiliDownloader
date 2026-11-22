"""顺序选集会话（纯逻辑，无 Qt 依赖，便于无头测试）。

背景
----
用户在「浏览 / 搜索 / 批量解析」页一次勾选了**多个**条目时，条目可能是
「有分集容器」（番剧 / 影视 / 课程 / 合集 / 多分P）与「无分集视频」混合。
旧实现为每个容器各起一个线程去解析，解析完成后各自调用
``show_episode_select`` 覆写同一个内联 BrowsePage —— 结果只有最后一个容器
的分集被显示，前面的选择全部丢失，体验很差。

本模块提供 ``SequentialSelectSession``：把每个「有分集容器」当成一个段
(segment)，按用户勾选顺序**依次**解析、依次让用户勾选分集；每段各自记住
勾选状态，用户可用「上一个 / 下一个」来回切换；全部走完后一次性汇总所有
分集 + 无分集视频，交给主流程入队。

职责边界：只管理「顺序 + 每段勾选态 + 汇总」的数据逻辑；网络解析与 UI
渲染由 MainWindow / BrowsePage 负责。
"""
from __future__ import annotations


def _key_of(item):
    """与 ui.select_list_view._key_of 相同的稳定键（避免反向依赖 Qt 模块）。"""
    if not item:
        return None
    return item.get("url") or item.get("bvid") or id(item)


class Segment:
    """单个待选择段：有分集容器（episodes）或 UP主空间（space）。"""

    __slots__ = ("source", "title", "kind", "episodes", "checked", "selected", "error")

    def __init__(self, source, title="", kind=None):
        self.source = source            # 容器 / UP主条目（含 url / title / mid）
        # kind: "episodes"=有分集容器按分集选择；"space"=UP主空间按其视频选择
        self.kind = kind or ("space" if (source or {}).get("type") == "user"
                             else "episodes")
        self.title = title or (
            (source or {}).get("title") or
            (source or {}).get("uploader") or "")
        self.episodes = None            # None=尚未解析；list=已解析（含空列表）
        self.checked = set()            # 用户勾选项的 key 集合（切换段时保留）
        self.selected = []              # 用户勾选的条目对象列表
        self.error = None               # 解析失败信息（None=无错误）


class SequentialSelectSession:
    """顺序选集会话。

    :param containers: 待解析段条目列表（按用户勾选顺序）：有分集容器、或
                       ``type=="user"`` 的 UP主（按空间视频选择），每项含 url/title/mid
    :param normals:    同一批勾选中的无分集视频（最后随各段结果一起入队）
    """

    def __init__(self, containers, normals=None):
        self.segments = []
        seen = set()
        for c in (containers or []):
            if not c:
                continue
            key = c.get("url") or c.get("bvid") or c.get("mid") or id(c)
            if key in seen:
                continue
            seen.add(key)
            self.segments.append(Segment(c))
        self.normals = list(normals or [])
        self.index = 0

    # ------------------------------------------------------------------ #
    # 基础状态
    # ------------------------------------------------------------------ #
    def __len__(self):
        return len(self.segments)

    @property
    def total(self):
        return len(self.segments)

    @property
    def current(self):
        if 0 <= self.index < len(self.segments):
            return self.segments[self.index]
        return None

    def has_prev(self):
        return self.index > 0

    def has_next(self):
        return self.index < len(self.segments) - 1

    def is_last(self):
        return bool(self.segments) and self.index == len(self.segments) - 1

    # ------------------------------------------------------------------ #
    # 勾选态
    # ------------------------------------------------------------------ #
    def snapshot(self, checked_keys, selected_items):
        """离开当前段前，把该段勾选态存入会话。"""
        seg = self.current
        if seg is None:
            return
        seg.checked = set(checked_keys or ())
        seg.selected = list(selected_items or [])

    def move_prev(self):
        if self.has_prev():
            self.index -= 1
            return True
        return False

    def move_next(self):
        if self.has_next():
            self.index += 1
            return True
        return False

    # ------------------------------------------------------------------ #
    # 汇总
    # ------------------------------------------------------------------ #
    def collected_episodes(self):
        """所有段勾选的分集，按段顺序汇总并按稳定键去重。"""
        out, seen = [], set()
        for seg in self.segments:
            for it in seg.selected:
                k = _key_of(it)
                if k in seen:
                    continue
                seen.add(k)
                out.append(it)
        return out

    def final_items(self):
        """最终入队项 = 各段勾选分集 + 同批无分集视频（去重）。"""
        out = self.collected_episodes()
        seen = {_key_of(it) for it in out}
        for it in self.normals:
            k = _key_of(it)
            if k in seen:
                continue
            seen.add(k)
            out.append(it)
        return out
