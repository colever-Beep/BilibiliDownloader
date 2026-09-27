"""无头冒烟：验证「首次登录警告弹窗」恢复且只弹一次、持久化。

- 拦截 msg_warn（避免 offscreen 下模态阻塞），改为记录调用。
- 模拟已登录态（api.uid 已设置），run() 经 QTimer 触发一次警告。
- 断言：启动路径弹 1 次；login_api_warned 置位并落盘；重复调用不再弹。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from config import ConfigManager
from utils.logger import Logger
from bili_api import BiliAPI
from download_engine import DownloadEngine
from ui.theme import apply_theme
from ui import main_window
from ui.main_window import MainWindow

calls = []


def recorder(parent, message, title):
    calls.append((message, title))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("B站下载器 Pro")

    config = ConfigManager("settings.json")
    try:
        from utils.i18n import set_language
        set_language(config.get("language", "zh_CN"))
    except Exception:
        pass
    try:
        apply_theme(config.get("accent_color"), config.get("appearance", "dark"))
    except Exception:
        pass

    logger = Logger(log_file="download.log")
    bili_api = BiliAPI("")
    bili_api.uid = 12345  # 模拟已登录
    engine = DownloadEngine(config, logger, bili_api)

    config.set("login_api_warned", False)  # 复位起点
    main_window.msg_warn = recorder        # 拦截真实弹窗

    win = MainWindow(config, logger, bili_api, engine)
    # 启动路径：run() 内 QTimer.singleShot(0) 触发一次
    win.run()
    app.processEvents()

    assert len(calls) == 1, f"启动路径应弹 1 次，实际 {len(calls)}"
    assert config.get("login_api_warned") is True, "flag 未置位"

    # 再次调用不应重复弹
    calls.clear()
    win._maybe_show_login_api_warning()
    assert len(calls) == 0, "已展示过应不再弹"

    # 重新读盘确认持久化
    cfg2 = ConfigManager("settings.json")
    assert cfg2.get("login_api_warned") is True, "未持久化到磁盘"

    # 复位，避免污染 settings.json
    config.set("login_api_warned", False)

    print("LOGIN_WARN_SMOKE_OK start_calls=", 1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
