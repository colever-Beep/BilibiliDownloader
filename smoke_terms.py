"""无头冒烟：验证《用户协议》窗口与启动接线。

- 直接构造 TermsOfUseDialog：accept 落盘 accepted_terms=True；reject 不改。
- 构造 MainWindow：patch 掉 TermsOfUseDialog.exec 与 quit_app，
  验证 show_terms_of_use 在「拒绝」时调用 quit_app、「同意」时不调用且写回 flag。
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
from ui import terms_dialog as terms_mod


def build_window(config, app):
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
    bili_api = BiliAPI("")  # 空 cookie：不发网络请求
    engine = DownloadEngine(config, logger, bili_api)
    return MainWindow(config, logger, bili_api, engine)


def test_dialog_direct():
    """直接构造协议窗口，验证 accept/reject 对持久化键的影响。"""
    from ui.terms_dialog import TermsOfUseDialog
    from config import ConfigManager
    cfg = ConfigManager("settings.json")
    cfg.set("accepted_terms", False)

    # accept → 置位
    dlg = TermsOfUseDialog(None, cfg)
    assert dlg.windowTitle() == "用户协议", dlg.windowTitle()
    assert dlg.accept  # 方法存在
    dlg.accept()
    assert cfg.get("accepted_terms", False) is True, "accept 后未写回 accepted_terms"
    cfg.set("accepted_terms", False)

    # reject → 保持 False
    dlg2 = TermsOfUseDialog(None, cfg)
    dlg2.reject()
    assert cfg.get("accepted_terms", False) is False, "reject 不该改变 accepted_terms"
    print("TERMS_DIALOG_OK accept->True reject->False")


def test_show_terms_wiring(app):
    config = ConfigManager("settings.json")
    config.set("accepted_terms", False)
    win = build_window(config, app)

    calls = {"quit": 0}

    def fake_quit():
        calls["quit"] += 1

    win.quit_app = fake_quit

    # 1) 拒绝 → 必须退出（exec 真正走 reject，以验证不写回 flag）
    terms_mod.TermsOfUseDialog.exec = lambda self: (self.reject(), False)[1]
    win.show_terms_of_use()
    assert calls["quit"] == 1, "拒绝协议后未退出程序"
    assert config.get("accepted_terms", False) is False, "拒绝时不该写回 flag"

    # 2) 同意 → 不退出且写回 flag（exec 真正走 accept，验证落盘）
    terms_mod.TermsOfUseDialog.exec = lambda self: (self.accept(), True)[1]
    win.show_terms_of_use()
    assert calls["quit"] == 1, "同意协议后不应再次退出"
    assert config.get("accepted_terms", False) is True, "同意后未写回 flag"

    config.set("accepted_terms", False)  # 复位，避免污染
    print("TERMS_WIRING_OK reject_quit=", calls["quit"])


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("B站下载器 Pro")
    test_dialog_direct()
    test_show_terms_wiring(app)
    print("TERMS_SMOKE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
