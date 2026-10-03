"""功能型子对话框（Fluent 版）：关于 / 登录 / 搜索 / 解析记录 / 批量解析 /
日志 / 直播中心 / 录制直播 / 收藏夹选择。

统一范式（与设置窗口、下载选项窗口、侧边栏一致）：
- 全部基于 `qfluentwidgets`：`FluentContentDialog`（标题栏 + 内容区 + 底部按钮排）
  或 `TopNavigationDialog`（顶部 Pivot 分页，登录窗口用）；
- 消息提示一律走 `ui.fluent_dialog` 的 `msg_info / msg_warn / msg_error / msg_confirm`
  （遮罩式 Fluent `MessageBox`），不再出现 `QMessageBox`；
- 模态语义由基类用 `QEventLoop` 模拟，对外仍是 `dlg.exec()`（返回值 True=确定）。

约定：
- 所有「可见静态文本」用 tr() 包裹，便于多语言即时刷新；
- 配置值 / 选项（如 "dark" / "1080p" / "mp4"）只作为内部存储值，绝不翻译，
  仅翻译其「显示标签」；
- 后台线程一律 `utils.main_thread.run_on_main` 回主线程刷 UI。
"""
from __future__ import annotations

import os
import threading

import requests

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QImage, QPixmap, QTextCursor, QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QHeaderView, QListWidgetItem, QScrollArea,
    QStackedWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, FlowLayout, ImageLabel,
    LargeTitleLabel, LineEdit, ListWidget, PrimaryPushButton, PushButton,
    SearchLineEdit, TableWidget, TextEdit,
)

from utils.i18n import tr, register
from utils.main_thread import run_on_main
from utils.cookie_manager import load_cookie_string
from utils.bili_qrcode import (
    generate_qr, poll_qr,
    SCAN_SUCCESS, SCAN_EXPIRED, SCAN_CONFIRMED, SCAN_WAITING,
)

from ui.fluent_dialog import (
    FluentContentDialog, TopNavigationDialog,
    msg_info, msg_warn, msg_error, msg_confirm,
)
from ui.list_layout import LayoutModeToggle, manager, is_compact
from ui.select_list_view import SelectListView, _key_of
from ui.select_dialog import PaginationMixin, SelectDialogBase
from ui.icons import icon_pixmap
from ui.theme import palette, get_accent

APP_NAME = "BilibiliDownloader"

# FluentIcon 简写
FIF = FluentIcon


def _page():
    """返回一个「空白内容页」：QWidget + 竖向零边距布局（给分页窗口用）。"""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(14)
    return w, lay


# --------------------------------------------------------------------------- #
# 关于
# --------------------------------------------------------------------------- #
class AboutDialog(FluentContentDialog):
    def __init__(self, parent=None, config=None):
        super().__init__((460, 320), parent, title=tr("关于"))
        self.config = config

        self.add_widget(LargeTitleLabel(APP_NAME, self))
        self.add_widget(CaptionLabel("v2.0.0 · PySide6 · qfluentwidgets", self))

        desc = BodyLabel(tr(
            "基于 PySide6 重构的 B 站视频下载工具，支持视频 / 番剧 / 直播录制"
            "与批量下载、弹幕字幕元数据抓取。"
        ), self)
        desc.setWordWrap(True)
        self.add_widget(desc, 1)

        # 左下角：查看《用户协议》（只读，不接受也不退出程序）
        terms = self.add_button(tr("用户协议"), slot=self._open_terms, right=False)
        register(terms, "用户协议")

        ok = self.add_button(tr("确定"), primary=True, slot=self.accept)
        register(ok, "确定")

    def _open_terms(self):
        from ui.terms_dialog import TermsOfUseDialog
        TermsOfUseDialog(self, self.config).exec()


# --------------------------------------------------------------------------- #
# 登录（二维码 / Cookie 双页）
# --------------------------------------------------------------------------- #
def _save_session_cookies(session, path):
    """把 requests.Session 里的 Cookie 以 Netscape 格式落盘，供后续启动读取。"""
    lines = ["# Netscape HTTP Cookie File"]
    for c in session.cookies:
        domain = c.domain or ".bilibili.com"
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path_ = c.path or "/"
        secure = "TRUE" if c.secure else "FALSE"
        expires = str(int(c.expires)) if c.expires else "0"
        lines.append("\t".join([domain, flag, path_, secure, expires, c.name, c.value]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _pil_to_pixmap(img):
    img = img.convert("RGB")
    w, h = img.size
    data = img.tobytes("raw", "RGB")
    qimg = QImage(data, w, h, w * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)


class LoginDialog(TopNavigationDialog):
    """登录窗口：顶部 Pivot 切「二维码登录 / Cookie 登录」，右下仅「取消」。

    二维码逻辑（生成 → 展示 → 轮询 → 落盘 cookies.txt → on_success 回调）与
    Cookie 校验逻辑全部沿用原实现，仅替换外壳为 Fluent。
    """

    def __init__(self, parent, api, on_success=None):
        super().__init__((560, 640), parent, title=tr("登录 B站"),
                         with_ok=False, cancel_text=tr("取消"))
        self.api = api
        self.on_success = on_success
        self._qr_key = None
        self._stop = threading.Event()

        self.qr_page = self._build_qr_page()
        self.cookie_page = self._build_cookie_page()
        self.add_page("qr", tr("二维码登录"), FIF.CAMERA, self.qr_page)
        self.add_page("cookie", tr("Cookie 登录"), FIF.PEOPLE, self.cookie_page)
        self.show_page("qr")
        self.stackedWidget.setCurrentWidget(self.qr_page)

        register(self.cancelBtn, "取消")

        # 启动二维码生成（默认页）
        self._generate()

    # ---------- 二维码页 ----------
    def _build_qr_page(self):
        w, lay = _page()

        self.qr_label = ImageLabel(self)
        self.qr_label.setFixedSize(248, 248)
        self.qr_label.setBorderRadius(8, 8, 8, 8)
        self.qr_label.setScaledContents(True)
        lay.addWidget(self.qr_label, alignment=Qt.AlignHCenter)

        self.status_label = CaptionLabel(tr("正在生成二维码…"), self)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        lay.addWidget(self.status_label)

        lay.addStretch(1)

        self.refresh_btn = PushButton(tr("刷新二维码"), self)
        self.refresh_btn.setIcon(FIF.SYNC)
        self.refresh_btn.setMinimumWidth(140)
        self.refresh_btn.clicked.connect(self._generate)
        lay.addWidget(self.refresh_btn, alignment=Qt.AlignHCenter)

        register(self.refresh_btn, "刷新二维码")
        return w

    # ---------- Cookie 页 ----------
    def _build_cookie_page(self):
        w, lay = _page()

        hint = BodyLabel(tr("粘贴浏览器中复制的 Cookie 字符串（支持 Netscape / 请求头 "
                            "Cookie / JSON 三种格式），点击登录即可。二维码异常时可用此方式登录。"),
                         self)
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.cookie_edit = TextEdit(self)
        self.cookie_edit.setAcceptRichText(False)
        self.cookie_edit.setPlaceholderText(
            "SESSDATA=...; bili_jct=...; DedeUserID=...")
        lay.addWidget(self.cookie_edit, 1)

        self.cookie_status = CaptionLabel("", self)
        self.cookie_status.setWordWrap(True)
        lay.addWidget(self.cookie_status)

        login_btn = PrimaryPushButton(tr("使用 Cookie 登录"), self)
        login_btn.setMinimumWidth(180)
        login_btn.clicked.connect(self._on_cookie_login)
        lay.addWidget(login_btn, alignment=Qt.AlignHCenter)

        register(login_btn, "使用 Cookie 登录")
        return w

    def _on_cookie_login(self):
        text = self.cookie_edit.toPlainText().strip()
        if not text:
            self.cookie_status.setText(tr("请先粘贴 Cookie 字符串"))
            return
        self.cookie_status.setText(tr("正在验证 Cookie…"))
        try:
            ok = self.api.set_cookie_string(text)
        except Exception as e:
            self.cookie_status.setText(tr("登录失败：") + str(e))
            return
        if not ok:
            self.cookie_status.setText(
                tr("登录失败：Cookie 无效或已过期（需含 SESSDATA）"))
            return
        # 验证通过：落盘并回调
        try:
            _save_session_cookies(self.api.session, "cookies.txt")
        except Exception as e:
            self.cookie_status.setText(tr("登录成功，但保存 Cookie 失败：") + str(e))
            return
        self.api.set_cookie_string(load_cookie_string("cookies.txt"))
        self.accept()
        if self.on_success:
            cb = self.on_success
            QTimer.singleShot(0, cb)

    # ---------- 二维码生成 ----------
    def _generate(self):
        self._stop.set()          # 停掉旧轮询
        self.refresh_btn.setEnabled(False)
        self.status_label.setText(tr("正在生成二维码…"))
        threading.Thread(target=self._generate_thread, daemon=True).start()

    def _generate_thread(self):
        # 兜底：passport 部分环境要求 buvid3/buvid4，否则二维码生成异常
        try:
            ensure = getattr(self.api, "_ensure_buvid", None)
            if ensure is not None:
                ensure()
        except Exception:
            pass
        try:
            img, key, _url = generate_qr(self.api.session)
        except Exception as e:
            # 注意：异常变量 e 在 except 块结束即被删除，延迟回调必须当场绑定字符串；
            # 写成 lambda: ... str(e) 会在回调真正执行时报
            # "cannot access free variable 'e'"，从而丢掉错误提示。
            run_on_main(lambda err=str(e): self._on_generate_error(err))
            return
        self._qr_key = key
        run_on_main(lambda: self._on_generated(img))

    def _on_generated(self, img):
        self.qr_label.setImage(_pil_to_pixmap(img))
        self.status_label.setText(tr("请使用哔哩哔哩客户端扫码登录"))
        self.refresh_btn.setEnabled(True)
        self._stop.clear()
        threading.Thread(target=self._poll_loop, daemon=True).start()

    def _on_generate_error(self, err):
        self.status_label.setText(tr("二维码生成失败：") + err)
        self.refresh_btn.setEnabled(True)

    # ---------- 轮询 ----------
    def _poll_loop(self):
        while not self._stop.is_set():
            try:
                status = poll_qr(self.api.session, self._qr_key)
            except Exception as e:
                run_on_main(lambda: self.status_label.setText(
                    tr("轮询失败：") + str(e)))
                return
            if status == SCAN_SUCCESS:
                run_on_main(self._on_success)
                return
            if status == SCAN_EXPIRED:
                run_on_main(lambda: self.status_label.setText(
                    tr("二维码已失效，请点击刷新")))
                return
            if status == SCAN_CONFIRMED:
                run_on_main(lambda: self.status_label.setText(
                    tr("已扫码，请在手机端确认")))
            else:
                run_on_main(lambda: self.status_label.setText(
                    tr("等待扫码…")))
            self._stop.wait(2.0)

    # ---------- 成功 ----------
    def _on_success(self):
        try:
            _save_session_cookies(self.api.session, "cookies.txt")
            self.api.set_cookie_string(load_cookie_string("cookies.txt"))
        except Exception as e:
            self.status_label.setText(tr("登录成功，但保存 Cookie 失败：") + str(e))
        # 先关闭登录窗口，再异步执行成功回调（刷新侧栏 + 首次登录温馨提示），
        # 避免温馨提示弹窗被仍可见的登录窗压在后面（此前 on_success 先跑、登录窗
        # 尚未关，提示框父窗口是主窗口、被置顶的登录窗盖住）。
        self.accept()
        if self.on_success:
            cb = self.on_success
            QTimer.singleShot(0, cb)

    def reject(self):
        self._stop.set()
        super().reject()

    def closeEvent(self, e):
        self._stop.set()
        super().closeEvent(e)


# --------------------------------------------------------------------------- #
# 搜索（综合 / 音乐）
# --------------------------------------------------------------------------- #
class SearchDialog(PaginationMixin, SelectDialogBase):
    """B 站综合搜索 / 音乐搜索窗口（Fluent 版，复用分页逻辑）。

    顶部内联搜索框，回车或点「搜索」即在后台线程调用 search_fn(keyword, page=pn)，
    结果复用 SelectListView，以显示视频封面 / UP 主头像，并响应全局详细 / 精简布局。
    确认后把勾选项经 on_confirm(selected) 回调交给主窗口路由。

    分页：复用 PaginationMixin 的 fetch(pn, ps)->(items, has_more) 契约与翻页栏，
    搜索函数按 page 返回后续页（不再受单次 20 条上限约束），可翻到更多结果。

    search_fn 由调用方注入：
      - 综合搜索：api.get_search_results
      - 音乐搜索：api.get_music_search_results
    均为 (keyword:str, page:int=1) -> (items:list[dict], has_more:bool)。
    """

    def __init__(self, parent, search_fn, on_confirm=None, title=tr("搜索")):
        self.search_fn = search_fn
        # 复用分页契约：fetch(pn, ps) -> (items, has_more)
        self.fetch = lambda pn, ps: self._search_fetch(pn)
        self.ps = 20
        self.pn = 1
        self.has_more = True
        self._busy = False
        self._keyword = ""
        super().__init__(parent, on_confirm, title)
        self.input.setFocus()

    def _build_content(self):
        # 顶部：内联搜索框（置于最上方；列表、全选、分页栏由基类构建）
        top = QHBoxLayout()
        top.setSpacing(10)
        self.input = SearchLineEdit(self)
        self.input.setPlaceholderText(tr("输入关键词后回车或点击搜索"))
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self._do_search)
        self.search_btn = PrimaryPushButton(tr("搜索"), self)
        self.search_btn.setMinimumWidth(96)
        self.search_btn.setIcon(FIF.SEARCH)
        self.search_btn.clicked.connect(self._do_search)
        top.addWidget(self.input, 1)
        top.addWidget(self.search_btn)
        self.add_layout(top)
        super()._build_content()
        # 行尾「在浏览器中打开」按钮由 SelectListView 按 item 字段自动推导
        # （搜索结果自带 url：视频/BV 页、UP 主/个人空间、番剧/bangumi 页），无需显式设置。
        register(self.search_btn, "搜索")
        register(self.input, "输入关键词后回车或点击搜索", "placeholder_text")

    def _build_extra(self):
        # 复用分页栏（上一页 / 下一页 / 第 N 页 / 跳转）
        self._build_pagination_bar()

    def _search_fetch(self, pn):
        """按页拉取，兼容 search_fn 返回 list 或 (items, has_more)。"""
        if not self._keyword:
            return [], False
        res = self.search_fn(self._keyword, page=pn)
        if isinstance(res, tuple):
            items, has_more = (res[0] or []), bool(res[1])
        else:
            items, has_more = (res or []), False
        return items, has_more

    def _do_search(self):
        kw = self.input.text().strip()
        if not kw:
            return
        self._keyword = kw
        self._checked_keys.clear()
        self._selected.clear()
        self.search_btn.setEnabled(False)
        self._load_page(1)  # 复用分页加载（后台线程，UI 不阻塞）

    def _render_page(self, pn, items, has_more, total=None):
        self.pn = pn
        self.has_more = has_more
        if total is not None:
            self._total_pn = total
        if not has_more:
            self._last_pn = pn
        self._busy = False
        self._fill_table(items)
        M = self._total_pn or self._last_pn
        if M:
            self.page_lbl.setText(
                tr("第 {pn} / {total} 页").format(pn=pn, total=M))
        else:
            self.page_lbl.setText(tr("第 {pn} 页").format(pn=pn))
        self.jump_spin.setValue(pn)
        if M:
            self.jump_spin.setRange(1, max(1, M))
        self._set_nav_enabled(True)
        if M:
            self.status_lbl.setText(
                tr("第 {pn} / {total} 页，共 {n} 条结果").format(pn=pn, total=M, n=len(items)))
        else:
            self.status_lbl.setText(tr("第 {pn} 页，共 {n} 条结果").format(pn=pn, n=len(items)))
        self.search_btn.setEnabled(True)
        if not items:
            if pn == 1:
                msg_info(self, tr("未找到结果"))
            else:
                msg_info(self, tr("第 {pn} 页没有数据").format(pn=pn))

    def _on_error(self, pn, err):
        self._busy = False
        self._set_nav_enabled(True)
        self.status_lbl.setText(tr("加载失败"))
        self.search_btn.setEnabled(True)
        msg_error(self, tr("加载第 {pn} 页失败：{err}").format(pn=pn, err=err))

    def closeEvent(self, ev):
        self.list.close()
        super().closeEvent(ev)


# --------------------------------------------------------------------------- #
# 解析记录（本地 history.txt）
# --------------------------------------------------------------------------- #
def _read_parse_records(path="history.txt"):
    """解析 history.txt：每行 "时间 | URL | 标题 | 来源"。返回 list[dict]。"""
    records = []
    if not os.path.exists(path):
        return records
    try:
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                parts = ln.split(" | ")
                if len(parts) < 2:
                    continue
                ts = parts[0] if len(parts) >= 4 else ""
                url = parts[1] if len(parts) >= 4 else parts[0]
                title = parts[2] if len(parts) >= 4 else (parts[1] if len(parts) >= 2 else "")
                source = parts[3] if len(parts) >= 4 else "manual"
                records.append({"time": ts, "url": url, "title": title, "source": source})
    except Exception:
        pass
    # 最新在前
    records.reverse()
    return records


class ParseRecordsDialog(FluentContentDialog):
    """展示本地解析记录（history.txt），可加入队列 / 复制链接 / 删除 / 清空。"""

    def __init__(self, parent=None, on_add=None):
        super().__init__((880, 580), parent, title=tr("解析记录"))
        self.on_add = on_add
        self._records = []

        self.table = TableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            [tr("时间"), tr("标题"), tr("来源"), tr("链接")])
        self.table.setSelectionBehavior(TableWidget.SelectRows)
        self.table.setEditTriggers(TableWidget.NoEditTriggers)
        self.table.setWordWrap(False)
        hdr = self.table.horizontalHeader()
        for col in (1, 3):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self._on_double)
        self.add_widget(self.table, 1)

        self.add_btn = self.add_button(tr("加入队列"), right=False,
                                      slot=self._on_add)
        self.copy_btn = self.add_button(tr("复制链接"), right=False,
                                       slot=self._copy)
        self.del_btn = self.add_button(tr("删除选中"), right=False,
                                      slot=self._delete)
        self.clear_btn = self.add_button(tr("清空记录"), right=False,
                                        slot=self._clear)
        self.close_btn = self.add_button(tr("关闭"), primary=True,
                                        slot=self.accept)

        for b, k in ((self.add_btn, "加入队列"), (self.copy_btn, "复制链接"),
                     (self.del_btn, "删除选中"), (self.clear_btn, "清空记录"),
                     (self.close_btn, "关闭")):
            register(b, k)

        self._load()

    def _load(self):
        self._records = _read_parse_records()
        self.table.setRowCount(len(self._records))
        for i, r in enumerate(self._records):
            self.table.setItem(i, 0, QTableWidgetItem(r.get("time", "")))
            self.table.setItem(i, 1, QTableWidgetItem(r.get("title", "")))
            self.table.setItem(i, 2, QTableWidgetItem(r.get("source", "")))
            self.table.setItem(i, 3, QTableWidgetItem(r.get("url", "")))

    def _current(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._records):
            return None
        return self._records[row]

    def _on_double(self):
        r = self._current()
        if r and self.on_add:
            self.on_add(r.get("url", ""), r.get("title", ""))

    def _on_add(self):
        r = self._current()
        if not r:
            msg_info(self, tr("请先选中一条记录"))
            return
        if self.on_add:
            self.on_add(r.get("url", ""), r.get("title", ""))

    def _copy(self):
        r = self._current()
        if not r:
            return
        QGuiApplication.clipboard().setText(r.get("url", ""))

    def _delete(self):
        r = self._current()
        if not r:
            return
        self._records.pop(self.table.currentRow())
        self._write_records()
        self._load()

    def _clear(self):
        if not msg_confirm(self, tr("确定清空全部解析记录？")):
            return
        self._records = []
        self._write_records()
        self._load()

    def _write_records(self):
        try:
            with open("history.txt", "w", encoding="utf-8") as f:
                for r in reversed(self._records):
                    f.write(f"{r.get('time','')} | {r.get('url','')} | "
                            f"{r.get('title','')} | {r.get('source','manual')}\n")
        except Exception as e:
            msg_error(self, tr("写入解析记录失败：{}").format(str(e)))


# --------------------------------------------------------------------------- #
# 批量解析
# --------------------------------------------------------------------------- #
class BatchParseDialog(FluentContentDialog):
    """多行链接批量解析：每行一个 URL，确认后交给 on_parse(lines)。"""

    def __init__(self, parent=None, on_parse=None):
        super().__init__((620, 480), parent, title=tr("批量解析"))
        self.on_parse = on_parse

        hint = BodyLabel(tr("每行一个链接，支持视频 / 番剧 / 合集 / 用户空间等，自动识别类型"), self)
        hint.setWordWrap(True)
        self.add_widget(hint)

        self.edit = TextEdit(self)
        self.edit.setAcceptRichText(False)
        self.edit.setPlaceholderText("https://www.bilibili.com/video/BVxxxx\n"
                                     "https://www.bilibili.com/bangumi/play/ssxxxx\n...")
        self.add_widget(self.edit, 1)

        self.ok_btn = self.add_button(tr("开始解析"), primary=True,
                                     slot=self._on_accept)
        self.cancel_btn = self.add_button(tr("取消"), slot=self.reject)
        register(self.ok_btn, "开始解析")
        register(self.cancel_btn, "取消")

    def _on_accept(self):
        lines = [l.strip() for l in self.edit.toPlainText().splitlines()
                 if l.strip()]
        if not lines:
            msg_info(self, tr("请先粘贴至少一个链接"))
            return
        if self.on_parse:
            self.on_parse(lines)
        self.accept()


# --------------------------------------------------------------------------- #
# 日志窗口
# --------------------------------------------------------------------------- #
class LogWindow(FluentContentDialog):
    """展示 download.log 内容，可刷新 / 清空。"""

    def __init__(self, parent=None, logger=None):
        super().__init__((780, 580), parent, title=tr("日志"))
        self.logger = logger

        self.text = TextEdit(self)
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.text.setFont(QFont("Consolas", 10))
        self.add_widget(self.text, 1)

        self.refresh_btn = self.add_button(tr("刷新"), right=False,
                                          slot=self._load)
        self.clear_btn = self.add_button(tr("清空"), right=False,
                                        slot=self._clear)
        self.close_btn = self.add_button(tr("关闭"), primary=True,
                                        slot=self.accept)

        register(self.refresh_btn, "刷新")
        register(self.clear_btn, "清空")
        register(self.close_btn, "关闭")

        self._load()

    def _load(self):
        try:
            if os.path.exists("download.log"):
                with open("download.log", "r", encoding="utf-8") as f:
                    self.text.setPlainText(f.read())
            else:
                self.text.setPlainText("")
        except Exception as e:
            self.text.setPlainText(tr("读取日志失败：{}").format(str(e)))
        self.text.moveCursor(QTextCursor.MoveOperation.End)

    def _clear(self):
        if not msg_confirm(self, tr("即将清空日志窗口，同时会清空同目录下的 "
                                    "download.log 文件。\n是否继续？")):
            return
        try:
            open("download.log", "w", encoding="utf-8").close()
            if self.logger is not None:
                # 通知 UI 回调清空显示（落盘文件已空）
                for cb in getattr(self.logger, "ui_callbacks", []) or []:
                    try:
                        cb("")
                    except Exception:
                        pass
        except Exception as e:
            msg_error(self, tr("清空日志失败：{}").format(str(e)))
        self._load()


# --------------------------------------------------------------------------- #
# 直播中心（热门 / 搜索）
# --------------------------------------------------------------------------- #
class _LiveRoomCard(QFrame):
    """直播中心「详细」布局的单个直播间卡片（B 站风格：封面 + 标题 + UP + 在线）。

    点击选中、双击打开。选中态以强调色描边高亮；封面异步加载（带缓存）。
    """

    COVER_H = 116
    WIDTH = 200

    clicked = Signal()
    doubleClicked = Signal()

    def __init__(self, room, parent=None):
        super().__init__(parent)
        self.room = room
        self._selected = False
        self._cover_pm = None
        self.setFixedWidth(self.WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.cover_lbl = QLabel(self)
        self.cover_lbl.setFixedHeight(self.COVER_H)
        self.cover_lbl.setAlignment(Qt.AlignCenter)
        self.cover_lbl.setScaledContents(True)
        lay.addWidget(self.cover_lbl)

        info = QWidget(self)
        il = QVBoxLayout(info)
        il.setContentsMargins(8, 6, 8, 8)
        il.setSpacing(3)
        title = room.get("title", tr("未知直播"))
        self.title_lbl = BodyLabel(title, self)
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setMaximumHeight(38)
        il.addWidget(self.title_lbl)
        uname = room.get("uname", "")
        online = room.get("watched_show") or room.get("online") or ""
        meta = CaptionLabel(f"{uname}  ·  {online}", self)
        il.addWidget(meta)
        lay.addWidget(info)

        self._paint_placeholder()
        self._apply_style()

    # ------------------------------------------------------------------ #
    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        self.clicked.emit()

    def mouseDoubleClickEvent(self, e):
        super().mouseDoubleClickEvent(e)
        self.doubleClicked.emit()

    def resizeEvent(self, e):
        self._refresh_cover()
        super().resizeEvent(e)

    # ------------------------------------------------------------------ #
    def _paint_placeholder(self):
        try:
            pm = icon_pixmap(FluentIcon.VIDEO, 40, "#9aa0a6")
            if pm:
                self.cover_lbl.setPixmap(pm)
        except Exception:
            pass

    def set_cover(self, pm):
        if pm is None or pm.isNull():
            return
        self._cover_pm = pm
        self._refresh_cover()

    def _refresh_cover(self):
        if self._cover_pm is None or self._cover_pm.isNull():
            return
        w = self.cover_lbl.width() or self.WIDTH
        scaled = self._cover_pm.scaled(
            w, self.COVER_H, Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation)
        self.cover_lbl.setPixmap(scaled)

    def set_selected(self, s):
        if self._selected == s:
            return
        self._selected = s
        self._apply_style()

    def _apply_style(self):
        try:
            pal = palette()
            accent = get_accent()
            bg = pal["bg"]
            border = pal["border"]
        except Exception:
            bg, border, accent = "#ffffff", "#d0d0d0", "#2080f0"
        if self._selected:
            self.setStyleSheet(
                f"background:{bg};border:2px solid {accent};border-radius:8px;")
        else:
            self.setStyleSheet(
                f"background:{bg};border:1px solid {border};border-radius:8px;")


class LiveCenterDialog(FluentContentDialog):
    """直播中心：展示热门直播 / 搜索直播间，支持录制、打开直播间、复制链接。

    底部左侧的 ``LayoutModeToggle``（仅图标）切换布局：
    - 详细：B 站风格封面网格（``_LiveRoomCard`` + ``FlowLayout`` 自动换行）；
    - 精简：列表（``ListWidget``）。
    选择通过全局 ``manager`` 持久化（settings.json 的 ``list_layout``）。
    """

    _SOURCE_HOT = "hot"
    _SOURCE_SEARCH = "search"

    def __init__(self, parent=None, api=None, on_record=None, on_open_room=None):
        super().__init__((860, 640), parent, title=tr("直播中心"))
        self.api = api
        self.on_record = on_record
        self.on_open_room = on_open_room
        self._rooms = []
        self._current_room = None
        self._cards = []            # 当前网格页的卡片列表（避免 findChildren 取到已删除残留）
        self._cover_cache = {}      # url -> QPixmap（避免重复下载）
        self._cover_loading = set() # 正在下载的 url

        top = QHBoxLayout()
        top.setSpacing(10)
        self.input = SearchLineEdit(self)
        self.input.setPlaceholderText(tr("搜索直播间关键词"))
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self._do_search)
        self.search_btn = PrimaryPushButton(tr("搜索"), self)
        self.search_btn.setMinimumWidth(96)
        self.search_btn.setIcon(FIF.SEARCH)
        self.search_btn.clicked.connect(self._do_search)
        self.hot_btn = PushButton(tr("热门直播"), self)
        self.hot_btn.setMinimumWidth(110)
        self.hot_btn.setIcon(FIF.HISTORY)
        self.hot_btn.clicked.connect(self._load_hot)
        top.addWidget(self.input, 1)
        top.addWidget(self.search_btn)
        top.addWidget(self.hot_btn)
        self.add_layout(top)

        self.status_lbl = CaptionLabel("", self)
        self.add_widget(self.status_lbl)

        # ---- 内容区：详细=封面网格 / 精简=列表（底部左侧 LayoutModeToggle 切换）----
        self._stack = QStackedWidget(self)

        # 详细：B 站风格封面网格（FlowLayout 自动换行）
        self.grid_scroll = QScrollArea(self)
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.NoFrame)
        self.grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._grid_container = QWidget(self.grid_scroll)
        self._grid_flow = FlowLayout(self._grid_container)
        self._grid_flow.setContentsMargins(0, 0, 0, 0)
        self._grid_flow.setHorizontalSpacing(12)
        self._grid_flow.setVerticalSpacing(12)
        self.grid_scroll.setWidget(self._grid_container)

        # 精简：列表
        self.list = ListWidget(self)
        self.list.setSpacing(2)
        self.list.itemClicked.connect(self._on_list_pick)
        self.list.itemDoubleClicked.connect(self._on_open)

        self._stack.addWidget(self.grid_scroll)
        self._stack.addWidget(self.list)
        self.add_widget(self._stack, 1)

        self.rec_btn = self.add_button(tr("录制"), right=False, slot=self._on_record)
        self.open_btn = self.add_button(tr("打开直播间"), right=False, slot=self._on_open)
        self.copy_btn = self.add_button(tr("复制链接"), right=False, slot=self._copy)
        self.close_btn = self.add_button(tr("关闭"), primary=True, slot=self.accept)

        for b, k in ((self.search_btn, "搜索"), (self.hot_btn, "热门直播"),
                     (self.rec_btn, "录制"), (self.open_btn, "打开直播间"),
                     (self.copy_btn, "复制链接"), (self.close_btn, "关闭")):
            register(b, k)
        register(self.input, "搜索直播间关键词", "placeholder_text")

        self._closed = False
        self._leftBtns.insertWidget(0, LayoutModeToggle(self))
        self._unsub = manager.connect(lambda _m: self._rerender())

        self._load_hot()

    # ------------------------------------------------------------------ #
    # 渲染：详细(网格) / 精简(列表)
    # ------------------------------------------------------------------ #
    def _fill(self, rooms, label):
        self._rooms = list(rooms)
        if not rooms:
            self.status_lbl.setText(tr("未找到直播间"))
            self.list.clear()
            self._clear_grid()
            return
        self.status_lbl.setText(tr("共 {} 个直播间").format(len(rooms)))
        self._render()

    def _render(self):
        """按当前模式渲染可见页面（详细=网格 / 精简=列表）。"""
        if is_compact():
            self._render_list()
            self._stack.setCurrentWidget(self.list)
        else:
            self._render_grid()
            self._stack.setCurrentWidget(self.grid_scroll)

    def _render_list(self):
        self.list.clear()
        for r in self._rooms:
            li = QListWidgetItem(self._row_text(r))
            li.setData(Qt.UserRole, r)
            self.list.addItem(li)
            if self._current_room and r.get("roomid") == self._current_room.get("roomid"):
                self.list.setCurrentItem(li)

    def _clear_grid(self):
        try:
            self._grid_flow.takeAllWidgets()
        except Exception:
            pass
        for w in list(getattr(self, "_cards", [])):
            w.setParent(None)
            w.deleteLater()
        self._cards = []

    def _render_grid(self):
        self._clear_grid()
        if not self._rooms:
            return
        self._cards = []
        for r in self._rooms:
            card = _LiveRoomCard(r, self)
            card.clicked.connect(lambda _=None, rm=r: self._on_card_pick(rm))
            card.doubleClicked.connect(
                lambda _=None, rm=r: self._on_card_activate(rm))
            self._grid_flow.addWidget(card)
            self._cards.append(card)
            if self._current_room and r.get("roomid") == self._current_room.get("roomid"):
                card.set_selected(True)
        for r in self._rooms:
            card = self._card_of(r)
            if card is not None:
                self._load_cover(r, card)

    def _card_of(self, room):
        rid = room.get("roomid")
        for c in getattr(self, "_cards", []):
            if c.room.get("roomid") == rid:
                return c
        return None

    def _row_text(self, r):
        """精简列表行文本：标题 + UP主 + 在线 + 分区。"""
        title = r.get("title", tr("未知直播"))
        uname = r.get("uname", "")
        online = r.get("watched_show") or r.get("online") or ""
        area = r.get("area_name", "")
        return f"{title}  ·  {uname}  ·  {online}  ·  {area}"

    # ------------------------------------------------------------------ #
    # 选择 / 操作
    # ------------------------------------------------------------------ #
    def _on_list_pick(self, item):
        self._current_room = item.data(Qt.UserRole)

    def _on_card_pick(self, room):
        self._current_room = room
        for c in getattr(self, "_cards", []):
            c.set_selected(c.room.get("roomid") == room.get("roomid"))

    def _on_card_activate(self, room):
        self._on_card_pick(room)
        self._on_open()

    def _current(self):
        return getattr(self, "_current_room", None)

    def _load_cover(self, room, card):
        url = room.get("cover") or ""
        if not url:
            return
        cached = self._cover_cache.get(url)
        if cached is not None and not cached.isNull():
            card.set_cover(cached)
            return
        if url in self._cover_loading:
            return
        self._cover_loading.add(url)
        sess = self.api.session if self.api else None

        def work():
            try:
                resp = (sess or requests).get(
                    url, timeout=12,
                    headers={"Referer": "https://live.bilibili.com/",
                              "User-Agent": "Mozilla/5.0"})
                data = resp.content
            except Exception:
                return
            pm = QPixmap()
            if not pm.loadFromData(data):
                return
            self._cover_cache[url] = pm
            run_on_main(lambda: card.set_cover(pm))

        threading.Thread(target=work, daemon=True).start()

    def _rerender(self):
        if getattr(self, "_closed", False):
            return
        self._render()

    def _load_hot(self):
        if self.api is None:
            return
        self.status_lbl.setText(tr("加载热门直播中..."))
        self.list.clear()
        threading.Thread(target=self._hot_thread, daemon=True).start()

    def _hot_thread(self):
        try:
            rooms = self.api.get_live_hot() or []
        except Exception as e:
            run_on_main(lambda err=str(e): self.status_lbl.setText(
                tr("加载失败：{}").format(err)))
            return
        run_on_main(lambda: self._fill(rooms, self._SOURCE_HOT))

    def _do_search(self):
        kw = self.input.text().strip()
        if not kw or self.api is None:
            return
        self.status_lbl.setText(tr("搜索中..."))
        self.list.clear()
        threading.Thread(target=self._search_thread, args=(kw,), daemon=True).start()

    def _search_thread(self, kw):
        try:
            rooms = self.api.search_live_rooms(kw) or []
        except Exception as e:
            run_on_main(lambda err=str(e): self.status_lbl.setText(
                tr("搜索失败：{}").format(err)))
            return
        run_on_main(lambda: self._fill(rooms, self._SOURCE_SEARCH))

    def _on_record(self):
        r = self._current()
        if not r:
            msg_info(self, tr("请先选中一个直播间"))
            return
        if self.on_record:
            self.on_record(r)

    def _on_open(self):
        r = self._current()
        if not r:
            return
        if self.on_open_room:
            self.on_open_room(r)
        else:
            room_id = r.get("roomid")
            if room_id:
                import webbrowser
                webbrowser.open(f"https://live.bilibili.com/{room_id}")

    def _copy(self):
        r = self._current()
        if not r:
            return
        room_id = r.get("roomid")
        if room_id:
            QGuiApplication.clipboard().setText(
                f"https://live.bilibili.com/{room_id}")

    def closeEvent(self, ev):
        self._closed = True
        try:
            self._unsub()
        except Exception:
            pass
        super().closeEvent(ev)


# --------------------------------------------------------------------------- #
# 录制直播（按房间链接 / ID）
# --------------------------------------------------------------------------- #
class LiveRecordDialog(FluentContentDialog):
    """按直播间链接或房间号直接开始录制。"""

    def __init__(self, parent=None, on_record=None):
        super().__init__((540, 300), parent, title=tr("录制直播"))
        self.on_record = on_record

        hint = BodyLabel(tr("输入直播间链接（https://live.bilibili.com/房间号）或纯房间号"), self)
        hint.setWordWrap(True)
        self.add_widget(hint)

        self.input = LineEdit(self)
        self.input.setPlaceholderText("https://live.bilibili.com/12345  或  12345")
        self.input.returnPressed.connect(self._on_accept)
        self.add_widget(self.input)
        self.add_stretch(1)

        self.ok_btn = self.add_button(tr("开始录制"), primary=True,
                                     slot=self._on_accept)
        self.cancel_btn = self.add_button(tr("取消"), slot=self.reject)
        register(self.ok_btn, "开始录制")
        register(self.cancel_btn, "取消")

    def _on_accept(self):
        text = self.input.text().strip()
        if not text:
            msg_info(self, tr("请先输入直播间链接或房间号"))
            return
        if self.on_record:
            self.on_record(text)
        self.accept()


# --------------------------------------------------------------------------- #
# 收藏夹选择（我的收藏夹 -> 先选具体哪个收藏夹）
# --------------------------------------------------------------------------- #
class FavFolderDialog(FluentContentDialog):
    """选择一个收藏夹：先拉取用户的收藏夹列表，单击选中后「确定」/双击即回调 on_select(media_id, title)。

    背景：侧边栏「我的收藏夹」点击时尚未携带具体 media_id，必须先让用户挑一个收藏夹，
    再据此拉取该收藏夹的视频（否则 media_id=None 会触发 API 异常）。
    """

    def __init__(self, parent, api, on_select=None, title=tr("选择收藏夹")):
        super().__init__((600, 540), parent, title=title)
        self.api = api
        self.on_select = on_select

        self.status_lbl = CaptionLabel(tr("加载中..."), self)
        self.add_widget(self.status_lbl)

        self.list = ListWidget(self)
        self.list.setSpacing(2)
        self.list.itemDoubleClicked.connect(self._on_accept)
        self.add_widget(self.list, 1)

        self.btn_ok = self.add_button(tr("确定"), primary=True,
                                     slot=self._on_accept)
        self.btn_ok.setEnabled(False)
        self.btn_cancel = self.add_button(tr("取消"), slot=self.reject)

        threading.Thread(target=self._load_thread, daemon=True).start()

    def _load_thread(self):
        try:
            folders = self.api.get_favorite_folders() or []
        except Exception as e:
            run_on_main(lambda err=str(e): self._on_error(err))
            return
        run_on_main(lambda: self._render(folders))

    def _render(self, folders):
        self.list.clear()
        if not folders:
            self.status_lbl.setText(tr("你还没有创建任何收藏夹"))
            self.btn_ok.setEnabled(False)
            return
        self.status_lbl.setText(tr("共 {n} 个收藏夹").format(n=len(folders)))
        for f in folders:
            fid = f.get("id")
            name = f.get("title", tr("未命名收藏夹"))
            cnt = f.get("media_count", 0)
            li = QListWidgetItem(f"{name}  （{cnt}）")
            li.setData(Qt.UserRole, fid)
            self.list.addItem(li)
        self.btn_ok.setEnabled(True)

    def _on_error(self, err):
        self.status_lbl.setText(tr("加载失败"))
        msg_error(self, tr("加载收藏夹失败：{}").format(err))

    def _on_accept(self):
        it = self.list.currentItem()
        if it is None:
            return
        fid = it.data(Qt.UserRole)
        if fid is None:
            return
        title = it.text().split("  （")[0]
        if self.on_select is not None:
            self.on_select(fid, title)
        self.accept()
