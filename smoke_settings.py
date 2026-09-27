"""无头冒烟测试：验证 qfluentwidgets MSFluentWindow 设置窗口可导入并构造。

仅做构造级验证（不依赖真实显示）：QT_QPA_PLATFORM=offscreen。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from config import ConfigManager


def dummy(*a, **k):
    return None


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    cfg = ConfigManager("settings.json")

    from ui.settings_window import SettingsWindow
    w = SettingsWindow(None, cfg, dummy, dummy, dummy)
    w.show()
    app.processEvents()

    # 切换每个分类，触发抽屉式切换与重绘
    for rk in ("basic", "download", "options", "advanced"):
        try:
            w.navigationInterface.setCurrentItem(rk)
            app.processEvents()
        except Exception as e:
            print("WARN switch", rk, e)

    # 模拟一次语言切换刷新
    try:
        w._retranslate()
    except Exception as e:
        print("WARN retranslate", e)

    print("SETTINGS_WINDOW_OK routes=",
          [w.navigationInterface.widget(rk).text() for rk in
           ("basic", "download", "options", "advanced")])
    w.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
