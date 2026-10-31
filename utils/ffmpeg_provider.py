"""FFmpeg 供应器：本地优先，缺失则运行时下载（官方构建），并支持手动回退。

设计目标（与「两者都要」需求一致）：
1. 本地优先：同目录 bin/<ffmpeg>（开发态为项目根 bin/；冻结后为 exe 所在目录 bin/）。
2. 缺失则后台下载：首次用到时按当前平台下载对应压缩包，
   解压 bin/ 下的 ffmpeg / ffprobe 到本地 bin/，之后离线可用。
3. 手动回退：用户也可自行把 ffmpeg 放进 bin/（或「设置」里指定绝对路径），优先级最高。

只分发两个可执行文件（ffmpeg / ffprobe），**不分发 ffplay**：
- ffplay 是纯播放器，本项目与 yt-dlp 全程都不调用它，纯属浪费体积
  （静态构建里单个 ffplay.exe 就有 160MB+）。
- ffprobe 必须保留：yt-dlp 的 FFmpegMetadata 后处理器（内嵌元数据）会直接调用它，
  缺失时抛 PostProcessingError('ffprobe not found') 而中断下载流程。

跨平台适配：
- 二进制名：Windows 为 ffmpeg.exe / ffprobe.exe；Linux / macOS 为无扩展名的
  ffmpeg / ffprobe（下载后赋予可执行权限）。
- 下载源：
  - Windows 优先 gyan.dev 的 release essentials 构建（只含常用编解码器，
    体积远小于 full 构建），失败时回退 BtbN 的 win64 GPL 构建；
  - Linux x86_64 -> BtbN linux64 gpl tar.xz；Linux aarch64 -> BtbN linuxarm64 gpl tar.xz；
  - macOS x86_64 -> BtbN macos64 gpl tar.xz；macOS Apple Silicon -> BtbN macosarm64 gpl tar.xz。

冻结（PyInstaller onefile）说明：
- 程序文件位于 _MEIPASS 临时目录（只读、退出即清），不能把下载的 ffmpeg 写回那里；
  因此冻结态一律写到 sys.executable 所在目录的 bin/ 下。
"""
import os
import sys
import zipfile
import tarfile
import shutil
import threading

try:
    import requests
except Exception:  # requests 缺失时允许「手动回退」路径仍可用
    requests = None

_lock = threading.Lock()
_in_progress = False          # 是否已有下载在进行
_callbacks = []              # 下载结束时要回调的 on_done(path_or_None) 列表


# --------------------------------------------------------------------------- #
# 平台识别 & 文件名
# --------------------------------------------------------------------------- #
def _machine():
    """归一化 CPU 架构。"""
    import platform
    m = platform.machine().lower()
    if m in ("x86_64", "amd64", "x64"):
        return "x86_64"
    if m in ("aarch64", "arm64"):
        return "arm64"
    return m


def _platform_key():
    """返回 (系统, 架构) 归一化字符串。"""
    if sys.platform == "win32":
        return "windows", _machine()
    if sys.platform == "darwin":
        return "macos", _machine()
    if sys.platform.startswith("linux"):
        return "linux", _machine()
    return "unknown", _machine()


def ffmpeg_exe_name():
    """返回当前平台 ffmpeg 可执行文件名（Windows 带 .exe，其余无扩展名）。"""
    if sys.platform == "win32":
        return "ffmpeg.exe"
    return "ffmpeg"


def _download_spec():
    """返回 ``[(下载 URL, 归档类型), ...]``（按优先级排列）。

    归档类型：'zip'（Windows）或 'tarxz'（Linux / macOS）。
    Windows 给多个候选源：gyan 的 essentials 构建优先（体积小、无用库少），
    BtbN 的 GPL 构建作为兜底（gyan 不可达时仍能装上）。
    """
    sysname, mach = _platform_key()
    if sysname == "windows":
        return [
            ("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip", "zip"),
            ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
             "ffmpeg-master-latest-win64-gpl.zip", "zip"),
        ]
    if sysname == "linux":
        name = ("ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
                if mach == "arm64"
                else "ffmpeg-master-latest-linux64-gpl.tar.xz")
        return [("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/" + name,
                 "tarxz")]
    if sysname == "macos":
        name = ("ffmpeg-master-latest-macosarm64-gpl.tar.xz"
                if mach == "arm64"
                else "ffmpeg-master-latest-macos64-gpl.tar.xz")
        return [("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/" + name,
                 "tarxz")]
    return []


# --------------------------------------------------------------------------- #
# 路径解析
# --------------------------------------------------------------------------- #
def _frozen_base_dir():
    """冻结态下用于存放 bin/ 的可写基目录。

    - macOS .app：签名只读包，不能往包内写（会破坏签名）-> 用户 Application Support。
    - AppImage：运行时挂载为只读 squashfs（/tmp/.mount_*）-> XDG 数据目录。
    - 其余（Windows / Linux 普通 onedir）：exe 同目录（便携版就地下 bin/）。
    """
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support", "BilibiliDownloader")
    if os.environ.get("APPIMAGE"):
        xdg = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
        return os.path.join(xdg, "BilibiliDownloader")
    return os.path.dirname(os.path.abspath(sys.executable))


def get_ffmpeg_dir():
    """返回 bin/ 目录的绝对路径（与 get_bundled_ffmpeg_path 约定一致）。"""
    if getattr(sys, "frozen", False):
        # 冻结态：_MEIPASS 只读且会被清理，写到可写的基目录/bin（见 _frozen_base_dir）
        return os.path.join(_frozen_base_dir(), "bin")
    # 开发态：本文件在 utils/，项目根 = 上级目录
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")


def get_ffmpeg_path():
    return os.path.join(get_ffmpeg_dir(), ffmpeg_exe_name())


def is_available():
    p = get_ffmpeg_path()
    return os.path.isfile(p) and os.access(p, os.X_OK)


# --------------------------------------------------------------------------- #
# 下载调度
# --------------------------------------------------------------------------- #
def ensure_ffmpeg(logger=None, on_done=None):
    """返回 ffmpeg 路径；本地缺失则后台下载，返回 None。

    - 若已存在，直接返回路径（on_done 不会被调用）。
    - 若不存在：注册 on_done（若有），若无进行中的下载则启动一个后台线程；
      下载成功 -> on_done(路径)；失败 -> on_done(None)。期间返回 None。
    """
    if is_available():
        return get_ffmpeg_path()
    global _in_progress
    with _lock:
        if on_done is not None and on_done not in _callbacks:
            _callbacks.append(on_done)
        if _in_progress:
            if logger:
                logger.log("ffmpeg 正在后台下载，请稍候…")
            return None
        _in_progress = True
    if logger:
        logger.log("首次使用需下载 ffmpeg，将在后台下载，完成后自动继续…")
    threading.Thread(target=_download, args=(logger,), daemon=True).start()
    return None


def _fire(path):
    with _lock:
        cbs = _callbacks[:]
        _callbacks.clear()
    for cb in cbs:
        try:
            cb(path)
        except Exception:
            pass


def _download(logger):
    global _in_progress
    try:
        specs = _download_spec()
        if not specs:
            raise RuntimeError("当前平台不支持自动下载 ffmpeg（请手动放入 bin/ 或安装系统 ffmpeg）")
        bin_dir = get_ffmpeg_dir()
        os.makedirs(bin_dir, exist_ok=True)
        if requests is None:
            raise RuntimeError("缺少 requests 库，无法自动下载 ffmpeg（请手动放入 bin/）")
        last_err = None
        for idx, (url, kind) in enumerate(specs):
            if idx and logger:
                logger.log(f"主下载源失败，尝试备用源…")
            try:
                _download_one(url, kind, bin_dir, logger)
                if is_available():
                    if logger:
                        logger.log("ffmpeg 下载完成 ✅（已保存到 bin/，下次启动免下载）")
                    _fire(get_ffmpeg_path())
                    return
                last_err = RuntimeError("解压后未在 bin/ 中找到 ffmpeg")
            except Exception as e:
                last_err = e
        raise last_err or RuntimeError("ffmpeg 下载失败")
    except Exception as e:
        if logger:
            logger.log(f"ffmpeg 自动下载失败：{e}；可将平台对应的 ffmpeg 手动放入 bin/ 后重试")
        _fire(None)
    finally:
        with _lock:
            _in_progress = False


def _download_one(url, kind, bin_dir, logger=None):
    """从单个源下载并解压 ffmpeg/ffprobe；失败时抛异常（由调用方回退到下一源）。"""
    if logger:
        logger.log("开始下载 ffmpeg…")
    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0)) or 0
    downloaded = 0
    last_pct = -1
    ext = ".zip" if kind == "zip" else ".tar.xz"
    tmp = get_ffmpeg_path() + ext + ".download.tmp"
    try:
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    if pct >= last_pct + 10:  # 每 ~10% 记录一次
                        last_pct = pct
                        if logger:
                            logger.log(f"ffmpeg 下载中… {pct}%")
        _extract_archive(tmp, kind, bin_dir)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# 归档解压（zip / tar.xz 通用）
# --------------------------------------------------------------------------- #
def _copy_member(src, dst):
    with open(dst, "wb") as dst_f:
        shutil.copyfileobj(src, dst_f)


def _extract_archive(archive_path, kind, bin_dir):
    """从官方压缩包中提取 ffmpeg / ffprobe 到本地 bin_dir。

    - zip（Windows）：取归档内 bin/ 下名为 ffmpeg / ffprobe 的可执行文件。
    - tar.xz（Linux / macOS）：取归档内名为 ffmpeg / ffprobe 的文件
      （不限层级，自动适配 BtbN 不同平台的内部布局），额外赋予 0o755。

    刻意**不提取 ffplay**：它是纯播放器，本项目与 yt-dlp 都不会调用，
    而静态构建中它比 ffmpeg 本体还大，白白占用数百 MB。
    """
    wanted = ("ffmpeg", "ffprobe")
    if kind == "zip":
        with zipfile.ZipFile(archive_path) as z:
            for name in z.namelist():
                norm = name.replace("\\", "/")
                if "/bin/" not in norm:
                    continue
                base = os.path.basename(name)
                stem = base[:-4] if base.lower().endswith(".exe") else base
                if stem.lower() not in wanted:
                    continue
                target = os.path.join(bin_dir, base)
                with z.open(name) as src:
                    _copy_member(src, target)
    elif kind == "tarxz":
        with tarfile.open(archive_path, "r:*") as z:
            for m in z.getmembers():
                if not m.isfile():
                    continue
                base = os.path.basename(m.name)
                if base.lower() not in wanted:
                    continue
                target = os.path.join(bin_dir, base)
                with z.extractfile(m) as src:
                    _copy_member(src, target)
                try:
                    os.chmod(target, 0o755)
                except Exception:
                    pass
    else:
        raise RuntimeError(f"不支持的归档类型：{kind}")
