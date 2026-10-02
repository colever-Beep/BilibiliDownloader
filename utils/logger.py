import time

class Logger:
    def __init__(self, log_file="download.log"):
        self.log_file = log_file
        self.ui_callbacks = []   # 用于UI显示

    def log(self, msg):
        # 日志写入必须"绝不抛异常"：
        # 任何 IO 失败（文件被占用 / 无权限 / 磁盘满）若上抛，会打断调用方流程；
        # 尤其在退出路径上抛异常会阻止 os._exit 退出，界面表现为"点击退出后冻住"。
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{timestamp}] {msg}"
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            line = msg if isinstance(msg, str) else str(msg)
        # 通知UI（单个回调异常也不应影响其他回调 / 调用方）
        for cb in self.ui_callbacks:
            try:
                cb(line)
            except Exception:
                pass
