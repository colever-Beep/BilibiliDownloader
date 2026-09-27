"""无头冒烟：验证主窗口布局切换控件已并入「解析记录」所在行，且不再独占底部。

- 构造 MainWindow（offscreen）。
- 断言 layout_toggle 与 history_btn（解析记录）同父（即同一行）。
- 断言 main_window 已无独立 foot_bar 属性。
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
from ui.main_window import MainWindow


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
    # 空 cookie：BiliAPI.__init__ 不发网络请求，安全用于无头构造
    bili_api = BiliAPI("")
    engine = DownloadEngine(config, logger, bili_api)

    win = MainWindow(config, logger, bili_api, engine)

    # 1) 切换控件已就位
    assert hasattr(win, "layout_toggle"), "主窗口缺少 layout_toggle"
    # 2) 与「解析记录」同属一个父容器（同一行）
    assert win.history_btn.parentWidget() is win.layout_toggle.parentWidget(), \
        "layout_toggle 未与「解析记录」同处一行"
    # 3) 旧独立底部 bar 已移除
    assert not hasattr(win, "foot_bar"), "主窗口仍存在独立 foot_bar"

    # 切换模式不崩溃
    from ui.list_layout import set_mode
    set_mode("compact")
    app.processEvents()
    set_mode("detailed")
    app.processEvents()

    print("MAIN_TOGGLE_SMOKE_OK same_row_as_history=",
          win.history_btn.parentWidget() is win.layout_toggle.parentWidget())
    return 0


if __name__ == "__main__":
    sys.exit(main())
