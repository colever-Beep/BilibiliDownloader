"""通用「勾选下载」对话框（Fluent 版，参照 bili23 MultiPartListsDialog / CheckListView）。

- SelectDialog:          一次性传入完整 items 列表（适用于数据已拉全的场景，
                        如每周必看、排行榜、追番列表）。
- PaginatedSelectDialog: 分页拉取场景。构造即弹窗，先拉第 1 页并显示「加载中」，
                        用户点「上一页 / 下一页 / 跳转」时才再去拉对应页，避免一次
                        拉全导致弹窗长时间空白、影响体验。已选项跨页保留（按 url/bvid 去重）。

两者共用列表渲染与勾选 / 计数逻辑（基类 SelectDialogBase）。

外壳为 `ui.fluent_dialog.FluentContentDialog`（Fluent 标题栏 + 内容区 + 底部按钮排），
列表本体沿用 `ui.select_list_view.SelectListView`（圆角封面 + 矢量勾选框 + 副信息 +
整行悬停 + 点击整行切换勾选），与主界面、下载选项窗口视觉统一。

构造签名保持兼容：(parent, items, on_confirm, title) /
                (parent, fetch, ps, on_confirm, title)。
"""
import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout

from qfluentwidgets import CaptionLabel, CheckBox, PushButton, SpinBox

from utils.i18n import tr
from utils.main_thread import run_on_main
from ui.fluent_dialog import FluentContentDialog, msg_info, msg_error
from ui.select_list_view import SelectListView, _key_of
from ui.list_layout import LayoutModeToggle


class SelectDialogBase(FluentContentDialog):
    """列表 + 全选 + 计数 + 确认 / 取消 的共用骨架。"""

    def __init__(self, parent, on_confirm, title):
        super().__init__((880, 720), parent, title=title)
        self.on_confirm = on_confirm
        self._selected = {}          # key(url/bvid) -> item dict，跨页保留已选项
        self._checked_keys = set()   # 勾选真值源（SelectListView 读取）
        self._suppress = False
        self._build_content()

    # ------------------------------------------------------------------ #
    # UI 构建
    # ------------------------------------------------------------------ #
    def _build_content(self):
        # 顶部：全选复选框 + 计数标签
        top = QHBoxLayout()
        top.setSpacing(12)
        self.check_all = CheckBox(tr("全选"), self)
        self.check_all.setTristate(True)
        self.check_all.stateChanged.connect(self._on_check_all)
        self.count_lab = CaptionLabel("", self)
        top.addWidget(self.check_all)
        top.addWidget(self.count_lab)
        top.addStretch(1)
        self.add_layout(top)

        # 选择列表（圆角封面 + 勾选框 + 副信息，参照 bili23）
        self.list = SelectListView(self._checked_keys, self)
        self.list.rowClicked.connect(self._on_row_clicked)
        self.add_widget(self.list, 1)

        # 子类可在此插入额外控件（如分页栏）
        self._build_extra()

        # 底部按钮
        self.btn_ok = self.add_button(tr("确认"), primary=True, slot=self.accept)
        self.btn_ok.setEnabled(False)  # 至少选中 1 项后才可用（参照 bili23）
        self.btn_cancel = self.add_button(tr("取消"), slot=self.reject)

        # 底部左侧：详细 / 精简 布局切换（仅图标）
        self._leftBtns.addWidget(LayoutModeToggle(self))

    def _build_extra(self):
        """子类重写：在列表与底部按钮之间插入额外控件。"""
        pass

    # ------------------------------------------------------------------ #
    # 选择 / 计数
    # ------------------------------------------------------------------ #
    def _fill_table(self, items):
        """清空并填入一页 items；勾选态由 self._checked_keys 还原（跨页保留）。

        分页场景下同一页会被多次重新拉取，每次返回的 item 都是新对象（id 不同），
        但 url/bvid 稳定，因此 _selected / _checked_keys 统一以 url/bvid 为键，
        翻页回来后 key 仍对得上，已选项不会「丢失」。

        这里只做两件事：① set_items 重绘当前页；② 用本次拉取的最新 item 对象
        刷新 _selected 中仍勾选的条目（保持数据新鲜，且不破坏其它页的勾选）。
        注意：绝不能「只保留当前页存在的键」——那会误删其它页的已选项，违背
        跨页保留需求。
        """
        self.list.set_items(items)
        for it in items:
            key = _key_of(it)
            if key in self._checked_keys:
                self._selected[key] = it
        self._update_count()

    def _selected_items(self):
        return list(self._selected.values())

    def _on_row_clicked(self, index):
        """点击整行即切换勾选（bili23 CheckListView 行为）。"""
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
                self.btn_ok.setEnabled(True)
            else:
                self.count_lab.setText("")
                self.btn_ok.setEnabled(False)

            # 同步「全选」复选框的三态显示（仅基于当前页）
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
            # 不依赖三态复选框点击循环产生的 state（未选→部分→全选），
            # 而是基于「当前页是否已全部勾选」决定动作，避免首次点击落到
            # PartiallyChecked 被误判为「全不选」，导致「全选」要连点两次、
            # 或必须先手选一项才能用。
            # 注：分页场景下「全选」仅作用于当前页。
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
            self.list.set_items(self.list.items())  # 触发整表重绘
        finally:
            self._suppress = False
        self._update_count()

    # ------------------------------------------------------------------ #
    # 确认
    # ------------------------------------------------------------------ #
    def accept(self):
        selected = self._selected_items()
        if not selected:
            return
        if self.on_confirm is not None:
            self.on_confirm(selected)
        super().accept()


class SelectDialog(SelectDialogBase):
    """一次性列表（数据已拉全）。

    也可传 ``loading=True`` 配合 ``set_loading`` / ``fill`` 实现「先弹窗显示加载中、
    后台拉取完成后再填充」，避免数据多时弹窗长时间空白、给用户卡顿错觉。
    """

    def __init__(self, parent, items=None, on_confirm=None, title=tr("选择视频"),
                 loading=False):
        super().__init__(parent, on_confirm, title)
        # 加载态提示（列表与底部按钮之间），平时为空
        self._status = CaptionLabel("", self)
        self.add_widget(self._status)
        if loading:
            self.set_loading(True)
        elif items is not None:
            self._fill_table(list(items))

    def set_loading(self, on, message=None):
        """切换「加载中」状态。

        - on=True：清空列表并显示加载提示（默认「加载中...」），确认按钮禁用；
        - on=False：清除提示（可附 ``message`` 作为终态文案，如「获取失败」）。
        """
        if on:
            self._status.setText(message or tr("加载中..."))
            self.list.set_items([])
            self.btn_ok.setEnabled(False)
        else:
            self._status.setText(message or "")

    def set_status(self, text):
        self._status.setText(text)

    def fill(self, items):
        """后台拉取完成后填充数据并结束加载态。"""
        self._fill_table(list(items))
        self._status.setText("")


class PaginationMixin:
    """分页拉取能力（可被任意 SelectDialogBase 子类复用）。

    依赖宿主在 super().__init__ 之前设置：self.fetch / self.ps / self.pn /
    self.has_more / self._busy，并提供 self.list / self._fill_table 等基类能力。
    fetch 契约：callable(pn:int, ps:int) -> (items:list[dict], has_more:bool)
        - 返回两元组时按 (items, has_more) 解析；
        - 返回单列表 / None 时视为「无更多页」。
    提供：分页栏（上一页 / 下一页 / 第 N 页 / 跳转）、加载锁、状态行、错误提示。
    已选项跨页保留由 SelectDialogBase 负责。
    """

    # ------------------------------------------------------------------ #
    # 分页栏
    # ------------------------------------------------------------------ #
    def _build_pagination_bar(self):
        self.status_lbl = CaptionLabel("", self)
        self.add_widget(self.status_lbl)

        pg = QHBoxLayout()
        pg.setSpacing(10)
        self.btn_prev = PushButton(tr("上一页"), self)
        self.btn_next = PushButton(tr("下一页"), self)
        self.btn_prev.clicked.connect(self._go_prev)
        self.btn_next.clicked.connect(self._go_next)
        self.page_lbl = CaptionLabel(tr("第 1 页"), self)
        # 预留足够宽度，保证「第 N / M 页」在窄窗下也不被省略
        self.page_lbl.setMinimumWidth(120)
        self.jump_spin = SpinBox(self)
        self.jump_spin.setRange(1, 10000)
        self.jump_spin.setFixedWidth(110)
        self.btn_jump = PushButton(tr("跳转"), self)
        self.btn_jump.clicked.connect(self._go_jump)

        pg.addWidget(self.btn_prev)
        pg.addWidget(self.btn_next)
        pg.addSpacing(14)
        pg.addWidget(self.page_lbl)
        pg.addStretch(1)
        pg.addWidget(CaptionLabel(tr("跳至"), self))
        pg.addWidget(self.jump_spin)
        pg.addWidget(self.btn_jump)
        self.add_layout(pg)

        # 总页数追踪：
        #   self._total_pn  —— fetch 显式返回的总页数（已知即可立即限制跳页/显示）；
        #   self._last_pn   —— 无 total 来源（如搜索）靠「has_more=False」探明的最后一页，
        #                       作为总页数的兜底，避免跳页超出实际范围。
        self._total_pn = None
        self._last_pn = None

        self._set_nav_enabled(False)  # 首屏拉取中，先禁用导航

    # ------------------------------------------------------------------ #
    # 拉取
    # ------------------------------------------------------------------ #
    def _load_page(self, pn):
        if self._busy:
            return
        self._busy = True
        self._set_nav_enabled(False)
        self.status_lbl.setText(tr("正在加载第 {pn} 页...").format(pn=pn))
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
            self._last_pn = pn  # 已到末页，记录真实总页数（兜底）
        self._busy = False
        self._fill_table(items)
        # 已知总页数：fetch 显式返回优先，其次为探明的末页
        M = self._total_pn or self._last_pn
        if M:
            self.page_lbl.setText(
                tr("第 {pn} / {total} 页").format(pn=pn, total=M))
        else:
            self.page_lbl.setText(tr("第 {pn} 页").format(pn=pn))
        self.jump_spin.setValue(pn)
        if M:
            # 限制跳转框上限为总页数（不允许输入 / 跳转到超出范围的数字）
            self.jump_spin.setRange(1, max(1, M))
        self._set_nav_enabled(True)
        if M:
            self.status_lbl.setText(
                tr("第 {pn} / {total} 页，共 {n} 条").format(pn=pn, total=M, n=len(items)))
        else:
            self.status_lbl.setText(
                tr("第 {pn} 页，共 {n} 条").format(pn=pn, n=len(items)))
        if not items:
            if pn == 1:
                msg_info(self, tr("该分类下没有视频"))
            else:
                msg_info(self, tr("第 {pn} 页没有数据").format(pn=pn))

    def _on_error(self, pn, err):
        self._busy = False
        self._set_nav_enabled(True)
        self.status_lbl.setText(tr("加载失败"))
        msg_error(self, tr("加载第 {pn} 页失败：{err}").format(pn=pn, err=err))

    # ------------------------------------------------------------------ #
    # 导航
    # ------------------------------------------------------------------ #
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
        # 不允许跳到超出总页数的位置：超过则强制回到最后一页
        M = self._total_pn or self._last_pn
        if M and target > M:
            target = M
            self.jump_spin.setValue(M)
        if target < 1 or target == self.pn:
            return
        self._load_page(target)


class PaginatedSelectDialog(PaginationMixin, SelectDialogBase):
    """分页拉取对话框：构造即弹窗，按页按需拉取。

    fetch: callable(pn:int, ps:int) -> (items:list[dict], has_more:bool)
    已选项跨页保留（按 url/bvid 去重）；「全选」仅作用于当前页。
    """

    def __init__(self, parent, fetch, ps, on_confirm, title=tr("选择视频")):
        self.fetch = fetch
        self.ps = ps
        self.pn = 1
        self.has_more = True
        self._busy = False
        super().__init__(parent, on_confirm, title)
        self._load_page(1)  # 弹窗即拉第 1 页，后台线程进行，UI 不阻塞

    def _build_extra(self):
        self._build_pagination_bar()
