# utils/tray.py  (PySide6 版，使用原生 QSystemTrayIcon，移除 pystray 依赖)
import os
from io import BytesIO

from PIL import Image, ImageDraw
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtCore import Qt, QByteArray

from utils.helpers import open_in_browser
from utils.i18n import tr


class SystemTray:
    def __init__(self, app_window, config, logger, on_quit=None):
        self.app_window = app_window
        self.config = config
        self.logger = logger
        self.on_quit = on_quit
        self.icon = None
        self.is_running = False
        self.idle_color = "#4CAF50"
        self.download_color = "#2196F3"
        self.error_color = "#f44336"
        self._status_text = tr("状态: 空闲")

    # ---------- 图标 ----------
    def _make_icon(self, color):
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([4, 4, size - 4, size - 4], fill=color, outline="#333333", width=2)
        c = size // 2
        pts = [(c, size - 16), (c - 18, c + 4), (c - 8, c + 4),
               (c - 8, 14), (c + 8, 14), (c + 8, c + 4), (c + 18, c + 4)]
        d.polygon(pts, fill="white")
        d.rectangle([c - 20, size - 12, c + 20, size - 8], fill="white")
        buf = BytesIO()
        img.save(buf, "PNG")
        pm = QPixmap()
        pm.loadFromData(QByteArray(buf.getvalue()))
        return QIcon(pm)

    # ---------- 菜单 ----------
    def _build_menu(self):
        menu = QMenu()
        if self.app_window.isVisible():
            menu.addAction(tr("隐藏窗口"), self.hide_window)
        else:
            menu.addAction(tr("显示窗口"), self.show_window)
        menu.addSeparator()
        act = menu.addAction(self._status_text)
        act.setEnabled(False)
        menu.addAction(tr("打开下载目录"), self.open_download_dir)
        menu.addAction(tr("查看日志"), self.open_log)
        menu.addSeparator()
        menu.addAction(tr("退出"), self._quit)
        return menu

    def _on_activated(self, reason):
        # 左键单击直接显示窗口；右键由 setContextMenu 自动弹出菜单
        if reason == QSystemTrayIcon.Trigger:
            self.show_window()

    # ---------- 生命周期 ----------
    def run(self):
        if self.is_running:
            return
        self.is_running = True
        self.icon = QSystemTrayIcon(self._make_icon(self.idle_color), self.app_window)
        self.icon.setToolTip(tr("B站下载器 Pro"))
        self.icon.setContextMenu(self._build_menu())
        self.icon.activated.connect(self._on_activated)
        self.icon.show()

    def stop(self):
        self.is_running = False
        if self.icon is not None:
            try:
                self.icon.hide()
            except Exception:
                pass
            self.icon = None

    # ---------- 窗口显隐 ----------
    def hide_window(self):
        try:
            self.app_window.hide()
        except Exception:
            pass
        self.update_menu()

    def show_window(self):
        try:
            self.app_window.showNormal()
            self.app_window.activateWindow()
        except Exception:
            pass
        self.update_menu()

    # ---------- 菜单动作 ----------
    def open_download_dir(self):
        path = self.config.get("download_path")
        if os.path.exists(path):
            open_in_browser(path)
        else:
            self.logger.log("下载目录不存在")

    def open_log(self):
        log_file = "download.log"
        if os.path.exists(log_file):
            open_in_browser(log_file)
        else:
            self.logger.log("日志文件不存在")

    def update_menu(self):
        if self.icon is not None:
            self.icon.setContextMenu(self._build_menu())

    def update_icon(self, color):
        if self.icon is not None:
            self.icon.setIcon(self._make_icon(color))

    def set_downloading(self):
        self._status_text = tr("状态: 下载中")
        self.update_icon(self.download_color)
        self.update_menu()

    def set_idle(self):
        self._status_text = tr("状态: 空闲")
        self.update_icon(self.idle_color)
        self.update_menu()

    def set_error(self):
        self._status_text = tr("状态: 错误")
        self.update_icon(self.error_color)
        self.update_menu()

    def _quit(self):
        if self.on_quit is not None:
            self.on_quit()
        else:
            app = QApplication.instance()
            if app is not None:
                app.quit()
