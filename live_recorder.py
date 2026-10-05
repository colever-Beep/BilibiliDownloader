import subprocess
import os
import threading
import time
import re

from utils.helpers import safe_filename, resolve_filename_collision, send_windows_notification
from config import normalize_download_path


class LiveRecorder:
    """直播录制器（参照视频下载引擎的成熟基础设施重写）。

    与旧版差异（对齐 download_engine.py 的做法）：
    1. ffmpeg 不再强依赖系统 PATH，而是走 ``utils.ffmpeg_provider.ensure_ffmpeg``：
       本地 bin/ 优先，缺失则后台下载（约 80MB，下载完自动开始），与「视频下载」一致。
    2. 输出文件名用 safe_filename 清洗 + file_conflict_resolution（auto_rename）处理同名，
       并带「标题 + 时间戳」，与下载产物命名规则一致。
    3. 断流自动重连时通过 ``refetch`` 回调重新获取「新鲜」流地址（直播 URL 约几分钟即过期），
       而不是盲目复用早已失效的旧地址。
    4. 开始 / 停止 / 自动重连 时发送 Windows 原生通知（与下载完成通知同款体验）。
    """

    def __init__(self, config=None, output_dir=None, logger=None):
        self.config = config
        # 日志器：由调用方传入（与下载引擎一致），未传则为 None（静默）
        self.logger = logger
        # output_dir 优先级：显式传入 > 配置 download_path > 当前目录
        if output_dir:
            self.output_dir = output_dir
        elif config is not None:
            self.output_dir = normalize_download_path(
                config.get("download_path")) or os.getcwd()
        else:
            self.output_dir = os.getcwd()
        # 是否用户显式指定了目录：仅当使用默认（配置 download_path）时才自动归类子目录，
        # 避免覆盖用户在录制对话框里手动选择的路径。
        self._explicit_dir = bool(output_dir)
        self.proc = None
        self.thread = None
        self.running = False
        self.stop_requested = False
        self.current_outpath = None
        self.ffmpeg_path = None
        self._thread_started = False

    def _resolve_out_dir(self):
        out = self.output_dir or os.getcwd()
        # 按视频种类分文件夹：直播统一归入『直播』子目录
        # （仅当用户未自定义目录、且开启 create_folder 时生效）
        if (self.config is not None
                and self.config.get("create_folder", True)
                and not self._explicit_dir):
            out = os.path.join(out, "直播")
        try:
            os.makedirs(out, exist_ok=True)
        except Exception:
            pass
        return out

    def _default_ext(self):
        """录制封装格式对应的文件扩展名（来自「直播录制封装格式」设置）。"""
        fmt = "mp4"
        if self.config is not None:
            fmt = self.config.get("live_record_format", "mp4") or "mp4"
        return f".{fmt}" if fmt else ".mp4"

    def _make_outpath(self, filename):
        """生成最终输出路径：safe_filename + 同名冲突处理（auto_rename）。

        filename 为空时自动生成 ``标题_时间戳.mp4``（标题由调用方通过 filename 传入）。
        """
        out_dir = self._resolve_out_dir()
        if not filename:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"live_record_{timestamp}{self._default_ext()}"
        base, ext = os.path.splitext(filename)
        base = safe_filename(base)
        ext = (ext or "").lower()
        if ext not in (".mp4", ".mkv", ".flv", ".ts"):
            ext = ".mp4"
        mode = "auto_rename"
        if self.config is not None:
            mode = self.config.get("file_conflict_resolution", "auto_rename") or "auto_rename"
        if mode == "auto_rename":
            base, _ = resolve_filename_collision(out_dir, base, (ext,))
        return os.path.join(out_dir, base + ext)

    def _build_segment_name(self, title_hint=None):
        """断流重连后生成新的分段文件名（带时间戳，避免覆盖上一段）。"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        prefix = safe_filename(title_hint) if title_hint else "live_record"
        return f"{prefix}_{timestamp}{self._default_ext()}"

    def start(self, stream_url, filename=None, auto_reconnect=True, refetch=None,
              title_hint=None):
        """开始录制。

        - stream_url: 首个片段使用的流地址（通常由对话框选中的清晰度决定）。
        - refetch: 断流重连时调用的回调，返回「新鲜」流地址（或 None 表示复用旧地址）。
        - title_hint: 用于自动生成文件名 / 分段名（一般传主播名或房间标题）。
        """
        if self.is_recording():
            raise RuntimeError("已在录制中")
        if not filename:
            prefix = safe_filename(title_hint) if title_hint else "live_record"
            filename = f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}{self._default_ext()}"
        outpath = self._make_outpath(filename)
        self.current_outpath = outpath
        self.stop_requested = False
        self.running = True
        self._thread_started = False
        self._pending = (stream_url, outpath, auto_reconnect, refetch, title_hint)

        # ---- ffmpeg 解析：弹窗让用户选择「联网下载 / 手动放入」，下载完成后回调 _begin ----
        from PySide6.QtWidgets import QApplication
        from ui.ffmpeg_dialog import ensure_ffmpeg_prompted
        parent = QApplication.activeWindow()
        ok = ensure_ffmpeg_prompted(self.logger, on_done=self._begin, parent=parent)
        # ensure_ffmpeg_prompted 会在已存在或下载就绪时回调 on_done（即 _begin）；
        # 用户选择手动放入则返回 False，录制挂起等待其放入 ffmpeg 后再次点击。
        return outpath

    def _begin(self, ffmpeg_path):
        """ffmpeg 就绪后真正启动录制线程（可能被 ensure_ffmpeg 的回调异步触发）。"""
        if not self.running or self.stop_requested:
            return
        if self._thread_started:
            return
        self._thread_started = True
        self.ffmpeg_path = ffmpeg_path
        self.thread = threading.Thread(
            target=self._record_loop, args=self._pending, daemon=True)
        self.thread.start()
        name = os.path.basename(self.current_outpath or "")
        self.logger and self.logger.log(f"开始录制直播：{name}")
        send_windows_notification(
            "🎬 B站下载器 - 直播录制",
            f"开始录制：{name}\n📂 {os.path.dirname(self.current_outpath or '')}",
            duration=4)

    def _build_ffmpeg_cmd(self, stream_url, outpath):
        """根据「直播录制编码」设置构建 ffmpeg 命令。

        - copy : 原始流直接封装（CPU 占用最低；HEVC/AV1 源在部分播放器
                 会提示「解码不受支持」）。
        - h264 : 实时转码为 H.264（兼容性最好，CPU 占用较高）。
        - h265 : 实时转码为 H.265（体积更小，需播放器支持 HEVC）。

        另加 ``-loglevel error``：ffmpeg 会持续向 stderr 刷进度行，而录制线程
        并不消费 PIPE；长录制时 PIPE 缓冲区写满会导致 ffmpeg 卡死，error 级别
        日志量极小，可安全保留 PIPE 用于排错。
        """
        codec = "copy"
        if self.config is not None:
            codec = self.config.get("live_record_codec", "copy") or "copy"
        cmd = [self.ffmpeg_path, "-y", "-loglevel", "error", "-i", stream_url]
        if codec == "h264":
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "160k"]
        elif codec == "h265":
            cmd += ["-c:v", "libx265", "-preset", "veryfast", "-crf", "26",
                    "-c:a", "aac", "-b:a", "160k"]
        else:
            cmd += ["-c", "copy"]
        cmd.append(outpath)
        return cmd

    def _record_loop(self, stream_url, outpath, auto_reconnect, refetch, title_hint):
        current_url = stream_url
        while self.running and not self.stop_requested:
            try:
                cmd = self._build_ffmpeg_cmd(current_url, outpath)
                self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.PIPE)
                self.proc.wait()
                if self.proc.returncode not in (0, None) and not self.stop_requested:
                    # ffmpeg 非 0 退出：读取 error 级日志帮助定位（编码器缺失、
                    # 流地址失效等），避免静默失败。
                    try:
                        err = (self.proc.stderr.read() or b"").decode(
                            "utf-8", "replace").strip()
                    except Exception:
                        err = ""
                    self.logger and self.logger.log(
                        f"ffmpeg 退出码 {self.proc.returncode}：{err[-500:]}")
                if self.stop_requested or not self.running:
                    break
                if auto_reconnect:
                    # ---- 重新获取新鲜流地址（直播 URL 会过期）----
                    new_url = None
                    if callable(refetch):
                        try:
                            new_url = refetch()
                        except Exception as e:
                            self.logger and self.logger.log(f"重连获取流地址失败：{e}")
                            new_url = None
                    if not new_url:
                        new_url = current_url  # 兜底：沿用旧地址
                    current_url = new_url
                    # 新分段文件（带时间戳，避免覆盖上一段）
                    outpath = self._make_outpath(
                        self._build_segment_name(title_hint))
                    self.current_outpath = outpath
                    self.logger and self.logger.log(f"直播中断，尝试重连，新文件：{os.path.basename(outpath)}")
                    send_windows_notification(
                        "🎬 B站下载器 - 直播录制",
                        f"直播中断，自动重连中…\n📄 {os.path.basename(outpath)}",
                        duration=4)
                    time.sleep(3)
                else:
                    break
            except Exception as e:
                if self.stop_requested or not self.running:
                    break
                self.logger and self.logger.log(f"录制异常：{e}")
                if auto_reconnect:
                    time.sleep(3)
                else:
                    break

    def stop(self):
        self.stop_requested = True
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        name = os.path.basename(self.current_outpath or "")
        self.logger and self.logger.log(f"已停止录制：{name}")
        send_windows_notification(
            "🎬 B站下载器 - 直播录制",
            f"已停止录制：{name}",
            duration=4)

    def is_recording(self):
        return self.running and (self.proc is None or self.proc.poll() is None)
