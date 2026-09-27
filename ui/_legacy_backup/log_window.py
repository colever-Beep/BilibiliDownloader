import os

import customtkinter as ctk

from ui.log_view import LogView
from utils.i18n import tr
from ui.base_dialog import BaseDialog


class LogWindow(BaseDialog):
    """独立的日志窗口：只有在设置页点击「查看日志」时才打开。

    打开时从 logger 指向的日志文件回放历史内容，之后实时追加新日志
    （由 main_window 的 ui 回调路由过来）。单实例，重复点击只聚焦已有窗口。
    """

    _INSTANCE = None

    def __init__(self, master, logger):
        existing = self._singleton(master)
        if existing is not None:
            return
        super().__init__(master)
        self.logger = logger
        self.title(tr("日志"))
        # 按钮打开的窗口需显式置顶，否则在 Windows 上会落在父窗口（如设置对话框）后面
        self._show(master, "720x520", resizable=(True, True))

        self.log_view = LogView(self, logger)
        self.log_view.pack(fill="both", expand=True, padx=10, pady=10)

        self.protocol("WM_DELETE_WINDOW", self._close)
        LogWindow._INSTANCE = self

        # 回放历史日志（文件可能很大，限制最后 2000 行）
        self._replay_history()

    def _replay_history(self):
        try:
            path = getattr(self.logger, "log_file", None)
            if not path or not os.path.exists(path):
                return
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            tail = lines[-2000:] if len(lines) > 2000 else lines
            box = self.log_view.textbox
            box.configure(state="normal")
            for ln in tail:
                box.insert("end", ln if ln.endswith("\n") else ln + "\n")
            box.see("end")
            box.configure(state="disabled")
            self.log_view.log_count_label.configure(text=tr("共 {} 行").format(len(tail)))
        except Exception:
            pass

    def append_log(self, msg):
        """供 main_window 路由：窗口存在时把新日志写进来。"""
        try:
            if self.winfo_exists():
                self.log_view.append_log(msg)
        except Exception:
            pass

    def _close(self):
        LogWindow._INSTANCE = None
        try:
            self.destroy()
        except Exception:
            pass
