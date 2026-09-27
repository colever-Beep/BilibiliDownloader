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

ROOT = r"F:\b"

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
# 注意：ffmpeg 不再打包进 exe（缩小体积），首次使用时由 utils/ffmpeg_provider
# 后台从官方构建下载并解压到 exe 同目录 bin/；用户也可手动放入 bin/ 回退。
# i18n locale fragments -> bundle root utils/ (i18n.py globs locales_*.py here)
for loc in glob.glob(os.path.join(ROOT, "utils", "locales_*.py")):
    datas.append(f"{loc};utils")
# 应用图标：打包进 exe 资源（--icon）使其显示为文件/任务栏图标，
# 同时作为 --add-data 随包分发，运行时用 resource_path("icon.ico") 取窗口标题栏图标。
ICON = os.path.join(ROOT, "icon.ico")
datas.append(f"{ICON};.")

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
