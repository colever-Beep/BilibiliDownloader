"""FFmpeg 供应器：本地优先，缺失则运行时下载（官方构建），并支持手动回退。

设计目标（与「两者都要」需求一致）：
1. 本地优先：同目录 bin/ffmpeg.exe（开发态为项目根 bin/；冻结后为 exe 所在目录 bin/）。
2. 缺失则后台下载：首次用到时从 BtbN 官方 Windows 构建下载 zip，解压 bin/ 下的
   ffmpeg.exe / ffprobe.exe / ffplay.exe 到本地 bin/，之后离线可用。
3. 手动回退：用户也可自行把 ffmpeg.exe 放进 bin/（或「设置」里指定绝对路径），优先级最高。

冻结（PyInstaller onefile）说明：
- 程序文件位于 _MEIPASS 临时目录（只读、退出即清），不能把下载的 ffmpeg 写回那里；
  因此冻结态一律写到 sys.executable 所在目录的 bin/ 下。
"""
import os
import sys
import zipfile
import shutil
import threading

try:
    import requests
except Exception:  # requests 缺失时允许「手动回退」路径仍可用
    requests = None

# BtbN 官方构建（含 ffmpeg / ffprobe / ffplay）。latest 标签稳定可用。
_DOWNLOAD_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

_lock = threading.Lock()
_in_progress = False          # 是否已有下载在进行
_callbacks = []              # 下载结束时要回调的 on_done(path_or_None) 列表


def get_ffmpeg_dir():
    """返回 bin/ 目录的绝对路径（与 get_bundled_ffmpeg_path 约定一致）。"""
    if getattr(sys, "frozen", False):
        # 冻结态：写到 exe 所在目录的 bin/（_MEIPASS 只读且会被清理）
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "bin")
    # 开发态：本文件在 utils/，项目根 = 上级目录
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")


def get_ffmpeg_path():
    return os.path.join(get_ffmpeg_dir(), "ffmpeg.exe")


def is_available():
    p = get_ffmpeg_path()
    return os.path.isfile(p) and os.access(p, os.X_OK)


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
        logger.log("首次使用需下载 ffmpeg（约 80MB），将在后台下载，完成后自动继续…")
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
        bin_dir = get_ffmpeg_dir()
        os.makedirs(bin_dir, exist_ok=True)
        if requests is None:
            raise RuntimeError("缺少 requests 库，无法自动下载 ffmpeg（请手动放入 bin/）")
        if logger:
            logger.log("开始下载 ffmpeg…")
        resp = requests.get(_DOWNLOAD_URL, stream=True, timeout=30)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0)) or 0
        downloaded = 0
        last_pct = -1
        tmp = get_ffmpeg_path() + ".download.tmp"
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
        _extract(tmp, bin_dir)
        try:
            os.remove(tmp)
        except Exception:
            pass
        if is_available():
            if logger:
                logger.log("ffmpeg 下载完成 ✅（已保存到 bin/，下次启动免下载）")
            _fire(get_ffmpeg_path())
        else:
            raise RuntimeError("解压后未在 bin/ 中找到 ffmpeg.exe")
    except Exception as e:
        if logger:
            logger.log(f"ffmpeg 自动下载失败：{e}；可将 ffmpeg.exe 手动放入 bin/ 后重试")
        _fire(None)
    finally:
        with _lock:
            _in_progress = False


def _extract(zip_path, bin_dir):
    """从 ffmpeg 官方 zip 中提取 bin/ 子目录下的所有 .exe 到本地 bin_dir。

    BtbN / gyan 的 zip 顶层均为『发布名/bin/xxx.exe』结构。
    """
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            norm = name.replace("\\", "/")
            if "/bin/" not in norm:
                continue
            base = os.path.basename(name)
            if not base.endswith(".exe"):
                continue
            target = os.path.join(bin_dir, base)
            with z.open(name) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
