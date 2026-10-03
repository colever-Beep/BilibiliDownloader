"""便携版打包驱动（onedir 模式）。

与 build_exe.py 使用同一 auto-py-to-exe 引擎，区别：
- 不加 --onefile → 产物为 dist/BilibiliDownloader/ 文件夹（exe + _internal），
  启动无需解压临时目录，双击即用，适合压缩成 zip 分发的便携版。
- ffmpeg 仍不打包（体积考虑），首次使用时由 utils/ffmpeg_provider 自动
  下载到 exe 同目录 bin/；离线用户可手动放入。
"""
import os
import sys
import shlex
import glob
import subprocess

import auto_py_to_exe.config as ape_config
from auto_py_to_exe.packaging import package

# 动态取本脚本所在目录作为项目根：兼容本地 D:\VScode\b，也能在 CI runner 的
# 任意检出路径下工作。切勿写死绝对路径，否则非本机环境打包会写入不存在的目录而崩溃。
ROOT = os.path.dirname(os.path.abspath(__file__))

ape_config.temporary_directory = os.path.join(ROOT, ".build_tmp")
os.makedirs(ape_config.temporary_directory, exist_ok=True)

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
args += ["--noconsole"]  # 默认 onedir：dist/BilibiliDownloader/（--clean 会被沙箱删除拦截器挡住，构建前手动清 .build_tmp 即可）
args += ["--name", "BilibiliDownloader"]
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
