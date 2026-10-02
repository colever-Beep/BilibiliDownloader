"""Headless build driver for auto-py-to-exe.

Uses auto_py_to_exe.packaging.package() (the same engine auto-py-to-exe GUI
uses) so we don't need to open the browser GUI. The command string MUST start
with the literal token "pyinstaller" because package() drops index 0 before
passing args to PyInstaller.
"""
import os
import sys
import shlex
import glob
import subprocess

import auto_py_to_exe.config as ape_config
from auto_py_to_exe.packaging import package

ROOT = r"D:\VScode\b"

# Where PyInstaller does its temp work (build/spec/dist staging)
ape_config.temporary_directory = os.path.join(ROOT, ".build_tmp")
os.makedirs(ape_config.temporary_directory, exist_ok=True)

# Final output folder for the .exe
OUT_DIR = os.path.join(ROOT, "dist")
os.makedirs(OUT_DIR, exist_ok=True)

# 构建前用 .po 重新烘焙 i18n（无依赖；失败不影响打包）
try:
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "i18n_tools.py"), "bake"],
        check=False,
    )
except Exception:
    pass

# ---- Data files (SOURCE;DEST) ----
datas = []
# 注意：ffmpeg 不打包进 exe（缩小体积），运行时由 utils/ffmpeg_provider
# 优先从 exe 同目录 bin/ 读取，缺失则后台从官方构建下载解压到 bin/；
# 开发态则读 项目根/bin/。用户也可手动把 ffmpeg.exe 放进 bin/ 回退。
# i18n locale fragments -> bundle root utils/ (i18n.py globs locales_*.py here)
for loc in glob.glob(os.path.join(ROOT, "utils", "locales_*.py")):
    datas.append(f"{loc};utils")
# 应用图标 icon.ico：源文件保留在根目录（D:\VScode\b\icon.ico）不随包作为松散文件分发，
# 但需随包进入 _MEIPASS 临时目录，供运行时 resource_path("icon.ico") 取到 -> 窗口标题栏图标生效。
# 同时用 --icon 把图标嵌入 exe（任务栏 / 资源管理器图标）。dist 根目录不出现松散 icon.ico。
ICON = os.path.join(ROOT, "icon.ico")
if os.path.exists(ICON):
    datas.append(f"{ICON};.")

# 未登录占位头像 not_logged_in.jpeg（根目录），随包进入 _MEIPASS，供 resource_path("not_logged_in.jpeg") 取到
PLACEHOLDER_AVATAR = os.path.join(ROOT, "not_logged_in.jpeg")
if os.path.exists(PLACEHOLDER_AVATAR):
    datas.append(f"{PLACEHOLDER_AVATAR};.")

# ---- Hidden imports that may be missed by the static finder ----
hidden = [
    "PySide6",
    "shiboken6",
    "win10toast",
    "pyperclip",
    "qrcode",
    "segno",
    "requests",
    # 图标体系（bili23 同款 qfluentwidgets FluentIcon）+ 编译后的 Qt 资源
    "qfluentwidgets",
    "res.resources_rc",
]

args = ["pyinstaller", os.path.join(ROOT, "main.py")]
args += ["--onefile", "--noconsole", "--clean"]
args += ["--name", "BiliDownloader"]
if os.path.exists(ICON):
    args += ["--icon", ICON]
for d in datas:
    args += ["--add-data", d]
for h in hidden:
    args += ["--hidden-import", h]
args += ["--collect-data", "PySide6"]
args += ["--collect-data", "qfluentwidgets"]
args += ["--exclude-module", "bili23_example"]

command = shlex.join(args)
print("=== auto-py-to-exe command ===")
print(command)
print("===============================")

options = {
    "increaseRecursionLimit": True,
    "outputDirectory": OUT_DIR,
}

ok = package(command, options)
print("\n=== PACKAGING", "SUCCESS" if ok else "FAILED", "===")
