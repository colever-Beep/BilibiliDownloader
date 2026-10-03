#!/usr/bin/env python3
"""macOS .dmg / .app 打包脚本（必须在 macOS 上运行）。

流程：
1. bake i18n（用 .po 重新生成 utils/locales_weblate.py，失败不阻断）。
2. icon.ico -> iconset（多尺寸 PNG）-> iconutil -> app.icns（.app 图标）。
3. 直接调用 PyInstaller（不用 auto-py-to-exe，Windows 专用）--windowed 生成 .app。
   - 排除 win10toast（Windows 专有，本项目实际未用；通知走 QSystemTrayIcon）。
4. ad-hoc 签名（codesign --sign -）：Apple Silicon 上未签名的 .app 会被系统直接杀，
   签名是必须的（分发只需 ad-hoc，无需付费开发者证书）。
5. hdiutil create 生成 .dmg（含 /Applications 快捷方式，拖拽安装），
   同时输出一个 .app.zip 便于直接下载使用。

ffmpeg 不内置：沿用 utils/ffmpeg_provider 首次运行按平台自动下载；.app 是签名只读包，
ffmpeg_provider 会写入 ~/Library/Application Support/BilibiliDownloader/bin。
"""
import glob
import os
import platform
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "BilibiliDownloader"
WORK = os.path.join(ROOT, ".build_tmp")
DIST = os.path.join(ROOT, "dist")
SEP = ":"  # Unix --add-data 分隔符


def die(msg):
    print("ERROR:", msg, file=sys.stderr)
    sys.exit(1)


def run(cmd):
    printable = " ".join(str(c) for c in cmd)
    print("$", printable, flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def require_macos():
    if sys.platform != "darwin":
        die("dmg 必须在 macOS 上构建；当前 sys.platform=%s" % sys.platform)


def bake_i18n():
    try:
        run([sys.executable, os.path.join(ROOT, "scripts", "i18n_tools.py"), "bake"])
    except Exception as e:
        print("WARN: i18n bake 失败，继续打包：", e)


def make_icns(ico_path, out_icns):
    """icon.ico -> 多尺寸 iconset -> iconutil -> .icns。"""
    from PIL import Image
    base = os.path.splitext(out_icns)[0]
    iconset = base + ".iconset"
    shutil.rmtree(iconset, ignore_errors=True)
    os.makedirs(iconset)
    img = Image.open(ico_path).convert("RGBA")
    # (图标逻辑边长, 像素倍率) -> 文件名
    specs = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
             (256, 1), (256, 2), (512, 1), (512, 2)]
    for size, scale in specs:
        px = size * scale
        im = img.copy()
        im.thumbnail((px, px), Image.LANCZOS)
        canvas = Image.new("RGBA", (px, px), (0, 0, 0, 0))
        canvas.paste(im, ((px - im.width) // 2, (px - im.height) // 2), im)
        suffix = "" if scale == 1 else "@%dx" % scale
        canvas.save(os.path.join(iconset, "icon_%dx%d%s.png" % (size, size, suffix)))
    run(["iconutil", "-c", "icns", iconset, "-o", out_icns])
    shutil.rmtree(iconset, ignore_errors=True)


def pyinstaller_args(icns_path):
    datas = []
    for loc in glob.glob(os.path.join(ROOT, "utils", "locales_*.py")):
        datas.append(loc + SEP + "utils")
    for f in ("icon.ico", "not_logged_in.jpeg"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            datas.append(p + SEP + ".")
    hidden = [
        "PySide6", "shiboken6", "pyperclip", "qrcode", "segno", "requests",
        "qfluentwidgets", "res.resources_rc",
    ]
    args = [
        "pyinstaller", os.path.join(ROOT, "main.py"),
        "--noconfirm", "--clean",
        "--windowed",
        "--name", NAME,
        "--distpath", DIST,
        "--workpath", os.path.join(WORK, "pyi"),
        "--specpath", os.path.join(WORK, "pyi"),
    ]
    if os.path.exists(icns_path):
        args += ["--icon", icns_path]
    for d in datas:
        args += ["--add-data", d]
    for h in hidden:
        args += ["--hidden-import", h]
    args += ["--collect-data", "PySide6"]
    args += ["--collect-data", "qfluentwidgets"]
    args += ["--exclude-module", "bili23_example"]
    return args


def codesign_app(app_path):
    """ad-hoc 签名（分发够用；Apple Silicon 必需）。"""
    try:
        run(["codesign", "--force", "--deep", "--sign", "-", app_path])
    except subprocess.CalledProcessError:
        # 极少数环境无 codesign 时不阻断，仅提示
        print("WARN: ad-hoc 签名失败，.app 在 Apple Silicon 上可能无法运行")


def build_dmg():
    require_macos()
    os.makedirs(DIST, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)

    # 架构后缀：Apple Silicon 为 arm64，Intel 为 x86_64。CI 矩阵分别用
    # macos-14 / macos-13 跑出两种架构，产物名带后缀避免互相覆盖。
    arch = platform.machine()
    if arch not in ("arm64", "x86_64"):
        arch = "x86_64"

    bake_i18n()

    icns = os.path.join(WORK, "app.icns")
    ico = os.path.join(ROOT, "icon.ico")
    if os.path.exists(ico):
        make_icns(ico, icns)
    else:
        print("WARN: 未找到 icon.ico，.app 使用默认图标")

    # PyInstaller -> .app
    run(pyinstaller_args(icns))
    app = os.path.join(DIST, NAME + ".app")
    if not os.path.isdir(app):
        die("PyInstaller 未产出预期 .app：%s" % app)

    codesign_app(app)

    # .app.zip（便于直接下载）
    zip_base = os.path.join(DIST, "%s-macos-%s" % (NAME, arch))
    shutil.make_archive(zip_base, "zip", root_dir=DIST, base_dir=NAME + ".app")

    # .dmg（含 /Applications 快捷方式）
    stage = os.path.join(WORK, "dmgstage")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    # 拷贝 .app（不能用符号链接，dmg 里要真实内容）
    shutil.copytree(app, os.path.join(stage, NAME + ".app"), symlinks=True)
    # Applications 快捷方式
    link = os.path.join(stage, "Applications")
    if not os.path.exists(link):
        os.symlink("/Applications", link)
    out_dmg = os.path.join(DIST, "%s-macos-%s.dmg" % (NAME, arch))
    if os.path.exists(out_dmg):
        os.remove(out_dmg)
    run(["hdiutil", "create", "-volname", NAME,
         "-srcfolder", stage, "-ov", "-format", "UDZO", out_dmg])

    print("\n=== DMG BUILD SUCCESS ===")
    for p in (out_dmg, zip_base + ".zip"):
        if os.path.exists(p):
            print("产物:", p, "(%.1f MB)" % (os.path.getsize(p) / 1e6))


if __name__ == "__main__":
    build_dmg()
