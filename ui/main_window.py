"""主窗口（PySide6 版）。

完整保留原业务逻辑（链接解析、批量解析、分页拉取、下载控制、语言切换等），
仅将 UI 壳从 CustomTkinter 替换为 PySide6：QMainWindow + QWidget 布局 +
QListView 队列 + QSystemTrayIcon 托盘 + QSS 主题。

未在本轮迁移的子对话框（设置/搜索/历史/直播中心/关注/追番/批量解析/登录/关于等）
以信息框占位，保证所有按钮可点、程序不崩；这些对话框将在后续轮次逐个迁移。
视频/分集选择已分别用专属窗口（SelectDialog / EpisodeSelectDialog）实现，关注用
FollowingDialog，确认下载前可按设置弹出 DownloadOptionsDialog；解析多视频流程可走通。
"""
import os
import re
import sys
import threading

from PySide6.QtCore import Qt, QTimer, QEvent, QSize
from PySide6.QtGui import QIcon
from utils.main_thread import init_main_thread_bridge, run_on_main
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QMenu, QFrame,
)
from qfluentwidgets import (
    FluentIcon, LineEdit, PrimaryPushButton, ProgressBar, PushButton,
)

from ui.sidebar import NavigationBar
from ui.queue_view import QueueView, _set_progress_bar
from ui.select_dialog import SelectDialog, PaginatedSelectDialog
from ui.episode_select_dialog import EpisodeSelectDialog
from ui.following_dialog import FollowingDialog
from ui.download_options_dialog import DownloadOptionsDialog
from ui.fluent_dialog import (
    ChoiceDialog, msg_info, msg_warn, msg_error, msg_confirm,
)
from ui.dialogs import (AboutDialog, LoginDialog, SearchDialog,
                       ParseRecordsDialog, BatchParseDialog, LogWindow,
                       LiveCenterDialog, LiveRecordDialog, FavFolderDialog)
from ui.live_record_window import LiveRecordWindow
from ui.theme import (
    set_accent, get_accent, apply_appearance, DEFAULT_ACCENT,
    set_root_window,
)
from ui.list_layout import LayoutModeToggle
from download_engine import DownloadEngine
from utils.i18n import tr, register, set_language, retranslate_all, LANGUAGES
from utils.helpers import (
    resolve_short_url, duration_to_seconds, add_history_entry,
    open_in_browser, send_windows_notification,
)
from utils.tray import SystemTray


class _AppMainWindow(QMainWindow):
    """主窗口壳：把关闭事件转发给控制器，实现『关闭到托盘 / 退出』。

    控制器 ``MainWindow`` 是普通 Python 类，其 ``closeEvent`` 不会被 Qt 直接
    调用；此前 ``self.window`` 是裸 ``QMainWindow``，点击 X 走默认 ``closeEvent``
    （直接接受关闭），配合默认的 ``quitOnLastWindowClosed=True`` 直接退出、托盘
    随之失效。这里用最小子类把 ``Close`` 事件转发给控制器，由其决定最小化到托盘
    还是退出。
    """

    def __init__(self, controller):
        super().__init__()
        # 仅保存引用，不在构造期回调控制器（此时控制器尚未初始化完）
        self._controller = controller

    def closeEvent(self, ev):
        try:
            self._controller.closeEvent(ev)
        except Exception:
            # 极端异常下退化为默认行为，避免窗口卡死无法关闭
            super().closeEvent(ev)


class MainWindow:
    def __init__(self, config, logger, api, engine):
        # 必须在主线程初始化跨线程桥接器（MainWindow 在 main 线程构造）
        init_main_thread_bridge()
        self.config = config
        self.logger = logger
        self.api = api
        self.engine = engine
        self._live_windows = {}  # room_id -> LiveRecordWindow（去重常驻）
        self._live_manual = []   # 手动输入（无 room_id）的窗口，仅用于保活
        self._season_list_loading = False
        self.window = _AppMainWindow(self)
        self.window.setWindowTitle("BilibiliDownloader")
        self.window.resize(1100, 800)
        self.window.setMinimumSize(900, 650)
        # 窗口置顶（设置窗口可实时切换；启动时按配置恢复）
        self._apply_stay_on_top(bool(config.get("stay_on_top", False)))

        # 捕获未处理异常，避免静默丢失 / 吓到用户
        sys.excepthook = self._excepthook

        # 跟随系统主题轮询：appearance/accent 为 "system" 时，10s 内跟随
        # Windows 明暗模式 / 强调色变化（值未变化时 apply_theme 内部直接跳过）
        self._sys_theme_timer = QTimer(self.window)
        self._sys_theme_timer.timeout.connect(self.apply_theme_from_config)
        self._sys_theme_timer.start(10000)

        self.is_downloading = False
        self._quitting = False
        self._task_speeds = {}

        self.build_ui()

        # 托盘
        self.tray = SystemTray(self.window, config, logger, on_quit=self.quit_app)
        QTimer.singleShot(100, self.tray.run)

        # 引擎 / 日志回调（切回主线程刷新 UI）
        self.engine.status_callbacks.append(
            lambda q: run_on_main(lambda: self._on_queue_status(q)))
        self.engine.progress_callbacks.append(
            lambda url, p, s: run_on_main(lambda: self._on_task_progress(url, p, s)))
        self.engine.finish_callbacks.append(
            lambda c, f, ca: run_on_main(lambda: self.on_download_finished(c, f, ca)))
        self.engine.stop_callbacks.append(
            lambda: run_on_main(self._sync_download_buttons))
        self.logger.ui_callbacks.append(
            lambda msg: run_on_main(lambda: self._route_log(msg)))

        try:
            self.update_login_hint()
        except Exception:
            pass

    # ---------- 构建 UI ----------
    def build_ui(self):
        central = QWidget()
        central.setObjectName("mainCentral")
        self.window.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        self.sidebar = NavigationBar(central, self.api, self.on_nav_click,
                                     config=self.config, on_language_change=self.on_language_change,
                                     on_login=self.open_login, on_about=self.open_about,
                                     on_settings=self.open_settings)
        root.addWidget(self.sidebar)

        self.main_panel = QWidget()
        self.main_panel.setObjectName("mainContent")
        mp = QVBoxLayout(self.main_panel)
        mp.setContentsMargins(0, 0, 0, 0)
        mp.setSpacing(10)
        root.addWidget(self.main_panel, 1)

        # ---- 顶部操作区：链接解析 + 常用工具 ----
        toolbar = QFrame()
        toolbar.setObjectName("mainToolbar")
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 10, 12, 10)
        toolbar_layout.setSpacing(8)

        url_frame = QWidget()
        url_frame.setObjectName("toolbarUrlRow")
        uf = QHBoxLayout(url_frame)
        uf.setContentsMargins(0, 0, 0, 0)
        uf.setSpacing(10)
        self.url_entry = LineEdit(self.main_panel)
        self.url_entry.setPlaceholderText(tr("粘贴B站链接（视频/合集/番剧/课程/音频/每周必看…）"))
        self.url_entry.setFixedHeight(38)
        uf.addWidget(self.url_entry, 1)
        register(self.url_entry, "粘贴B站链接（视频/合集/番剧/课程/音频/每周必看…）", attr="placeholder_text")

        self.clip_btn = self._secondary_button(tr("粘贴"), self.paste_from_clipboard)
        self.clip_btn.setIcon(FluentIcon.PASTE.icon())
        self.clip_btn.setIconSize(QSize(16, 16))
        self.clip_btn.setFixedHeight(38)
        uf.addWidget(self.clip_btn)
        register(self.clip_btn, "粘贴")

        parse_frame = QFrame()
        parse_frame.setObjectName("parseButtonGroup")
        pf = QHBoxLayout(parse_frame)
        pf.setContentsMargins(0, 0, 0, 0)
        pf.setSpacing(0)
        self.add_btn = PrimaryPushButton(self.main_panel)
        self.add_btn.setText(tr("解析"))
        self.add_btn.setIcon(FluentIcon.SEARCH.icon())
        self.add_btn.setIconSize(QSize(16, 16))
        self.add_btn.setFixedSize(88, 38)
        self.add_btn.clicked.connect(self.add_from_entry)
        pf.addWidget(self.add_btn)
        register(self.add_btn, "解析")
        self.parse_dropdown = PushButton(self.main_panel)
        self.parse_dropdown.setIcon(FluentIcon.CHEVRON_DOWN_MED.icon())
        self.parse_dropdown.setIconSize(QSize(12, 12))
        self.parse_dropdown.setFixedSize(36, 38)
        self.parse_dropdown.clicked.connect(self._open_parse_menu)
        pf.addWidget(self.parse_dropdown)
        uf.addWidget(parse_frame)

        toolbar_layout.addWidget(url_frame)

        # 次级操作集中放置；搜索和设置由侧边栏提供唯一入口。
        extra_frame = QFrame()
        extra_frame.setObjectName("toolbarActionsRow")
        ef = QHBoxLayout(extra_frame)
        ef.setContentsMargins(0, 0, 0, 0)
        ef.setSpacing(8)
        self.history_btn = self._secondary_button(tr("解析记录"), self.show_history)
        self.history_btn.setIcon(FluentIcon.HISTORY.icon())
        ef.addWidget(self.history_btn)
        register(self.history_btn, "解析记录")
        self.open_dir_btn = self._secondary_button(tr("打开下载目录"), self.open_download_dir)
        self.open_dir_btn.setIcon(FluentIcon.FOLDER.icon())
        ef.addWidget(self.open_dir_btn)
        register(self.open_dir_btn, "打开下载目录")
        self.record_btn = self._secondary_button(tr("录制直播"), self.open_live_recorder)
        self.record_btn.setIcon(FluentIcon.VIDEO.icon())
        ef.addWidget(self.record_btn)
        register(self.record_btn, "录制直播")
        # 与「解析记录」等同行的右侧：详细 / 精简 列表布局切换（仅图标），避免底部单独成行突兀
        self.layout_toggle = LayoutModeToggle(self.main_panel)
        ef.addWidget(self.layout_toggle)
        ef.addStretch(1)
        toolbar_layout.addWidget(extra_frame)
        mp.addWidget(toolbar)

        # ---- 队列视图 ----
        self.queue_view = QueueView(self.main_panel, self.engine, self.config)
        self.queue_view.setObjectName("queueCard")
        self.queue_view.setAttribute(Qt.WA_StyledBackground, True)
        mp.addWidget(self.queue_view, 1)

        # ---- 总进度 ----
        overall_frame = QFrame()
        overall_frame.setObjectName("progressCard")
        ov = QVBoxLayout(overall_frame)
        ov.setContentsMargins(14, 10, 14, 10)
        ov.setSpacing(6)
        head_row = QHBoxLayout()
        self.overall_title_label = QLabel(tr("总进度"))
        self.overall_title_label.setStyleSheet("font-weight:bold;")
        head_row.addWidget(self.overall_title_label)
        register(self.overall_title_label, "总进度")
        self.overall_percent_label = QLabel("0%")
        head_row.addStretch(1)
        head_row.addWidget(self.overall_percent_label)
        ov.addLayout(head_row)

        self.overall_bar = ProgressBar()
        self.overall_bar.setFixedHeight(8)
        self.overall_bar.setValue(0)
        ov.addWidget(self.overall_bar)

        foot_row = QHBoxLayout()
        self.speed_label = QLabel(tr("空闲"))
        foot_row.addWidget(self.speed_label)
        self.overall_count_label = QLabel("")
        foot_row.addStretch(1)
        foot_row.addWidget(self.overall_count_label)
        ov.addLayout(foot_row)
        mp.addWidget(overall_frame)

        # ---- 控制按钮 ----
        ctrl_frame = QFrame()
        ctrl_frame.setObjectName("actionCard")
        cf = QHBoxLayout(ctrl_frame)
        cf.setContentsMargins(12, 8, 12, 8)
        cf.setSpacing(8)
        self.start_btn = PrimaryPushButton(self.main_panel)
        self.start_btn.setText(tr("开始下载"))
        self.start_btn.setIcon(FluentIcon.DOWNLOAD.icon())
        self.start_btn.setIconSize(QSize(16, 16))
        self.start_btn.setFixedHeight(38)
        self.start_btn.clicked.connect(self.start_download)
        register(self.start_btn, "开始下载")
        self.cancel_btn = PushButton(self.main_panel)
        self.cancel_btn.setText(tr("取消"))
        self.cancel_btn.setIcon(FluentIcon.CANCEL.icon())
        self.cancel_btn.setIconSize(QSize(16, 16))
        self.cancel_btn.setFixedHeight(38)
        self.cancel_btn.clicked.connect(self.cancel_download)
        self.cancel_btn.setEnabled(False)
        register(self.cancel_btn, "取消")
        self.clear_btn = PushButton(self.main_panel)
        self.clear_btn.setText(tr("清空队列"))
        self.clear_btn.setIcon(FluentIcon.DELETE.icon())
        self.clear_btn.setIconSize(QSize(16, 16))
        self.clear_btn.setFixedHeight(38)
        self.clear_btn.clicked.connect(self.clear_queue)
        register(self.clear_btn, "清空队列")
        for b in (self.start_btn, self.cancel_btn, self.clear_btn):
            cf.addWidget(b, 1)
        mp.addWidget(ctrl_frame)

        self.apply_theme_from_config()

    def _secondary_button(self, text, command):
        """创建 Fluent 次要操作按钮。"""
        b = PushButton(self.main_panel)
        b.setText(text)
        b.clicked.connect(command)
        return b

    # ---------- 日志路由 ----------
    def _route_log(self, msg):
        # 日志已由 logger 落盘；独立日志窗口将在后续轮次迁移
        pass

    def open_log_window(self):
        LogWindow(self.window, logger=self.logger).exec()

    def _apply_stay_on_top(self, on):
        """主窗口置顶开关（设置窗口实时切换；setWindowFlags 会隐藏窗口需重新 show）。

        Windows 经典坑：setWindowFlags 若未显式包含 SystemMenu/Min/Max/Close
        等 Hint，系统标题栏的按钮提示位会丢失，表现为「关闭按钮置灰」。
        因此这里显式构造完整 flag 集合，且状态未变化时绝不动 flags。
        """
        on = bool(on)
        if getattr(self, "_stay_on_top_applied", None) == on:
            return
        self._stay_on_top_applied = on
        try:
            from PySide6.QtCore import Qt
            w = self.window
            flags = (Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint
                     | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
                     | Qt.WindowCloseButtonHint)
            if on:
                flags |= Qt.WindowStaysOnTopHint
            was_visible = w.isVisible()
            w.setWindowFlags(flags)
            if was_visible:
                w.show()
        except Exception:
            pass

    # ---------- 总进度条 ----------
    def _on_queue_status(self, queue):
        self.queue_view.update_view(queue)
        self.refresh_overall_progress()
        self._sync_download_buttons()

    def _sync_download_buttons(self):
        running = getattr(self.engine, "is_running", False)
        self.is_downloading = running
        if running:
            self.start_btn.setEnabled(False)
            self.start_btn.setText(tr("下载中..."))
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.setText(tr("取消"))
            self.clear_btn.setEnabled(False)
        else:
            self.start_btn.setEnabled(True)
            self.start_btn.setText(tr("开始下载"))
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText(tr("取消"))
            self.clear_btn.setEnabled(True)

    def _on_task_progress(self, url, percent, speed):
        self.queue_view.update_task_progress(url, percent, speed)
        self._task_speeds[url] = speed or 0
        self.refresh_overall_progress()

    def refresh_overall_progress(self):
        bar = getattr(self, "overall_bar", None)
        if bar is None:
            return
        try:
            queue = list(self.engine.queue)
        except Exception:
            queue = []
        if not queue:
            _set_progress_bar(bar, 0)
            self.overall_percent_label.setText("0%")
            self._set_label_color(self.speed_label, "sub")
            self.speed_label.setText(tr("空闲"))
            self.overall_count_label.setText("")
            return
        finished_states = ("completed", "failed", "cancelled")
        acc = 0.0
        done = 0
        speed_sum = 0.0
        downloading = 0
        for t in queue:
            st = t.get("status")
            if st in finished_states:
                acc += 1.0
                done += 1
            elif st == "downloading":
                acc += max(0.0, min(1.0, t.get("progress") or 0))
                downloading += 1
                speed_sum += self._task_speeds.get(t.get("url"), 0) or 0
        frac = max(0.0, min(1.0, acc / len(queue)))
        _set_progress_bar(bar, frac)
        self.overall_percent_label.setText(f"{frac * 100:.1f}%")
        self.overall_count_label.setText(tr("{}/{} 已完成").format(done, len(queue)))
        if downloading and speed_sum > 0:
            self._set_label_color(self.speed_label, "#42a5f5")
            self.speed_label.setText(f"⬇️ {self._format_speed(speed_sum)}")
        elif self.is_downloading:
            self._set_label_color(self.speed_label, "sub")
            self.speed_label.setText(tr("准备中…"))
        elif done >= len(queue):
            self._set_label_color(self.speed_label, "#66bb6a")
            self.speed_label.setText(tr("全部结束"))
        else:
            self._set_label_color(self.speed_label, "sub")
            self.speed_label.setText(tr("空闲"))

    def _set_label_color(self, label, color):
        if color == "sub":
            from ui.theme import palette
            color = palette()["sub"]
        label.setStyleSheet(f"color:{color};")

    @staticmethod
    def _format_speed(bps):
        if bps >= 1024 * 1024:
            return f"{bps / 1024 / 1024:.2f} MB/s"
        if bps >= 1024:
            return f"{bps / 1024:.1f} KB/s"
        return f"{bps:.0f} B/s"

    def _excepthook(self, exc, val, tb):
        import traceback as _tb
        # Ctrl+C / 正常退出流程不算程序异常：不弹错误弹窗，
        # 转入优雅退出（取消下载、停托盘后 os._exit）。
        if isinstance(val, KeyboardInterrupt):
            if not getattr(self, "_quitting", False):
                self.quit_app()
            return
        if isinstance(val, SystemExit):
            return
        # 退出流程中的任何异常都不再弹模态错误框：此时弹框会让主界面冻住
        # （用户表现为"点击退出后卡很久"），且真正的退出已由 quit_app 的
        # finally 兜底完成。只打印到控制台便于排查。
        if getattr(self, "_quitting", False):
            import traceback as _tb2
            print("[退出阶段异常]", "".join(_tb2.format_exception(exc, val, tb)))
            return
        msg = "".join(_tb.format_exception(exc, val, tb))
        try:
            self.logger.log(f"[UI异常] {msg}")
        except Exception:
            print("[UI异常]", msg)
        try:
            msg_error(self.window, f"{tr('发生未处理的界面异常：')}\n\n{msg[-800:]}", tr("程序异常"))
        except Exception:
            pass

    # ---------- 关闭 / 最小化 ----------
    def changeEvent(self, ev):
        if ev.type() == QEvent.WindowStateChange:
            if self.window.isMinimized():
                self.on_minimize()
        super().changeEvent(ev) if hasattr(super(), "changeEvent") else None

    def on_minimize(self):
        if getattr(self, "_quitting", False):
            return
        self.window.hide()
        self.tray.hide_window()

    def closeEvent(self, ev):
        behavior = self.config.get("close_behavior", "")
        if behavior not in ("tray", "quit"):
            dlg = ChoiceDialog(self.window, tr("关闭方式"), tr("关闭程序时："),
                               options=[(tr("直接退出"), "quit"),
                                        (tr("最小化到托盘"), "tray")],
                               default="tray")
            dlg.exec()
            behavior = dlg.value
            try:
                self.config.set("close_behavior", behavior)
            except Exception:
                pass
        if behavior == "tray":
            ev.ignore()
            self.minimize_to_tray()
        else:
            # 顺序要紧：先 quit_app()（内部 os._exit(0) 立即结束进程），再 accept()。
            # 若反过来先 ev.accept()，Qt 会先走一遍窗口关闭流程（隐藏/销毁整棵控件树
            # ——侧边栏+队列+全部 UI，控件极多），这段销毁耗时就是用户看到的
            # "界面冻住一段时间才消失"。os._exit 是强制结束，不依赖任何清理。
            self.quit_app()
            ev.accept()

    def on_closing(self):
        # 兼容旧调用点；实际关闭由 closeEvent 驱动
        self.window.close()

    def minimize_to_tray(self):
        try:
            self.window.hide()
            self.tray.hide_window()
            self.logger.log("已最小化到系统托盘，后台继续运行")
        except Exception as e:
            self.logger.log(f"最小化到托盘失败：{e}")

    def quit_app(self):
        if getattr(self, "_quitting", False):
            return
        self._quitting = True
        # 退出流程必须"绝不阻塞、绝不抛异常"：任何异常上抛都会进 sys.excepthook
        # 弹出模态错误框，界面就会冻住等用户点击，且 os._exit 永远到不了
        # （用户表现为"点击退出后卡很久"）。故全部包 try，os._exit 放 finally 兜底。
        try:
            try:
                self.logger.log("程序退出中...")
            except Exception:
                pass
            try:
                if self.engine.is_running:
                    self.engine.cancel()
            except Exception:
                pass
            try:
                self.tray.stop()
            except Exception:
                pass
            try:
                app = QApplication.instance()
                if app is not None:
                    app.quit()
            except Exception:
                pass
        finally:
            try:
                os._exit(0)
            except Exception:
                pass

    # ---------- 通知 ----------
    def _alert(self, title, message, level="warning"):
        self.logger.log(message)
        box = {"error": msg_error, "warning": msg_warn,
               "info": msg_info}.get(level, msg_warn)
        try:
            box(self.window, message, title)
        except Exception:
            pass

    # ---------- 下载控制 ----------
    def start_download(self):
        if self.is_downloading:
            self._alert(tr("提示"), tr("下载正在进行中"), "info")
            return
        if not self.engine.queue:
            self._alert(tr("提示"), tr("队列为空，请先添加视频"), "warning")
            return
        if not self.engine._get_ffmpeg_path():
            self._alert(tr("错误"),
                       tr("未找到 FFmpeg，无法合并音视频（可在「设置」中指定路径，或留空使用 bin/ffmpeg）"),
                       "error")
            return
        self.tray.set_downloading()
        self.tray.update_menu()
        task_count = len(self.engine.queue)
        send_windows_notification(
            tr("B站下载器"),
            "开始下载 {} 个视频\n{}".format(task_count, self.config.get('download_path')),
            duration=3)
        self.is_downloading = True
        self.start_btn.setEnabled(False)
        self.start_btn.setText(tr("下载中..."))
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText(tr("取消"))
        self.clear_btn.setEnabled(False)
        self._task_speeds.clear()
        self.refresh_overall_progress()
        self.logger.log("===== 开始批量下载 =====")
        self.engine.start()
        if not self.engine.is_running:
            self.is_downloading = False
            self.start_btn.setEnabled(True)
            self.start_btn.setText(tr("开始下载"))
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText(tr("取消"))
            self.clear_btn.setEnabled(True)
            self._alert(tr("提示"),
                       tr("没有等待中的任务，请对暂停/失败的任务点击『继续/重试』"), "warning")

    def cancel_download(self):
        if not self.is_downloading:
            return
        self.logger.log("用户请求取消下载...")
        self.engine.cancel()
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText(tr("取消中..."))
        self.logger.log("正在取消下载...")
        self.tray.set_error()
        self.tray.update_menu()

    def on_download_finished(self, completed, failed, cancelled):
        self.is_downloading = False
        self.start_btn.setEnabled(True)
        self.start_btn.setText(tr("开始下载"))
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText(tr("取消"))
        self.clear_btn.setEnabled(True)
        self._task_speeds.clear()
        self.refresh_overall_progress()
        msg_info(self.window, tr("下载结束：完成{}，失败{}，取消{}\n保存路径: {}").format(
                completed, failed, cancelled, self.config.get('download_path')), tr("下载完成"))
        if completed > 0 and self.config.get("open_folder_after_download", True):
            self.open_download_dir()
        if failed > 0:
            self.tray.set_error()
        else:
            self.tray.set_idle()
        self.tray.update_menu()
        if cancelled > 0:
            self.logger.log(f"下载结束：完成{completed}，失败{failed}，取消{cancelled}")
        else:
            self.logger.log(f"下载完成：成功{completed}，失败{failed}")
        remaining = [t for t in self.engine.queue if t["status"] in ("failed", "cancelled")]
        if remaining:
            self.logger.log(f"队列中还有 {len(remaining)} 个失败/取消的任务")

    def clear_queue(self):
        if self.is_downloading:
            self._alert(tr("提示"), tr("下载进行中，无法清空队列"), "warning")
            return
        if not self.engine.queue:
            self.logger.log("队列已为空")
            return
        res = msg_confirm(
            self.window,
            tr("确定要清空队列中的 {} 个任务吗？").format(len(self.engine.queue)),
            tr("确认清空"))
        if res:
            self.engine.queue.clear()
            try:
                self.engine.save_tasks()
            except Exception:
                pass
            self._task_speeds.clear()
            self._on_queue_status(self.engine.queue)
            self.refresh_overall_progress()
            self.logger.log("队列已清空")

    def paste_from_clipboard(self):
        try:
            import pyperclip
            text = pyperclip.paste().strip()
            if "bilibili.com" in text or "b23.tv" in text:
                self.url_entry.clear()
                self.url_entry.setText(text)
                self.logger.log(f"从剪贴板粘贴：{text}")
            else:
                self.logger.log("剪贴板内容非B站链接")
        except Exception as e:
            self.logger.log(f"粘贴失败：{str(e)}")

    def add_from_entry(self):
        url = self.url_entry.text().strip()
        if not url:
            return
        real_url = resolve_short_url(url)
        if not real_url:
            self._alert(tr("提示"), tr("链接解析失败，请确认输入的是有效的 B 站链接"), "warning")
            return
        self.add_btn.setEnabled(False)
        self.add_btn.setText(tr("解析中..."))
        threading.Thread(target=self._parse_and_add, args=(real_url,), daemon=True).start()

    def show_history(self):
        ParseRecordsDialog(self.window, on_add=self._add_record_to_queue).exec()

    def _add_record_to_queue(self, url, title):
        if not url:
            return
        self.logger.log(f"从解析记录加入队列：{title} ({url})")
        threading.Thread(target=self._parse_and_add, args=(url,), daemon=True).start()

    def open_download_dir(self):
        path = self.config.get("download_path")
        if os.path.exists(path):
            open_in_browser(path)
        else:
            self.logger.log("下载目录不存在，请检查设置")

    # ---------- 链接解析（业务逻辑，原样保留）----------
    def _resolve_url_to_videos(self, url):
        import re
        url = (url or "").strip()
        if not url:
            return None, "", "链接为空", False
        if "b23.tv" in url or "bili2233.cn" in url:
            real = resolve_short_url(url)
            if real and real != url:
                self.logger.log(f"短链跳转: {url} -> {real}")
                url = real
        m_cheese = re.search(r'cheese/play/(ss|ep)(\d+)', url)
        if m_cheese:
            kind, val = m_cheese.group(1), m_cheese.group(2)
            self.logger.log(f"识别到课程 cheese，{kind}{val}")
            vlist = (self.api.get_cheese_episodes(ssid=int(val))
                     if kind == "ss" else self.api.get_cheese_episodes(epid=int(val)))
            if vlist:
                return vlist, f"课程 {kind}{val}", None, True
            return None, "", "课程解析失败", False
        if "audio" in url or "music.bilibili" in url:
            m_audio = re.search(r'(am|au)(\d+)', url)
            if m_audio:
                kind, val = m_audio.group(1), m_audio.group(2)
                self.logger.log(f"识别到音频，{kind}{val}")
                vlist = (self.api.get_audio_list(amid=int(val))
                         if kind == "am" else self.api.get_audio_list(auid=int(val)))
                if vlist:
                    return vlist, f"音频 {kind}{val}", None, False
                return None, "", "音频解析失败", False
        if "v/popular" in url or "popular/series" in url:
            m_num = re.search(r'num=(\d+)', url)
            num = int(m_num.group(1)) if m_num else None
            self.logger.log(f"识别到每周必看（第 {num if num else '最新'} 期），加载中...")
            vlist = self.api.get_popular_weekly(number=num)
            if vlist:
                return vlist, "每周必看", None, False
            return None, "", "每周必看解析失败", False
        if "bilibili.com/festival" in url:
            self.logger.log("识别到活动页，提取内嵌视频...")
            bvid = self.api.get_festival_bvid(url)
            if bvid:
                try:
                    info = self.api.get_video_pages(bvid)
                    single = info.get("single")
                    if single:
                        if info.get("collection"):
                            return info["collection"], single["title"], None, True
                        if len(info.get("pages", [])) > 1:
                            return info["pages"], single["title"], None, True
                        return [single], single["title"], None, False
                except Exception as e:
                    self.logger.log(f"活动页内嵌视频解析失败，回退: {e}")
            return self._yt_dlp_resolve(url, "活动页")
        m_season = re.search(r'space\.bilibili\.com/(\d+)/lists/(\d+)', url)
        if m_season:
            mid, season_id = m_season.group(1), m_season.group(2)
            self.logger.log(f"识别到空间合集，mid={mid} season_id={season_id}")
            vlist = self.api.get_space_season_videos(mid, season_id)
            if vlist:
                return vlist, f"合集 {season_id}", None, False
            return None, "", "合集解析失败", False
        m_series = re.search(r'space\.bilibili\.com/(\d+)/series/(\d+)', url)
        if m_series:
            mid, series_id = m_series.group(1), m_series.group(2)
            self.logger.log(f"识别到空间系列，mid={mid} series_id={series_id}")
            vlist = self.api.get_space_series_videos(mid, series_id)
            if vlist:
                return vlist, f"系列 {series_id}", None, False
            return None, "", "系列解析失败", False
        up_match = re.search(r'space\.bilibili\.com/(\d+)', url)
        if up_match:
            mid = up_match.group(1)
            if "/dynamic" in url:
                self.logger.log(f"识别到动态，mid={mid}，提取视频...")
                vlist = self.api.get_dynamic_videos(mid)
                if vlist:
                    return vlist, f"动态 {mid}", None, False
                return None, "", "动态解析失败", False
            self.logger.log(f"识别到UP主空间，mid={mid}，按需翻页拉取（与收藏夹/稍后再看统一）...")
            def fetch(pn, ps):
                res = self.api.get_uploader_videos(mid, pn=pn, ps=ps) or {}
                items = res.get("items", []) or []
                self.api.enrich_videos(items)
                total = res.get("total", 0)
                total_pages = (total + ps - 1) // ps if total else None
                return items, res.get("has_more", False), total_pages
            return None, f"UP主空间 {mid}", None, False, fetch
        ep_match = re.search(r'bangumi/(?:play|media)/ep(\d+)', url)
        ss_match = re.search(r'bangumi/(?:play|media)/(?:ss|md)(\d+)', url)
        if ep_match or ss_match:
            if ep_match:
                epid = ep_match.group(1)
                self.logger.log(f"识别到番剧分集，epid={epid}")
                vlist = self.api.get_season_episodes(epid=epid)
                t = f"番剧 ep{epid}"
            else:
                sid = ss_match.group(1)
                is_md = "md" in ss_match.group(0)
                self.logger.log(f"识别到番剧，{'md'+sid if is_md else 'ss'+sid}")
                vlist = (self.api.get_season_episodes(mdid=sid)
                         if is_md else self.api.get_season_episodes(ssid=sid))
                t = f"番剧 {'md'+sid if is_md else 'ss'+sid}"
            if vlist:
                return vlist, t, None, True
            return self._yt_dlp_resolve(url, t)
        bvid_match = (re.search(r'/video/(BV[0-9A-Za-z]+)', url)
                      or re.search(r'[?&]bvid=(BV[0-9A-Za-z]+)', url)
                      or re.search(r'(BV[0-9A-Za-z]+)', url))
        bvid = bvid_match.group(1) if bvid_match else None
        if bvid:
            self.logger.log(f"识别到视频 bvid={bvid}，解析合集/分P...")
            try:
                info = self.api.get_video_pages(bvid)
                single = info.get("single")
                if single:
                    if info.get("collection"):
                        self.logger.log(f"命中合集，共 {len(info['collection'])} 个视频")
                        return info["collection"], single["title"], None, True
                    if len(info.get("pages", [])) > 1:
                        self.logger.log(f"命中多分P，共 {len(info['pages'])} 个分P")
                        return info["pages"], single["title"], None, True
                    return [single], single["title"], None, False
            except Exception as e:
                self.logger.log(f"原生解析失败，回退 yt_dlp: {e}")
            return self._yt_dlp_resolve(url, bvid)
        return self._yt_dlp_resolve(url, "")

    def _resolve_videos(self, url):
        """统一解析入口：把 _resolve_url_to_videos 的返回规范为 5 元组
        ``(video_list, title, err, episode_like, fetch)``。

        - 可翻页来源（如 UP 主空间）返回 ``fetch`` 回调（``(pn, ps) -> (items, has_more)``），
          调用方据此弹统一的「分页选择」对话框，按需翻页拉取，而非一次性拉全。
        - 非翻页来源 ``fetch`` 为 ``None``，沿用原有的整列表展示逻辑。
        """
        r = self._resolve_url_to_videos(url)
        fetch = r[4] if len(r) > 4 else None
        return r[0], r[1], r[2], r[3], fetch

    def _yt_dlp_resolve(self, url, fallback_title=""):
        import yt_dlp
        try:
            opts = {"quiet": True, "no_warnings": True, "extract_flat": False,
                    "cookiefile": "cookies.txt" if os.path.exists("cookies.txt") else None}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None, "", "无数据", False
                playlist_title = info.get("title", fallback_title or "合集")
                if "entries" in info and info["entries"]:
                    video_list = []
                    for entry in info["entries"]:
                        if not entry:
                            continue
                        video_list.append({
                            "url": entry.get("webpage_url") or entry.get("url") or url,
                            "title": entry.get("title", "未知分P"),
                            "duration": entry.get("duration", 0),
                            "thumbnail": entry.get("thumbnail", "") or info.get("thumbnail", ""),
                            "view_count": entry.get("view_count", 0) or 0,
                            "like_count": entry.get("like_count", 0) or 0,
                            "favorite_count": entry.get("favorite_count", 0) or 0,
                            "publish_time": self._fmt_yt_date(entry.get("upload_date", "")),
                            "uploader": entry.get("uploader", "") or info.get("uploader", ""),
                        })
                    return video_list, playlist_title, None, False
                else:
                    title = info.get("title", "未知标题")
                    return [{
                        "url": url, "title": title, "duration": info.get("duration", 0),
                        "thumbnail": info.get("thumbnail", ""),
                        "view_count": info.get("view_count", 0) or 0,
                        "like_count": info.get("like_count", 0) or 0,
                        "favorite_count": info.get("favorite_count", 0) or 0,
                        "publish_time": self._fmt_yt_date(info.get("upload_date", "")),
                        "uploader": info.get("uploader", "") or info.get("channel", ""),
                    }], title, None, False
        except Exception as e:
            return None, "", f"解析失败: {str(e)}", False

    def _parse_and_add(self, url):
        try:
            video_list, title, err, episode_like, fetch = self._resolve_videos(url)
            if err:
                self._add_done(False, err)
                return
            self._add_done(True, f"解析：{title or ''}")
            if fetch is not None:
                # 可翻页来源（UP 主空间等）：复用统一的「分页选择」对话框，
                # 先弹窗、仅拉第 1 页、按需翻页，不再一次性分页拉全。
                run_on_main(lambda t=title, f=fetch: self._pull_all_and_show(t, f))
                return
            if not video_list:
                self._add_done(False, "无数据")
                return
            if len(video_list) == 1:
                self._add_videos_direct(video_list)
            elif episode_like:
                run_on_main(lambda: self.show_episode_select(video_list))
            else:
                try:
                    self.api.enrich_videos(video_list)
                except Exception:
                    pass
                run_on_main(lambda: self.show_video_select(video_list))
        except Exception as e:
            # 异常变量 e 在 except 结束即被删除，延迟回调须当场绑定字符串
            run_on_main(lambda err=str(e): self._add_done(False, err))

    def _fmt_yt_date(self, d):
        if d and len(str(d)) == 8:
            d = str(d)
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        return str(d) if d else ""

    def load_season_videos(self, ssid):
        self.logger.log(f"加载番剧视频... ssid={ssid}")
        threading.Thread(target=self._load_season_videos_thread, args=(ssid,), daemon=True).start()

    def _load_season_videos_thread(self, ssid):
        try:
            video_list = self.api.get_season_episodes(ssid=ssid)
            if not video_list:
                import yt_dlp
                self.logger.log("原生番剧解析失败，回退 yt-dlp")
                opts = {"quiet": True, "no_warnings": True}
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(f"https://www.bilibili.com/bangumi/play/ss{ssid}", download=False)
                    if not info:
                        run_on_main(lambda: self.logger.log("番剧解析失败"))
                        return
                    entries = info.get('entries', [])
                    if not entries:
                        run_on_main(lambda: self.logger.log("该番剧没有视频"))
                        return
                    video_list = [{
                        "url": ep.get('webpage_url') or ep.get('url'),
                        "title": ep.get('title', '未知分P'),
                        "duration": ep.get('duration', 0),
                        "thumbnail": ep.get('thumbnail', ''),
                        "view_count": 0, "like_count": 0, "favorite_count": 0,
                        "publish_time": ep.get('upload_date', ''),
                        "uploader": info.get('uploader', '番剧')
                    } for ep in entries]
            if not video_list:
                run_on_main(lambda: self.logger.log("该番剧没有视频"))
                return
            run_on_main(lambda n=len(video_list): self.logger.log(f"已加载 {n} 个番剧分集"))
            run_on_main(lambda: self.show_episode_select(video_list))
        except Exception as e:
            run_on_main(lambda err=e: self.logger.log(f"加载番剧视频失败：{str(err)}"))

    def _add_done(self, success, msg):
        self.add_btn.setEnabled(True)
        self.add_btn.setText(tr("解析"))
        if success:
            self.logger.log(msg)
        else:
            self.logger.log(f"添加失败：{msg}")

    # ---------- 解析下拉菜单 / 批量解析 ----------
    def _open_parse_menu(self):
        try:
            menu = QMenu(self.window)
            menu.addAction(tr("批量解析（一行一个链接，自动识别类型）"), self.open_batch_parse)
            menu.exec(self.parse_dropdown.mapToGlobal(self.parse_dropdown.rect().bottomLeft()))
        except Exception:
            pass

    def open_batch_parse(self):
        BatchParseDialog(self.window, on_parse=self.batch_parse_links).exec()

    def batch_parse_links(self, lines):
        if not lines:
            self.logger.log("批量解析：没有有效链接")
            return
        threading.Thread(target=self._batch_parse_thread, args=(lines,), daemon=True).start()

    def _batch_parse_thread(self, links):
        aggregated = []           # 非翻页来源解析出的整列表
        pending_dialogs = []      # (title, fetch)：可翻页来源各自弹统一的分页选择框
        failed = 0
        for raw in links:
            url = resolve_short_url(raw) or raw
            try:
                vlist, title, err, _ep, fetch = self._resolve_videos(url)
                if err or (not vlist and fetch is None):
                    failed += 1
                    self.logger.log(f"批量解析失败：{raw}")
                    continue
                if fetch is not None:
                    # 可翻页来源（UP 主空间等）不再一次性拉全，改为各自弹
                    # 「按需分页」选择框，与收藏夹/稍后再看保持一致。
                    pending_dialogs.append((title, fetch))
                else:
                    aggregated.extend(vlist)
            except Exception as e:
                failed += 1
                self.logger.log(f"批量解析失败：{raw} {e}")
        if failed:
            self.logger.log(f"批量解析：{failed} 个链接解析失败")
        # 非翻页来源汇总到一个勾选框
        if aggregated:
            self.logger.log(f"批量解析：共 {len(aggregated)} 个视频，请在弹窗中勾选")
            run_on_main(lambda v=list(aggregated): self.show_video_select(v))
        # 可翻页来源各自弹统一的「按需分页」选择框
        for title, fetch in pending_dialogs:
            run_on_main(lambda t=title, f=fetch: self._pull_all_and_show(t, f))
        if not aggregated and not pending_dialogs and not failed:
            self.logger.log("批量解析：未获取到任何视频")

    def open_settings(self):
        # 设置窗口基于 qfluentwidgets.MSFluentWindow（modeless，自带抽屉式切换动画）。
        # 懒加载，避免在未打开设置时引入 qfluentwidgets。
        from ui.settings_window import SettingsWindow
        if getattr(self, "settings_window", None) is not None:
            try:
                if not self.settings_window.isHidden():
                    self.settings_window.raise_()
                    self.settings_window.activateWindow()
                    return
            except Exception:
                pass
        self.settings_window = SettingsWindow(
            self.window, self.config, self.on_language_change,
            self.on_settings_changed, self._preview_theme,
            on_open_logs=self.open_log_window,
            on_stay_on_top=self._apply_stay_on_top)
        # 居中到主窗口：默认 show() 由窗口系统级联定位，会偏左上，需手动居中
        pw = self.window
        self.settings_window.move(
            pw.x() + (pw.width() - self.settings_window.width()) // 2,
            pw.y() + (pw.height() - self.settings_window.height()) // 2)
        self.settings_window.show()

    def open_login(self):
        def on_success():
            try:
                self.sidebar.refresh()
            except Exception:
                pass
            try:
                self.update_login_hint()
            except Exception:
                pass
            try:
                self.logger.log(f"登录成功：{self.api.nickname}")
            except Exception:
                pass
            # 首次登录成功后展示一次「接口频率限制」提醒（持久化，之后不再弹）
            self._maybe_show_login_api_warning()
        LoginDialog(self.window, self.api, on_success=on_success).exec()

    # ---------- 首次登录：接口频率限制警告（仅展示一次）----------
    def _maybe_show_login_api_warning(self):
        """登录成功后展示一次 B 站接口频率限制提醒，由 login_api_warned 持久化避免重复弹窗。"""
        if self.config.get("login_api_warned", False):
            return
        try:
            msg_warn(
                self.window,
                tr("登录成功！温馨提示：B 站接口存在频率限制，短时间内大量解析或请求可能触发风控，"
                   "导致接口失败甚至 IP 封禁。请适度使用，避免频繁批量操作。"),
                tr("温馨提示"),
            )
            self.config.set("login_api_warned", True)
        except Exception as e:
            self.logger.log(f"首次登录警告弹窗失败：{e}")

    def open_about(self):
        AboutDialog(self.window, self.config).exec()

    def on_settings_changed(self):
        self.apply_theme_from_config()
        self.logger.log("设置已更新")

    def apply_theme_from_config(self):
        # 单次合并应用强调色 + 明暗（set_accent/apply_appearance 各自都会触发
        # 全应用 re-polish，逐个调用会造成双倍卡顿）；值未变化时内部直接跳过。
        # appearance/accent 支持 "system"（跟随 Windows），解析后比较，
        # 配合定时轮询即可在系统主题变化时自动跟随。
        from ui.theme import apply_theme
        changed = apply_theme(self.config.get("accent_color", DEFAULT_ACCENT),
                              self.config.get("appearance", "dark"))
        # 导航栏图标随明暗/强调色自绘，主题变化后强制重绘
        if changed and getattr(self, "sidebar", None) is not None:
            self.sidebar.update()

    def _preview_theme(self, values):
        if values is None:
            self.apply_theme_from_config()
            return
        if "accent" in values:
            set_accent(values["accent"])
        if "appearance" in values:
            apply_appearance(values["appearance"])
        if getattr(self, "sidebar", None) is not None:
            self.sidebar.update()

    def on_nav_click(self, nav_type, data):
        # 在导航栏中高亮当前项（非导航项如 logout 会被忽略）
        if getattr(self, "sidebar", None) is not None:
            self.sidebar.setCurrentItem(nav_type)
        if nav_type == "folder":
            self.load_folder_videos(data)
        elif nav_type == "toview":
            self.load_toview()
        elif nav_type == "history":
            self.load_history()
        elif nav_type == "logout":
            self.logout()
        elif nav_type == "login_changed":
            self.update_login_hint()
        elif nav_type == "following":
            self.load_following()
        elif nav_type == "season":
            self.load_season_list()
        elif nav_type == "popular":
            self.load_popular()
        elif nav_type == "ranking":
            self.load_ranking()
        elif nav_type == "search":
            self.open_search()
        elif nav_type == "music":
            self.open_music_search()
        elif nav_type == "live_center":
            self.open_live_center()

    def load_folder_videos(self, media_id):
        # 未指定具体收藏夹（侧边栏点击「我的收藏夹」时 media_id 为 None）：
        # 先让用户从收藏夹列表里挑一个，再据此拉取其视频。
        if not media_id:
            self._select_favorite_folder()
            return
        self.logger.log(f"加载收藏夹视频列表（media_id={media_id}）...")
        def fetch(pn, ps):
            res = self.api.get_favorite_list(media_id, pn=pn, ps=ps) or {}
            items = self._map_folder_items(res.get("items", []))
            self.api.enrich_videos(items)
            total = res.get("total", 0)
            total_pages = (total + ps - 1) // ps if total else None
            return items, res.get("has_more", False), total_pages
        self._pull_all_and_show("收藏夹", fetch, ps=20)

    def _select_favorite_folder(self):
        if not getattr(self.api, 'uid', None):
            msg_warn(self.window, tr("登录后才能查看收藏夹"), tr("未登录"))
            return
        self.logger.log("加载收藏夹列表...")
        FavFolderDialog(
            self.window, self.api,
            on_select=lambda mid, t: self.load_folder_videos(mid),
        ).exec()

    def _map_folder_items(self, raw):
        video_list = []
        for v in raw:
            bvid = v.get("bvid")
            if not bvid:
                continue
            video_list.append({
                "url": f"https://www.bilibili.com/video/{bvid}",
                "title": v.get("title", "未知标题"),
                "duration": duration_to_seconds(v.get("duration", 0)),
                "thumbnail": v.get("thumbnail") or v.get("pic") or "",
                "view_count": v.get("play", 0) or 0,
                "like_count": v.get("like", 0) or 0,
                "favorite_count": v.get("fav", 0) or 0,
                "publish_time": v.get("publish_time") or self.api.format_timestamp(v.get("pubdate") or v.get("ctime")),
                "favorite_time": v.get("favorite_time", ""),
            })
        return video_list

    def load_history(self):
        if not getattr(self.api, 'uid', None):
            msg_warn(self.window, tr("登录后才能查看历史记录"), tr("未登录"))
            return
        self.logger.log("加载浏览历史记录...")
        def fetch(pn, ps):
            res = self.api.get_history_search(pn=pn, ps=ps) or {}
            items = self._map_history_items(res.get("items", []))
            self.api.enrich_videos(items)
            total = res.get("total", 0)
            total_pages = (total + ps - 1) // ps if total else None
            return items, res.get("has_more", False), total_pages
        self._pull_all_and_show("历史记录", fetch, ps=20)

    def _map_history_items(self, raw):
        video_list = []
        for item in raw:
            hist = item.get("history", {})
            bvid = hist.get("bvid") or item.get("bvid")
            if not bvid:
                continue
            title = item.get("title", "未知标题")
            cover = item.get("cover", "")
            view_at = item.get("view_at") or hist.get("view_at")
            pub_time = ""
            if view_at:
                try:
                    from datetime import datetime
                    pub_time = datetime.fromtimestamp(view_at).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
            video_list.append({
                "url": f"https://www.bilibili.com/video/{bvid}",
                "title": title, "duration": 0, "thumbnail": cover,
                "view_count": 0, "like_count": 0, "favorite_count": 0,
                "publish_time": pub_time,
            })
        return video_list

    def load_following(self):
        if not getattr(self.api, 'uid', None):
            msg_warn(self.window, tr("请先登录以查看关注列表"), tr("未登录"))
            return
        self.logger.log("加载关注列表...")
        threading.Thread(target=self._load_following_thread, daemon=True).start()

    def _load_following_thread(self):
        try:
            follows = self.api.get_following_list()
            if not follows:
                run_on_main(lambda: (self.logger.log("关注列表为空"),
                                              msg_info(self.window, tr("关注列表为空"), tr("提示"))))
                return
            run_on_main(lambda: self.show_following_dialog(follows))
        except Exception as e:
            run_on_main(lambda err=e: (self.logger.log(f"加载关注列表失败：{str(err)}"),
                                                 msg_error(self.window, tr("加载关注列表失败：{}").format(str(err)), tr("错误"))))

    def show_following_dialog(self, follows):
        if not follows:
            self.logger.log("关注列表为空")
            msg_info(self.window, tr("关注列表为空"), tr("提示"))
            return

        def on_open_space(mid):
            self.load_uploader_videos(mid)

        FollowingDialog(self.window, follows, on_open_space).exec()

    def load_uploader_videos(self, mid):
        self.logger.log(f"加载UP主空间视频... (mid={mid})")
        def fetch(pn, ps):
            res = self.api.get_uploader_videos(mid, pn=pn, ps=ps) or {}
            items = res.get("items", []) or []
            self.api.enrich_videos(items)
            total = res.get("total", 0)
            total_pages = (total + ps - 1) // ps if total else None
            return items, res.get("has_more", False), total_pages
        self._pull_all_and_show(f"UP主空间 {mid}", fetch, ps=30)

    def load_season_list(self):
        if not getattr(self.api, 'uid', None):
            msg_warn(self.window, tr("请先登录以查看追番列表"), tr("未登录"))
            return
        if getattr(self, "_season_list_loading", False):
            return
        self._season_list_loading = True
        self.logger.log("加载追番列表...")
        try:
            threading.Thread(target=self._load_season_thread, daemon=True).start()
        except Exception:
            self._season_list_loading = False
            raise

    def _load_season_thread(self):
        try:
            video_list = self.api.get_season_list()
            run_on_main(lambda result=video_list: self._on_season_list_loaded(result))
        except Exception as e:
            run_on_main(lambda err=e: self._on_season_list_failed(err))

    def _on_season_list_loaded(self, season_list):
        try:
            self.show_season_select(season_list)
        finally:
            self._season_list_loading = False

    def _on_season_list_failed(self, error):
        try:
            self.logger.log(f"加载追番列表失败：{str(error)}")
            msg_error(self.window,
                      tr("加载追番列表失败：{}").format(str(error)), tr("错误"))
        finally:
            self._season_list_loading = False

    def load_toview(self):
        if not getattr(self.api, 'uid', None):
            msg_warn(self.window, tr("请先登录B站账号，否则无法获取稍后再看列表。"), tr("未登录"))
            return
        self.logger.log("加载稍后再看列表...")
        def fetch(pn, ps):
            res = self.api.get_toview(pn=pn, ps=ps) or {}
            items = self._map_toview_items(res.get("items", []))
            self.api.enrich_videos(items)
            total = res.get("total", 0)
            total_pages = (total + ps - 1) // ps if total else None
            return items, res.get("has_more", False), total_pages
        self._pull_all_and_show("稍后再看", fetch, ps=20)

    def _map_toview_items(self, raw):
        video_list = []
        for v in raw:
            bvid = v.get("bvid")
            if not bvid:
                continue
            video_list.append({
                "url": f"https://www.bilibili.com/video/{bvid}",
                "title": v.get("title", "未知标题"),
                "duration": duration_to_seconds(v.get("duration", 0)),
                "thumbnail": v.get("thumbnail") or v.get("cover") or v.get("pic") or "",
                "view_count": 0, "like_count": 0, "favorite_count": 0,
                "publish_time": v.get("publish_time") or self.api.format_timestamp(v.get("view_at") or v.get("pubdate") or v.get("ctime")),
            })
        return video_list

    def load_popular(self):
        self.logger.log("加载每周必看（最新一期）...")
        # 先弹窗显示「加载中」，再后台拉取，避免弹窗空白造成卡顿错觉
        dlg = SelectDialog(self.window, None, self._on_videos_selected,
                           title=tr("每周必看"), loading=True)
        threading.Thread(target=self._load_popular_thread, args=(dlg,), daemon=True).start()
        dlg.exec()

    def _load_popular_thread(self, dlg):
        try:
            video_list = self.api.get_popular_weekly()
            if not video_list:
                run_on_main(lambda: (dlg.set_loading(False, tr("每周必看为空或获取失败")),
                                              msg_warn(dlg, tr("每周必看为空或获取失败"), tr("提示"))))
                return
            self.api.enrich_videos(video_list)
            run_on_main(lambda n=len(video_list): self.logger.log(f"已加载 {n} 个每周必看视频"))
            run_on_main(lambda: dlg.fill(video_list))
        except Exception as e:
            run_on_main(lambda err=str(e): (dlg.set_loading(False, tr("加载每周必看失败：{}").format(err)),
                                                 msg_error(dlg, tr("加载每周必看失败：{}").format(err), tr("错误"))))

    def load_ranking(self):
        self.logger.log("加载排行榜（全站）...")
        # 先弹窗显示「加载中」，再后台拉取，避免弹窗空白造成卡顿错觉
        dlg = SelectDialog(self.window, None, self._on_videos_selected,
                           title=tr("排行榜"), loading=True)
        threading.Thread(target=self._load_ranking_thread, args=(dlg,), daemon=True).start()
        dlg.exec()

    def _load_ranking_thread(self, dlg):
        try:
            video_list = self.api.get_ranking(rid=0)
            if not video_list:
                run_on_main(lambda: (dlg.set_loading(False, tr("排行榜为空或获取失败")),
                                              msg_warn(dlg, tr("排行榜为空或获取失败"), tr("提示"))))
                return
            self.api.enrich_videos(video_list)
            run_on_main(lambda n=len(video_list): self.logger.log(f"已加载 {n} 个排行榜视频"))
            run_on_main(lambda: dlg.fill(video_list))
        except Exception as e:
            run_on_main(lambda err=str(e): (dlg.set_loading(False, tr("加载排行榜失败：{}").format(err)),
                                                 msg_error(dlg, tr("加载排行榜失败：{}").format(err), tr("错误"))))

    def _record_history(self, video_list, source="manual"):
        try:
            for item in video_list:
                add_history_entry(
                    item.get("url", ""),
                    item.get("title", "") or (video_list[0].get("title", "") if video_list else ""),
                    source=source)
        except Exception:
            pass

    def _add_videos_direct(self, video_list):
        if not video_list:
            return
        self._record_history(video_list, source="manual")
        tasks = []
        for item in video_list:
            tasks.append((
                item["url"], item["title"], item["duration"],
                item.get("publish_time", ""), item.get("view_count", 0),
                item.get("like_count", 0), item.get("favorite_count", 0),
                item.get("thumbnail", ""), item.get("uploader", ""), item.get("category", "")))
        add_cnt = self.engine.add_tasks_batch(tasks)
        self.logger.log(f"已添加 {add_cnt} 个视频到下载队列")
        self._on_queue_status(self.engine.queue)

    def open_search(self):
        SearchDialog(self.window, self.api.get_search_results,
                     on_confirm=self._route_search_selected,
                     title=tr("搜索 B站")).exec()

    def open_music_search(self):
        SearchDialog(self.window, self.api.get_music_search_results,
                     on_confirm=self._route_search_selected,
                     title=tr("bilibili音乐")).exec()

    def _route_search_selected(self, selected):
        if not selected:
            self.logger.log("未勾选任何结果")
            return
        videos, users, seasons = [], [], []
        for s in selected:
            if s.get("type") == "user":
                users.append(s)
            elif s.get("type") == "bangumi":
                seasons.append(s)
            else:
                videos.append(s)
        # UP主结果 → 展开其空间视频再勾选
        for u in users:
            mid = u.get("mid")
            if mid:
                self.load_uploader_videos(mid)
        if seasons:
            self._expand_seasons_to_episodes(seasons)
        # 视频结果直接进入下载设置；番剧结果已展开为可选分集。
        if videos:
            self._add_selected_to_queue(videos)

    def _add_videos_via_options(self, video_list):
        if not video_list:
            return
        self._on_videos_selected(video_list)

    # ========== 选择对话框 ==========
    def _pull_all_and_show(self, title, fetch, ps=30):
        """打开分页选择对话框：立即弹窗，仅先拉第 1 页，后续按需翻页拉取。

        原先是「拉完全部再弹窗」，数据多时弹窗空白很久、体验差；现改为
        PaginatedSelectDialog，构造即显示，上/下一页或跳转时才拉对应页。
        fetch 回调返回 (items, has_more)，已在各调用点内部完成 enrich_videos。
        """
        self.logger.log(f"打开「{title}」分页选择（每页 {ps} 条，按需拉取）")
        dlg = PaginatedSelectDialog(
            self.window, fetch, ps,
            on_confirm=self._on_videos_selected,
            title=title,
        )
        dlg.exec()

    def show_video_select(self, video_list):
        if not video_list:
            self.logger.log("该分类下无视频")
            msg_info(self.window, tr("该分类下无视频"), tr("提示"))
            return

        def on_confirm(selected_items):
            self._on_videos_selected(selected_items)

        SelectDialog(self.window, video_list, on_confirm).exec()

    def show_episode_select(self, episode_list):
        if not episode_list:
            self.logger.log("该分类下无分集")
            msg_info(self.window, tr("该分类下无分集"), tr("提示"))
            return

        EpisodeSelectDialog(self.window, episode_list,
                           on_confirm=self._on_videos_selected,
                           title=tr("选择分集")).exec()

    def show_season_select(self, season_list):
        if not season_list:
            self.logger.log("追番列表为空")
            msg_info(self.window, tr("追番列表为空"), tr("提示"))
            return

        def on_confirm(selected):
            if selected:
                self._expand_seasons_to_episodes(selected)

        SelectDialog(self.window, season_list, on_confirm, title=tr("我的追番")).exec()

    def _expand_seasons_to_episodes(self, series_list):
        series_list = list(series_list)
        self.logger.log(f"正在解析 {len(series_list)} 个番剧的分集…")
        total = len(series_list)

        def worker():
            all_episodes = []
            failed = []
            for s in series_list:
                sid = s.get("season_id")
                if not sid:
                    m = re.search(r"(?:ss|season_id[=/])(\d+)", s.get("url", ""))
                    if m:
                        sid = m.group(1)
                if not sid:
                    failed.append(s.get("title", "未知番剧"))
                    continue
                try:
                    eps = self.api.get_season_episodes(ssid=sid)
                except Exception as e:
                    failed.append(f"{s.get('title', '')}: {e}")
                    continue
                if not eps:
                    failed.append(s.get("title", "未知番剧"))
                    continue
                all_episodes.extend(eps)
            if not all_episodes:
                def _show_error():
                    self.logger.log("未解析到任何分集")
                    detail = "（" + "，".join(str(f) for f in failed) + "）" if failed else ""
                    msg_error(self.window, tr("未解析到任何分集") + detail, tr("错误"))
                run_on_main(_show_error)
                return
            self.logger.log(f"已汇总 {len(all_episodes)} 个分集（来自 {total} 个番剧）")
            run_on_main(lambda: self.show_episode_select(all_episodes))

        threading.Thread(target=worker, daemon=True).start()

    def _on_videos_selected(self, selected):
        if not selected:
            self.logger.log("未勾选任何视频")
            return
        # 选择视频/分集后，按设置决定是否弹出「下载选项」对话框（参照 bili23）
        if self.config.get("show_download_options_dialog", True):
            DownloadOptionsDialog(
                self.window, self.config, len(selected),
                on_confirm=lambda: self._add_selected_to_queue(selected),
            ).exec()
        else:
            self._add_selected_to_queue(selected)

    def _add_selected_to_queue(self, selected):
        self._record_history(selected, source="manual")
        tasks = []
        for item in selected:
            tasks.append((
                item.get("url", ""), item.get("title", ""),
                item.get("duration", 0), item.get("publish_time", ""),
                item.get("view_count", 0), item.get("like_count", 0),
                item.get("favorite_count", 0), item.get("thumbnail", ""),
                item.get("uploader", ""), item.get("category", "")))
        add_cnt = self.engine.add_tasks_batch(tasks)
        self.logger.log(f"已添加 {add_cnt} 个视频到下载队列")
        self._on_queue_status(self.engine.queue)

    def _nav_load_done(self, msg):
        self.logger.log(msg)
        self._on_queue_status(self.engine.queue)

    def logout(self):
        self.api.uid = None
        self.api.nickname = None
        self.api.session.cookies.clear()
        try:
            if os.path.exists("cookies.txt"):
                os.remove("cookies.txt")
                self.logger.log("已删除 cookies.txt")
        except Exception as e:
            self.logger.log(f"删除 cookies.txt 失败：{e}")
        self.sidebar.refresh()
        self.logger.log("已登出")
        self.update_login_hint()

    def update_login_hint(self):
        try:
            if getattr(self, "sidebar", None) is not None:
                self.sidebar.refresh()
        except Exception:
            pass

    def open_live_recorder(self):
        """打开直播录制监控窗口（非模态，可随时启停）。无预填目标时由用户手动输入。"""
        self._open_live_record_window(None)

    def _open_live_record_window(self, target=None):
        """打开（或聚焦已存在的）直播录制监控窗口。

        target 可为 room dict / 房间链接 / 房间号；提供则预填并自动开始录制。
        同一 room_id 的窗口只保留一个（已开则聚焦），避免重复录制。
        """
        rid = None
        if target is not None:
            rid = self._resolve_room_id(target)
        if rid is not None and rid in self._live_windows:
            w = self._live_windows[rid]
            if w.isVisible():
                w.activateWindow()
                w.raise_()
                return
        w = LiveRecordWindow(parent=self.window, api=self.api,
                             config=self.config, logger=self.logger, target=target)

        def remove(r):
            self._live_windows.pop(r, None)
            if w in self._live_manual:
                self._live_manual.remove(w)
        w._registry_remove = remove
        if rid is not None:
            self._live_windows[rid] = w
        else:
            self._live_manual.append(w)  # 保活，避免局部变量回收导致窗口闪退
        w.show()  # 非模态：不阻塞主窗口

    def open_live_center(self):
        LiveCenterDialog(
            self.window, api=self.api,
            on_record=self._start_live_record,
            on_open_room=self._open_live_room,
        ).exec()

    # ---------- 直播录制 ----------
    def _resolve_room_id(self, target):
        """从房间链接或纯数字房间号里提取 roomid。"""
        import re
        if isinstance(target, dict):
            return target.get("roomid")
        target = (target or "").strip()
        m = re.search(r"live\.bilibili\.com/?(\d+)", target)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d+)", target)
        return int(m.group(1)) if m else None

    def _start_live_record(self, target):
        """直播中心「录制」按钮的回调：打开监控窗口并自动开始（不弹确认框）。"""
        self._open_live_record_window(target)

    def _open_live_room(self, room):
        room_id = room.get("roomid") if isinstance(room, dict) else None
        if room_id:
            import webbrowser
            webbrowser.open(f"https://live.bilibili.com/{room_id}")

    # ---------- 语言切换 ----------
    def on_language_change(self, lang):
        set_language(lang)
        try:
            self.config.set("language", lang)
        except Exception:
            pass
        self.window.setWindowTitle("BilibiliDownloader")
        retranslate_all()
        try:
            self.refresh_overall_progress()
        except Exception:
            pass
        try:
            self.sidebar.refresh()
            self.sidebar.retranslate()
            self.sidebar.set_language_display(lang)
        except Exception:
            pass
        try:
            self.queue_view.retranslate()
        except Exception:
            pass
        try:
            self.tray.update_menu()
        except Exception:
            pass

    def run(self):
        self.window.show()
        # 首次启动（尚未同意《用户协议》）先弹协议，不接受则退出
        if not self.config.get("accepted_terms", False):
            QTimer.singleShot(0, self.show_terms_of_use)
            return
        # 已同意过：启动时若已处于登录态且尚未展示过警告，则补一次
        # （覆盖通过 cookies.txt 持久登录、未走「登录」弹窗的情况；仅首次）
        if getattr(self.api, "uid", None):
            QTimer.singleShot(0, self._maybe_show_login_api_warning)

    def show_terms_of_use(self):
        """弹出《用户协议》窗口；不接受则退出程序（首次启动场景）。

        从「关于」窗口打开时为只读查看，拒绝/关闭不会退出程序。
        """
        from ui.terms_dialog import TermsOfUseDialog

        dlg = TermsOfUseDialog(self.window, self.config)
        if not dlg.exec():
            # 用户不接受使用协议 → 关闭程序
            self.logger.log("用户未接受《用户协议》，程序退出")
            self.quit_app()
            return
        self.logger.log("用户已同意《用户协议》")
        # 同意后续：登录态补一次接口限制警告（仅首次）
        if getattr(self.api, "uid", None):
            QTimer.singleShot(0, self._maybe_show_login_api_warning)
