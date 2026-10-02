import os
import json
import time
import threading
import shutil
import yt_dlp
from utils.helpers import safe_filename
import uuid
from utils.helpers import send_windows_notification
from utils import media_extras as mx
from config import normalize_download_path
class DownloadEngine:
    def __init__(self, config, logger, api):
        self.config = config
        self.logger = logger
        self.api = api  # 新增API对象，读取内存cookie
        self.is_running = False
        self.cancel_flag = False
        self.queue = []
        self.status_callbacks = []
        self.progress_callbacks = []
        self.finish_callbacks = []
        self.stop_callbacks = []      # 引擎停止（自然结束或取消）时复位 UI
        self._lock = threading.Lock()
        self._last_progress = {}     # url -> 上次上报的进度（用于节流，避免进度回调刷屏）
        # ---- 任务持久化 / 单任务控制 ----
        self.tasks_file = "tasks.json"
        self._transient_keys = ("_abort", "_files")
        self._engine_stop = threading.Event()   # 全局停止（cancel / 退出）
        self._active_count = 0                  # 正在下载的任务数（worker 池并发控制）
        self._workers = set()                    # 当前批次存活的 worker 线程对象
        self._session_stats = {"completed": 0, "failed": 0, "cancelled": 0, "paused": 0}
        self._session_activity = False
        # 启动时恢复未完成任务（下载中 -> 暂停，等待用户继续）
        self.load_tasks()


    def add_task(self, url, title, duration=0, publish_time="", view_count=0, like_count=0, favorite_count=0, thumbnail="", uploader="", category=""):
        with self._lock:
            for item in self.queue:
                if item["url"] == url:
                    return False
            task = {
                "id": str(uuid.uuid4()),
                "url": url,
                "title": title,
                "status": "waiting",
                "progress": 0,
                "duration": duration,
                "publish_time": publish_time,
                "view_count": view_count,
                "like_count": like_count,
                "favorite_count": favorite_count,
                "thumbnail": thumbnail,
                "uploader": uploader,
                "category": category
            }
            self.queue.append(task)
        self._notify_status()
        return True
    def start(self, max_workers=None):
        """启动 worker 池处理所有『等待中』的任务。

        与旧版『一次性把整队任务铺满线程』不同，这里改为常驻 worker 循环：
        空闲时自动退出（自然结束 / 取消），新任务（继续 / 重试 / 新增）可随时
        唤醒池子，从而支持单任务 暂停/继续/重试 而无需重启整批下载。
        """
        if self.is_running:
            return
        if not any(t.get("status") == "waiting" for t in self.queue):
            self.logger.log("没有等待中的任务（暂停/失败的任务请单独点击继续/重试）")
            return
        ffmpeg = self._get_ffmpeg_path()
        if not ffmpeg:
            # 本地缺失：_get_ffmpeg_path 已触发后台下载，这里登记回调——
            # 下载完成后自动重试 start()，无需用户手动再点一次。
            from utils.ffmpeg_provider import ensure_ffmpeg
            ensure_ffmpeg(self.logger, on_done=lambda path: self.start() if path else None)
            return

        self.is_running = True
        self.cancel_flag = False
        self._engine_stop.clear()
        self._active_count = 0
        self._last_progress.clear()
        self._session_stats = {"completed": 0, "failed": 0, "cancelled": 0, "paused": 0}
        self._session_activity = False
        workers = max_workers or self.config.get("max_workers", 3)
        self._workers = set()
        for _ in range(workers):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            self._workers.add(t)
            t.start()
        self.logger.log(f"启动下载，并行数：{workers}")

    def _worker_loop(self):
        """worker 线程主循环：不断从队列领取『等待中』任务下载，直到空闲或被要求停止。"""
        try:
            while True:
                if self._engine_stop.is_set() or self.cancel_flag:
                    return
                with self._lock:
                    task = next((t for t in self.queue if t.get("status") == "waiting"), None)
                    if task is None:
                        # 没有可领任务：若当前也无正在下载的任务，则本 worker 可以退出
                        if self._active_count == 0:
                            return
                    else:
                        task["status"] = "downloading"
                        self._active_count += 1
                if task is None:
                    time.sleep(0.3)
                    continue
                self._notify_status()
                self._download_one(task)
                with self._lock:
                    self._active_count -= 1
                    still_waiting = any(t.get("status") == "waiting" for t in self.queue)
                    if (self._active_count == 0 and not still_waiting
                            and not self.cancel_flag and not self._engine_stop.is_set()):
                        self._on_all_idle()
        finally:
            with self._lock:
                self._workers.discard(threading.current_thread())
                if not self._workers and self.is_running:
                    self._on_engine_stopped()

    def _on_all_idle(self):
        """所有任务处理完毕（无等待、无下载中），自然结束。"""
        if not self.is_running:
            return
        self.is_running = False
        stats = self._session_stats
        completed, failed, cancelled = stats["completed"], stats["failed"], stats["cancelled"]
        if completed + failed + cancelled > 0:
            self._send_notification(completed, failed, cancelled)
            for cb in self.finish_callbacks:
                try:
                    cb(completed, failed, cancelled)
                except Exception as e:
                    self.logger.log(f"完成回调错误：{str(e)}")
        else:
            # 无实际下载活动（例如全部被暂停）：仅复位 UI，不弹完成提示
            for cb in self.stop_callbacks:
                try:
                    cb()
                except Exception as e:
                    self.logger.log(f"停止回调错误：{str(e)}")

    def _on_engine_stopped(self):
        """worker 池全部退出（通常是用户取消 / 程序退出）。复位 UI，但不弹完成提示。"""
        if not self.is_running:
            return
        self.is_running = False
        for cb in self.stop_callbacks:
            try:
                cb()
            except Exception as e:
                self.logger.log(f"停止回调错误：{str(e)}")

    def _record_result(self, result):
        with self._lock:
            if result in self._session_stats:
                self._session_stats[result] += 1
            if result in ("completed", "failed", "cancelled"):
                self._session_activity = True
    def _send_notification(self, completed, failed, cancelled):
        """发送下载完成通知"""
        # 构建通知内容
        title = "🎬 B站下载器 - 下载完成"
        
        if cancelled > 0:
            status = f"✅ 成功: {completed} 个\n❌ 失败: {failed} 个\n⏹️ 取消: {cancelled} 个"
        else:
            status = f"✅ 成功: {completed} 个"
            if failed > 0:
                status += f"\n❌ 失败: {failed} 个"
        
        # 添加下载路径信息
        download_path = self.config.get("download_path", "")
        status += f"\n📂 {download_path}"
        
        # 发送通知（显示8秒）
        send_windows_notification(title, status, duration=8)
    def add_tasks_batch(self, tasks):
        """tasks: list of (url, title, duration, publish_time, view_count, like_count,
        favorite_count, thumbnail, uploader, category?)"""
        with self._lock:
            added = 0
            for task_data in tasks:
                url = task_data[0]
                exists = any(item["url"] == url for item in self.queue)
                if not exists:
                    task = {
                        "id": str(uuid.uuid4()),
                        "url": url,
                        "title": task_data[1],
                        "status": "waiting",
                        "progress": 0,
                        "duration": task_data[2] if len(task_data) > 2 else 0,
                        "publish_time": task_data[3] if len(task_data) > 3 else "",
                        "view_count": task_data[4] if len(task_data) > 4 else 0,
                        "like_count": task_data[5] if len(task_data) > 5 else 0,
                        "favorite_count": task_data[6] if len(task_data) > 6 else 0,
                        "thumbnail": task_data[7] if len(task_data) > 7 else "",
                        "uploader": task_data[8] if len(task_data) > 8 else "",
                        "category": task_data[9] if len(task_data) > 9 else ""
                    }
                    self.queue.append(task)
                    added += 1
        if added > 0:
            self._notify_status()
        return added

    def _get_ffmpeg_path(self):
        """返回配置的FFmpeg路径；留空时优先使用同目录 bin/ffmpeg.exe，否则在 PATH 中查找。

        本地 bin/ 缺失时由 utils.ffmpeg_provider 后台下载（首次使用），下载期间返回 None。
        """
        import shutil
        config_path = self.config.get("ffmpeg_path", "").strip()
        # 1) 用户明确填写了有效路径 -> 直接使用（最高优先级）
        if config_path and os.path.isfile(config_path) and os.access(config_path, os.X_OK):
            return os.path.abspath(config_path)
        # 2) 留空 -> 优先本地 bin/ffmpeg.exe；缺失则触发运行时下载
        from utils.ffmpeg_provider import ensure_ffmpeg
        local = ensure_ffmpeg(self.logger)
        if local:
            return os.path.abspath(local)
        # 3) 兜底：在系统 PATH 中查找
        found = shutil.which("ffmpeg")
        if found:
            return os.path.abspath(found)
        return None

    def _build_format(self, quality):
        """根据清晰度与「音画分离」开关构建 yt-dlp format 字符串。

        - 默认：使用配置里的合并规则（bestvideo+bestaudio 自动合并为单文件）。
        - 音画分离：将合并符 '+' 改为逗号，使视频流与音频流分别下载为独立文件，
          且不再设置 merge_output_format，从而保留两个独立文件供单独使用。
        """
        import re
        # 仅音频：直接取最佳音频流
        if self.config.get("audio_only", False):
            target = mx.audio_format_ext(self.config.get("audio_format", ""))
            if target in ("m4a", "mp3", "opus"):
                # 优先挑选同容器的音频流，可以省掉一次转码
                return f"bestaudio[ext={target}]/bestaudio/best"
            return "bestaudio/best"
        rule = self.config.get_quality_rule(quality)
        if self.config.get("audio_video_separate", False):
            h = "1080"
            m = re.search(r"height<=(\d+)", rule)
            if m:
                h = m.group(1)
            vf = ""
            mc = re.search(r"\[(vcodec\^=\w+)\]", rule)
            if mc:
                vf = "[" + mc.group(1) + "]"
            af = ""
            ma = re.search(r"\[(acodec\^=\w+)\]", rule)
            if ma:
                af = "[" + ma.group(1) + "]"
            # 逗号分隔 = 两个独立文件，不合并
            return f"bestvideo[height<={h}]{vf},bestaudio{af}/bestvideo,bestaudio/best"
        return rule

    def _build_sub_langs(self):
        """组装 yt-dlp 的 subtitleslangs。

        B 站在 yt-dlp 中把弹幕暴露成名为 ``danmaku`` 的字幕轨（原始 XML），
        真正的 CC / AI 字幕则是 ``zh-Hans`` / ``ai-zh`` / ``en`` 等语言轨。
        因此两者虽然共用同一套开关，但语言列表要分开拼。
        """
        langs = []
        want_danmaku = self.config.get("download_danmaku", True)
        want_sub = self.config.get("download_subtitle", False)

        if want_sub:
            lang_opt = self.config.get("subtitle_lang", "全部语言")
            if lang_opt == "仅中文":
                langs += ["zh.*", "ai-zh"]
            elif lang_opt == "仅英文":
                langs += ["en.*", "ai-en"]
            else:
                # all 会把 danmaku 也带上，不需要弹幕时显式排除
                langs.append("all")
                if not want_danmaku:
                    langs.append("-danmaku")

        if want_danmaku and "all" not in langs:
            langs.append("danmaku")
        return langs

    def _post_process(self, task, out_dir, safe_title, ffmpeg_path=None):
        """下载结束后处理附加产物：弹幕/字幕格式转换、生成 NFO、分离音频转码。"""
        cfg = self.config
        files = mx.list_outputs(out_dir, safe_title)
        title = task.get("title", "")

        # ---- 1. 弹幕：yt-dlp 落盘的是 *.danmaku.xml ----
        if cfg.get("download_danmaku", True):
            fmt = (cfg.get("danmaku_format", "xml") or "xml").lower()
            if fmt in ("ass", "json"):
                for path in files:
                    if not path.endswith(".danmaku.xml"):
                        continue
                    text = mx.read_text(path)
                    if not text:
                        continue
                    content = (mx.danmaku_to_ass(text, title) if fmt == "ass"
                               else mx.danmaku_to_json(text))
                    new_path = path[:-len("xml")] + fmt
                    if mx.write_text(new_path, content) and new_path != path:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                        self.logger.log(f"弹幕已转换为 {fmt}：{os.path.basename(new_path)}")

        # ---- 2. 字幕：yt-dlp 已把 B 站 JSON 字幕转成 *.<lang>.srt ----
        if cfg.get("download_subtitle", False):
            fmt = (cfg.get("subtitle_format", "srt") or "srt").lower()
            if fmt != "srt":
                for path in files:
                    if not path.endswith(".srt") or ".danmaku." in os.path.basename(path):
                        continue
                    text = mx.read_text(path)
                    if not text:
                        continue
                    content, ext = mx.convert_subtitle(text, fmt, title)
                    new_path = path[:-len("srt")] + ext
                    if mx.write_text(new_path, content) and new_path != path:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                        self.logger.log(f"字幕已转换为 {ext}：{os.path.basename(new_path)}")

        # ---- 3. 元数据：json 保留 info.json；nfo 由 info.json + 任务信息生成 ----
        if cfg.get("download_metadata", False):
            meta_fmt = (cfg.get("metadata_format", "json") or "json").lower()
            info_path = os.path.join(out_dir, f"{safe_title}.info.json")
            if meta_fmt == "nfo":
                info = {}
                if os.path.isfile(info_path):
                    try:
                        with open(info_path, "r", encoding="utf-8") as f:
                            info = json.load(f)
                    except (OSError, ValueError):
                        info = {}
                nfo_path = os.path.join(out_dir, f"{safe_title}.nfo")
                if mx.write_text(nfo_path, mx.build_nfo(task, info)):
                    self.logger.log(f"已生成元数据：{os.path.basename(nfo_path)}")
                # nfo 模式下 info.json 只是中间产物
                if os.path.isfile(info_path):
                    try:
                        os.remove(info_path)
                    except OSError:
                        pass

        # ---- 4. 音画分离模式下，把独立的音频文件转成用户选择的格式 ----
        if cfg.get("audio_video_separate", False) and not cfg.get("audio_only", False):
            target_ext = mx.audio_format_ext(cfg.get("audio_format", ""))
            if target_ext:
                bitrate = str(cfg.get("audio_bitrate", "192k"))
                for item in task.get("_files", []):
                    path = item.get("path")
                    if not path or item.get("vcodec") not in (None, "none"):
                        continue
                    if os.path.splitext(path)[1].lstrip(".").lower() not in mx.AUDIO_EXTS:
                        continue
                    new_path = mx.convert_audio(path, target_ext, ffmpeg_path, bitrate)
                    if new_path:
                        self.logger.log(f"音频已转换为 {target_ext}：{os.path.basename(new_path)}")
                    else:
                        self.logger.log(f"音频转换为 {target_ext} 失败，已保留原文件")

    def _resolve_conflict_title(self, out_dir, safe_title):
        """依据 settings 的『同名文件处理』决定最终文件名基名。

        - overwrite：保持原名，由 yt-dlp 的 force_overwrites 覆盖写入；
        - auto_rename：若已存在同名（任意常见扩展名）文件，自动追加 ' (n)'
          直到不冲突（bili23 的 FileConflictResolution.AUTO_RENAME 同款行为）。
        返回一个（可能与入参不同的）新的 safe_title 基名。
        """
        if not out_dir or not os.path.isdir(out_dir):
            return safe_title
        mode = self.config.get("file_conflict_resolution", "auto_rename")
        if mode != "auto_rename":
            return safe_title
        exts = ["mp4", "mkv", "webm", "m4a", "jpg", "png", "webp",
                "avif", "json", "srt", "ass", "nfo", "xml", "vtt"]
        exists = lambda name: any(
            os.path.exists(os.path.join(out_dir, f"{name}.{e}")) for e in exts)
        if not exists(safe_title):
            return safe_title
        n = 1
        while True:
            cand = f"{safe_title} ({n})"
            if not exists(cand):
                self.logger.log(f"同名文件已存在，自动重命名为：{cand}")
                return cand
            n += 1

    def _delete_embedded_cover(self, idx, out_dir, safe_title, separate):
        """内嵌封面后，按设置删除原封面文件（仅 embed_cover 且非音画分离时生效）。"""
        if separate:
            return
        if not self.config.get("embed_cover", False):
            return
        if not self.config.get("download_cover", True):
            return
        if not self.config.get("delete_cover_after_attach", False):
            return
        cover_ext = (self.config.get("cover_type", "jpg") or "jpg").lower()
        cover_path = os.path.join(out_dir, f"{safe_title}.{cover_ext}")
        if os.path.isfile(cover_path):
            try:
                os.remove(cover_path)
                self.logger.log(f"[{idx+1}] 已内嵌封面并删除原封面文件：{os.path.basename(cover_path)}")
            except OSError as e:
                self.logger.log(f"[{idx+1}] 删除原封面文件失败：{e}")

    def _classify_folder(self, task):
        """根据链接 / 来源标签推断应归属的『视频种类』子目录名。

        返回空串表示不分文件夹（平铺到下载根目录）。
        """
        from utils.bili_classify import classify_bili_kind, safe_kind
        kind = classify_bili_kind(task.get("url", ""), task.get("category", ""))
        return safe_kind(kind)

    def _download_one(self, task):
        """下载单个任务（worker 池调用）。

        - 暂停（task["_abort"] 置位）：中止 yt-dlp 并保留 .part 断点，状态置为 paused，
          任务保留在队列，可后续『继续』从断点续传。
        - 全局取消（cancel_flag）：状态置为 cancelled（保留在队列，可重试）。
        - 普通异常：状态置为 failed（保留在队列，可『重试』断点续传）。
        """
        result = "completed"  # 默认
        try:
            aborted = self._is_aborted(task)
            if self.cancel_flag or aborted:
                # 任务在开始前被取消/暂停：直接置为对应状态，不进入下载
                if self.cancel_flag and not aborted:
                    task["status"] = "cancelled"
                    result = "cancelled"
                else:
                    task["status"] = "paused"
                    result = "paused"
                self._notify_status()
                return

            task["status"] = "downloading"
            self._notify_status()
            self.logger.log(f"开始下载：{task['title']}")

            quality = self.config.get("quality", "1080p")
            separate = self.config.get("audio_video_separate", False)
            audio_only = self.config.get("audio_only", False)
            quality_rule = self._build_format(quality)
            base_dir = self.config.get("download_path")
            # 兜底：归一到当前用户可用、可写的目录，避免跨电脑/跨用户时
            # settings.json 残留的旧用户名路径导致下载失败。
            base_dir = normalize_download_path(base_dir)
            self.config.config["download_path"] = base_dir

            # ---- 按视频种类自动分文件夹 ----
            # create_folder（默认开）：在下载根目录下建 <种类>/ 子目录，
            # 例如 视频/ 番剧/ 直播/ 音频/ 等。关闭则全部平铺到根目录（旧行为）。
            folder = ""
            if self.config.get("create_folder", True):
                folder = self._classify_folder(task)
            out_dir = os.path.join(base_dir, folder) if folder else base_dir
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception:
                pass
            # 记录实际落盘目录，供『打开文件夹』等功能定位
            # （queue_view._open_location 已支持 task["folder"] / task["download_path"]）
            task["download_path"] = out_dir
            task["folder"] = folder

            safe_title = self._resolve_conflict_title(
                out_dir, safe_filename(task["title"]))
            out_template = os.path.join(out_dir, f"{safe_title}.%(ext)s")
            task["_files"] = []   # 记录本次产出的媒体文件，供后处理使用

            opts = {
                "format": quality_rule,
                "outtmpl": out_template,
                "quiet": True,
                "no_warnings": True,
                "continue": True,            # 断点续传：存在 .part 时从断点继续
                "retries": 3,                # 网络抖动自动重试（与用户手动『重试』互补）
                "fragment_retries": 3,
                "progress_hooks": [lambda d: self._progress_hook(d, task)],
                "cookiefile": "cookies.txt" if os.path.exists("cookies.txt") else None,
            }
            # ---- 下载限速：单位 KB/s，0 表示不限（yt-dlp 的 ratelimit 单位为字节/秒）----
            try:
                limit = int(self.config.get("download_limit", 0) or 0)
            except (TypeError, ValueError):
                limit = 0
            if limit > 0:
                opts["ratelimit"] = limit * 1024
            # 后处理器需按「抽取音频 -> 写元数据 -> 嵌封面」的顺序执行
            pp_audio, pp_meta, pp_thumb = [], [], []
            # 音画分离 / 仅音频：不做合并，保留独立文件
            if not separate and not audio_only:
                opts["merge_output_format"] = self.config.get("merge_format", "mp4")
            ffmpeg_path = self._get_ffmpeg_path()
            if ffmpeg_path:
                opts["ffmpeg_location"] = ffmpeg_path
            # 同名文件处理：overwrite 模式交给 yt-dlp 强制覆盖；
            # auto_rename 已在上方通过修改 safe_title 规避冲突。
            if self.config.get("file_conflict_resolution", "auto_rename") == "overwrite":
                opts["force_overwrites"] = True
            cookie_dict = {}
            if self.api.SESSDATA and self.api.bili_jct:
                cookie_dict["SESSDATA"] = self.api.SESSDATA
                cookie_dict["bili_jct"] = self.api.cookies.get("buvid3", "")
                cookie_dict["buvid4"] = self.api.cookies.get("buvid4", "")
                cookie_dict["DedeUserID"] = self.api.uid
                opts["cookies_from_dict"] = cookie_dict
            elif os.path.exists("cookies.txt"):
                opts["cookiefile"] = "cookies.txt"

            # ---- 弹幕 / 字幕：都走 yt-dlp 的字幕轨，danmaku 是 B 站专属轨道 ----
            sub_langs = self._build_sub_langs()
            if sub_langs:
                opts["writesubtitles"] = True
                opts["subtitleslangs"] = sub_langs

            # ---- 元数据 ----
            meta_fmt = (self.config.get("metadata_format", "json") or "json").lower()
            want_meta = self.config.get("download_metadata", False)
            if want_meta:
                if meta_fmt.startswith("内嵌"):
                    pp_meta.append({"key": "FFmpegMetadata",
                                    "add_metadata": True, "add_chapters": True})
                else:
                    # json 直接留用 info.json；nfo 也先取 info.json 作为素材，之后再删
                    opts["writeinfojson"] = True

            # ---- 封面 ----
            if self.config.get("download_cover", True):
                opts["writethumbnail"] = True
                # 内嵌封面（音画分离时视频/音频各自独立，不做内嵌）
                # 注意：embedthumbnail 只是命令行开关，API 侧必须显式挂后处理器
                if self.config.get("embed_cover", False) and not separate:
                    pp_thumb.append({"key": "EmbedThumbnail",
                                     "already_have_thumbnail": True})

            # ---- 仅音频时的转码交给 yt-dlp 的抽取器 ----
            if audio_only:
                target_ext = mx.audio_format_ext(self.config.get("audio_format", ""))
                if target_ext:
                    pp = {"key": "FFmpegExtractAudio", "preferredcodec": target_ext}
                    bitrate = str(self.config.get("audio_bitrate", "192k")).rstrip("kK")
                    if target_ext in ("mp3", "aac", "m4a", "opus") and bitrate.isdigit():
                        pp["preferredquality"] = bitrate
                    pp_audio.append(pp)

            postprocessors = pp_audio + pp_meta + pp_thumb
            if postprocessors:
                opts["postprocessors"] = postprocessors

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([task["url"]])

            # ---- 下载完成后统一处理附加文件（格式转换 / NFO / 音频转码）----
            aborted = self._is_aborted(task)
            if self.cancel_flag:
                task["status"] = "cancelled"
                result = "cancelled"
            elif aborted:
                task["status"] = "paused"
                result = "paused"
            else:
                self.logger.log(f"下载完成：{task['title']}")
                try:
                    self._post_process(task, out_dir, safe_title, ffmpeg_path)
                except Exception as e:
                    self.logger.log(f"附加内容处理失败：{str(e)}")
                # 内嵌封面后，按设置删除原封面文件
                self._delete_embedded_cover(-1, out_dir, safe_title, separate)
                # ✅ 下载完成：从队列中移除任务
                with self._lock:
                    for i, item in enumerate(self.queue):
                        if item["url"] == task["url"]:
                            del self.queue[i]
                            break
                task["status"] = "completed"
                result = "completed"
            self._notify_status()  # 通知 UI 更新
        except Exception as e:
            aborted = self._is_aborted(task)
            if self.cancel_flag and not aborted:
                task["status"] = "cancelled"
                result = "cancelled"
            elif aborted:
                task["status"] = "paused"
                result = "paused"
            else:
                task["status"] = "failed"
                result = "failed"
                self.logger.log(f"下载失败：{str(e)}")
            self._notify_status()
        finally:
            self._record_result(result)

    def _is_aborted(self, task):
        """任务是否被用户暂停。注意 _abort 是 threading.Event，必须用 is_set() 判断，
        直接 bool(task.get("_abort")) 会永远为 True（Event 对象本身为真）。"""
        evt = task.get("_abort")
        return bool(evt and evt.is_set())

    def _progress_hook(self, data, task):
        if self.cancel_flag or self._is_aborted(task):
            raise Exception("用户取消")
        try:
            url = task.get("url", "")
            if data["status"] == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate", 0)
                down = data.get("downloaded_bytes", 0)
                speed = data.get("speed", 0)
                percent = down / total if total > 0 else 0
                task["progress"] = percent
                # 节流：进度变化 >=2% 才上报，避免高频刷新 UI
                last = self._last_progress.get(url, -1)
                if abs(percent - last) >= 0.02 or last < 0:
                    self._last_progress[url] = percent
                    for cb in self.progress_callbacks:
                        try:
                            cb(url, percent, speed)
                        except Exception:
                            pass
            elif data["status"] == "finished":
                # 记录本次落盘的媒体文件，音画分离时靠 vcodec 区分音频流
                info = data.get("info_dict") or {}
                file_path = data.get("filename") or info.get("filepath")
                if file_path:
                    task.setdefault("_files", []).append({
                        "path": file_path,
                        "vcodec": info.get("vcodec"),
                        "acodec": info.get("acodec"),
                    })
                task["progress"] = 1.0
                self._last_progress[url] = 1.0
                for cb in self.progress_callbacks:
                    try:
                        cb(url, 1.0, 0)
                    except Exception:
                        pass
        except Exception:
            pass

    def cancel(self):
        """全局取消：中止所有正在进行的下载与等待中的任务（worker 池随后退出）。"""
        self.cancel_flag = True
        self._engine_stop.set()
        self.logger.log("正在取消所有下载...")

    # ---------- 单任务控制 ----------
    def pause_task(self, url):
        """暂停单个任务：正在下载的会中止并保留断点（.part），等待中的直接置为暂停。"""
        changed = False
        with self._lock:
            for t in self.queue:
                if t.get("url") == url:
                    if t["status"] == "downloading":
                        t.setdefault("_abort", threading.Event()).set()
                        # 状态由 _download_one 在中断后改为 paused
                    elif t["status"] == "waiting":
                        t["status"] = "paused"
                        changed = True
                    break
        if changed:
            self._notify_status()

    def resume_task(self, url):
        """继续 / 重试单个任务：清除暂停标记，置为等待，并唤醒 worker 池。"""
        with self._lock:
            t = next((x for x in self.queue if x.get("url") == url), None)
            if t is None:
                return
            t["_abort"] = threading.Event()
            if t["status"] in ("paused", "failed", "cancelled", "waiting"):
                t["status"] = "waiting"
        self._notify_status()
        self.start()

    def retry_task(self, url):
        """重试失败 / 取消的任务（断点续传）。"""
        self.resume_task(url)

    # ---------- 任务持久化 ----------
    def save_tasks(self):
        """将队列（剥离瞬态字段）原子写入 tasks.json，供下次启动恢复。"""
        try:
            data = []
            with self._lock:
                for t in self.queue:
                    item = {k: v for k, v in t.items()
                            if not k.startswith("_") and k not in self._transient_keys}
                    if item:
                        data.append(item)
            tmp = self.tasks_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.tasks_file)
        except Exception as e:
            self.logger.log(f"保存任务失败：{str(e)}")

    def load_tasks(self):
        """启动时从 tasks.json 恢复未完成任务；下载中 -> 暂停（线程已不在）。"""
        try:
            if not os.path.exists(self.tasks_file):
                return
            with open(self.tasks_file, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return
            with self._lock:
                self.queue = []
                for t in data:
                    if not isinstance(t, dict) or not t.get("url"):
                        continue
                    t.setdefault("status", "waiting")
                    t.setdefault("progress", 0)
                    t.setdefault("id", str(uuid.uuid4()))
                    # 进程已退出，原『下载中』不再是活跃状态 -> 暂停，等待用户继续
                    if t["status"] == "downloading":
                        t["status"] = "paused"
                    # 清理可能残留的瞬态字段
                    for k in list(t.keys()):
                        if k.startswith("_") or k in self._transient_keys:
                            del t[k]
                    self.queue.append(t)
            if self.queue:
                self.logger.log(f"已恢复 {len(self.queue)} 个任务（下载中已转为暂停）")
        except Exception as e:
            self.logger.log(f"恢复任务失败：{str(e)}")

    def _notify_status(self):
        self.save_tasks()
        for cb in self.status_callbacks[:]:
            try:
                cb(self.queue)
            except Exception as e:
                self.logger.log(f"状态回调错误：{str(e)}")
