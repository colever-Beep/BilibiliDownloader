import customtkinter as ctk

from utils.i18n import tr

class LogView(ctk.CTkFrame):
    def __init__(self, master, logger):
        super().__init__(master)
        self.logger = logger
        self.build()

    def build(self):
        # 日志显示区域
        self.textbox = ctk.CTkTextbox(self, height=120, state="disabled", font=("Consolas", 11))
        self.textbox.pack(fill="both", expand=True)

        # 按钮栏
        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(fill="x", pady=(5,0))

        self.log_count_label = ctk.CTkLabel(btn_frame, text="", font=("", 10))
        self.log_count_label.pack(side="left", padx=5)

        ctk.CTkButton(btn_frame, text=tr("清空日志"), command=self.clear_log, width=80, height=25).pack(side="right")

    def append_log(self, msg):
        self.textbox.configure(state="normal")
        self.textbox.insert("end", f"{msg}\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

        # 更新计数
        line_count = int(self.textbox.index("end-1c").split(".")[0])
        self.log_count_label.configure(text=tr("共 {} 行").format(line_count - 1))

    def clear_log(self):
        from tkinter import messagebox
        # 弹窗提醒用户：清空日志会同时清空同目录下的 download.log 文件
        ans = messagebox.askyesno(
            tr("清空日志"),
            tr("即将清空日志窗口，同时会清空同目录下的 download.log 文件。\n是否继续？")
        )
        if not ans:
            return
        # 清空同目录下的 download.log 文件内容
        try:
            with open(self.logger.log_file, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
        self.log_count_label.configure(text=tr("已清空"))