#!/usr/bin/env python3
"""AppImage 打包脚本（必须在 Linux 上运行；Windows/macOS 上请改用 build_exe.py /
build_macos_dmg.py）。

流程：
1. bake i18n（用 .po 重新生成 utils/locales_weblate.py，无依赖，失败不阻断）。
2. icon.ico -> 256x256 PNG（Pillow，供 AppImage 桌面图标用）。
3. 直接调用 PyInstaller（不用 auto-py-to-exe，那是 Windows 专用）onedir 模式打包。
   - Unix 下 --add-data 分隔符为 ':'（不是 Windows 的 ';'）。
   - 排除 win10toast（Windows 专有，且本项目实际未用到；通知走 QSystemTrayIcon）。
4. 组装 AppDir（AppRun + .desktop + 图标 + onedir 产物），再用 appimagetool 打成
   单文件 .AppImage。

ffmpeg 不内置：沿用 utils/ffmpeg_provider 首次运行按平台自动下载。AppImage 运行时
挂载为只读 squashfs，ffmpeg_provider 会检测 $APPIMAGE 并写入 XDG 数据目录，不会写
进只读挂载点。
"""
import glob
import os
import platform
import shutil
import stat
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "BilibiliDownloader"
ICON_NAME = "bilibili-downloader"
WORK = os.path.join(ROOT, ".build_tmp")
DIST = os.path.join(ROOT, "dist")
APPDIR = os.path.join(WORK, "AppDir")
SEP = ":"  # Unix --add-data 分隔符


def die(msg):
    print("ERROR:", msg, file=sys.stderr)
    sys.exit(1)


def run(cmd):
    printable = " ".join(str(c) for c in cmd)
    print("$", printable, flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def require_linux():
    if sys.platform != "linux":
        die("AppImage 必须在 Linux 上构建；当前 sys.platform=%s" % sys.platform)


def bake_i18n():
    try:
        run([sys.executable, os.path.join(ROOT, "scripts", "i18n_tools.py"), "bake"])
    except Exception as e:
        print("WARN: i18n bake 失败，继续打包：", e)


def make_icon_png(ico_path, out_png, size=256):
    """icon.ico -> 居中方形透明 PNG（AppImage 桌面图标）。"""
    from PIL import Image
    img = Image.open(ico_path).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    canvas.save(out_png)


def pyinstaller_args(png_path):
    datas = []
    for loc in glob.glob(os.path.join(ROOT, "utils", "locales_*.py")):
        datas.append(loc + SEP + "utils")
    for f in ("icon.ico", "not_logged_in.jpeg"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            datas.append(p + SEP + ".")
    # Windows 专有 win10toast 不列入（不存在于 Linux，PyInstaller 会报缺 hidden import）
    hidden = [
        "PySide6", "shiboken6", "pyperclip", "qrcode", "segno", "requests",
        "qfluentwidgets", "res.resources_rc",
    ]
    args = [
        "pyinstaller", os.path.join(ROOT, "main.py"),
        "--noconfirm", "--clean",
        "--name", NAME,
        "--distpath", DIST,
        "--workpath", os.path.join(WORK, "pyi"),
        "--specpath", os.path.join(WORK, "pyi"),
    ]
    if os.path.exists(os.path.join(ROOT, "icon.ico")):
        args += ["--icon", os.path.join(ROOT, "icon.ico")]
    for d in datas:
        args += ["--add-data", d]
    for h in hidden:
        args += ["--hidden-import", h]
    args += ["--collect-data", "PySide6"]
    args += ["--collect-data", "qfluentwidgets"]
    args += ["--exclude-module", "bili23_example"]
    return args


APPRUN = """#!/bin/sh
# AppImage 入口：转交到 PyInstaller onedir 产物
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/{name}" "$@"
"""

DESKTOP = """[Desktop Entry]
Type=Application
Name={name}
Name[zh_CN]=BilibiliDownloader（B 站下载器）
Comment=Bilibili content downloader
Exec={name}
Icon={icon}
Categories=Network;FileTransfer;AudioVideo;
Terminal=false
"""


def appimagetool_url():
    m = platform.machine().lower()
    if m in ("aarch64", "arm64"):
        return ("https://github.com/AppImage/AppImageKit/releases/download/continuous/"
                "appimagetool-aarch64.AppImage")
    return ("https://github.com/AppImage/AppImageKit/releases/download/continuous/"
            "appimagetool-x86_64.AppImage")


def fetch_appimagetool(dest):
    url = appimagetool_url()
    print("下载 appimagetool:", url, flush=True)
    urllib.request.urlretrieve(url, dest)
    os.chmod(dest, os.stat(dest).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def build_appimage():
    require_linux()
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    os.makedirs(DIST, exist_ok=True)

    bake_i18n()

    png = os.path.join(WORK, ICON_NAME + ".png")
    ico = os.path.join(ROOT, "icon.ico")
    if os.path.exists(ico):
        make_icon_png(ico, png)
    else:
        print("WARN: 未找到 icon.ico，AppImage 将不带图标")

    # PyInstaller onedir
    run(pyinstaller_args(png))
    onedir = os.path.join(DIST, NAME)
    if not os.path.isdir(onedir):
        die("PyInstaller 未产出预期目录：%s" % onedir)

    # 组装 AppDir
    shutil.rmtree(APPDIR, ignore_errors=True)
    os.makedirs(APPDIR)
    # 拷贝 onedir 全部内容（可执行文件 + _internal/）
    for item in os.listdir(onedir):
        src = os.path.join(onedir, item)
        dst = os.path.join(APPDIR, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
            if item == NAME:
                os.chmod(dst, os.stat(dst).st_mode | stat.S_IEXEC)
    # AppRun
    apprun = os.path.join(APPDIR, "AppRun")
    with open(apprun, "w", encoding="utf-8") as f:
        f.write(APPRUN.format(name=NAME))
    os.chmod(apprun, 0o755)
    # .desktop
    with open(os.path.join(APPDIR, NAME + ".desktop"), "w", encoding="utf-8") as f:
        f.write(DESKTOP.format(name=NAME, icon=ICON_NAME))
    # 图标（appimagetool 按 desktop 的 Icon 名在 AppDir 根找 <name>.png/.svg/.DirIcon）
    if os.path.exists(png):
        shutil.copy2(png, os.path.join(APPDIR, ICON_NAME + ".png"))

    # appimagetool 打包（GitHub Actions 等无 FUSE 环境需 EXTRACT_AND_RUN）
    tool = os.path.join(WORK, "appimagetool")
    fetch_appimagetool(tool)
    arch = "aarch64" if platform.machine().lower() in ("aarch64", "arm64") else "x86_64"
    out = os.path.join(DIST, "%s-%s.AppImage" % (NAME, arch))
    if os.path.exists(out):
        os.remove(out)
    env = dict(os.environ, APPIMAGE_EXTRACT_AND_RUN="1")
    cmd = [tool, "--no-appstream", APPDIR, out]
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, env=env)

    print("\n=== APPIMAGE BUILD SUCCESS ===")
    print("产物:", out, "(%.1f MB)" % (os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    build_appimage()
