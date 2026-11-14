"""百宝箱（设置 -> 高级）：三个与下载主流程无关的娱乐小功能。

- **自定义链接下载**：用 yt-dlp 下载任意链接（不限 B 站），跑在独立线程里，
  自带进度条与日志；不占用主下载引擎的 worker、不进主下载队列，与下载器解耦。
- **今日人品**：PCL 启动器同款——按「名字 + 日期」哈希出 0~100 的分数，
  同一天、同一名字结果固定，跨天自动刷新。
- **千万别点**：PCL 启动器同款——点一次按钮跑一次，文案逐级升级，
  点到第 8 次给一颗彩蛋（今日人品 +5）。

约定（与设置窗口 / 下载选项窗口一致）：
- 可见静态文本一律 ``tr()`` 包裹（且必须是字面量，否则脚本抽不到）；
  配置值（``best`` / ``1080p`` / ``audio``）只作内部存储值，绝不翻译；
- 后台线程一律 ``utils.main_thread.run_on_main`` 回主线程刷 UI；
- 弹窗骨架复用 ``ui.fluent_dialog.FluentContentDialog``（标题栏 + 内容区 + 按钮排）。
"""
from __future__ import annotations

import getpass
import hashlib
import os
import random
import threading
from datetime import date

import yt_dlp

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QTextCursor
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QTextEdit, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel, CaptionLabel, ComboBox, LineEdit, PrimaryPushButton, ProgressBar,
    PushButton, TextEdit,
)

from utils.i18n import tr, register
from utils.main_thread import run_on_main

from ui.fluent_dialog import FluentContentDialog, msg_error, msg_info, msg_warn


# --------------------------------------------------------------------------- #
# 通用小工具
# --------------------------------------------------------------------------- #
def _cfg_get(config, key, default=None):
    """读配置：config 可能为 None（单测 / 独立调用），此时返回默认值。"""
    try:
        val = config.get(key, default)
        return default if val is None else val
    except Exception:
        return default


def _cfg_set(config, key, value):
    try:
        config.set(key, value)
    except Exception:
        pass


def _ffmpeg_path(config=None):
    """解析 ffmpeg：用户指定路径 > bin/ 内置 > 供应器缓存目录；都没有返回 None。"""
    try:
        raw = (_cfg_get(config, "ffmpeg_path", "") or "").strip()
        if raw and os.path.isfile(raw):
            return raw
    except Exception:
        pass
    try:
        from config import get_bundled_ffmpeg_path
        p = get_bundled_ffmpeg_path()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    try:
        from utils.ffmpeg_provider import get_ffmpeg_path, is_available
        if is_available():
            return get_ffmpeg_path()
    except Exception:
        pass
    return None


def default_seed():
    """今日人品默认名字：当前系统用户名（取不到就用「玩家」）。"""
    try:
        name = getpass.getuser()
        if name:
            return name
    except Exception:
        pass
    return tr("玩家")


def _human_size(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "--"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)}B" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return "--"


def _human_time(sec):
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return "--"
    if sec < 0:
        return "--"
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# --------------------------------------------------------------------------- #
# 一、自定义链接下载
# --------------------------------------------------------------------------- #
# 画质选项：tr() 实参必须是字面量（i18n 抽取要求）；右侧是内部存储值，永不翻译
def dl_quality_items():
    return [
        (tr("最佳画质（自动合并）"), "best"),
        (tr("1080p 及以下"), "1080p"),
        (tr("720p 及以下"), "720p"),
        (tr("仅音频（m4a）"), "audio"),
    ]


def dl_format_rule(quality, has_ffmpeg=True):
    """把界面画质选项翻译成 yt-dlp 的 format 表达式。

    没有 ffmpeg 时无法合并音视频，统一退化为 ``best``（单文件直出）。
    """
    if not has_ffmpeg:
        return "best"
    if quality == "1080p":
        return "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
    if quality == "720p":
        return "bestvideo[height<=720]+bestaudio/best[height<=720]"
    if quality == "audio":
        return "bestaudio/best"
    return "bestvideo*+bestaudio/best"


class _Cancelled(Exception):
    """用户手动停止下载时，从 progress hook 里抛出以中断 yt-dlp。"""


class _YdlWorker(threading.Thread):
    """后台下载线程：跑 yt-dlp，进度 / 日志经 run_on_main 回主线程。"""

    def __init__(self, dialog, url, out_dir, quality, ffmpeg_path):
        super().__init__(daemon=True)
        self.dlg = dialog
        self.url = url
        self.out_dir = out_dir
        self.quality = quality
        self.ffmpeg_path = ffmpeg_path
        self.stop_event = threading.Event()
        self._first_hook = True

    def _ui(self, fn, *args):
        """把 UI 更新排到主线程（严禁在工作线程直接碰控件）。"""
        run_on_main(lambda: fn(*args))

    def _hook(self, d):
        """yt-dlp 进度回调（工作线程内执行）。"""
        if self.stop_event.is_set():
            raise _Cancelled()
        try:
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                pct = int(done * 100 / total) if total else 0
                name = os.path.basename(d.get("filename") or "")
                if self._first_hook and name:
                    self._first_hook = False
                    self._ui(self.dlg.append_log, tr("开始下载：{}").format(name))
                speed = d.get("speed") or 0
                self._ui(self.dlg.update_progress, pct,
                         tr("下载中 {}%（{}，剩余 {}）").format(
                             pct,
                             (_human_size(speed) + "/s") if speed else tr("速度未知"),
                             _human_time(d.get("eta"))))
            elif status == "finished":
                self._ui(self.dlg.update_progress, 100, tr("正在处理文件……"))
                self._ui(self.dlg.append_log,
                         tr("已下载：{}").format(os.path.basename(d.get("filename") or "")))
        except _Cancelled:
            raise
        except Exception:
            pass

    def run(self):
        opts = {
            "format": dl_format_rule(self.quality, bool(self.ffmpeg_path)),
            "outtmpl": os.path.join(self.out_dir, "%(title).150B.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "retries": 3,
            "fragment_retries": 3,
            "continuedl": True,
            "progress_hooks": [self._hook],
        }
        if os.path.exists("cookies.txt"):
            opts["cookiefile"] = "cookies.txt"
        if self.ffmpeg_path:
            opts["ffmpeg_location"] = self.ffmpeg_path
        if self.quality == "best":
            opts["merge_output_format"] = "mp4"
        if self.quality == "audio":
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}]

        try:
            if not self.ffmpeg_path:
                self._ui(self.dlg.append_log,
                         tr("未检测到 ffmpeg：本次按最佳单文件下载（不合并、不转码）。"))
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])
        except _Cancelled:
            self._ui(self.dlg.on_worker_end, "cancelled", "")
            return
        except Exception as e:
            if self.stop_event.is_set():
                self._ui(self.dlg.on_worker_end, "cancelled", "")
            else:
                self._ui(self.dlg.on_worker_end, "failed", str(e))
            return
        self._ui(self.dlg.on_worker_end, "completed", "")


class CustomDownloadDialog(FluentContentDialog):
    """自定义链接下载（yt-dlp 通用下载器，与 B 站下载队列互不干扰）。"""

    def __init__(self, parent=None, config=None):
        super().__init__((700, 560), parent, title=tr("自定义链接下载"))
        self.config = config
        self._worker = None

        # ---- 链接 ----
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(CaptionLabel(tr("链接"), self))
        self.url_edit = LineEdit(self)
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.setPlaceholderText(
            tr("粘贴视频 / 播放列表 / 用户主页链接，支持 yt-dlp 可解析的任意站点"))
        row.addWidget(self.url_edit, 1)
        self.add_layout(row)

        # ---- 保存目录 ----
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(CaptionLabel(tr("保存到"), self))
        self.dir_edit = LineEdit(self)
        self.dir_edit.setText(self._initial_dir())
        self.dir_edit.setReadOnly(True)
        row.addWidget(self.dir_edit, 1)
        self.browse_btn = PushButton(tr("浏览"), self)
        self.browse_btn.clicked.connect(self._browse)
        row.addWidget(self.browse_btn)
        self.add_layout(row)

        # ---- 画质 ----
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(CaptionLabel(tr("下载画质"), self))
        self.quality_box = ComboBox(self)
        for label, value in dl_quality_items():
            self.quality_box.addItem(label, userData=value)
        cur = str(_cfg_get(config, "toolbox_download_quality", "best") or "best")
        idx = self.quality_box.findData(cur)
        self.quality_box.setCurrentIndex(idx if idx >= 0 else 0)
        self.quality_box.setMinimumWidth(200)
        row.addWidget(self.quality_box)
        row.addStretch(1)
        self.add_layout(row)

        # ---- 进度 ----
        self.bar = ProgressBar(self)
        self.bar.setValue(0)
        self.add_widget(self.bar)
        self.status = CaptionLabel(tr("准备就绪"), self)
        self.add_widget(self.status)

        # ---- 日志 ----
        self.log = TextEdit(self)
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log.setFont(QFont("Consolas", 9))
        self.add_widget(self.log, 1)

        # ---- 按钮排 ----
        self.open_btn = self.add_button(tr("打开目录"), right=False, slot=self._open_dir)
        self.start_btn = self.add_button(tr("开始下载"), primary=True, slot=self._toggle)
        self.close_btn = self.add_button(tr("关闭"), slot=self.reject)
        register(self.browse_btn, "浏览")
        register(self.open_btn, "打开目录")
        register(self.close_btn, "关闭")

    # ------------------------------------------------------------------ #
    def _initial_dir(self):
        raw = (_cfg_get(self.config, "toolbox_download_dir", "") or "").strip()
        if raw and os.path.isdir(raw):
            return raw
        try:
            from config import normalize_download_path
            return normalize_download_path(_cfg_get(self.config, "download_path", ""))
        except Exception:
            return os.path.expanduser("~")

    def _browse(self):
        path = QFileDialog.getExistingDirectory(
            self, tr("选择下载目录"), self.dir_edit.text() or os.path.expanduser("~"))
        if path:
            self.dir_edit.setText(path)
            _cfg_set(self.config, "toolbox_download_dir", path)

    def _open_dir(self):
        path = self.dir_edit.text()
        if path and os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ------------------------------------------------------------------ #
    def append_log(self, text):
        try:
            self.log.append(text)
            self.log.moveCursor(QTextCursor.MoveOperation.End)
        except Exception:
            pass

    def update_progress(self, pct, text=""):
        try:
            self.bar.setValue(max(0, min(100, int(pct))))
        except Exception:
            pass
        if text:
            self.status.setText(text)

    # ------------------------------------------------------------------ #
    def _toggle(self):
        if self._worker is not None and self._worker.is_alive():
            self._stop()
        else:
            self._start()

    def _start(self):
        url = self.url_edit.text().strip()
        if not url:
            msg_warn(self, tr("请先粘贴要下载的链接。"))
            return
        out_dir = self.dir_edit.text().strip()
        if not out_dir:
            msg_warn(self, tr("请先选择保存目录。"))
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            msg_error(self, tr("创建保存目录失败：{}").format(str(e)))
            return

        quality = self.quality_box.currentData() or "best"
        ffmpeg_path = _ffmpeg_path(self.config)
        if quality == "audio" and not ffmpeg_path:
            msg_warn(self, tr("「仅音频」需要 ffmpeg，请先在「高级」里配置 ffmpeg 路径。"))
            return
        _cfg_set(self.config, "toolbox_download_quality", quality)

        self.log.clear()
        self.append_log(tr("任务开始：{}").format(url))
        self.update_progress(0, tr("正在解析链接……"))
        self.start_btn.setText(tr("停止"))
        self.url_edit.setEnabled(False)

        self._worker = _YdlWorker(self, url, out_dir, quality, ffmpeg_path)
        self._worker.start()

    def _stop(self):
        if self._worker is not None:
            self._worker.stop_event.set()
            self.status.setText(tr("正在停止……"))

    def on_worker_end(self, result, error):
        """工作线程结束回调（已回到主线程）。"""
        self._worker = None
        self.start_btn.setText(tr("开始下载"))
        self.url_edit.setEnabled(True)
        if result == "completed":
            self.bar.setValue(100)
            self.status.setText(tr("下载完成"))
            self.append_log(tr("下载完成。"))
        elif result == "cancelled":
            self.bar.setValue(0)
            self.status.setText(tr("已取消"))
            self.append_log(tr("已取消。"))
        else:
            self.status.setText(tr("下载失败"))
            self.append_log(tr("下载失败：{}").format(error))

    def closeEvent(self, e):
        # 关窗即停：不让后台线程继续跑（daemon 线程虽会随进程退出，这里更干净）
        if self._worker is not None and self._worker.is_alive():
            self._worker.stop_event.set()
        super().closeEvent(e)


# --------------------------------------------------------------------------- #
# 二、今日人品
# --------------------------------------------------------------------------- #
def luck_score(seed, day=None, bonus=0):
    """今日人品分数：同一天、同一名字结果固定（哈希取模 0~100，再加彩蛋加成）。"""
    day = day or date.today().isoformat()
    raw = hashlib.sha256(f"{seed}|{day}".encode("utf-8")).hexdigest()
    base = int(raw[:8], 16) % 101
    try:
        bonus = int(bonus or 0)
    except (TypeError, ValueError):
        bonus = 0
    return max(0, min(100, base + bonus))


def luck_tiers():
    """人品评语分档（下限, 上限, 评语）。

    注意：tr() 的实参必须是字面量，i18n 抽取脚本（ast）才能收录；
    因此这里写成函数而不是「中文表 + 循环 tr」，也保证每次打开弹窗都取最新语言。
    """
    return [
        (0, 0, tr("0 分。今天诸事不宜，建议原地躺平。")),
        (1, 20, tr("运气有点差，出门先看看黄历。")),
        (21, 40, tr("平平淡淡，适合摸鱼。")),
        (41, 60, tr("中规中矩，一切照旧。")),
        (61, 80, tr("运气不错，适合做点正事。")),
        (81, 99, tr("欧气满满，今天宜抽卡、宜投稿。")),
        (100, 100, tr("满分！欧皇附体，今天做什么都顺。")),
    ]


class LuckDialog(FluentContentDialog):
    """今日人品：名字 + 日期哈希 -> 0~100 的手气值（娱乐）。"""

    def __init__(self, parent=None, config=None):
        super().__init__((560, 430), parent, title=tr("今日人品"))
        self.config = config
        self._ticks = 0
        self._final = 0
        self._lines = luck_tiers()
        self._timer = QTimer(self)
        self._timer.setInterval(55)
        self._timer.timeout.connect(self._tick)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(CaptionLabel(tr("名字"), self))
        self.seed_edit = LineEdit(self)
        seed = str(_cfg_get(config, "toolbox_luck_seed", "") or "") or default_seed()
        self.seed_edit.setText(seed)
        self.seed_edit.setPlaceholderText(tr("换个名字会有不同结果"))
        row.addWidget(self.seed_edit, 1)
        self.add_layout(row)

        self.score_label = BodyLabel("--", self)
        f = QFont(self.score_label.font())
        f.setPointSize(56)
        f.setBold(True)
        self.score_label.setFont(f)
        self.score_label.setAlignment(Qt.AlignCenter)
        self.add_widget(self.score_label, 1)

        self.comment_label = BodyLabel(tr("点下面的按钮，看看今天的手气。"), self)
        self.comment_label.setAlignment(Qt.AlignCenter)
        self.comment_label.setWordWrap(True)
        self.add_widget(self.comment_label)

        self.hint = CaptionLabel(tr("同一名字同一天的结果固定，每天 0 点刷新。"), self)
        self.hint.setAlignment(Qt.AlignCenter)
        self.add_widget(self.hint)

        bonus = int(_cfg_get(config, "toolbox_luck_bonus", 0) or 0)
        if bonus:
            self.hint.setText(self.hint.text() + tr("本次含彩蛋加成 +{}。").format(bonus))

        self.divine_btn = self.add_button(tr("开始占卜"), primary=True, slot=self.divine)
        self.close_btn = self.add_button(tr("关闭"), slot=self.reject)
        register(self.close_btn, "关闭")

    # ------------------------------------------------------------------ #
    def _comment(self, score):
        for lo, hi, text in self._lines:
            if lo <= score <= hi:
                return text
        return self._lines[-1][2]

    def divine(self):
        seed = self.seed_edit.text().strip() or default_seed()
        _cfg_set(self.config, "toolbox_luck_seed", seed)
        bonus = int(_cfg_get(self.config, "toolbox_luck_bonus", 0) or 0)
        self._final = luck_score(seed, bonus=bonus)
        self._ticks = 0
        self.comment_label.setText(tr("占卜中……"))
        self.divine_btn.setEnabled(False)
        self._timer.start()

    def _tick(self):
        self._ticks += 1
        if self._ticks >= 10:
            self._timer.stop()
            self.score_label.setText(str(self._final))
            self.comment_label.setText(self._comment(self._final))
            self.divine_btn.setEnabled(True)
        else:
            self.score_label.setText(str(random.randint(0, 100)))


# --------------------------------------------------------------------------- #
# 三、千万别点
# --------------------------------------------------------------------------- #
class _Playground(QWidget):
    """「逃跑按钮」活动区：尺寸变化时通知父对话框重新摆放按钮。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.on_resize = None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if callable(self.on_resize):
            try:
                self.on_resize()
            except Exception:
                pass


def dnc_lines():
    """「千万别点」逐级升级的文案（最后一条即彩蛋）。

    同 ``luck_tiers``：tr() 实参必须字面量，才能被 i18n 抽取脚本收录。
    """
    return [
        tr("都说了千万别点！"),
        tr("你怎么还在点？"),
        tr("再点下去要出事了……"),
        tr("我认真的，别点了。"),
        tr("你的耐心让我有点害怕。"),
        tr("第 6 次了，我已经开始怀疑人生。"),
        tr("最后一次警告：再点一下有彩蛋（大概）。"),
        tr("彩蛋到手：今日人品 +5，去「今日人品」那页看看吧。"),
    ]


class DoNotClickDialog(FluentContentDialog):
    """千万别点：按钮点一次跑一次，点到第 8 次有彩蛋。"""

    def __init__(self, parent=None, config=None):
        super().__init__((600, 430), parent, title=tr("千万别点"))
        self.config = config
        self.clicks = int(_cfg_get(config, "toolbox_dnc_clicks", 0) or 0)
        self._lines = dnc_lines()

        self.tip = CaptionLabel(tr("这个按钮没有任何用途。真的。"), self)
        self.add_widget(self.tip)

        self.msg_label = BodyLabel(tr("来都来了，点一下吧。"), self)
        self.msg_label.setAlignment(Qt.AlignCenter)
        self.msg_label.setWordWrap(True)
        self.add_widget(self.msg_label)

        self.playground = _Playground(self)
        self.playground.setFixedHeight(170)
        self.playground.on_resize = self._move_button
        self.run_btn = PrimaryPushButton(tr("千万别点"), self.playground)
        self.run_btn.setFixedSize(170, 44)
        self.run_btn.clicked.connect(self._on_click)
        self.add_widget(self.playground)

        self.count_label = CaptionLabel("", self)
        self.count_label.setAlignment(Qt.AlignCenter)
        self.add_widget(self.count_label)
        self._refresh_count()

        self.reset_btn = self.add_button(tr("重置"), right=False, slot=self._reset)
        self.close_btn = self.add_button(tr("关闭"), primary=True, slot=self.accept)
        register(self.reset_btn, "重置")
        register(self.close_btn, "关闭")

    # ------------------------------------------------------------------ #
    def showEvent(self, e):
        super().showEvent(e)
        self._move_button()

    def _move_button(self):
        """在活动区内随机换位（首次布局前尺寸为 0，用 max(1, ...) 兜底）。"""
        w = max(1, self.playground.width() - self.run_btn.width())
        h = max(1, self.playground.height() - self.run_btn.height())
        self.run_btn.move(random.randint(0, w), random.randint(0, h))

    def _refresh_count(self):
        self.count_label.setText(tr("已累计点击 {} 次。").format(self.clicks))

    def _on_click(self):
        self.clicks += 1
        _cfg_set(self.config, "toolbox_dnc_clicks", self.clicks)
        idx = min(self.clicks, len(self._lines)) - 1
        self.msg_label.setText(self._lines[idx])
        # 彩蛋：第 8 次点击给「今日人品」+5（累计上限 +20，避免无限叠加）
        if self.clicks == len(self._lines):
            bonus = int(_cfg_get(self.config, "toolbox_luck_bonus", 0) or 0)
            new_bonus = min(20, bonus + 5)
            _cfg_set(self.config, "toolbox_luck_bonus", new_bonus)
            if new_bonus > bonus:
                msg_info(self,
                         tr("彩蛋触发成功：今日人品 +5（当前加成 +{}）。").format(new_bonus),
                         tr("彩蛋"))
        self._refresh_count()
        self._move_button()

    def _reset(self):
        self.clicks = 0
        _cfg_set(self.config, "toolbox_dnc_clicks", 0)
        self.msg_label.setText(tr("来都来了，点一下吧。"))
        self._refresh_count()
        self._move_button()


__all__ = [
    "CustomDownloadDialog", "LuckDialog", "DoNotClickDialog",
    "luck_score", "luck_tiers", "dnc_lines", "dl_format_rule",
    "dl_quality_items", "default_seed",
]
