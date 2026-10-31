"""软件更新服务（参照 ClassIsland 的 UpdateService 设计思路，适配本项目的 Python/PySide6 架构）。

核心能力
--------
* **更新通道（Channel）**：``stable``（仅稳定版）/ ``beta``（含测试版，指向最新的 Release）。
* **版本比对**：拉取 GitHub Release 清单后，按语义化版本号与本地 ``APP_VERSION`` 比较，
  仅在「远端更新」时判定为发现新版本，避免误报。
* **后台检查 / 下载**：网络请求全部在独立线程执行，不阻塞 GUI；进度通过回调回主线程，
  回调内部已用 ``run_on_main`` 兜底（无论从哪个线程调用都安全）。
* **下载进度**：按块累计，回传 ``(已下载字节, 总字节, 速度 B/s, 预计剩余秒)``，供 UI 显示
  进度条 / 速度 / ETA（复刻 ClassIsland 下载抽屉的展示维度）。
* **部署辅助**：下载完成后可打开所在目录 / 运行安装包（安装版）/ 解压覆盖（便携版）。

状态模型（对齐 ClassIsland 的 ``LastUpdateStatus`` / ``CurrentWorkingStatus`` 语义）：

    UpdateStatus        : IDLE / CHECKING / UP_TO_DATE / AVAILABLE / DOWNLOADING / ERROR
    UpdateWorkingStatus : IDLE / CHECKING / DOWNLOADING

网络异常（无网 / 限流 / 超时）会被捕获并转化为 ``UpdateStatus.ERROR``，不会让 UI 崩溃。
"""
from __future__ import annotations

import os
import sys
import threading
import time

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

import requests

from utils.version import (
    APP_NAME, APP_VERSION, GITHUB_API_RELEASES, is_newer, normalize_version,
)
from utils.main_thread import run_on_main

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
CHANNEL_STABLE = "stable"
CHANNEL_BETA = "beta"
CHANNELS = {
    CHANNEL_STABLE: "稳定版",
    CHANNEL_BETA: "测试版",
}

# 更新模式（对应设置项 update_mode 的取值）
UPDATE_MODE_NEVER = "never"        # 从不自动更新
UPDATE_MODE_NOTIFY = "notify"      # 自动检查并通知
UPDATE_MODE_DOWNLOAD = "download"   # 自动检查并下载
UPDATE_MODE_INSTALL = "install"     # 自动检查并安装（本软件：下载后提示运行安装包/解压）

UPDATE_MODES = {
    UPDATE_MODE_NEVER: "从不自动更新",
    UPDATE_MODE_NOTIFY: "自动检查并通知",
    UPDATE_MODE_DOWNLOAD: "自动检查并下载",
    UPDATE_MODE_INSTALL: "自动检查并安装",
}

UPDATE_API_TIMEOUT = 20          # 单次网络请求超时（秒）
UPDATE_CHUNK = 64 * 1024         # 下载分块大小
PROGRESS_THROTTLE = 0.1          # 进度 UI 刷新最小间隔（秒）


class UpdateStatus(str, Enum):
    """本地视角的更新状态（对齐 ClassIsland 的 LastUpdateStatus）。"""
    IDLE = "idle"
    CHECKING = "checking"
    UP_TO_DATE = "uptodate"
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    ERROR = "error"


class UpdateWorkingStatus(str, Enum):
    """后台工作态（对齐 ClassIsland 的 CurrentWorkingStatus）。"""
    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"


@dataclass
class Asset:
    """Release 的一个可下载资产（安装包 / 便携压缩包等）。"""
    name: str
    url: str
    size: int = 0
    content_type: str = ""


@dataclass
class UpdateInfo:
    """一次「发现的新版本」的完整描述。"""
    version: str                     # 规范化版本号，如 "2.1.1"
    tag: str                        # Release tag，如 "v2.1.1"
    name: str                       # Release 标题
    body: str = ""                  # 更新日志（Markdown）
    published_at: str = ""
    prerelease: bool = False
    channel: str = CHANNEL_STABLE
    assets: list = field(default_factory=list)

    @property
    def default_asset(self) -> Optional[Asset]:
        return pick_default_asset(self)


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def build_proxies(config) -> Optional[dict]:
    """根据 config 的代理设置构造 requests 用的 proxies 字典；不使用代理时返回 None。"""
    if config is None:
        return None
    ptype = (config.get("proxy_type", "none") or "none").strip().lower()
    if ptype in ("none", ""):
        return None
    host = (config.get("proxy_host", "") or "").strip()
    port = str(config.get("proxy_port", "") or "").strip()
    if not host:
        return None
    user = (config.get("proxy_user", "") or "").strip()
    pwd = (config.get("proxy_pass", "") or "").strip()
    auth = f"{user}:{pwd}@" if user else ""
    url = f"{ptype}://{auth}{host}:{port}"
    return {"http": url, "https": url}


def _platform_rank(name: str) -> int:
    """按「当前操作系统」给资产排序打分（越小越优先）。

    Release 里通常同时挂着 Windows 安装包 / 便携包、macOS dmg、Linux AppImage。
    若不做平台筛选，Windows 用户可能被匹配到 dmg/AppImage，装不上。
    """
    n = (name or "").lower()
    if sys.platform.startswith("win"):
        if n.endswith(".exe"):
            return 0
        if n.endswith(".zip"):
            return 1
        return 6
    if sys.platform == "darwin":
        if n.endswith(".dmg"):
            return 0
        if n.endswith(".zip"):
            return 1
        return 6
    # Linux / 其它
    if n.endswith(".appimage"):
        return 0
    if n.endswith(".tar.gz") or n.endswith(".7z"):
        return 1
    if n.endswith(".zip"):
        return 2
    return 6


def pick_default_asset(info: UpdateInfo) -> Optional[Asset]:
    """为新版本挑选一个默认下载资产。

    挑选顺序：

    1. 过滤 GitHub 自动生成的「Source code」源码包（用户通常不需要）；
    2. 优先当前操作系统能直接使用的格式（Windows → .exe/.zip，macOS → .dmg，
       Linux → .AppImage），跨平台资产排在后面；
    3. 同平台内：便携压缩包(.zip) 优先于安装包(.exe)——便携包解压即用，
       不需要管理员权限。
    """
    if not info or not info.assets:
        return None
    assets = [a for a in info.assets
              if a.name and "source code" not in a.name.lower()]
    if not assets:
        assets = list(info.assets)

    def score(a: Asset) -> tuple:
        n = (a.name or "").lower()
        plat = _platform_rank(n)
        if plat <= 1:
            # 同为可用格式：便携包优先于安装包
            kind = 0 if n.endswith(".zip") and "portable" in n else 1
        else:
            kind = 2
        return (plat, kind, a.name or "")

    return sorted(assets, key=score)[0]


def _run_in_thread(target, on_done=None, on_error=None):
    """在守护线程里执行 target，并把结果/异常回调到主线程。

    与本项目「回主线程更新 UI」的约定一致：所有 UI 刷新都经 ``run_on_main`` 排队到
    主线程事件循环，避免在工作线程操作 Qt 控件导致崩溃。
    """
    def _wrap():
        try:
            result = target()
            if on_done:
                run_on_main(lambda: on_done(result))
        except Exception as exc:  # noqa: BLE001 - 统一把异常回传 UI
            if on_error:
                run_on_main(lambda: on_error(exc))
    t = threading.Thread(target=_wrap, daemon=True)
    t.start()
    return t


# --------------------------------------------------------------------------- #
# 更新服务
# --------------------------------------------------------------------------- #
class UpdateService:
    """封装「检查更新 / 下载更新」的全部网络与状态逻辑。

    用法（典型）：
        svc = UpdateService(config)
        svc.check_for_updates(channel,
            on_result=lambda st, info: ...,   # st: UpdateStatus, info: UpdateInfo|None
            on_error=lambda e: ...)
        # 发现新版本后：
        svc.download_asset(info.default_asset, dest_dir,
            on_progress=lambda d, t, sp, eta: ...,
            on_done=lambda path: ...,
            on_error=lambda e: ...)
    """

    def __init__(self, config=None, proxies=None, api_url: str = GITHUB_API_RELEASES):
        self.config = config
        self.proxies = proxies if proxies is not None else build_proxies(config)
        self.api_url = api_url
        self.session = requests.Session()
        # GitHub API 要求带 User-Agent，否则会被 403
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "User-Agent": APP_NAME,
        })
        self._cancel = threading.Event()
        # 最近一次检查结果（供 UI 直接读取，避免重复网络请求）
        self.last_status: UpdateStatus = UpdateStatus.IDLE
        self.last_info: Optional[UpdateInfo] = None
        self.last_error: Optional[Exception] = None
        self.last_check_time: float = 0.0

    # ------------------------------------------------------------------ #
    # 检查更新（同步核心，由 *_async 包装到后台线程）
    # ------------------------------------------------------------------ #
    def fetch_latest(self, channel: str = CHANNEL_STABLE) -> tuple:
        """拉取指定通道的最新 Release 并与本地版本比较。

        返回 ``(UpdateStatus, UpdateInfo|None)``；网络/解析异常直接抛出，由调用方捕获。
        """
        resp = self.session.get(self.api_url, timeout=UPDATE_API_TIMEOUT,
                                proxies=self.proxies)
        resp.raise_for_status()
        releases = resp.json()
        if not isinstance(releases, list) or not releases:
            # 没有 Release 视为已是最新（避免误报）
            self.last_status = UpdateStatus.UP_TO_DATE
            self.last_info = None
            return UpdateStatus.UP_TO_DATE, None

        info = self._select_release(releases, channel)
        if info is None:
            self.last_status = UpdateStatus.UP_TO_DATE
            self.last_info = None
            return UpdateStatus.UP_TO_DATE, None

        if is_newer(info.version, APP_VERSION):
            self.last_status = UpdateStatus.AVAILABLE
            self.last_info = info
            return UpdateStatus.AVAILABLE, info
        # 远端版本不新于本地
        self.last_status = UpdateStatus.UP_TO_DATE
        self.last_info = info
        return UpdateStatus.UP_TO_DATE, None

    def _select_release(self, releases: list, channel: str) -> Optional[UpdateInfo]:
        """按通道从 Release 列表里挑出版本最高、且符合通道规则的一项。

        - stable：首个 ``prerelease == False`` 的 Release（只认稳定版）。
        - beta  ：列表里最新的一个（无论是否 prerelease，指向最新构建）。
        GitHub API 默认按发布时间倒序返回，故首个即最新。
        """
        candidates = list(releases)
        if channel == CHANNEL_STABLE:
            candidates = [r for r in candidates if not r.get("prerelease")]
        if not candidates:
            return None
        latest = candidates[0]
        return self._to_info(latest, channel)

    @staticmethod
    def _to_info(release: dict, channel: str) -> UpdateInfo:
        tag = release.get("tag_name", "") or ""
        version = normalize_version(tag)
        assets = []
        for a in release.get("assets", []) or []:
            assets.append(Asset(
                name=a.get("name", ""),
                url=a.get("browser_download_url", ""),
                size=int(a.get("size", 0) or 0),
                content_type=a.get("content_type", "") or "",
            ))
        return UpdateInfo(
            version=".".join(str(x) for x in version),
            tag=tag,
            name=release.get("name", tag),
            body=release.get("body", "") or "",
            published_at=release.get("published_at", "") or "",
            prerelease=bool(release.get("prerelease")),
            channel=channel,
            assets=assets,
        )

    # ------------------------------------------------------------------ #
    # 异步封装：后台线程 + 主线程回调
    # ------------------------------------------------------------------ #
    def check_for_updates(self, channel: str = CHANNEL_STABLE,
                          on_result=None, on_error=None):
        """后台检查更新。结果回调 ``on_result(status, info)``，异常回调 ``on_error(exc)``。"""
        self.last_status = UpdateStatus.CHECKING
        self.last_check_time = time.time()

        def _work():
            return self.fetch_latest(channel)

        def _deliver_result(result):
            if on_result is not None:
                status, info = result
                on_result(status, info)

        return _run_in_thread(
            _work,
            on_done=_deliver_result if on_result is not None else None,
            on_error=on_error)

    # ------------------------------------------------------------------ #
    # 下载
    # ------------------------------------------------------------------ #
    def download_asset(self, asset: Asset, dest_dir: str,
                       filename: str = None,
                       on_progress=None, on_done=None, on_error=None):
        """后台下载某个资产到 dest_dir（自动建目录）。

        - ``on_progress(downloaded, total, speed, eta)``：节流刷新（约 10 次/秒）。
        - ``on_done(path)``：下载完成（path 为本地文件）。
        - ``on_error(exc)``：失败（含取消）。
        """
        self._cancel.clear()
        os.makedirs(dest_dir, exist_ok=True)
        fname = filename or (asset.name or "update.bin")
        # 清理非法文件名字符
        for ch in ('/', '\\', ':', '*', '?', '"', '<', '>', '|'):
            fname = fname.replace(ch, "_")
        dest_path = os.path.join(dest_dir, fname)

        def _work():
            try:
                resp = self.session.get(
                    asset.url, stream=True, timeout=UPDATE_API_TIMEOUT,
                    proxies=self.proxies)
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0) or 0)
                downloaded = 0
                last_t = time.time()
                last_d = 0
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_content(UPDATE_CHUNK):
                        if self._cancel.is_set():
                            raise _Cancelled("用户取消了下载")
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if now - last_t >= PROGRESS_THROTTLE or downloaded >= total:
                            dt = now - last_t
                            speed = ((downloaded - last_d) / dt) if dt > 0 else 0.0
                            eta = ((total - downloaded) / speed) if speed > 0 and total else 0.0
                            if on_progress:
                                run_on_main(
                                    lambda: on_progress(downloaded, total, speed, eta))
                            last_t, last_d = now, downloaded
                if on_done:
                    run_on_main(lambda: on_done(dest_path))
            except _Cancelled:
                # 取消：清理半成品文件
                try:
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                except Exception:
                    pass
                if on_error:
                    run_on_main(lambda: on_error(_Cancelled("已取消")))
            except Exception as exc:  # noqa: BLE001
                if on_error:
                    # 同上：except 块结束后 exc 会被删除，需用默认参数绑定。
                    run_on_main(lambda e=exc: on_error(e))

        self.last_status = UpdateStatus.DOWNLOADING
        threading.Thread(target=_work, daemon=True).start()

    def cancel_download(self):
        self._cancel.set()


class _Cancelled(Exception):
    """内部：下载被取消。"""
