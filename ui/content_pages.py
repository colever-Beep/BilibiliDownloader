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
from PySide6.QtCore import (
    Qt, QEvent, QPropertyAnimation, QEasingCurve, QThread, QTimer, QByteArray,
    Signal,
)
from PySide6.QtGui import QImage, QPixmap, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from qfluentwidgets import (
    BodyLabel, CaptionLabel, CheckBox, ComboBox, FluentIcon, FlowLayout,
    ImageLabel, ListWidget, PrimaryPushButton, PushButton, SearchLineEdit,
    SpinBox, TransparentToolButton,
)

from utils.i18n import tr
from utils.main_thread import run_on_main
from utils.helpers import optimize_thumbnail_url, open_in_browser
from ui.list_layout import LayoutModeToggle, manager, is_compact
from utils.touch_scroll import enable_touch_scroll
from ui.select_list_view import SelectListView, _key_of
from ui.fluent_dialog import msg_error
from ui.dialogs import _LiveRoomCard


# --------------------------------------------------------------------------- #
# 视频列表排序 / 本地过滤：公共实现在 ui.list_tools（与选择对话框共用，避免循环 import）
# --------------------------------------------------------------------------- #
from ui.list_tools import (  # noqa: E402
    SORT_KEYS, SORT_LABELS, sort_items, filter_items,
)
from ui.loading_overlay import LoadingOverlay, wrap as wrap_loading  # noqa: E402


# --------------------------------------------------------------------------- #
# 通用页头：返回按钮 + 标题
# --------------------------------------------------------------------------- #
class _Header(QWidget):
    backClicked = Signal()

    def __init__(self, parent=None, title_key=""):
        super().__init__(parent)
        self._title_key = title_key
        self._title_args = ()
        self._title_kwargs = {}
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

    def set_title(self, key, *args, **kwargs):
        """设置标题（翻译键 + 格式化参数），供动态标题（UP主名 / 父视频标题）使用。

        参数会被保存，语言切换时由 ``retranslate()`` 用新语言重新格式化。
        """
        self._title_key = key
        self._title_args = tuple(args)
        self._title_kwargs = dict(kwargs)
        self.title_lbl.setText(tr(key, *args, **kwargs))

    def retranslate(self):
        self.title_lbl.setText(tr(self._title_key, *self._title_args,
                                  **self._title_kwargs))
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
        self._status_key = None
        self._status_args = ()
        self._status_kwargs = {}
        # 顺序选集模式：多个「有分集容器」依次让用户勾选，底部按钮切换为
        # 「上一个 / 下一个」，全部完成后恢复「加入下载队列」。
        self._seq_mode = False
        self._seq_on_prev = None
        self._seq_on_next = None
        self._seq_index = 0
        self._seq_total = 0
        self._seq_title = ""
        # 「添加到下载队列」按钮文案随选中项类型动态切换（解析器由 MainWindow 注入，
        # 复用其路由判定，保证文案与实际点击行为一致）；未注入时保持默认文案。
        self._add_text_key = "添加到下载队列"
        self._add_text_resolver = None
        # 视频列表排序键（SORT_KEYS 之一）
        self._sort_key = "default"
        # 当前已加载项（分页的一页 / oneshot 的一批），用于本地过滤 + 排序叠加
        self._all_items = []
        # 搜索联想：函数由 MainWindow 注入；防抖定时器 + 弹出列表 + 序号防串扰
        self._suggest_fn = None
        self._suggest_popup = None
        self._suggest_animation = None
        self._suggest_closing = False
        self._suggest_seq = 0
        self._suggest_timer = QTimer(self)
        self._suggest_timer.setSingleShot(True)
        self._suggest_timer.setInterval(280)
        self._suggest_timer.timeout.connect(self._fetch_suggest)
        self._build()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

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

        # 搜索栏：两种用途共用同一行
        #   - 网络搜索（search 模式）：search_box + search_btn + 联想
        #   - 本地过滤（paginated / oneshot / 顺序选集模式）：local_filter，
        #     样式同「我的关注」搜索框（SearchLineEdit + 清除按钮 + 输入即时过滤已加载项）
        self.search_box = SearchLineEdit(self)
        self.search_box.setClearButtonEnabled(True)
        self.search_box.returnPressed.connect(self._do_search)
        # 输入联想：仅在 search 模式下、由 _suggest_fn 存在时生效（防抖）
        self.search_box.textChanged.connect(self._on_search_text_changed)
        self.search_btn = PrimaryPushButton(tr("搜索"), self)
        self.search_btn.setMinimumWidth(80)
        self.search_btn.setIcon(FluentIcon.SEARCH.icon())
        self.search_btn.clicked.connect(self._do_search)

        self.local_filter = SearchLineEdit(self)
        self.local_filter.setClearButtonEnabled(True)
        self.local_filter.setPlaceholderText(tr("搜索当前列表（标题 / UP主）…"))
        self.local_filter.textChanged.connect(self._on_local_filter_changed)

        self.search_box.hide()
        self.search_btn.hide()
        self.local_filter.hide()
        sh = QHBoxLayout()
        sh.setSpacing(10)
        sh.addWidget(self.search_box, 1)
        sh.addWidget(self.search_btn)
        sh.addWidget(self.local_filter, 1)
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
        self.sort_label = CaptionLabel(tr("排序"), self)
        sel.addWidget(self.sort_label)
        self.sort_combo = ComboBox(self)
        self.sort_combo.addItems([tr(SORT_LABELS[k]) for k in SORT_KEYS])
        self.sort_combo.setMinimumWidth(120)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        sel.addWidget(self.sort_combo)
        v.addLayout(sel)

        # 列表（包一层带转圈动画的加载遮罩，加载中在中央提示）
        self.list = SelectListView(self._checked_keys, self)
        self.list.rowClicked.connect(self._on_row_clicked)
        self._list_container, self._loading = wrap_loading(self.list)
        v.addWidget(self._list_container, 1)

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
        self.jump_label = CaptionLabel(tr("跳至"), self)
        pg.addWidget(self.jump_label)
        pg.addWidget(self.jump_spin)
        pg.addWidget(self.btn_jump)
        v.addLayout(pg)
        self._pager_widgets = [self.btn_prev, self.btn_next, self.page_lbl,
                               self.jump_spin, self.btn_jump]

        # 底部：左侧布局切换 + 右侧「添加到下载队列」/「上一个·下一个」
        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addWidget(LayoutModeToggle(self))
        bottom.addStretch(1)
        # 顺序选集进度提示（仅 seq 模式显示）
        self.seq_progress_lbl = CaptionLabel("", self)
        self.seq_progress_lbl.setVisible(False)
        bottom.addWidget(self.seq_progress_lbl)
        self.btn_seq_prev = PushButton(tr("上一个"), self)
        self.btn_seq_prev.setVisible(False)
        self.btn_seq_prev.clicked.connect(self._on_seq_prev)
        bottom.addWidget(self.btn_seq_prev)
        self.btn_seq_next = PushButton(tr("下一个"), self)
        self.btn_seq_next.setVisible(False)
        self.btn_seq_next.clicked.connect(self._on_seq_next)
        bottom.addWidget(self.btn_seq_next)
        self.btn_add = PrimaryPushButton(tr("添加到下载队列"), self)
        self.btn_add.setIcon(FluentIcon.DOWNLOAD.icon())
        self.btn_add.setEnabled(False)
        self.btn_add.clicked.connect(self._on_add)
        bottom.addWidget(self.btn_add)
        self._bottom_btns = (self.btn_seq_prev, self.btn_seq_next,
                             self.seq_progress_lbl, self.btn_add)
        v.addLayout(bottom)

    # ------------------------------------------------------------------ #
    # 外部接口
    # ------------------------------------------------------------------ #
    def set_on_back(self, fn):
        self._on_back = fn

    def set_on_confirm(self, fn):
        self.on_confirm = fn

    def set_add_text_resolver(self, fn):
        """注入「选中项 → 按钮文案翻译键」解析器（MainWindow 复用路由判定）。"""
        self._add_text_resolver = fn

    def set_header_title(self, key, *args, **kwargs):
        """设置页头标题（支持翻译键 + 格式化参数，语言切换自动刷新）。"""
        self.header.set_title(key, *args, **kwargs)

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
        if loading_text is None:
            self._show_loading(tr("加载中..."))
            self._set_status_key("")
        else:
            self._show_loading(loading_text)
            self._set_status("")
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
        self._set_status_key("输入关键词后回车或点击搜索")

    def fill(self, items):
        self._fill_table(items)
        self._hide_loading()
        self._set_status("")

    def set_loading(self, on, message=None, message_key=None):
        if on:
            self.list.set_items([])
            self.btn_add.setEnabled(False)
            if message_key:
                self._show_loading(tr(message_key))
                self._set_status("")
            elif message is None:
                self._show_loading(tr("加载中..."))
                self._set_status("")
            else:
                self._show_loading(message)
                self._set_status("")
        else:
            self._hide_loading()
            if message_key:
                self._set_status_key(message_key)
            else:
                self._set_status(message if message is not None else "")

    def show_error(self, message, message_key=None, *args):
        self.list.set_items([])
        self.btn_add.setEnabled(False)
        self._hide_loading()
        if message_key:
            self._set_status_key(message_key, *args)
        else:
            self._set_status(message)

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #
    def _show_pager(self, show):
        for w in self._pager_widgets:
            w.setVisible(show)

    def _show_search(self, show):
        """show=True → 网络搜索框（search 模式）；show=False → 本地过滤框。"""
        self.search_box.setVisible(show)
        self.search_btn.setVisible(show)
        self.local_filter.setVisible(not show)
        if show:
            self.local_filter.clear()
        else:
            self.search_box.clear()

    def _set_status(self, text):
        self._status_key = None
        self._status_args = ()
        self._status_kwargs = {}
        self.status_lbl.setText(text or "")

    def _set_status_key(self, key, *args, **kwargs):
        self._status_key = key
        self._status_args = args
        self._status_kwargs = kwargs
        self.status_lbl.setText(tr(key, *args, **kwargs))

    def _show_loading(self, text):
        """在列表中央显示转圈加载动画；text 为已翻译文案。"""
        try:
            self._loading.set_text(text)
            self._loading.show()
        except Exception:
            pass

    def _hide_loading(self):
        try:
            self._loading.hide()
        except Exception:
            pass

    def _reset(self):
        self._suggest_timer.stop()
        self._hide_suggest()
        self._all_items = []
        try:
            self.local_filter.blockSignals(True)
            self.local_filter.clear()
        finally:
            self.local_filter.blockSignals(False)
        self._suppress = True
        try:
            self._checked_keys.clear()
            self._selected.clear()
            self.pn = 1
            self.has_more = True
            self._busy = False
            self._total_pn = None
            self._last_pn = None
            self._keyword = ""
            self.check_all.setCheckState(Qt.CheckState.Unchecked)
            self.list.set_items([])
            self._set_status("")
        finally:
            self._suppress = False
        # 常规重配置时退出顺序选集导航（若确实要进入，调用方会在之后
        # 再显式 set_sequential_nav(True, ...)）。
        if self._seq_mode:
            self.set_sequential_nav(False)
        self._update_count()

    # ------------------------------------------------------------------ #
    # 勾选 / 计数
    # ------------------------------------------------------------------ #
    def _fill_table(self, items):
        self._all_items = list(items)
        self._apply_view()

    def _apply_view(self):
        """对当前已加载项应用「本地过滤 + 排序」，勾选态按 key 保留。"""
        items = filter_items(self._all_items, self.local_filter.text())
        self.list.set_items(sort_items(items, self._sort_key))
        for it in self._all_items:
            key = _key_of(it)
            if key in self._checked_keys:
                self._selected[key] = it
        self._update_count()

    def _on_local_filter_changed(self, text):
        """本地过滤框输入变化：即时过滤当前已加载项。"""
        self._apply_view()

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
        # 按钮文案随选中项类型切换（UP主 / 分集容器 / 多类型混合）
        key = "添加到下载队列"
        if self._add_text_resolver is not None:
            try:
                key = self._add_text_resolver(self._selected_items()) or key
            except Exception:
                key = "添加到下载队列"
        self._add_text_key = key
        self.btn_add.setText(tr(key))

    def _on_sort_changed(self, index):
        """切换排序键：对当前已加载的可见项重排（勾选态按 key 保留）。"""
        if not (0 <= index < len(SORT_KEYS)):
            return
        self._sort_key = SORT_KEYS[index]
        self._apply_view()

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
    # 顺序选集模式（多类型混合勾选时，逐个有分集容器让用户勾选）
    # ------------------------------------------------------------------ #
    def set_sequential_nav(self, on, on_prev=None, on_next=None):
        """进入/退出「上一个·下一个」导航模式。

        进入时隐藏「添加到下载队列」，显示「上一个 / 下一个」及进度标签；
        退出时恢复常规底部按钮。回调由 MainWindow 提供，负责切换当前段。
        """
        self._seq_mode = bool(on)
        if on:
            self._seq_on_prev = on_prev
            self._seq_on_next = on_next
        self.seq_progress_lbl.setVisible(self._seq_mode)
        self.btn_seq_prev.setVisible(self._seq_mode)
        self.btn_seq_next.setVisible(self._seq_mode)
        self.btn_add.setVisible(not self._seq_mode)

    def update_sequential_nav(self, index, total, title=""):
        """刷新第 index 段（0 基）的进度文案与按钮可用态。

        ``title`` 兼容旧调用：非空时作为翻译键设置页头（无格式化参数）。
        带参数的动态标题请改用 :meth:`set_header_title`。
        """
        self._seq_index = index
        self._seq_total = total
        self._seq_title = title or ""
        self.seq_progress_lbl.setText(
            tr("分集视频 {i}/{n}").format(i=index + 1, n=total))
        self.btn_seq_prev.setEnabled(index > 0)
        # 最后一段：下一个按钮变回「添加到下载队列」语义由回调内部处理，
        # 文案仍显示「下一个」以保持视觉稳定；完成时由 MainWindow 恢复常规模式。
        self.btn_seq_next.setEnabled(True)
        if title:
            self.header.set_title(title)

    def _on_seq_prev(self):
        if callable(self._seq_on_prev):
            self._seq_on_prev()

    def _on_seq_next(self):
        if callable(self._seq_on_next):
            self._seq_on_next()

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
        self._show_loading(tr("正在加载第 {pn} 页...").format(pn=pn))
        self._set_status("")
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
        self._hide_loading()
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
                self._set_status_key(self._empty_msg)
            elif pn == 1:
                self._set_status_key("（空）")
        else:
            if M:
                self._set_status_key("第 {pn} / {total} 页，共 {n} 条",
                                     pn=pn, total=M, n=len(items))
            else:
                self._set_status_key("第 {pn} 页，共 {n} 条",
                                     pn=pn, n=len(items))
        self.search_btn.setEnabled(True)

    def _on_error(self, pn, err):
        self._busy = False
        self._hide_loading()
        self._set_nav_enabled(True)
        self._set_status_key("加载失败")
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

    # ------------------------------------------------------------------ #
    # 搜索联想（suggest）
    # ------------------------------------------------------------------ #
    def set_suggest_fn(self, fn):
        """注入联想词获取函数 ``fn(keyword) -> list[str]``；None 表示禁用。"""
        self._suggest_fn = fn

    def _on_search_text_changed(self, text):
        """输入变化：仅在搜索模式 + 已注入联想函数时防抖拉取联想。"""
        self._suggest_timer.stop()
        if self._mode != "search" or self._suggest_fn is None:
            self._hide_suggest()
            return
        if len((text or "").strip()) < 1:
            self._hide_suggest()
            return
        self._suggest_timer.start()

    def _fetch_suggest(self):
        """后台拉取联想词（序号防串扰：只接受最后一次请求的结果）。"""
        kw = self.search_box.text().strip()
        if not kw or self._suggest_fn is None:
            return
        self._suggest_seq += 1
        seq = self._suggest_seq

        def worker():
            try:
                return kw, seq, self._suggest_fn(kw) or []
            except Exception:
                return kw, seq, []

        def done(result):
            rkw, rseq, words = result
            # 过期结果 / 输入已变化：丢弃
            if rseq != self._suggest_seq or rkw != self.search_box.text().strip():
                return
            if words:
                self._show_suggest(words)
            else:
                self._hide_suggest()

        def target():
            result = worker()                       # 线程内完成网络请求
            run_on_main(lambda: done(result))       # 回主线程刷新弹窗

        if not hasattr(self, "_suggest_threads"):
            self._suggest_threads = []
        self._suggest_threads = [t for t in self._suggest_threads
                                 if t.is_alive()]
        t = threading.Thread(target=target, daemon=True)
        self._suggest_threads.append(t)
        t.start()

    def _show_suggest(self, words):
        """在搜索框下方弹出联想列表。"""
        if self._suggest_popup is None:
            popup = QListWidget(self)
            popup.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
            popup.setAttribute(Qt.WA_ShowWithoutActivating, True)
            popup.setUniformItemSizes(True)
            popup.itemClicked.connect(self._on_suggest_picked)
            self._suggest_popup = popup
        self._stop_suggest_animation()
        popup = self._suggest_popup
        self._suggest_closing = False
        popup.clear()
        for w in words[:10]:
            popup.addItem(QListWidgetItem(str(w)))
        popup.setFixedWidth(self.search_box.width())
        pos = self.search_box.mapToGlobal(self.search_box.rect().bottomLeft())
        popup.move(pos)
        popup.setWindowOpacity(0.0)
        popup.show()
        popup.raise_()
        self._animate_suggest_opacity(1.0, 150)

    def _hide_suggest(self):
        self._suggest_seq += 1  # 使在途结果失效
        popup = self._suggest_popup
        if popup is None or not popup.isVisible() or self._suggest_closing:
            return
        self._suggest_closing = True
        self._stop_suggest_animation()
        self._animate_suggest_opacity(0.0, 120, hide_on_finish=True)

    def _stop_suggest_animation(self):
        animation = self._suggest_animation
        if animation is not None:
            animation.stop()
            animation.deleteLater()
            self._suggest_animation = None

    def _animate_suggest_opacity(self, opacity, duration, hide_on_finish=False):
        popup = self._suggest_popup
        animation = QPropertyAnimation(popup, b"windowOpacity", self)
        animation.setDuration(duration)
        animation.setStartValue(popup.windowOpacity())
        animation.setEndValue(opacity)
        animation.setEasingCurve(
            QEasingCurve.Type.OutCubic if opacity else QEasingCurve.Type.InCubic)
        self._suggest_animation = animation

        def finish():
            if self._suggest_animation is not animation:
                return
            self._suggest_animation = None
            animation.deleteLater()
            if hide_on_finish and self._suggest_closing:
                popup.hide()
                popup.setWindowOpacity(1.0)
                self._suggest_closing = False

        animation.finished.connect(finish)
        animation.start()

    def eventFilter(self, watched, event):
        popup = self._suggest_popup
        if (event.type() == QEvent.Type.MouseButtonPress
                and popup is not None and popup.isVisible()):
            global_pos = event.globalPosition().toPoint()
            in_search_box = self.search_box.rect().contains(
                self.search_box.mapFromGlobal(global_pos))
            if not popup.frameGeometry().contains(global_pos) and not in_search_box:
                self._hide_suggest()
        return super().eventFilter(watched, event)

    def _on_suggest_picked(self, item):
        """点选联想词：填入搜索框并立即发起搜索。"""
        text = item.text()
        self._hide_suggest()
        self.search_box.setText(text)
        self._do_search()

    def _do_search(self):
        kw = self.search_box.text().strip()
        self._hide_suggest()
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
        self.jump_label.setText(tr("跳至"))
        self.btn_jump.setText(tr("跳转"))
        self.search_btn.setText(tr("搜索"))
        self.btn_add.setText(tr(self._add_text_key))
        self.sort_label.setText(tr("排序"))
        self.local_filter.setPlaceholderText(tr("搜索当前列表（标题 / UP主）…"))
        try:
            self.sort_combo.blockSignals(True)
            cur = self.sort_combo.currentIndex()
            self.sort_combo.clear()
            self.sort_combo.addItems([tr(SORT_LABELS[k]) for k in SORT_KEYS])
            self.sort_combo.setCurrentIndex(max(0, cur))
        finally:
            self.sort_combo.blockSignals(False)
        self.btn_seq_prev.setText(tr("上一个"))
        self.btn_seq_next.setText(tr("下一个"))
        if self._seq_mode:
            self.seq_progress_lbl.setText(
                tr("分集视频 {i}/{n}").format(i=self._seq_index + 1,
                                              n=self._seq_total))
        if self._mode == "search" and self._search_placeholder_key:
            self.search_box.setPlaceholderText(tr(self._search_placeholder_key))
        self._update_count()
        self._render_pager_labels()
        if self._status_key is not None:
            self.status_lbl.setText(
                tr(self._status_key, *self._status_args, **self._status_kwargs))

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
        open_btn.clicked.connect(
            lambda _=False, m=mid, n=uname: self._open_space(m, n))
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

    def _open_space(self, mid, name=None):
        if mid is None:
            return
        if callable(self.on_open_space):
            try:
                self.on_open_space(mid, name)
            except TypeError:
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
        enable_touch_scroll(self.grid_scroll)
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
