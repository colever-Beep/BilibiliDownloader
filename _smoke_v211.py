"""v2.1.1 无头烟测：强调色迁移 / 更新服务 / 设置页更新子界面 / 更新对话框。"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, r"D:/VScode/b")
os.chdir(tempfile.mkdtemp())

from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

# ---------------------------------------------------------------- 1. 版本工具
from utils.version import APP_VERSION, is_newer, normalize_version
assert APP_VERSION == "2.1.1", APP_VERSION
assert normalize_version("v2.1.1") == (2, 1, 1)
assert normalize_version("2.1.2") == (2, 1, 2)
assert normalize_version("v3.0") == (3, 0, 0)
assert normalize_version("garbage") == (0, 0, 0)
assert is_newer("2.1.2", "2.1.1") is True
assert is_newer("2.1.1", "2.1.1") is False
assert is_newer("2.1.0", "2.1.1") is False
print("1) version OK  APP_VERSION =", APP_VERSION)

# ---------------------------------------------------------------- 2. 主题默认值
from ui.theme import DEFAULT_ACCENT, PRESET_ACCENTS
assert DEFAULT_ACCENT == "#f07090", DEFAULT_ACCENT
assert PRESET_ACCENTS[0] == "#f07090"
print("2) theme OK  DEFAULT_ACCENT =", DEFAULT_ACCENT)

# ---------------------------------------------------------------- 3. 配置迁移
import json
import config as cfg_mod
tmpdir = tempfile.mkdtemp()
cfg_path = os.path.join(tmpdir, "settings.json")
with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump({"accent_color": "#1f8a4c",
               "accent_color_custom": "#1f8a4c",
               "download_path": os.path.join(tmpdir, "Videos")}, f)
cm = cfg_mod.ConfigManager(cfg_path)
assert cm.get("accent_color") == "#f07090", cm.get("accent_color")
assert cm.get("accent_color_custom") == "#f07090"
with open(cfg_path, "r", encoding="utf-8") as f:
    saved = json.load(f)
assert saved["accent_color"] == "#f07090", saved["accent_color"]
print("3) accent migration OK ->", saved["accent_color"])

# 自定义过颜色的用户不应被覆盖
cfg2 = os.path.join(tmpdir, "s2.json")
with open(cfg2, "w", encoding="utf-8") as f:
    json.dump({"accent_color": "#2f80ed", "accent_color_custom": "#2f80ed"}, f)
cm2 = cfg_mod.ConfigManager(cfg2)
assert cm2.get("accent_color") == "#2f80ed", cm2.get("accent_color")
print("4) custom accent preserved OK ->", cm2.get("accent_color"))

# ---------------------------------------------------------------- 5. 更新服务
from utils.updater import (UpdateService, UpdateStatus, UpdateInfo, Asset,
                           CHANNEL_STABLE, CHANNEL_BETA, build_proxies,
                           pick_default_asset)
svc = UpdateService({"proxy_type": "none"})
rel_stable = {"tag_name": "v2.1.1", "name": "Stable 2.1.1", "body": "notes",
               "prerelease": False, "published_at": "2026-10-01T00:00:00Z",
               "assets": [{"name": "BilibiliDownloader-v2.1.1-portable.zip",
                           "browser_download_url": "u1", "size": 100},
                          {"name": "Source code (zip)", "browser_download_url": "u2"}]}
rel_beta = {"tag_name": "v2.2.0-beta1", "name": "Beta", "body": "b",
            "prerelease": True, "published_at": "2026-10-20T00:00:00Z",
            "assets": [{"name": "BilibiliDownloader-v2.2.0b-setup.exe",
                        "browser_download_url": "u3", "size": 200}]}
i_s = svc._select_release([rel_beta, rel_stable], CHANNEL_STABLE)
i_b = svc._select_release([rel_beta, rel_stable], CHANNEL_BETA)
assert i_s.version == "2.1.1", i_s.version
assert i_b.version == "2.2.0", i_b.version
assert i_s.default_asset.name.endswith("portable.zip"), i_s.default_asset.name
assert "source code" not in i_s.default_asset.name.lower()
assert build_proxies({"proxy_type": "none"}) is None
assert build_proxies({"proxy_type": "http", "proxy_host": "127.0.0.1",
                       "proxy_port": "8080"}) == {
    "http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"}
print("5) updater channel/asset/proxy OK")

# 错误路径：except 块里的 exc 被删除后，延迟回调必须仍能拿到异常对象
def _boom():
    raise ValueError("boom-msg")
err_holder = []
t = None
try:
    from utils.updater import _run_in_thread
    import utils.updater as up
    err_holder = []
    _run_in_thread(_boom, on_done=None, on_error=lambda e: err_holder.append(e))
    import time as _t
    _t.sleep(0.6)
    assert err_holder and isinstance(err_holder[0], ValueError), err_holder
    assert str(err_holder[0]) == "boom-msg"
except Exception as e:
    print("   ERROR-CAPTURE FAIL:", e)
    raise
print("6) error-capture lambda OK ->", type(err_holder[0]).__name__)

# ---------------------------------------------------------------- 7. 设置窗口
from ui.settings_window import SettingsWindow
sw = SettingsWindow(None, cm, None, None, None)
try:
    sw.show()
    app.processEvents()
    nav = sw.navigationInterface
    keys = []
    for rk in ("basic", "download", "options", "advanced", "update"):
        w = nav.widget(rk)
        keys.append(rk if w is not None else f"MISSING:{rk}")
    assert all(not k.startswith("MISSING") for k in keys), keys
    print("7) settings window OK  nav =", keys)

    # 更新页存在
    up_page = getattr(sw, "_update", None)
    assert up_page is not None
    assert sw._btn_check is not None and sw._btn_download is not None
    assert sw._update_browser is not None

    # 触发检查（网络失败也应安全降级到错误卡片）
    sw._update_check()
    app.processEvents()
    print("   update page widgets OK")

    # 手动驱动「发现新版本」分支
    from utils.updater import UpdateInfo as _UI
    fake = _UI(version="9.9.9", tag="v9.9.9", name="x", body="**hi**")
    sw._on_check_result(UpdateStatus.AVAILABLE, fake)
    app.processEvents()
    # 更新页子界面当前未切换到前台，isVisible() 会因父级隐藏而恒为 False；
    # 用 isHidden() 判断「是否被显式隐藏」才准确。
    assert not sw._btn_download.isHidden(), "下载按钮应可见"
    assert sw._btn_open.isHidden(), "「打开下载文件」此时应隐藏"
    assert "9.9.9" in sw._update_header.titleLabel.text()
    print("8) available-branch OK ->", sw._update_header.titleLabel.text())

    # 已是最新分支
    sw._on_check_result(UpdateStatus.UP_TO_DATE, None)
    app.processEvents()
    assert "最新" in sw._update_header.titleLabel.text()
    print("9) uptodate-branch OK ->", sw._update_header.titleLabel.text())

    # 错误分支
    sw._on_check_error(RuntimeError("net down"))
    app.processEvents()
    assert not sw._update_err_card.isHidden(), "错误卡片应可见"
    print("10) error-branch OK ->", sw._update_err_text.text())

    # 多语言刷新不炸
    sw._retranslate()
    app.processEvents()
    print("11) retranslate OK")
finally:
    sw.close()

# ---------------------------------------------------------------- 12. 更新对话框
from ui.update_dialog import UpdateDialog
from utils.updater import UpdateInfo as _UI2
dlg = UpdateDialog(None, _UI2(version="9.9.9", tag="v9.9.9", name="n",
                               body="# 标题\n正文"), UpdateService({"proxy_type": "none"}))
dlg.show()
app.processEvents()
dlg._on_progress(1024 * 1024, 4 * 1024 * 1024, 2 * 1024 * 1024, 1.5)
app.processEvents()
print("12) update dialog OK ->", dlg._prog_text.text())
dlg.close()

print("ALL_OK")
