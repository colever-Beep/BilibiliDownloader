#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from ui.main_window import MainWindow
from ui.theme import apply_theme, set_root_window
from config import ConfigManager
from utils.logger import Logger
from utils.i18n import set_language
from utils.resources import get_app_icon_path
from bili_api import BiliAPI
from download_engine import DownloadEngine
from utils.cookie_manager import load_cookie_string
from utils.qfw_compat import patch_qfw_style_watchers
import warnings
import urllib3

# 关闭未校验HTTPS警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore")

# qfluentwidgets 样式 watcher 防 GC 补丁：必须在创建任何 Qt 控件之前打上
patch_qfw_style_watchers()


def main():
    # 设置 DPI 感知（仅 Windows），让高分屏下 UI 不糊
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    # 初始化配置
    config = ConfigManager()
    # 应用已保存的界面语言
    set_language(config.get("language", "zh_CN"))

    # 列表布局模式（详细 / 精简）持久化注入，供所有列表窗口共享
    from ui.list_layout import set_config
    set_config(config)

    # Qt 应用对象（单例，必须在任何 Qt 窗口之前创建）
    app = QApplication(sys.argv)
    app.setApplicationName("BilibiliDownloader")

    # QApplication 就绪后一次性应用主题，确保全局 QSS 和 Fluent 强调色
    # 在主窗口构建前写入，避免首帧使用默认色。
    apply_theme(config.get("accent_color"), config.get("appearance", "dark"))

    logger = Logger(log_file="download.log")
    logger.log("===== 程序启动（PySide6） =====")

    # 样式表自诊断：捕获 Qt 的 "Could not parse stylesheet" 警告，
    # 一旦触发就把全局 QSS 与各按钮局部样式表 dump 到 qss_diag.txt，
    # 便于在 windowsvista 等严格风格下快速定位残留的非法 QSS（只写一次）。
    try:
        from PySide6.QtCore import qInstallMessageHandler, QtMsgType
        from PySide6.QtWidgets import QPushButton

        _qss_dumped = {"done": False}

        def _qt_msg_handler(msg_type, ctx, msg):
            if msg_type not in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg):
                return
            if "stylesheet" not in msg.lower() and "parse" not in msg.lower():
                return
            if _qss_dumped["done"]:
                return
            _qss_dumped["done"] = True
            try:
                with open("qss_diag.txt", "w", encoding="utf-8") as f:
                    f.write(f"[QSS-WARN] {msg}\n\n")
                    app_inst = QApplication.instance()
                    if app_inst is not None:
                        f.write("=== 全局 QSS ===\n")
                        f.write(app_inst.styleSheet() + "\n\n")
                        f.write("=== 所有 QPushButton 的局部样式表 ===\n")
                        for b in app_inst.allWidgets():
                            if isinstance(b, QPushButton):
                                f.write(f"[{b.text() or b.objectName() or '?'}] -> {b.styleSheet()[:300]}\n")
                logger.log("检测到样式表解析警告，已写入 qss_diag.txt 供排查")
            except Exception:
                pass

        qInstallMessageHandler(_qt_msg_handler)
    except Exception:
        pass
    # Cookie
    cookie_str = load_cookie_string("cookies.txt") if os.path.exists("cookies.txt") else ""
    bili_api = BiliAPI(cookie_str)
    if bili_api.uid:
        logger.log(f"已登录用户：{bili_api.nickname}")
    else:
        if cookie_str:
            logger.log("Cookie文件存在但验证失败，可能已过期")
        else:
            logger.log("未找到Cookie，请登录")
    # 下载引擎
    engine = DownloadEngine(config, logger, bili_api)

    # 主窗口
    win = MainWindow(config, logger, bili_api, engine)
    # 登记根窗口，使切换强调色时能重上色已注册的强调色按钮
    set_root_window(win.window)
    # 设置窗口标题栏图标。
    # 打包后 icon.ico 通过 --add-data 进入 _MEIPASS 临时目录，resource_path 可直接取到；
    # 开发态从项目根目录 icon.ico 取；另用 --icon 把图标嵌入 exe（任务栏/资源管理器图标）。
    # 二者皆缺失则跳过（标题栏不显示图标）。
    _icon = get_app_icon_path()
    if os.path.exists(_icon):
        try:
            win.window.setWindowIcon(QIcon(_icon))
        except Exception:
            pass
    # 关闭逻辑（取消下载 / 销毁托盘 / 退出）统一由 MainWindow 内部处理
    win.run()

    # 进入 Qt 事件循环
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
