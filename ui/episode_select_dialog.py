"""选集窗口（番剧 / 多分P / 合集 / 课程 等）—— Fluent 版。

参照 bili23 多分P选择窗口，但与通用 SelectDialog 区分：本窗口只列分集的
「选择 / # / 标题 / 时长」，并额外提供列表内搜索、计数标签「总计 N 个分集（匹配 M）」、
「全选 / 清空勾选」按钮；确认按钮（bili23 的 Download Selected Items）在至少选中 1 项前禁用。

分集数据里通常没有封面 / 发布时间 / 播放点赞等字段，强行补全会把分集当普通视频去
enrich，导致标题/统计错乱——这正是此前触发 BUG 的根因，故本窗口不展示这些冗余列。

外壳为 `ui.fluent_dialog.FluentContentDialog`；列表本体沿用
`ui.select_list_view.SelectListView`（紧凑模式：无封面、无统计，显示 # / 标题 / 时长，
整行悬停 + 点击整行切换勾选），与主界面视频选择风格一致。

弹在父窗口之上，确认后通过 on_confirm 回调把勾选的分集交回主流程（统一走「下载选项」→ 入队）。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout

from qfluentwidgets import CaptionLabel, SearchLineEdit

from utils.i18n import tr
from ui.fluent_dialog import FluentContentDialog
from ui.select_list_view import SelectListView, _key_of
from ui.list_layout import LayoutModeToggle


class EpisodeSelectDialog(FluentContentDialog):
    def __init__(self, parent, episode_list, on_confirm, title=None):
        super().__init__((880, 700), parent, title=title or tr("选择分集"))
        self.full_list = list(episode_list or [])
        self.on_confirm = on_confirm
        self._states = {}          # url -> 0/1，跨过滤保持勾选
        self._selected = {}        # key -> item，供 accept 返回
        self._checked_keys = set()
        self._filtered = []
        self._suppress = False      # 防止 rebuild / 全选 时递归触发

        self._build_content()
        self._apply_filter()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_content(self):
        # 顶部：计数 + 搜索
        top = QHBoxLayout()
        top.setSpacing(12)
        self.count_lab = CaptionLabel("", self)
        top.addWidget(self.count_lab)
        top.addStretch(1)
        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText(tr("搜索分集标题…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        top.addWidget(self.search)
        self.add_layout(top)

        # 选择列表（紧凑模式，复用 SelectListView）
        self.list = SelectListView(self._checked_keys, self)
        self.list.rowClicked.connect(self._on_row_clicked)
        self.add_widget(self.list, 1)

        # 底部：全选 / 清空 / 确认 / 取消
        self.btn_all = self.add_button(tr("全选"), right=False, slot=self._select_all)
        self.btn_none = self.add_button(tr("清空勾选"), right=False,
                                       slot=self._unselect_all)
        self.btn_ok = self.add_button(tr("添加选中到下载队列"), primary=True,
                                     slot=self.accept, min_width=160)
        self.btn_ok.setEnabled(False)
        self.btn_cancel = self.add_button(tr("取消"), slot=self.reject)

        # 底部左侧：详细 / 精简 布局切换（仅图标）
        self._leftBtns.addWidget(LayoutModeToggle(self))

    # ------------------------------------------------------------------ #
    # 数据 / 过滤 / 渲染
    # ------------------------------------------------------------------ #
    def _apply_filter(self):
        kw = self.search.text().strip().lower()
        if kw:
            self._filtered = [
                it for it in self.full_list
                if kw in (it.get("title", "") or "").lower()
            ]
        else:
            self._filtered = list(self.full_list)
        self.list.set_items(self._filtered)
        self._update_count()

    # ------------------------------------------------------------------ #
    # 交互
    # ------------------------------------------------------------------ #
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
            self._states[key] = False
        else:
            self._checked_keys.add(key)
            self._selected[key] = it
            self._states[key] = True
        self.list.refresh_row(index)
        self._update_count()

    def _selected_items(self):
        return [it for it in self.full_list
                if self._states.get(_key_of(it), False)]

    def _update_count(self):
        if self._suppress:
            return
        self._suppress = True
        try:
            sel = sum(1 for it in self.full_list if self._states.get(_key_of(it), False))
            total = len(self.full_list)
            kw = self.search.text().strip()
            if kw:
                self.count_lab.setText(
                    tr("总计 {total} 个分集（匹配 {matched}）").format(
                        total=total, matched=len(self._filtered)))
            else:
                self.count_lab.setText(tr("总计 {total} 个分集").format(total=total))
            self.btn_ok.setEnabled(sel > 0)
        finally:
            self._suppress = False

    def _select_all(self):
        for it in self._filtered:
            key = _key_of(it)
            if key is None:
                continue
            self._checked_keys.add(key)
            self._selected[key] = it
            self._states[key] = True
        self.list.set_items(self._filtered)
        self._update_count()

    def _unselect_all(self):
        for it in self._filtered:
            key = _key_of(it)
            if key is None:
                continue
            self._checked_keys.discard(key)
            self._selected.pop(key, None)
            self._states[key] = False
        # set_items 会复用/重建 item 对象；用稳定的 url 键收敛，避免 id 漂移导致状态丢失
        living = {_key_of(it) for it in self._filtered}
        for k in list(self._states.keys()):
            if k not in living:
                self._states.pop(k, None)
        self.list.set_items(self._filtered)
        self._update_count()

    def accept(self):
        selected = self._selected_items()
        if not selected:
            return
        if self.on_confirm is not None:
            self.on_confirm(selected)
        super().accept()
