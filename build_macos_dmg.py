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
import time

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
        "--noconfirm",
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


def prune_app(app_path):
    """删除 .app 中未使用的 Qt 翻译/示例数据，缩小体积、加快 codesign 与打包。

    本项目翻译走自己的 .po -> utils/locales_weblate.py，不依赖 Qt 的 .qm，
    因此 Qt/translations 下 100+ 语言的 .qm（几十 MB）和 examples 可安全删除。
    """
    res = os.path.join(app_path, "Contents", "Resources")
    for cand in (
        os.path.join(res, "PySide6", "Qt", "translations"),
        os.path.join(res, "PySide6", "examples"),
    ):
        if os.path.isdir(cand):
            shutil.rmtree(cand, ignore_errors=True)
    # 兜底：删除任何残留的 .qm
    for root, _dirs, files in os.walk(res):
        for f in files:
            if f.endswith(".qm"):
                try:
                    os.remove(os.path.join(root, f))
                except OSError:
                    pass


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
    # macos-14 / macos-15-intel 跑出两种架构（macos-13 已于 2025-12 下线），
    # 产物名带后缀避免互相覆盖。
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

    # 裁剪未使用的 Qt 数据（翻译/示例），缩小 .app，加快后续 codesign 与打包
    prune_app(app)

    codesign_app(app)

    # .app.zip（便于直接下载）
    zip_base = os.path.join(DIST, "%s-macos-%s" % (NAME, arch))
    shutil.make_archive(zip_base, "zip", root_dir=DIST, base_dir=NAME + ".app")

    # .dmg（含 /Applications 快捷方式）
    # 先在临时目录(WORK)生成 .dmg，再移动到 DIST——
    # 避免把输出文件放在正被 -srcfolder 包含的源目录(DIST)里，
    # 否则 hdiutil 边读源目录边写目标会触发 Resource busy。
    stage = os.path.join(WORK, "dmgstage")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    # Applications 快捷方式（仅一个软链，不复制 .app 内容）
    link = os.path.join(stage, "Applications")
    if not os.path.exists(link):
        os.symlink("/Applications", link)
    # 临时与最终路径分离
    out_dmg_final = os.path.join(DIST, "%s-macos-%s.dmg" % (NAME, arch))
    out_dmg_tmp = os.path.join(WORK, "%s-macos-%s.dmg" % (NAME, arch))
    if os.path.exists(out_dmg_tmp):
        os.remove(out_dmg_tmp)
    # 重试逻辑：应对 CI 环境偶发的短暂文件系统锁定(Resource busy)
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            run(["hdiutil", "create", "-volname", NAME,
                 "-srcfolder", app, "-srcfolder", stage, "-ov", "-format", "UDZO", out_dmg_tmp])
            break
        except subprocess.CalledProcessError as e:
            if attempt < max_attempts:
                print("WARN: hdiutil create failed (attempt %d), retrying..." % attempt, flush=True)
                time.sleep(2 * attempt)
            else:
                # 最后一次仍失败则抛出，保持原有 CI 报错可定位行为
                raise
    # 移动到最终目录（覆盖现有同名文件）
    if os.path.exists(out_dmg_final):
        os.remove(out_dmg_final)
    shutil.move(out_dmg_tmp, out_dmg_final)

    print("\n=== DMG BUILD SUCCESS ===")
    for p in (out_dmg_final, zip_base + ".zip"):
        if os.path.exists(p):
            print("产物:", p, "(%.1f MB)" % (os.path.getsize(p) / 1e6))


if __name__ == "__main__":
    build_dmg()
