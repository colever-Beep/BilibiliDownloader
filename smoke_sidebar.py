"""无头冒烟测试：验证侧边栏适配 qfluentwidgets 后可构造、刷新、切换选中。

仅做构造级验证（不依赖真实显示）：QT_QPA_PLATFORM=offscreen。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from config import ConfigManager


class _Api:
    uid = None
    nickname = None
    avatar = None


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    cfg = ConfigManager("settings.json")

    from ui.sidebar import NavigationBar

    calls = []

    def on_nav(*a):
        calls.append(a)

    bar = NavigationBar(
        None, _Api(), on_nav,
        config=cfg, on_language_change=lambda c: None,
        on_login=lambda: None, on_about=lambda: None, on_settings=lambda: None,
    )
    bar.show()
    app.processEvents()

    # 切换选中
    bar.setCurrentItem("history")
    app.processEvents()
    assert bar._items["history"]._selected, "history should be selected"

    # 触发点击回调
    bar._items["search"].clicked.emit(False)
    app.processEvents()
    assert calls and calls[-1][0] == "search", "search click should fire on_nav_click"

    # 语言刷新（重建）
    bar.refresh()
    app.processEvents()
    print("SIDEBAR_OK items=", list(bar._items.keys()))
    print("lang_combo present=", hasattr(bar, "lang_combo"))
    print("selected after refresh=", bar._current_route)

    bar.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
