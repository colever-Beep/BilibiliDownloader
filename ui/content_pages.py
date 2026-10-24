"""主界面内联内容页（2.1.0 UI 重构）。

把原本点击导航栏后弹出的子窗口迁移为「主界面内嵌页面」，由 MainWindow 的
QStackedWidget 在「首页(下载)」与这些页面之间切换，不再弹出独立窗口：

- BrowsePage     取代 SelectDialog / PaginatedSelectDialog / SearchDialog
                 （勾选下载浏览页：全选 / 计数 / 分页 / 搜索 / 添加到下载队列）
- FollowingPage  取代 FollowingDialog（关注列表，点击进入 UP 主空间）
- FavFolderPage  取代 FavFolderDialog（收藏夹选择）
- LiveCenterPage 取代 LiveCenterDialog（直播中心）

全部为普通 QWidget，交互 / 视觉沿用既有组件（SelectListView、FlowLayout、
LayoutModeToggle），与设置窗口、下载选项窗口保持一致；并通过 retranslate() 接入
多语言即时刷新。
"""
import threading

import requests
from PySide6.QtCore import Qt, QThread, QByteArray, Signal
from PySide6.QtGui import QImage, QPixmap, QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidgetItem, QScrollArea, QStackedWidget,
    QVBoxLayout, QWidget,
)

from qfluentwidgets import (
    BodyLabel, CaptionLabel, CheckBox, FluentIcon, FlowLayout, ImageLabel,
    ListWidget, PrimaryPushButton, PushButton, SearchLineEdit, SpinBox,
    TransparentToolButton,
)

from utils.i18n import tr
from utils.main_thread import run_on_main
from utils.helpers import optimize_thumbnail_url, open_in_browser
from ui.list_layout import LayoutModeToggle, manager, is_compact
from ui.select_list_view import SelectListView, _key_of
from ui.fluent_dialog import msg_error
from ui.dialogs import _LiveRoomCard


# --------------------------------------------------------------------------- #
# 通用页头：返回按钮 + 标题
# --------------------------------------------------------------------------- #
class _Header(QWidget):
    backClicked = Signal()

    def __init__(self, parent=None, title_key=""):
        super().__init__(parent)
        self._title_key = title_key
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.back_btn = TransparentToolButton(FluentIcon.LEFT_ARROW, self)
        self.back_btn.setFixedSize(36, 32)
        self.back_btn.setToolTip(tr("返回"))
        self.back_btn.clicked.connect(self.backClicked.emit)
        lay.addWidget(self.back_btn)
        self.title_lbl = CaptionLabel("", self)
        self.title_lbl.setStyleSheet("font-size:15px;font-weight:bold;")
        lay.addWidget(self.title_lbl)
        lay.addStretch(1)
        self.set_title(title_key)

    def set_title(self, key):
        self._title_key = key
        self.title_lbl.setText(tr(key))

    def retranslate(self):
        self.title_lbl.setText(tr(self._title_key))
        self.back_btn.setToolTip(tr("返回"))


# --------------------------------------------------------------------------- #
# 浏览页：取代 Select / Paginated / Search 对话框
# --------------------------------------------------------------------------- #
class BrowsePage(QWidget):
    """主界面内嵌的「勾选下载」浏览页。

    支持三种模式：
      - paginated：fetch(pn, ps) -> (items, has_more[, total])，带分页栏；
      - oneshot：一次性填充（每周必看 / 排行榜 / 追番 / 分集）；
      - search：内联搜索框 + 分页拉取（综合搜索 / 音乐搜索）。
    勾选态按 url/bvid 跨页保留；确认后把选中项交给 on_confirm 回调。
    """

    def __init__(self, parent=None, on_confirm=None, on_back=None):
        super().__init__(parent)
        self.on_confirm = on_confirm
        self._on_back = on_back
        self._checked_keys = set()
        self._selected = {}
        self._suppress = False
        self.fetch = None
        self.ps = 20
        self.pn = 1
        self.has_more = True
        self._busy = False
        self._total_pn = None
        self._last_pn = None
        self._search_fn = None
        self._keyword = ""
        self._empty_msg = None
        self._mode = "paginated"
        self._search_placeholder_key = None
        self._build()

    # ------------------------------------------------------------------ #
    # 构建
    # ------------------------------------------------------------------ #
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        self.header = _Header(self, tr("浏览"))
        self.header.backClicked.connect(self._on_back_clicked)
        v.addWidget(self.header)

        # 搜索栏（默认隐藏，仅 search 模式显示）
        self.search_box = SearchLineEdit(self)
        self.search_box.setClearButtonEnabled(True)
        self.search_box.returnPressed.connect(self._do_search)
        self.search_btn = PrimaryPushButton(tr("搜索"), self)
        self.search_btn.setMinimumWidth(80)
        self.search_btn.setIcon(FluentIcon.SEARCH.icon())
        self.search_btn.clicked.connect(self._do_search)
        self.search_box.hide()
        self.search_btn.hide()
        sh = QHBoxLayout()
        sh.setSpacing(10)
        sh.addWidget(self.search_box, 1)
        sh.addWidget(self.search_btn)
        v.addLayout(sh)

        # 全选 + 计数
        sel = QHBoxLayout()
        sel.setSpacing(12)
        self.check_all = CheckBox(tr("全选"), self)
        self.check_all.setTristate(True)
        self.check_all.stateChanged.connect(self._on_check_all)
        self.count_lab = CaptionLabel("", self)
        sel.addWidget(self.check_all)
        sel.addWidget(self.count_lab)
        sel.addStretch(1)
        v.addLayout(sel)

        # 列表
        self.list = SelectListView(self._checked_keys, self)
        self.list.rowClicked.connect(self._on_row_clicked)
        v.addWidget(self.list, 1)

        # 状态行
        self.status_lbl = CaptionLabel("", self)
        v.addWidget(self.status_lbl)

        # 分页栏
        self.page_lbl = CaptionLabel(tr("第 1 页"), self)
        self.page_lbl.setMinimumWidth(120)
        self.btn_prev = PushButton(tr("上一页"), self)
        self.btn_next = PushButton(tr("下一页"), self)
        self.btn_prev.clicked.connect(self._go_prev)
        self.btn_next.clicked.connect(self._go_next)
        self.jump_spin = SpinBox(self)
        self.jump_spin.setRange(1, 10000)
        self.jump_spin.setFixedWidth(110)
        self.btn_jump = PushButton(tr("跳转"), self)
        self.btn_jump.clicked.connect(self._go_jump)
        pg = QHBoxLayout()
        pg.setSpacing(10)
        pg.addWidget(self.btn_prev)
        pg.addWidget(self.btn_next)
        pg.addSpacing(14)
        pg.addWidget(self.page_lbl)
        pg.addStretch(1)
        pg.addWidget(CaptionLabel(tr("跳至"), self))
        pg.addWidget(self.jump_spin)
        pg.addWidget(self.btn_jump)
        v.addLayout(pg)
        self._pager_widgets = [self.btn_prev, self.btn_next, self.page_lbl,
                               self.jump_spin, self.btn_jump]

        # 底部：左侧布局切换 + 右侧「添加到下载队列」
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addWidget(LayoutModeToggle(self))
        bottom.addStretch(1)
        self.btn_add = PrimaryPushButton(tr("添加到下载队列"), self)
        self.btn_add.setIcon(FluentIcon.DOWNLOAD.icon())
        self.btn_add.setEnabled(False)
        self.btn_add.clicked.connect(self._on_add)
        bottom.addWidget(self.btn_add)
        v.addLayout(bottom)

    # ------------------------------------------------------------------ #
    # 外部接口
    # ------------------------------------------------------------------ #
    def set_on_back(self, fn):
        self._on_back = fn

    def set_on_confirm(self, fn):
        self.on_confirm = fn

    def _on_back_clicked(self):
        if callable(self._on_back):
            self._on_back()

    def configure_paginated(self, title_key, fetch, ps=20, empty_msg=None):
        self._reset()
        self._mode = "paginated"
        self.fetch = fetch
        self.ps = ps
        self._empty_msg = empty_msg
        self._show_pager(True)
        self._show_search(False)
        self.header.set_title(title_key)
        self._load_page(1)

    def configure_oneshot(self, title_key, loading_text=None):
        self._reset()
        self._mode = "oneshot"
        self._show_pager(False)
        self._show_search(False)
        self.header.set_title(title_key)
        self.list.set_items([])
        self._set_status(loading_text if loading_text is not None else tr("加载中..."))
        self.btn_add.setEnabled(False)

    def configure_search(self, title_key, search_fn, placeholder_key, ps=20):
        self._reset()
        self._mode = "search"
        self._search_fn = search_fn
        self.ps = ps
        self.fetch = lambda pn, ps: self._search_fetch(pn)
        self._search_placeholder_key = placeholder_key
        self._show_pager(True)
        self._show_search(True)
        self.search_box.setPlaceholderText(tr(placeholder_key))
        self.search_box.clear()
        self.header.set_title(title_key)
        self.list.set_items([])
        self._set_status(tr("输入关键词后回车或点击搜索"))

    def fill(self, items):
        self._fill_table(items)
        self._set_status("")

    def set_loading(self, on, message=None):
        if on:
            self.list.set_items([])
            self.btn_add.setEnabled(False)
            self._set_status(message if message is not None else tr("加载中..."))
        else:
            self._set_status(message if message is not None else "")

    def show_error(self, message):
        self.list.set_items([])
        self.btn_add.setEnabled(False)
        self._set_status(message)

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #
    def _show_pager(self, show):
        for w in self._pager_widgets:
            w.setVisible(show)

    def _show_search(self, show):
        self.search_box.setVisible(show)
        self.search_btn.setVisible(show)

    def _set_status(self, text):
        self.status_lbl.setText(text or "")

    def _reset(self):
        self._checked_keys.clear()
        self._selected.clear()
        self._suppress = False
        self.pn = 1
        self.has_more = True
        self._busy = False
        self._total_pn = None
        self._last_pn = None
        self._keyword = ""
        self.check_all.setCheckState(Qt.CheckState.Unchecked)
        self._update_count()

    # ------------------------------------------------------------------ #
    # 勾选 / 计数
    # ------------------------------------------------------------------ #
    def _fill_table(self, items):
        self.list.set_items(items)
        for it in items:
            key = _key_of(it)
            if key in self._checked_keys:
                self._selected[key] = it
        self._update_count()

    def _selected_items(self):
        return list(self._selected.values())

    def _on_row_clicked(self, index):
        if self._suppress:
            return
        it = self.list.model().item_at(index.row())
        key = _key_of(it)
        if key is None:
            return
        if key in self._checked_keys:
            self._checked_keys.discard(key)
            self._selected.pop(key, None)
        else:
            self._checked_keys.add(key)
            self._selected[key] = it
        self.list.refresh_row(index)
        self._update_count()

    def _update_count(self):
        if self._suppress:
            return
        self._suppress = True
        try:
            n = len(self._selected)
            total = self.list.model().rowCount()
            if n > 0:
                self.count_lab.setText(tr("已选 {n}").format(n=n))
                self.btn_add.setEnabled(True)
            else:
                self.count_lab.setText("")
                self.btn_add.setEnabled(False)
            if total == 0:
                self.check_all.setCheckState(Qt.CheckState.Unchecked)
            else:
                checked = sum(
                    1 for r in range(total)
                    if _key_of(self.list.model().item_at(r)) in self._checked_keys
                )
                if checked == 0:
                    self.check_all.setCheckState(Qt.CheckState.Unchecked)
                elif checked == total:
                    self.check_all.setCheckState(Qt.CheckState.Checked)
                else:
                    self.check_all.setCheckState(Qt.CheckState.PartiallyChecked)
        finally:
            self._suppress = False

    def _on_check_all(self, state=None):
        if self._suppress:
            return
        self._suppress = True
        try:
            total = self.list.model().rowCount()
            if total == 0:
                self._suppress = False
                return
            all_checked = all(
                _key_of(self.list.model().item_at(r)) in self._checked_keys
                for r in range(total)
            )
            check = not all_checked
            for r in range(total):
                it = self.list.model().item_at(r)
                key = _key_of(it)
                if key is None:
                    continue
                if check:
                    self._checked_keys.add(key)
                    self._selected[key] = it
                else:
                    self._checked_keys.discard(key)
                    self._selected.pop(key, None)
            self.list.set_items(self.list.items())
        finally:
            self._suppress = False
        self._update_count()

    # ------------------------------------------------------------------ #
    # 确认 / 添加
    # ------------------------------------------------------------------ #
    def _on_add(self):
        sel = self._selected_items()
        if not sel:
            return
        if callable(self.on_confirm):
            self.on_confirm(sel)

    # ------------------------------------------------------------------ #
    # 分页
    # ------------------------------------------------------------------ #
    def _load_page(self, pn):
        if self._busy:
            return
        self._busy = True
        self._set_nav_enabled(False)
        self._set_status(tr("正在加载第 {pn} 页...").format(pn=pn))
        threading.Thread(target=self._fetch_thread, args=(pn,), daemon=True).start()

    def _fetch_thread(self, pn):
        try:
            res = self.fetch(pn, self.ps)
            if res is None:
                items, has_more, total = [], False, None
            elif isinstance(res, tuple):
                if len(res) >= 3 and res[2] is not None:
                    items, has_more, total = (res[0] or []), bool(res[1]), res[2]
                else:
                    items, has_more, total = (res[0] or []), bool(res[1]), None
            else:
                items, has_more, total = res or [], False, None
        except Exception as e:
            run_on_main(lambda err=str(e): self._on_error(pn, err))
            return
        run_on_main(lambda: self._render_page(pn, items, has_more, total))

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
        if not items:
            if pn == 1 and self._empty_msg:
                self._set_status(self._empty_msg)
            elif pn == 1:
                self._set_status(tr("（空）"))
        else:
            if M:
                self._set_status(tr("第 {pn} / {total} 页，共 {n} 条").format(
                    pn=pn, total=M, n=len(items)))
            else:
                self._set_status(tr("第 {pn} 页，共 {n} 条").format(
                    pn=pn, n=len(items)))
        self.search_btn.setEnabled(True)

    def _on_error(self, pn, err):
        self._busy = False
        self._set_nav_enabled(True)
        self._set_status(tr("加载失败"))
        self.search_btn.setEnabled(True)
        msg_error(self, tr("加载第 {pn} 页失败：{err}").format(pn=pn, err=err))

    def _set_nav_enabled(self, enabled):
        self.btn_prev.setEnabled(enabled and self.pn > 1)
        self.btn_next.setEnabled(enabled and self.has_more)

    def _go_prev(self):
        if self.pn > 1:
            self._load_page(self.pn - 1)

    def _go_next(self):
        if self.has_more:
            self._load_page(self.pn + 1)

    def _go_jump(self):
        target = self.jump_spin.value()
        M = self._total_pn or self._last_pn
        if M and target > M:
            target = M
            self.jump_spin.setValue(M)
        if target < 1 or target == self.pn:
            return
        self._load_page(target)

    # ------------------------------------------------------------------ #
    # 搜索
    # ------------------------------------------------------------------ #
    def _search_fetch(self, pn):
        if not self._keyword:
            return [], False
        res = self._search_fn(self._keyword, page=pn)
        if isinstance(res, tuple):
            items, has_more = (res[0] or []), bool(res[1])
        else:
            items, has_more = (res or []), False
        return items, has_more

    def _do_search(self):
        kw = self.search_box.text().strip()
        if not kw:
            return
        self._keyword = kw
        self._checked_keys.clear()
        self._selected.clear()
        self.search_btn.setEnabled(False)
        self._load_page(1)

    # ------------------------------------------------------------------ #
    # 多语言
    # ------------------------------------------------------------------ #
    def retranslate(self):
        self.header.retranslate()
        self.check_all.setText(tr("全选"))
        self.btn_prev.setText(tr("上一页"))
        self.btn_next.setText(tr("下一页"))
        self.btn_jump.setText(tr("跳转"))
        self.search_btn.setText(tr("搜索"))
        self.btn_add.setText(tr("添加到下载队列"))
        if self._mode == "search" and self._search_placeholder_key:
            self.search_box.setPlaceholderText(tr(self._search_placeholder_key))
        self._update_count()
        self._render_pager_labels()

    def _render_pager_labels(self):
        M = self._total_pn or self._last_pn
        if M:
            self.page_lbl.setText(
                tr("第 {pn} / {total} 页").format(pn=self.pn, total=M))
        else:
            self.page_lbl.setText(tr("第 {pn} 页").format(pn=self.pn))


# --------------------------------------------------------------------------- #
# 关注页：取代 FollowingDialog
# --------------------------------------------------------------------------- #
class _AvatarLoader(QThread):
    loaded = Signal(str, bytes)

    def __init__(self, urls):
        super().__init__()
        self.urls = list(urls)
        self._stop = False

    def run(self):
        for url in self.urls:
            if self._stop:
                break
            try:
                thumb = optimize_thumbnail_url(url, width=120, height=120)
                resp = requests.get(thumb, timeout=4)
                if resp.status_code == 200:
                    self.loaded.emit(url, resp.content)
            except Exception:
                continue

    def stop(self):
        self._stop = True


class FollowingPage(QWidget):
    def __init__(self, parent=None, on_open_space=None, on_back=None):
        super().__init__(parent)
        self.on_open_space = on_open_space
        self._on_back = on_back
        self.full_list = []
        self._avatar_labels = {}
        self._avatar_cache = {}
        self._build()
        self._unsub = manager.connect(lambda _m: self._apply_filter())

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.header = _Header(self, tr("我的关注"))
        self.header.backClicked.connect(self._on_back_clicked)
        v.addWidget(self.header)

        top = QHBoxLayout()
        top.setSpacing(12)
        self.title_label = CaptionLabel("", self)
        top.addWidget(self.title_label)
        top.addStretch(1)
        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText(tr("搜索UP主昵称 / 签名…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        top.addWidget(self.search)
        v.addLayout(top)

        self.list = ListWidget(self)
        self.list.setSpacing(4)
        v.addWidget(self.list, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addWidget(LayoutModeToggle(self))
        self.hint = CaptionLabel(
            tr("点击「打开TA的个人空间」浏览并下载该UP的视频"), self)
        bottom.addWidget(self.hint)
        bottom.addStretch(1)
        self.close_btn = PushButton(tr("返回"), self)
        self.close_btn.clicked.connect(self._on_back_clicked)
        bottom.addWidget(self.close_btn)
        v.addLayout(bottom)

    def set_data(self, following_list):
        self.full_list = list(following_list or [])
        self._apply_filter()
        self._start_loader()

    def _on_back_clicked(self):
        if callable(self._on_back):
            self._on_back()

    def _apply_filter(self):
        kw = self.search.text().strip().lower()
        if kw:
            filtered = [
                u for u in self.full_list
                if kw in (u.get("uname", "") or "").lower()
                or kw in (u.get("sign", "") or "").lower()
            ]
        else:
            filtered = list(self.full_list)
        self.title_label.setText(
            tr("我的关注 · 共 {total} 位UP主").format(total=len(self.full_list))
            + (tr("（匹配 {matched}）").format(matched=len(filtered)) if kw else ""))

        self._avatar_labels.clear()
        self.list.clear()
        for u in filtered:
            item = QListWidgetItem()
            row = self._make_row(u)
            item.setSizeHint(row.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, row)

    def _make_row(self, u):
        mid = u.get("mid")
        face = u.get("face", "") or ""
        if face.startswith("//"):
            face = "https:" + face

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(12)

        avatar = ImageLabel(row)
        avatar.setFixedSize(56, 56)
        avatar.setBorderRadius(28, 28, 28, 28)
        avatar.setText("👤")
        if face:
            self._avatar_labels[face] = avatar
            cached = self._avatar_cache.get(face)
            if cached is not None:
                avatar.setImage(cached)
                avatar.setFixedSize(56, 56)
        h.addWidget(avatar)

        info = QVBoxLayout()
        info.setSpacing(2)
        uname = u.get("uname", tr("未知UP主"))
        name = BodyLabel(uname if len(uname) <= 22 else uname[:22] + "…", row)
        sign = u.get("sign", "") or ""
        sign_lab = CaptionLabel((sign[:42] + "…") if len(sign) > 42 else sign, row)
        info.addWidget(name)
        info.addWidget(sign_lab)
        if is_compact():
            sign_lab.hide()
        h.addLayout(info, stretch=1)

        open_btn = PrimaryPushButton(tr("打开TA的个人空间"), row)
        open_btn.clicked.connect(lambda _=False, m=mid: self._open_space(m))
        h.addWidget(open_btn)

        browser_btn = TransparentToolButton(FluentIcon.LINK, row)
        browser_btn.setFixedWidth(36)
        browser_btn.setToolTip(tr("在浏览器中打开主页"))
        browser_btn.clicked.connect(
            lambda _=False, m=mid: open_in_browser(f"https://space.bilibili.com/{m}"))
        h.addWidget(browser_btn)
        return row

    def _start_loader(self):
        urls = [u.get("face", "") for u in self.full_list if u.get("face")]
        urls = [("https:" + u) if u.startswith("//") else u for u in urls]
        self._worker = _AvatarLoader(urls)
        self._worker.loaded.connect(self._on_avatar_loaded)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_avatar_loaded(self, url, data):
        img = QImage.fromData(QByteArray(data))
        if img.isNull():
            return
        pix = QPixmap.fromImage(img).scaled(
            56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._avatar_cache[url] = pix
        lab = self._avatar_labels.get(url)
        if lab is None:
            return
        lab.setImage(pix)
        lab.setFixedSize(56, 56)

    def _open_space(self, mid):
        if mid is None:
            return
        if callable(self.on_open_space):
            self.on_open_space(mid)

    def retranslate(self):
        self.header.retranslate()
        self.search.setPlaceholderText(tr("搜索UP主昵称 / 签名…"))
        self.title_label.setText(
            tr("我的关注 · 共 {total} 位UP主").format(total=len(self.full_list)))
        self.hint.setText(tr("点击「打开TA的个人空间」浏览并下载该UP的视频"))
        self.close_btn.setText(tr("返回"))
        self._apply_filter()


# --------------------------------------------------------------------------- #
# 收藏夹选择页：取代 FavFolderDialog
# --------------------------------------------------------------------------- #
class FavFolderPage(QWidget):
    def __init__(self, parent=None, api=None, on_select=None, on_back=None):
        super().__init__(parent)
        self.api = api
        self.on_select = on_select
        self._on_back = on_back
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.header = _Header(self, tr("选择收藏夹"))
        self.header.backClicked.connect(self._on_back_clicked)
        v.addWidget(self.header)

        self.status_lbl = CaptionLabel(tr("加载中..."), self)
        v.addWidget(self.status_lbl)

        self.list = ListWidget(self)
        self.list.setSpacing(2)
        self.list.itemDoubleClicked.connect(self._on_accept)
        v.addWidget(self.list, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addStretch(1)
        self.btn_ok = PrimaryPushButton(tr("确定"), self)
        self.btn_ok.setEnabled(False)
        self.btn_ok.clicked.connect(self._on_accept)
        bottom.addWidget(self.btn_ok)
        self.btn_cancel = PushButton(tr("返回"), self)
        self.btn_cancel.clicked.connect(self._on_back_clicked)
        bottom.addWidget(self.btn_cancel)
        v.addLayout(bottom)

    def load(self):
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
        if callable(self.on_select):
            self.on_select(fid, title)

    def _on_back_clicked(self):
        if callable(self._on_back):
            self._on_back()

    def retranslate(self):
        self.header.retranslate()
        self.btn_ok.setText(tr("确定"))
        self.btn_cancel.setText(tr("返回"))


# --------------------------------------------------------------------------- #
# 直播中心页：取代 LiveCenterDialog
# --------------------------------------------------------------------------- #
class LiveCenterPage(QWidget):
    _SOURCE_HOT = "hot"
    _SOURCE_SEARCH = "search"

    def __init__(self, parent=None, api=None, on_record=None,
                 on_open_room=None, on_back=None):
        super().__init__(parent)
        self.api = api
        self.on_record = on_record
        self.on_open_room = on_open_room
        self._on_back = on_back
        self._rooms = []
        self._current_room = None
        self._cards = []
        self._cover_cache = {}
        self._cover_loading = set()
        self._build()
        self._unsub = manager.connect(lambda _m: self._rerender())

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.header = _Header(self, tr("直播中心"))
        self.header.backClicked.connect(self._on_back_clicked)
        v.addWidget(self.header)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.input = SearchLineEdit(self)
        self.input.setPlaceholderText(tr("搜索直播间关键词"))
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self._do_search)
        self.search_btn = PrimaryPushButton(tr("搜索"), self)
        self.search_btn.setMinimumWidth(96)
        self.search_btn.setIcon(FluentIcon.SEARCH.icon())
        self.search_btn.clicked.connect(self._do_search)
        self.hot_btn = PushButton(tr("热门直播"), self)
        self.hot_btn.setMinimumWidth(110)
        self.hot_btn.setIcon(FluentIcon.HISTORY.icon())
        self.hot_btn.clicked.connect(self._load_hot)
        top.addWidget(self.input, 1)
        top.addWidget(self.search_btn)
        top.addWidget(self.hot_btn)
        v.addLayout(top)

        self.status_lbl = CaptionLabel("", self)
        v.addWidget(self.status_lbl)

        self._stack = QStackedWidget(self)
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

        self.list = ListWidget(self)
        self.list.setSpacing(2)
        self.list.itemClicked.connect(self._on_list_pick)
        self.list.itemDoubleClicked.connect(self._on_open)

        self._stack.addWidget(self.grid_scroll)
        self._stack.addWidget(self.list)
        v.addWidget(self._stack, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addWidget(LayoutModeToggle(self))
        bottom.addStretch(1)
        self.rec_btn = PushButton(tr("录制"), self)
        self.open_btn = PushButton(tr("打开直播间"), self)
        self.copy_btn = PushButton(tr("复制链接"), self)
        self.rec_btn.clicked.connect(self._on_record)
        self.open_btn.clicked.connect(self._on_open)
        self.copy_btn.clicked.connect(self._copy)
        bottom.addWidget(self.rec_btn)
        bottom.addWidget(self.open_btn)
        bottom.addWidget(self.copy_btn)
        v.addLayout(bottom)

    # ------------------------------------------------------------------ #
    def load_hot(self):
        self._load_hot()

    def _fill(self, rooms):
        self._rooms = list(rooms)
        if not rooms:
            self.status_lbl.setText(tr("未找到直播间"))
            self.list.clear()
            self._clear_grid()
            return
        self.status_lbl.setText(tr("共 {} 个直播间").format(len(rooms)))
        self._render()

    def _render(self):
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
        title = r.get("title", tr("未知直播"))
        uname = r.get("uname", "")
        online = r.get("watched_show") or r.get("online") or ""
        area = r.get("area_name", "")
        return f"{title}  ·  {uname}  ·  {online}  ·  {area}"

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
        run_on_main(lambda: self._fill(rooms))

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
        run_on_main(lambda: self._fill(rooms))

    def _on_record(self):
        r = self._current()
        if not r:
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

    def _on_back_clicked(self):
        if callable(self._on_back):
            self._on_back()

    def retranslate(self):
        self.header.retranslate()
        self.input.setPlaceholderText(tr("搜索直播间关键词"))
        self.search_btn.setText(tr("搜索"))
        self.hot_btn.setText(tr("热门直播"))
        self.rec_btn.setText(tr("录制"))
        self.open_btn.setText(tr("打开直播间"))
        self.copy_btn.setText(tr("复制链接"))
        if self._rooms:
            self._render()
