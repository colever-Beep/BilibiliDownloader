"""直播录制监控窗口（Fluent，非模态）。

取代原先「点开始录制后只弹一个确认框」的体验：打开一个常驻窗口，实时显示
直播间信息、录制状态、已录制时长、输出文件与大小，并提供「开始 / 停止」按钮，
可随时启停录制。窗口把 LiveRecorder 的内部日志也实时投到文本区，便于排查。
"""
from __future__ import annotations

import os
import re
import time
import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QTextEdit, QWidget,
)

from qfluentwidgets import (
    BodyLabel, CaptionLabel, LineEdit, PrimaryPushButton,
)

from ui.fluent_dialog import FluentContentDialog, msg_error
from utils.i18n import tr, register
from utils.main_thread import run_on_main


def resolve_room_id(target):
    """从房间链接或纯数字房间号里提取 roomid（与 main_window 同逻辑）。"""
    if isinstance(target, dict):
        return target.get("roomid")
    if isinstance(target, int):
        return target
    target = (target or "").strip()
    if not target:
        return None
    m = re.search(r"live\.bilibili\.com/?(\d+)", target)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)", target)
    return int(m.group(1)) if m else None


class _WindowLogger:
    """把 LiveRecorder 的日志消息转投到录制窗口的文本区（线程安全）。"""

    def __init__(self, window):
        self.window = window

    def log(self, msg):
        run_on_main(lambda: self.window.append_log(msg))


class LiveRecordWindow(FluentContentDialog):
    """直播录制监控窗口：输入房间号 -> 开始/停止录制 -> 实时显示详情。"""

    def __init__(self, parent=None, api=None, config=None, logger=None,
                 target=None):
        super().__init__((600, 500), parent, title=tr("直播录制"))
        self.api = api
        self.config = config
        self.logger = logger
        self.logger_adapter = _WindowLogger(self)

        self.recorder = None
        self.recording = False
        self._start_time = 0.0
        self._room_id = None
        self._title_hint = ""
        self._timer = None
        self._registry_remove = None  # 由主窗口注入：移除登记
        self._auto_start = False

        self._build_ui()

        if target is not None:
            rid = resolve_room_id(target)
            if rid is not None:
                self.input.setText(str(rid))
                self._title_hint = self._make_title_hint(target)
            self._auto_start = True  # showEvent 后再自动开始

    # ------------------------------------------------------------------ #
    # 构建 UI
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        # ---- 输入行：房间号 + 开始/停止 ----
        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        self.input = LineEdit(self)
        self.input.setPlaceholderText(
            "https://live.bilibili.com/房间号  或  纯房间号")
        self.input.returnPressed.connect(self._on_toggle)
        input_row.addWidget(self.input, 1)
        self.toggle_btn = PrimaryPushButton(tr("开始录制"), self)
        self.toggle_btn.setMinimumWidth(110)
        self.toggle_btn.clicked.connect(self._on_toggle)
        input_row.addWidget(self.toggle_btn)
        self.add_layout(input_row)

        # ---- 分隔线 ----
        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        self.add_widget(sep)

        # ---- 详情网格 ----
        grid = QGridLayout()
        grid.setSpacing(8)
        self._vals = {}
        rows = [
            (tr("直播间"), "room"),
            (tr("房间号"), "rid"),
            (tr("状态"), "status"),
            (tr("已录制"), "duration"),
            (tr("文件大小"), "size"),
            (tr("输出文件"), "file"),
        ]
        for i, (key, attr) in enumerate(rows):
            lab = CaptionLabel(key, self)
            lab.setMinimumWidth(64)
            val = BodyLabel("—", self)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._vals[attr] = val
            grid.addWidget(lab, i, 0)
            grid.addWidget(val, i, 1)
        grid.setColumnStretch(1, 1)
        self.add_layout(grid)

        # ---- 日志区 ----
        self.log_edit = QTextEdit(self)
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(140)
        self.add_widget(self.log_edit, 1)

        # ---- 底部按钮 ----
        self.close_btn = self.add_button(tr("关闭"), slot=self._on_close)
        register(self.close_btn, "关闭")

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #
    def _make_title_hint(self, target):
        if isinstance(target, dict):
            uname = target.get("uname", "")
            rid = target.get("roomid")
            return f"{uname}_{rid}" if uname else str(rid)
        rid = resolve_room_id(target)
        return str(rid) if rid else tr("直播")

    def append_log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_edit.append(f"[{ts}] {msg}")
        self.log_edit.moveCursor(QTextCursor.End)

    def _set_val(self, attr, text):
        self._vals[attr].setText(text)

    # ------------------------------------------------------------------ #
    # 启停
    # ------------------------------------------------------------------ #
    def _on_toggle(self):
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        if self.recording:
            return
        target = self.input.text().strip() or self._title_hint
        rid = resolve_room_id(target)
        if rid is None:
            msg_error(self, tr("无法识别直播间：{}").format(target), tr("错误"))
            return
        self._room_id = rid
        self._title_hint = self._make_title_hint(target)
        self._set_val("rid", str(rid))
        self._set_val("room", self._title_hint)

        # ---- 录制选项弹窗（与视频下载的「下载选项」同款体验）----
        # 确认后本次设置已写回 config（编码 / 封装格式 / 清晰度 / 重连 / 保存路径）。
        if self.config is None or bool(
                self.config.get("live_record_options_dialog", True)):
            try:
                from ui.live_record_options_dialog import LiveRecordOptionsDialog
                dlg = LiveRecordOptionsDialog(self, self.config,
                                              room_hint=self._title_hint)
                dlg.exec()
                if dlg.result is not True:
                    self.append_log(tr("已取消录制"))
                    return
            except Exception as e:
                # 弹窗异常不阻断录制（回退为直接按当前配置开始）
                self.append_log(tr("录制选项弹窗异常，按默认设置开始：{}").format(e))

        self._set_status(tr("获取流地址中…"))
        self.toggle_btn.setEnabled(False)
        self.append_log(tr("正在获取直播流地址：roomid={}").format(rid))
        qn = 10000
        if self.config is not None:
            try:
                qn = int(self.config.get("live_record_qn", 10000) or 10000)
            except (TypeError, ValueError):
                qn = 10000

        def work():
            try:
                stream = self.api.get_live_playurl(rid, qn=qn)
            except Exception as e:
                run_on_main(lambda err=str(e): self._on_stream_failed(err))
                return
            if not stream:
                run_on_main(lambda: self._on_stream_failed(
                    tr("未获取到直播流地址（未开播 / 风控拦截）")))
                return
            run_on_main(lambda s=stream: self._on_stream_ready(s))

        threading.Thread(target=work, daemon=True).start()

    def _on_stream_ready(self, stream):
        auto_reconnect = True
        if self.config is not None:
            auto_reconnect = bool(self.config.get("live_record_auto_reconnect", True))
        try:
            from live_recorder import LiveRecorder
            rec = LiveRecorder(config=self.config, logger=self.logger_adapter)
            qn = 10000
            if self.config is not None:
                try:
                    qn = int(self.config.get("live_record_qn", 10000) or 10000)
                except (TypeError, ValueError):
                    qn = 10000
            outpath = rec.start(
                stream, title_hint=self._title_hint,
                auto_reconnect=auto_reconnect,
                refetch=lambda: self.api.get_live_playurl(self._room_id, qn=qn))
        except Exception as e:
            self._on_stream_failed(str(e))
            return
        self.recorder = rec
        self.recording = True
        self._start_time = time.time()
        self._set_val("file", outpath)
        self._set_status(tr("录制中"))
        self.toggle_btn.setText(tr("停止录制"))
        self.toggle_btn.setEnabled(True)
        # 计时器刷新时长 / 大小
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self.append_log(tr("已开始录制：{}").format(os.path.basename(outpath)))

    def _on_stream_failed(self, err):
        self._set_status(tr("出错"))
        self.toggle_btn.setEnabled(True)
        self.append_log(tr("获取流地址失败：{}").format(err))
        if self.logger:
            self.logger.log(f"直播录制失败：{err}")

    def _stop_recording(self):
        if not self.recording:
            return
        if self.recorder is not None:
            try:
                self.recorder.stop()
            except Exception as e:
                self.append_log(tr("停止异常：{}").format(e))
        self.recording = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._set_status(tr("已停止"))
        self.toggle_btn.setText(tr("开始录制"))
        self.append_log(tr("已停止录制"))

    def _tick(self):
        if not self.recording:
            return
        elapsed = int(time.time() - self._start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        self._set_val("duration", f"{h:02d}:{m:02d}:{s:02d}")
        size = 0
        out = self.recorder.current_outpath if self.recorder else None
        if out and os.path.exists(out):
            try:
                size = os.path.getsize(out)
            except Exception:
                size = 0
        self._set_val("size", self._fmt_size(size))

    @staticmethod
    def _fmt_size(n):
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def _set_status(self, text):
        self._set_val("status", text)

    def showEvent(self, e):
        super().showEvent(e)
        if getattr(self, "_auto_start", False):
            self._auto_start = False
            if not self.recording:
                self._start_recording()

    def closeEvent(self, e):
        if self.recording:
            self._stop_recording()
        cb = getattr(self, "_registry_remove", None)
        if callable(cb):
            try:
                cb(self._room_id)
            except Exception:
                pass
        super().closeEvent(e)

    def _on_close(self):
        self.close()
