"""应用版本与更新相关常量 / 工具。

集中维护版本号与仓库信息，供关于页、更新服务、自述文件同步使用。

版本号采用四段式纯数字：``主.次.修订.构建``，例如 ``2.1.1.1``。
GitHub Release 的 tag 常带前缀 ``v``（如 ``v2.1.1.1``），比较时统一去前缀。
第四段用于同一修订版内的修复 / 重新发版；保持全数字是为了让 Inno Setup
等打包工具能直接接受版本号，避免带后缀 tag 被回退成 ``0.0.0``。
"""
from __future__ import annotations

import re

# 应用名（同时用于窗口标题、关于页、更新日志来源标识）
APP_NAME = "BilibiliDownloader"

# 当前版本（四段式纯数字）；v2.1.1 开发线的修复重发
APP_VERSION = "2.1.2"

# GitHub 仓库（更新检查与「主页」链接的来源）
GITHUB_REPO = "colever-Beep/BilibiliDownloader"
GITHUB_HOMEPAGE = f"https://github.com/{GITHUB_REPO}"
# GitHub Releases API（更新服务拉取版本清单的地方）
GITHUB_API_RELEASES = f"https://api.github.com/repos/{GITHUB_REPO}/releases"

# 固定解析 4 段，缺失段补 0：v2.1.1 -> (2,1,1,0)，v2.1.1.1 -> (2,1,1,1)。
# 元组长度一致，避免 Python 把「前缀相同但更长的元组」误判为更大。
_VERSION_RE = re.compile(
    r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?", re.IGNORECASE)


def normalize_version(v) -> tuple:
    """把 ``v2.1.1.1`` / ``2.1.1`` / ``2.1`` 解析为 ``(主, 次, 修订, 构建)``。

    统一返回 4 元组（缺失段补 0）；无法解析时返回 ``(0, 0, 0, 0)``，
    保证比较安全（不会因脏值崩溃，也不会因元组长度不同误判大小）。
    """
    if not v:
        return (0, 0, 0, 0)
    m = _VERSION_RE.match(str(v).strip())
    if not m:
        return (0, 0, 0, 0)
    return tuple(int(x) if x is not None else 0 for x in m.groups())


def is_newer(remote: str, current: str = APP_VERSION) -> bool:
    """``remote`` 是否比 ``current`` 新（按版本号数值比较）。"""
    return normalize_version(remote) > normalize_version(current)
