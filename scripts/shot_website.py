#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离屏渲染网站展示截图：真实 Qt 控件 + 假数据，不污染用户配置。

为什么要离屏渲染，而不是让用户手动截图：
- 真实控件绘制，字体/圆角/图标全部与软件一致；
- 假任务由脚本注入，可重复生成、可同时出浅色 / 深色两套；
- 全程 offscreen，无需显示桌面。

关键坑位（改脚本前先读）：
1. ConfigManager / Logger 都按 cwd 落盘 —— 必须 chdir 到临时目录，否则会覆盖
   用户真实的 settings.json / download.log。
2. MainWindow._fit_window_to_screen() 只在 run() 里调用；本脚本不调用 run()，
   所以 resize(1440, 900) 不会被屏幕可用区 clamp 掉。
3. ui.theme 有 140ms 防抖提交器：首次 apply_theme 是同步的，之后切换必须
   显式 _flush_commit()，否则截到的是上一套主题。
4. offscreen 平台默认不扫描系统字体（families() 返回 0，中文全变豆腐块）：
   - QT_QPA_FONTDIR 能在 QApplication 前扫到目录内 ttf/otf；
   - 但 .ttc 字体合集不被目录扫描，中文必须 addApplicationFont 单独注册。

用法：
    <venv>/python.exe scripts/shot_website.py
输出：
    website/public/shots/
      main-light.png / main-dark.png       主界面
      settings-light.png / settings-dark.png  设置 · 基本设置
      update-light.png / update-dark.png      设置 · 更新（发现新版本）
"""
import os
import sys
import tempfile

# offscreen + 2x 缩放：必须在创建 QApplication 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "2")
# offscreen 平台默认不扫描系统字体库（见文件头坑位 4）
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# ConfigManager / Logger 按 cwd 落盘，切到临时目录以免覆盖用户配置
_SHOT_CWD = tempfile.mkdtemp(prefix="bd_shot_")
os.chdir(_SHOT_CWD)

from PySide6.QtWidgets import QApplication                      # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase, QPixmap         # noqa: E402
from PySide6.QtTest import QTest                                # noqa: E402

from config import ConfigManager                                # noqa: E402
from utils.logger import Logger                                 # noqa: E402
from utils.i18n import set_language                             # noqa: E402
from bili_api import BiliAPI                                    # noqa: E402
from download_engine import DownloadEngine                      # noqa: E402
from ui.list_layout import set_config as set_layout_config      # noqa: E402
from ui.theme import apply_theme, apply_appearance, _flush_commit  # noqa: E402
from ui.main_window import MainWindow                           # noqa: E402
from ui.settings_window import SettingsWindow                   # noqa: E402
from utils.updater import UpdateInfo, Asset, UpdateStatus       # noqa: E402

ACCENT = "#f07090"
OUT_DIR = os.path.join(ROOT, "website", "public", "shots")

# 主界面窗口逻辑尺寸（2x 导出 => 2880x1640）
WIN_W, WIN_H = 1440, 820

# 假任务：字段对齐 ui/queue_view.py 里 TaskDelegate 实际读取的键
# （title / uploader / category / duration / publish_time / view_count /
#   like_count / favorite_count / status / progress，progress 为 0~1 比例）
DEMO_TASKS = [
    {
        "id": "demo-1",
        "url": "https://www.bilibili.com/video/BV1xx411c7mD",
        "title": "【4K】城市夜景延时摄影 · 陆家嘴的二十四小时",
        "category": "视频",
        "uploader": "光影记录者",
        "duration": 1284,
        "publish_time": "2026-10-28",
        "view_count": 1284000,
        "like_count": 86400,
        "favorite_count": 21300,
        "status": "downloading",
        "progress": 0.68,
    },
    {
        "id": "demo-2",
        "url": "https://www.bilibili.com/video/BV1yy411c7mE",
        "title": "从零实现一个 Fluent 风格的桌面播放器（第一集）",
        "category": "课程",
        "uploader": "代码实验室",
        "duration": 2436,
        "publish_time": "2026-10-25",
        "view_count": 356000,
        "like_count": 24800,
        "favorite_count": 9120,
        "status": "downloading",
        "progress": 0.32,
    },
    {
        "id": "demo-3",
        "url": "https://www.bilibili.com/video/BV1zz411c7mF",
        "title": "深夜电台 · 适合写代码的轻音乐合集（第三期）",
        "category": "音频",
        "uploader": "深夜电台",
        "duration": 10800,
        "publish_time": "2026-10-20",
        "view_count": 892000,
        "like_count": 51200,
        "favorite_count": 30700,
        "status": "waiting",
        "progress": 0.0,
    },
    {
        "id": "demo-4",
        "url": "https://www.bilibili.com/bangumi/play/ep123456",
        "title": "【番剧】小镇日常 · 第一话「夏日的风铃」",
        "category": "番剧",
        "uploader": "番剧研究所",
        "duration": 1440,
        "publish_time": "2026-10-18",
        "view_count": 2340000,
        "like_count": 156000,
        "favorite_count": 88000,
        "status": "waiting",
        "progress": 0.0,
    },
]

# 每条任务的模拟速度（字节/秒），用于底部「总速度」标签
DEMO_SPEEDS = [6.2 * 1024 * 1024, 3.4 * 1024 * 1024, 0, 0]

# 设置窗口逻辑尺寸（2x 导出原始 1960x1400，截图时裁掉顶部 48px 标题栏 => 1960x1304）
SET_W, SET_H = 980, 700

# 更新页演示数据：构造一个「发现新版本」状态（不联网、不触发下载）
DEMO_UPDATE = UpdateInfo(
    version="2.1.1.1",
    tag="v2.1.1.1",
    name="BilibiliDownloader v2.1.1.1",
    body=(
        "### 新增\n"
        "- 内置更新检查：支持 **稳定版 / 测试版** 两条通道\n"
        "- 发现新版本后可查看更新日志，并一键下载安装\n\n"
        "### 优化\n"
        "- 默认强调色改为软件图标的粉色，界面观感更统一\n"
        "- 精简安装包内的 FFmpeg 组件，安装体积更小\n\n"
        "### 修复\n"
        "- 修复若干细节问题，提升稳定性"
    ),
    published_at="2026-10-31",
    prerelease=False,
    assets=[
        Asset(name="BilibiliDownloader_Setup_v2.1.2.exe",
              url="https://example.invalid/setup.exe", size=98 * 1024 * 1024),
        Asset(name="BilibiliDownloader_v2.1.2_portable.zip",
              url="https://example.invalid/portable.zip", size=112 * 1024 * 1024),
    ],
)

# 假封面配色：(顶部色, 底部色, [(光斑x, 光斑y, 半径, 颜色), ...])
_COVER_SPECS = [
    ((14, 22, 48), (40, 18, 72), [(120, 78, 130, (78, 62, 216)), (382, 205, 110, (236, 88, 158))]),
    ((52, 30, 10), (116, 54, 12), [(112, 72, 128, (255, 168, 64)), (400, 208, 118, (255, 112, 44))]),
    ((26, 16, 44), (62, 20, 62), [(140, 88, 148, (166, 82, 250)), (356, 182, 118, (255, 92, 138))]),
    ((10, 30, 34), (14, 62, 54), [(110, 80, 132, (46, 200, 170)), (390, 200, 112, (120, 240, 190))]),
]


def _load_fonts():
    """补注册中文 .ttc 合集（QT_QPA_FONTDIR 只扫 ttf/otf，不含 ttc）。"""
    if sys.platform != "win32":
        return
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)


def _make_covers(dirpath):
    """生成抽象渐变封面：不联网、不涉及他人版权，仅用于界面演示。"""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    os.makedirs(dirpath, exist_ok=True)
    w, h = 480, 270
    paths = []
    for i, (top, bottom, blobs) in enumerate(_COVER_SPECS):
        img = Image.new("RGB", (w, h))
        d = ImageDraw.Draw(img)
        for y in range(h):
            t = y / (h - 1)
            d.line([(0, y), (w, y)],
                   fill=tuple(int(top[k] + (bottom[k] - top[k]) * t) for k in range(3)))

        # 柔光斑
        glow = Image.new("RGB", (w, h), (0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for cx, cy, r, col in blobs:
            gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
        glow = glow.filter(ImageFilter.GaussianBlur(58))
        img = ImageChops.add(img, glow)

        # 斜向高光
        gloss = Image.new("L", (w, h), 0)
        ImageDraw.Draw(gloss).polygon(
            [(0, h), (w * 0.55, 0), (w * 0.78, 0), (w * 0.2, h)], fill=26)
        gloss = gloss.filter(ImageFilter.GaussianBlur(18))
        img = Image.composite(Image.new("RGB", (w, h), (255, 255, 255)), img, gloss)

        path = os.path.join(dirpath, f"cover{i + 1}.png")
        img.save(path, "PNG")
        paths.append(path)
    return paths


def _make_avatar(path, size=160):
    """生成粉紫渐变圆形头像（演示用，不涉及真实用户）。"""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (size, size), (240, 112, 144))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2.0
    r_out = size / 2.0
    for i in range(int(r_out), 0, -1):
        t = i / r_out
        col = (int(255 - 15 * t), int(214 - 102 * t), int(228 - 84 * t))
        d.ellipse([cx - i, cy - i, cx + i, cy + i], fill=col)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    out.save(path, "PNG")
    return path


def _set_user_card(card, title, subtitle, avatar_path=None):
    """改侧边栏用户卡文案。

    NavigationUserCard 的标题不是 QLabel，而是 paintEvent 用 _title/_subtitle 自绘，
    所以必须走 setTitle/setSubtitle（旧写法 titleLabel.setText 会静默失效）。
    """
    for meth, val in (("setTitle", title), ("setSubtitle", subtitle)):
        fn = getattr(card, meth, None)
        if fn is not None:
            try:
                fn(val)
            except Exception:
                pass

    if avatar_path:
        avatar = getattr(card, "avatar", None)
        if avatar is not None:
            try:
                avatar.setImage(QPixmap(avatar_path))
            except Exception:
                pass
    try:
        card.update()
    except Exception:
        pass


def _set_appearance_label(sw, label):
    """把设置页「外观」下拉框改到指定项（浅色/深色），使其与截图主题一致。

    「外观」下拉框读取 config.appearance，截图脚本切主题时不经过它，导致深色
    截图里下拉框仍显示「浅色」。这里按选项内容定位该 ComboBox 并改值（不重建
    窗口——离屏下重建 SettingsWindow 会崩溃）。
    """
    try:
        from qfluentwidgets import ComboBox
        for cb in sw._basic.findChildren(ComboBox):
            texts = [cb.itemText(i) for i in range(cb.count())]
            if "浅色" in texts and "深色" in texts:
                if cb.currentText() != label:
                    # 阻断信号：只改显示值，不触发 _on_appearance 里的 setTheme
                    # （主题已由 _set_mode 应用；重复 setTheme 会在离屏析构时崩溃）。
                    cb.blockSignals(True)
                    cb.setCurrentText(label)
                    cb.blockSignals(False)
                return True
    except Exception:
        pass
    return False


def _safe_excepthook(etype, value, tb):
    """离屏截图时不允许 excepthook 弹模态错误框（offscreen 下会永久阻塞）。
    只打印异常，便于暴露渲染过程中的真实错误。"""
    import traceback as _tb
    _tb.print_exception(etype, value, tb)


def _pump(app, rounds=10):
    for _ in range(rounds):
        app.processEvents()


def _shot(app, widget, path, crop_top=0):
    """抓图并保存。

    crop_top：按「逻辑像素」裁掉顶部（用于去掉 MSFluentWindow 顶部 48px 标题栏：
    离屏 + 深色下标题栏底色不随 setTheme 刷新，会留一条白边）。实际像素会按
    pixmap 的 devicePixelRatio 换算。
    """
    _pump(app)
    pix = widget.grab()
    if crop_top:
        cut = int(round(crop_top * (pix.devicePixelRatio() or 1)))
        cut = max(0, min(cut, pix.height() - 1))
        if cut:
            pix = pix.copy(0, cut, pix.width(), pix.height() - cut)
    pix.save(path, "PNG")
    print(f"  saved {os.path.basename(path):18s} {pix.width()}x{pix.height()}")
    return pix


def build_main_window(app, config, logger, api, engine, covers, avatar_path):
    engine.queue[:] = DEMO_TASKS
    win = MainWindow(config, logger, api, engine)
    # MainWindow.__init__ 把 sys.excepthook 接成「弹模态错误框」，离屏环境会永久
    # 阻塞。截图脚本改为只打印异常，避免渲染期间任何未捕获异常卡死进程。
    sys.excepthook = _safe_excepthook

    # 封面：直接塞进缩略图缓存，避免 delegate 走网络加载 / 显示灰占位块
    for task, path in zip(DEMO_TASKS, covers):
        task["thumbnail"] = path
        win.queue_view._thumbs[path] = QPixmap(path)

    # 运行态 + 速度：让总进度条、总速度、底部按钮呈现真实「下载中」
    engine.is_running = True
    win._task_speeds = {t["url"]: spd for t, spd in zip(DEMO_TASKS, DEMO_SPEEDS)}
    win._on_queue_status(engine.queue)
    win.queue_view._list.viewport().update()

    _set_user_card(win.sidebar.user_card, "哔哩哔哩用户", "UID 10000000", avatar_path)
    win.window.resize(WIN_W, WIN_H)
    win.window.show()
    # 侧边栏展开动画会让用户卡文字从 opacity 0 淡入（200ms），
    # processEvents 不推进真实时间，必须 qWait 等它走完，否则截不到用户名。
    QTest.qWait(420)
    _pump(app, 8)
    return win


def build_settings_window(app, config):
    """构造设置窗口（独立顶层，parent=None），并切到「基本设置」。"""
    def _noop_preview(_payload):
        pass

    sw = SettingsWindow(
        None, config,
        on_language_change=lambda _code: None,
        on_settings_changed=lambda: None,
        preview_theme=_noop_preview,
        on_open_logs=lambda: None,
        on_stay_on_top=lambda _v: None,
    )
    sw.resize(SET_W, SET_H)
    sw.show()
    QTest.qWait(300)          # 等导航展开/卡片入场动画走完
    _pump(app, 8)
    try:
        sw.switchTo(sw._basic)
    except Exception:
        pass
    QTest.qWait(120)
    _pump(app, 6)
    return sw


def show_update_state(app, sw):
    """把更新页切到「发现新版本 2.1.2」，用于演示截图。"""
    try:
        sw.switchTo(sw._update)
    except Exception:
        pass
    print("    ..switched to update page", flush=True)
    QTest.qWait(120)
    try:
        sw._on_check_result(UpdateStatus.AVAILABLE, DEMO_UPDATE)
    except Exception as e:      # 演示态注入失败不该中断截图
        print("  [warn] update state inject failed:", e)
    print("    ..injected update state", flush=True)
    # 更新日志是 MarkdownBrowser，等它异步排版完
    QTest.qWait(260)
    _pump(app, 8)
    print("    ..pumped", flush=True)


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    _load_fonts()
    app.setFont(QFont("Microsoft YaHei UI", 9))
    set_language("zh_CN")

    os.makedirs(OUT_DIR, exist_ok=True)
    covers = _make_covers(os.path.join(_SHOT_CWD, "covers"))
    avatar_path = _make_avatar(os.path.join(_SHOT_CWD, "avatar.png"))

    config = ConfigManager()
    config.set("accent_color", ACCENT)
    config.set("appearance", "light")
    set_layout_config(config)

    # 首次 apply_theme 走同步提交（_QSS_READY=False），基线由此建立
    apply_theme(ACCENT, "light")

    logger = Logger(log_file="shot.log")
    api = BiliAPI("", validate=False)
    engine = DownloadEngine(config, logger, api)

    def _set_mode(mode):
        """切换明暗并强制提交（否则截到上一套主题）。"""
        apply_appearance(mode)
        _flush_commit()
        QTest.qWait(180)
        _pump(app, 10)

    print("[1/6] 主界面（浅色）")
    win = build_main_window(app, config, logger, api, engine, covers, avatar_path)
    _shot(app, win.window, os.path.join(OUT_DIR, "main-light.png"))

    print("[2/6] 主界面（深色）")
    _set_mode("dark")
    _shot(app, win.window, os.path.join(OUT_DIR, "main-dark.png"))

    # ---- 设置窗口（浅色）----
    _set_mode("light")
    config.set("appearance", "light")
    print("[3/6] 设置 · 基本设置（浅色）")
    sw = build_settings_window(app, config)
    # MSFluentWindow 顶部固定 48px 给标题栏（setContentsMargins(0,48,0,0)）。
    # 离屏下标题栏底色未必跟随主题，统一裁掉，只保留内容区。
    _tb_h = 48
    _shot(app, sw, os.path.join(OUT_DIR, "settings-light.png"), crop_top=_tb_h)

    print("[4/6] 设置 · 更新（浅色）")
    show_update_state(app, sw)
    _shot(app, sw, os.path.join(OUT_DIR, "update-light.png"), crop_top=_tb_h)

    print("[5/6] 设置 · 更新（深色）")
    _set_mode("dark")
    # 外观下拉框读 config.appearance，深色画面里若仍显示「浅色」会自相矛盾；
    # 直接改下拉框（复用一个窗口，离屏重建 SettingsWindow 会崩溃）。
    _set_appearance_label(sw, "深色")
    QTest.qWait(120)
    _pump(app, 6)
    _shot(app, sw, os.path.join(OUT_DIR, "update-dark.png"), crop_top=_tb_h)

    print("[6/6] 设置 · 基本设置（深色）")
    try:
        sw.switchTo(sw._basic)
    except Exception:
        pass
    QTest.qWait(140)
    _pump(app, 6)
    _shot(app, sw, os.path.join(OUT_DIR, "settings-dark.png"), crop_top=_tb_h)

    print("done ->", OUT_DIR, flush=True)


if __name__ == "__main__":
    main()
