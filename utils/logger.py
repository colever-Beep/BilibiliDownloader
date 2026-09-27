import time

class Logger:
    def __init__(self, log_file="download.log"):
        self.log_file = log_file
        self.ui_callbacks = []   # 用于UI显示

    def log(self, msg):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {msg}"
        # 写入文件
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        # 通知UI
        for cb in self.ui_callbacks:
            cb(line)