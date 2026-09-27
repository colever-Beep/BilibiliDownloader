import tkinter as tk
import weakref
import customtkinter as ctk
from utils.i18n import tr, register


def get_dpi_scale(widget):
    """获取 CustomTkinter 的 widget 缩放因子。

    CustomTkinter 在高 DPI 屏幕上会自动放大所有 CTk 控件尺寸（字体、高度、padding），
    但 tk.Canvas 的坐标是物理像素、不受此缩放影响。若不补偿，Canvas create_window
    分配的固定行高会远小于被 CTk 放大的行内容实际高度，导致行与行严重重叠。
    """
    try:
        return ctk.ScalingTracker.get_widget_scaling(widget)
    except Exception:
        return 1.0


class VirtualList(ctk.CTkFrame):
    """高性能虚拟滚动列表（解决快速滚动重叠 / 撕裂 / 卡顿）。

    实现要点（区别于 CTkScrollableFrame + grid 的反模式）：
    - 用原生 tk.Canvas 作为视口，每行是一个独立的 CTkFrame，
      通过 canvas.create_window 放在内容坐标 y = index * ROW_HEIGHT 上。
    - 滚动时 Tk 仅移动 window item 的*显示位置*（C 层实现），不重绘 widget 内容
      —— CustomTkinter 复合 widget 不再被整片重绘，帧率极高、不撕裂。
    - 每行 y 坐标被内容坐标锁定，render / unrender 永远落在正确位置，绝不重叠。
    - 滚动（滚轮 / 滚动条拖动）通过 yscrollcommand 即时触发 _check_render，
      不依赖定时器轮询，跟手。
    - 行控件复用（widget recycling）：进出视口的行复用同一组 frame / canvas
      窗口，只重填内容并移动位置，**绝不在滚动中 destroy / create 控件**，
      从根上消除撕裂与重叠。
    - DPI 感知：__init__ 时检测 CTk widget_scaling 并将 ROW_HEIGHT / column_widths
      同比放大，使 Canvas 分配的行高 / 列宽与被 CTk 放大的行内容匹配，
      从根本上解决高分辨率（150% / 200% 缩放）下行元素重叠的问题。

    子类需实现：
        build_row(self, frame, index, item)   # 在 frame 内布局第 index 行
    可选实现：
        update_row(self, frame, index, item) -> bool  # 数据结构未变时增量刷新，
                                                       # 返回 True 表示已处理（不重建）。
    """

    ROW_HEIGHT = 80
    # 缓冲行数：快速滚动时每行窗口（CTk 复合控件 ×N）的重定位/重绘是单帧内最大的
    # 开销。buffer 越大视口内窗口越多，单次 flush 越容易超一帧（16.7ms@60Hz）→
    # DWM 在 flush 中途合成"部分行已移动、部分未动"的中间帧 = 撕裂。
    # 实测每行 41 个 CTk 窗口时 flush 38-56ms（2.3~3.4 帧），buffer 4→2 可减少
    # 约 25% 的窗口重定位量。
    RENDER_BUFFER = 2

    # 连续两次 flush 间隔小于此值（秒）即判定为「快速滚动突发」，期间行复用跳过
    # 内容刷新（只挪位置），滚动停止后补刷。
    _FAST_GAP = 0.25

    # 全局滚轮分发：所有 VirtualList 实例共享一个进程级 <MouseWheel> 处理器，
    # 通过指针坐标命中测试定位目标列表，彻底解决 Windows 下「光标停在行内嵌入控件
    # 上时滚轮/触控板事件路由不可靠」导致触控板失效、滚轮偶发失效的问题。
    _INSTANCES = weakref.WeakSet()
    _GLOBAL_BOUND = False
    # Tk 9.0 起，触控板 / 高分辨率鼠标的滚动产生 <TouchpadScroll> 事件（不再是
    # <MouseWheel>），且其 delta 是「X 滚动(高16位) + Y 滚动(低16位)」的组合编码。
    # 只绑定 <MouseWheel> 会导致触控板滚动完全不触发处理器（触控板失效的根因）。
    # <Button-4>/<Button-5> 是 Linux 滚轮。
    WHEEL_SEQS = ("<MouseWheel>", "<TouchpadScroll>", "<Button-4>", "<Button-5>")

    def __init__(self, master, column_widths=None, empty_text="暂无数据",
                 build_row=None, update_row=None, row_height=None, **kwargs):
        super().__init__(master, **kwargs)
        # 仅存翻译键（简体中文原文），渲染空状态时才 tr()，避免 import 时被默认语言烤死
        self._empty_text = empty_text
        # build_row / update_row 由宿主（QueueView / 各 Dialog）以回调形式注入，
        # 这样 VirtualList 内部渲染时能调用到宿主的布局逻辑。
        self._build_row = build_row if build_row is not None else self.build_row
        self._update_row = update_row if update_row is not None else self.update_row
        self._items = []
        # 行控件对象池（widget recycling）：固定一组 frame + canvas 窗口，滚动时
        # 不再销毁/重建，只把内容重填进已有 frame 并移动窗口位置。这是消除"撕裂/
        # 重叠"的关键 —— 旧实现每次滚动都 destroy/create 整棵 CTkFrame 树并
        # delete/create canvas 窗口，画布已滚到位而控件尚未重绘便露缝。
        self._rendered = {}            # index -> (frame, canvas_id)  对外接口，保持兼容
        self._index_to_slot = {}      # index -> slot 下标
        self._slots = []              # [{"frame", "cid", "index"}]
        self._free = []               # 空闲 slot 下标
        self._last_first = None
        self._last_last = None
        self._last_canvas_w = None   # 画布宽度缓存：<Configure> 首次触发时比对用，须先初始化
        self._closed = False
        self._empty_cid = None
        self._empty_widget = None
        # 渲染调度：滚动回调里不直接改画布（见 _on_scroll / _schedule_render）
        self._render_job = None
        self._in_render = False
        # 滚轮事件合并：同一 Tk idle 周期内的多个滚轮事件累积成一次原子滚动+渲染，
        # 从根上消除「画布已滚但行窗口 SetWindowPos 还未执行」造成的撕裂/重叠。
        # （update_idletasks 仍可保证每行窗口位置在最终上屏前已对齐，但 Windows 的
        #  DWM 合成发生在 idle 调度之间——每多一次事件就多一次合成机会=多一次撕裂
        #  窗口；合并后每个 idle 周期最多一次合成，彻底根除。）
        self._pending_scroll = 0
        self._scroll_job = None
        # 快速滚动内容降级：连续滚动突发期间，行复用时跳过 update_row 的内容刷新
        # （configure 十几个字段较贵），只挪位置；滚动停止 ~150ms 后统一补刷。
        # 位置对齐（coords/itemconfigure）永远执行，绝不产生行重叠。
        self._fast_scroll = False
        self._last_flush_t = None
        self._stale_job = None

        # ---- DPI 缩放 ----
        # CTk 自动缩放控件尺寸（font/height/padding），但 tk.Canvas 坐标不走 CTk 缩放。
        # 必须把行高和列宽同比放大，否则 create_window 分配的空间装不下被放大的内容。
        self._dpi_scale = get_dpi_scale(self)
        base_height = row_height if row_height is not None else self.ROW_HEIGHT
        self.ROW_HEIGHT = int(base_height * self._dpi_scale)
        raw_widths = list(column_widths) if column_widths else []
        self.column_widths = [int(w * self._dpi_scale) for w in raw_widths]

        # 视口：原生 Canvas（CustomTkinter 无 CTkCanvas）
        # yscrollincrement=1 -> 1 个 "units" = 1 像素，滚轮按像素滚动（手感顺滑）。
        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                 bg=self._theme_bg(), yscrollincrement=1)
        self._scrollbar = ctk.CTkScrollbar(self, orientation="vertical",
                                          command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._on_scroll)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar.grid(row=0, column=1, sticky="ns")
        # 隐藏拖动条：拖动滚动条会高频触发虚拟列表重绘，易产生撕裂/错位等 UI 问题。
        # 隐藏后仍可用鼠标滚轮 / 触控板滚动（全局分发器 _do_scroll 直接驱动 yview），
        # 对象保留以便 _on_scroll 回调继续调用 .set() 同步滚动位置。
        self._scrollbar.grid_remove()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 事件：滚动即时重算渲染集（不靠轮询）
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        # 滚轮：注册到全局命中测试分发器（见 _install_global_wheel）。
        # 不再给 canvas / 行内子控件逐一绑定——那套方案依赖滚轮事件精确路由到光标
        # 下的子控件，而行是 canvas.create_window 嵌入的窗口，Windows 下 WM_MOUSEWHEEL
        # 对这些嵌入窗口的路由不可靠，导致触控板完全失效、鼠标滚轮偶发收不到。
        # 全局处理器用指针坐标命中测试定位目标列表，与具体子控件无关，彻底根治。
        VirtualList._INSTANCES.add(self)
        self._install_global_wheel()

    # ---------- 主题背景 ----------
    def _theme_bg(self):
        try:
            mode = ctk.get_appearance_mode()
            colors = ctk.ThemeManager.theme["CTkFrame"]["fg_color"]
            if isinstance(colors, (list, tuple)):
                return colors[1] if mode == "Dark" else colors[0]
            return colors if isinstance(colors, str) else "#f9f9f9"
        except Exception:
            return "#f9f9f9"

    def refresh_appearance(self):
        """明暗主题切换后刷新原生部件颜色（canvas / 行 frame 背景色）。

        行容器是原生 tk.Frame（见 _acquire_slot），不会像 CTk 控件那样自动跟随
        主题；行内的原生 label 由宿主（如 QueueView）在 update_row 里刷新。
        刷新后强制回收全部行并重渲染，确保每行内容色一致。
        """
        if self._closed:
            return
        bg = self._theme_bg()
        try:
            self._canvas.configure(bg=bg)
        except Exception:
            pass
        for slot in self._slots:
            try:
                slot["frame"].configure(bg=bg)
            except Exception:
                pass
        self._recycle_all()
        self._check_render()

    @classmethod
    def refresh_appearance_all(cls):
        """进程内所有 VirtualList 实例刷新主题色（由 ui.theme.apply_appearance 调用）。"""
        for vl in list(cls._INSTANCES):
            try:
                if vl.winfo_exists():
                    vl.refresh_appearance()
            except Exception:
                continue

    # ---------- 钩子（子类实现）----------
    def build_row(self, frame, index, item):
        raise NotImplementedError

    def update_row(self, frame, index, item):
        """可选：数据结构未变时增量刷新已渲染行。返回 True 表示已处理（不重建）。"""
        return False

    # ---------- 数据 ----------
    def set_items(self, items, rebuild=True, refresh=False):
        """设置数据。
        rebuild=True  : 清空所有已渲染行并重建（换页 / 过滤 / 增删）。
        rebuild=False : 仅更新引用；若 refresh=True 则增量刷新已渲染行内容。
        """
        items = list(items)
        if not rebuild and self._items and len(items) == len(self._items):
            self._items = items
            if refresh:
                for i in list(self._rendered.keys()):
                    slot_idx = self._index_to_slot.get(i)
                    if slot_idx is None:
                        continue
                    frame = self._slots[slot_idx]["frame"]
                    if not self._update_row(frame, i, items[i]):
                        self._fill_slot(slot_idx, i)   # 复用 frame 重填
            self._update_scrollregion()
            return

        # 释放所有行（仅归还槽位，不销毁 frame / 不 delete canvas 窗口）
        if self._rendered:
            self._recycle_all()
        self._items = items
        self._clear_empty()
        self._last_first = self._last_last = None
        self._update_scrollregion()
        self._clamp_view()
        if not self._items:
            self._render_empty()
        else:
            self._check_render()

    def _clamp_view(self):
        """数据变短后把视口夹回有效范围。

        Tk 不会立刻根据新的 scrollregion 修正当前 yview，若原先滚到很深的位置
        而新列表很短，canvasy(0) 仍返回旧偏移，渲染区间会整体落到列表之外，
        表现为"列表有数据却一片空白"。
        """
        try:
            total = len(self._items) * self.ROW_HEIGHT
            h = self._canvas.winfo_height()
            if total <= 0 or h <= 1:
                self._canvas.yview_moveto(0)
                return
            max_top = max(0, total - h)
            if self._canvas.canvasy(0) > max_top:
                self._canvas.yview_moveto(max_top / total)
        except Exception:
            pass

    def item_count(self):
        return len(self._items)

    def get_item(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def get_rendered_frame(self, index):
        """返回当前已渲染行的 frame（未渲染返回 None）。供宿主做定向增量更新。"""
        entry = self._rendered.get(index)
        return entry[0] if entry else None

    # ---------- 滚动区域 ----------
    def _update_scrollregion(self):
        total = len(self._items) * self.ROW_HEIGHT
        w = self._canvas_w()
        self._canvas.configure(scrollregion=(0, 0, w, total))

    def _on_canvas_configure(self, e):
        w = e.width
        if w and w != self._last_canvas_w:
            self._last_canvas_w = w
            self._recycle_all()
        self._canvas.configure(scrollregion=(0, 0, w, len(self._items) * self.ROW_HEIGHT))
        for slot in self._slots:
            try:
                self._canvas.itemconfigure(slot["cid"], width=w)
            except Exception:
                pass
        # 空状态提示文字居中跟随画布尺寸变化
        if self._empty_widget is not None and self._empty_widget.winfo_exists():
            try:
                h = e.height
                self._canvas.coords(self._empty_cid, w / 2, h / 2)
            except Exception:
                pass
        # 拖拽改变窗口大小时 <Configure> 会连珠炮式触发，若每次都同步重建渲染集，
        # 拉伸窗口会明显卡顿。同样交给 idle 合并，一次拉伸只重排一次。
        self._schedule_render()

    @staticmethod
    def _parse_wheel_delta(delta):
        """从 Tk 的 <MouseWheel> delta 提取垂直滚动量（有符号）。

        Tk 9.0 起，Windows 的 <MouseWheel> 事件 delta 字段是「X 滚动(高 16 位) +
        Y 滚动(低 16 位)」的组合编码（见 tk::PreciseScrollDeltas），且触控板 /
        高分辨率鼠标产生的是平滑小值（如 ±30）而非 ±120。若直接把它当纯垂直滚动量，
        向下滚（Y 为负）时低 16 位是 0xFFxx 的大数，会算出巨大 amount 导致滚动失效
        —— 这正是 Tk 9.0 下触控板无法滚动、滚轮偶发失效的根因。
        这里取低 16 位并做符号扩展，得到真正的垂直滚动量；对 Tk 8.6 的 ±120 同样正确，
        向后兼容。
        """
        low = delta & 0xFFFF
        return low if low < 0x8000 else low - 0x10000

    def _do_scroll(self, event):
        # 列表为空时禁止滚动：空状态提示文字（如"队列为空"）不应跟随滚轮移动
        if not self._items:
            return "break"
        # 解析滚动方向：Windows delta；Linux 用 Button-4/5 的 num
        delta = getattr(event, "delta", 0)
        if delta == 0:
            num = getattr(event, "num", 0)
            if num == 4:
                delta = 120
            elif num == 5:
                delta = -120
        if not delta:
            return "break"
        # Tk 9.0 的 delta 是 X/Y 组合编码，先提取垂直分量（有符号）
        delta = self._parse_wheel_delta(delta)
        if not delta:
            return "break"
        # canvas 的 yscrollincrement 已设为 1（1 unit = 1 像素），故用 "units" 滚动、
        # amount 直接是像素数即可获得顺滑手感。触控板平滑滚动的 delta 很小（如 ±30），
        # 四舍五入可能落到 0，此时退化为 ±1 像素，保证每格都动、不卡死。
        amount = int(round(-delta / 120.0 * self.ROW_HEIGHT))
        if amount == 0:
            amount = -1 if delta > 0 else 1
        # ---- 滚轮事件合并（防撕裂的关键）----
        # 同一 Tk idle 周期内的多个滚轮事件（高频滚动 / 触控板平滑滚动会一帧内堆 N 个）
        # 累积到 _pending_scroll，并在下一个 idle 周期**一次**完成 yview_scroll + 渲染 +
        # 行窗口重定位 + update_idletasks —— 把「画布已滚但行窗口 SetWindowPos 还未执行」
        # 造成的撕裂窗口压缩到 0 次。
        # 单次滚轮点击的延迟 ≈ 1 个 idle 周期（亚毫秒），用户无感。
        self._pending_scroll += amount
        if self._scroll_job is None:
            try:
                self._scroll_job = self.after_idle(self._flush_pending_scroll)
            except Exception:
                # 兜底：直接同步执行，避免调度失败导致滚轮完全失效
                self._flush_pending_scroll()
        return "break"

    def _flush_pending_scroll(self):
        """原子地冲刷累积的滚轮位移：一次 yview_scroll + 渲染 + 行窗口重定位。

        必须在主线程同步执行（after_idle 本就在主线程）。若期间窗口已销毁，安静返回。
        """
        self._scroll_job = None
        if self._closed:
            self._pending_scroll = 0
            return
        # 快速滚动检测：距上次 flush < 250ms 视为连续滚动突发。
        # 突发期间行复用跳过内容刷新（configure 一行十几个字段 × 多行也容易把
        # flush 推过一帧），只保证位置/槽位交换；停止后 _refresh_stale_rows 补刷。
        import time as _time
        now = _time.monotonic()
        self._fast_scroll = (self._last_flush_t is not None
                             and (now - self._last_flush_t) < self._FAST_GAP)
        self._last_flush_t = now

        amount = self._pending_scroll
        self._pending_scroll = 0
        if amount:
            try:
                self._canvas.yview_scroll(amount, "units")
            except Exception:
                pass
            # yview_scroll 触发 yscrollcommand -> _on_scroll -> 同步 _check_render
            # （已在上一轮修复中改为同步，紧跟滚动填入/移出行窗口）。
            # 关键：update_idletasks 强制 Tk 把本周期内的画布局部 idle 任务（嵌入
            # 窗口的 SetWindowPos、DisplayCanvas）全部同步完成，确保本帧上屏时
            # 画布内容与行窗口位置严格一致，根除撕裂/重叠。
            try:
                self._canvas.update_idletasks()
            except Exception:
                pass
        else:
            # 没有位移但 idle 仍触发：兜底做一次轻量渲染（如窗口尺寸变化后某行丢失）
            self._check_render()
        # 若有行在快速滚动期间被降级（内容滞后），安排停止后补刷
        if self._stale_job is None and any(s.get("stale") for s in self._slots):
            try:
                self._stale_job = self.after(150, self._refresh_stale_rows)
            except Exception:
                pass

    def _refresh_stale_rows(self):
        """滚动停止后，为快速滚动期间被降级（内容滞后）的行补一次 update_row。

        _fast_scroll 只在 _flush_pending_scroll 里更新，滚动一旦停止就再不会有新的
        flush 来复位它 —— 必须**基于时间**判定滚动是否已停（距上次 flush 超过
        _FAST_GAP 即视为停止），否则它会永远卡在 True 导致本方法自我重排、
        stale 行永不补刷，且残留状态会波及 set_items 的重建路径（行内容全错位）。
        """
        self._stale_job = None
        if self._closed:
            return
        import time as _time
        if self._fast_scroll:
            if self._last_flush_t is not None and (
                    _time.monotonic() - self._last_flush_t) < self._FAST_GAP:
                # 仍在滚动突发中：稍后再试
                if self._stale_job is None:
                    try:
                        self._stale_job = self.after(150, self._refresh_stale_rows)
                    except Exception:
                        pass
                return
            # 已停顿 -> 判定滚动结束，复位标志后才能补刷
            self._fast_scroll = False
        for idx in list(self._rendered.keys()):
            slot_idx = self._index_to_slot.get(idx)
            if slot_idx is None:
                continue
            slot = self._slots[slot_idx]
            if not slot.get("stale"):
                continue
            frame = slot["frame"]
            slot["stale"] = False
            try:
                self._update_row(frame, idx, self._items[idx])
            except Exception:
                pass

    def _on_scroll(self, first, last):
        self._scrollbar.set(first, last)
        # 快速滚动时渲染必须紧跟滚动：若用 after_idle 合并，事件队列在连续滚动时
        # 始终不空，滚入视口的行迟迟不创建，露出大片空白/割裂，滚动停止后才一次性
        # 补渲染（用户看到的"刷新速率不够快"）。
        # 对象池复用下 _check_render 开销极小——只有滚动跨越行边界时才会重建边缘
        # 1~2 行，其余情况直接早退——故这里直接同步渲染，紧跟每一帧滚动。
        # resize 场景（<Configure> 连珠炮）仍走 _schedule_render 的 after_idle 合并。
        self._check_render()

    # ---------- 滚轮绑定（全局命中测试，兼容触控板 / 鼠标滚轮）----------
    # 旧方案给每个控件递归挂私有 bindtag，依赖事件精确路由到光标下的子控件。但行是
    # canvas.create_window 嵌入的窗口，Windows 下 WM_MOUSEWHEEL 对嵌入窗口的路由
    # 不可靠：触控板两指滚动（同样走 WM_MOUSEWHEEL）完全收不到，鼠标滚轮偶发收不到。
    # 改为在顶层安装「进程级」<MouseWheel> 处理器，收到事件后用指针坐标命中测试定位
    # 目标列表并滚动——不依赖事件能否抵达具体子控件，彻底根治。

    def _install_global_wheel(self):
        """在本进程安装唯一的全局滚轮处理器（仅一次）。"""
        cls = type(self)
        if cls._GLOBAL_BOUND:
            return
        cls._GLOBAL_BOUND = True
        try:
            root = self.winfo_toplevel()
            for seq in cls.WHEEL_SEQS:
                root.bind_all(seq, _global_wheel_dispatch, add="+")
        except Exception:
            # 兜底：绑定失败则下次实例化重试，绝不抛错中断 UI
            cls._GLOBAL_BOUND = False

    @classmethod
    def _find_under(cls, x, y):
        """返回指针 (x, y) 下真正应滚动的 VirtualList，否则 None。

        步骤：
        1) 矩形命中收集所有包含指针的列表画布（坐标尺度经验证与屏幕一致）；
        2) 只有一个命中 -> 直接返回；
        3) 多个命中（不同窗口的列表在屏幕上有重叠区）-> 按所属 Toplevel 的
           Z 序（`wm stackorder`，底层在前、顶层在末尾）选**最上层窗口**的列表。

        旧实现忽略 Z 序、直接选「面积最小」，这是**错的**：当主窗口的列表区域
        恰好比对话框（如视频选择窗口）的列表小时，指针停在对话框列表上方、同时
        也在主窗口列表矩形内，会永远选中主窗口 —— 表现为「点回对话框后它滚不动、
        滚的却是主窗口队列」（用户报的窗口切换后滚动失效）。

        注：曾尝试 Tk 的 `winfo_containing(x,y)` 做精确命中，但本环境 Tk 9.0 +
        Windows 下它对任何坐标都返回 None（实测失效），故退回矩形 + Z 序方案。
        未命中任何列表时返回 None，事件交还 Tk 默认行为。
        """
        hits = []
        for vl in list(cls._INSTANCES):
            try:
                if not vl.winfo_exists():
                    continue
                cv = vl._canvas
                if not cv.winfo_exists() or not cv.winfo_viewable():
                    continue
                rw, rh = cv.winfo_width(), cv.winfo_height()
                if rw <= 1 or rh <= 1:
                    continue
                rx, ry = cv.winfo_rootx(), cv.winfo_rooty()
                if rx <= x <= rx + rw and ry <= y <= ry + rh:
                    hits.append(vl)
            except Exception:
                continue
        if not hits:
            return None
        if len(hits) == 1:
            return hits[0]
        # 多个命中：按所属 toplevel 的 Z 序分组
        tops = {}
        for vl in hits:
            try:
                t = vl.winfo_toplevel()
            except Exception:
                continue
            key = str(t)
            tops.setdefault(key, (t, []))[1].append(vl)
        if len(tops) == 1:
            # 同一窗口内（理论上不会重叠）防御性兜底：面积最小
            return min(hits, key=lambda v: v._canvas.winfo_width() * v._canvas.winfo_height())
        # 跨窗口：查 stack order（同 Tk app 内全局，低->高）
        order = []
        try:
            any_top = next(iter(tops.values()))[0]
            raw = any_top.tk.call("wm", "stackorder", str(any_top))
            order = list(raw) if raw else []
        except Exception:
            order = []
        if order:
            pos = {str(t): i for i, t in enumerate(order)}
            top_key = max(tops.keys(), key=lambda k: pos.get(k, -1))
            group = tops[top_key][1]
            if len(group) == 1:
                return group[0]
        # 兜底：面积最小
        return min(hits, key=lambda v: v._canvas.winfo_width() * v._canvas.winfo_height())

    # ---------- 渲染调度（防撕裂）----------
    def _schedule_render(self):
        if self._closed or self._render_job is not None:
            return
        self._render_job = self.after_idle(self._run_scheduled_render)

    def _run_scheduled_render(self):
        self._render_job = None
        self._check_render()

    def _canvas_w(self):
        w = self._canvas.winfo_width()
        if w and w > 1:
            return w
        # 画布尚未布局（winfo_width() 返回 1）时，给一个稳妥的回退宽度，
        # 否则行宽会被写成 1px。
        try:
            p = self.winfo_width()
            if p and p > 1:
                return p - (self._scrollbar.winfo_width() or 16)
        except Exception:
            pass
        return 100

    # ---------- 虚拟渲染（行控件对象池 / widget recycling）----------
    def _check_render(self):
        # _in_render 重入保护：渲染时重建行内子控件会触发 Tk 的几何计算与 idle
        # 任务，可能反过来再次触发 <Configure> / 滚动回调。若重入，同一 index
        # 可能被处理两次或渲染集算到一半被打断，表现为行重叠。
        if self._closed or self._in_render or not self._items:
            return
        try:
            top = self._canvas.canvasy(0)
        except Exception:
            return
        h = self._canvas.winfo_height()
        if h <= 1:
            return
        first = max(0, int(top // self.ROW_HEIGHT) - self.RENDER_BUFFER)
        last = min(len(self._items) - 1,
                   int((top + h) // self.ROW_HEIGHT) + self.RENDER_BUFFER)
        # 数据变短而 Tk 尚未把 yview 夹回范围内时，top 仍停在旧的深处，
        # 会算出 first > last，range() 为空 -> 一行都不渲染（列表整片空白）。
        if first > last:
            first = max(0, last)
        if first == self._last_first and last == self._last_last:
            return
        self._in_render = True
        try:
            self._last_first, self._last_last = first, last
            visible = set(range(first, last + 1))
            assigned = set(self._rendered.keys())
            # 1) 先释放滚出的行：仅归还槽位、隐藏其 canvas 窗口，**绝不 delete**，
            #    因此画布上永远有窗口覆盖每个可视行，不会出现"旧行已删、新行未建"的露缝。
            for i in (assigned - visible):
                self._release_slot(i)
            # 2) 再为滚入的行取一个空闲槽位（复用既有 frame，不创建/不销毁），
            #    稳态滚动时只有边缘 1~2 行变化，绝大多数行保持原位，开销极小。
            for i in (visible - assigned):
                slot_idx = self._acquire_slot()
                self._fill_slot(slot_idx, i)
        finally:
            self._in_render = False

    # ---------- 对象池操作 ----------
    def _acquire_slot(self):
        """取一个空闲槽位；池不足时新建一个 frame + canvas 窗口（极少发生）。

        行容器用**原生 tk.Frame** 而非 CTkFrame：CTkFrame 是 frame+canvas 双层复合
        控件，每次滚动重定位都会触发内部 canvas 的 Python 层 _draw（圆角矩形），
        视口内 N 行 × CTk 子控件数个 canvas 的重绘是快速滚动 flush 超帧的主力开销。
        原生 frame 由系统直接绘制，几乎零重绘成本；主题背景色手动跟随（见
        refresh_appearance）。CTk 子控件放进原生 frame 完全兼容。
        """
        if self._free:
            return self._free.pop()
        frame = tk.Frame(self._canvas, bg=self._theme_bg(),
                         bd=0, highlightthickness=0)
        cid = self._canvas.create_window(
            0, -self.ROW_HEIGHT, window=frame, anchor="nw",
            width=self._canvas_w(), height=self.ROW_HEIGHT,
        )
        slot_idx = len(self._slots)
        self._slots.append({"frame": frame, "cid": cid, "index": None, "stale": False})
        return slot_idx

    def _release_slot(self, index):
        """把某行归还到空闲池：隐藏其 canvas 窗口，frame 保留待用。"""
        slot_idx = self._index_to_slot.pop(index, None)
        if slot_idx is None:
            return
        self._rendered.pop(index, None)
        slot = self._slots[slot_idx]
        slot["index"] = None
        try:
            self._canvas.itemconfigure(slot["cid"], state="hidden")
        except Exception:
            pass
        self._free.append(slot_idx)

    def _move_slot_into_view(self, slot, cid, index):
        """把槽位的行窗口移动到 index 对应的内容坐标并显示（位置对齐永远执行）。"""
        y = index * self.ROW_HEIGHT
        w = self._canvas_w()
        self._canvas.coords(cid, 0, y)
        try:
            self._canvas.itemconfigure(cid, width=w, height=self.ROW_HEIGHT, state="normal")
        except Exception:
            pass

    def _fill_slot(self, slot_idx, index):
        """把池中槽位填充为 index 行。

        行控件对象池（widget recycling）下，**复用**槽位时优先用 `update_row` 增量
        更新（configure 字段，不 destroy），避免快速滚动时 destroy+rebuild 几十个
        CTk 控件导致的撕裂/半成品/卡顿——这是快速滚动割裂/重叠/消失的根因。
        仅首次填充（无子控件）或 update_row 失败/未实现时才 destroy + build_row。

        快速滚动突发期间（_fast_scroll，见 _flush_pending_scroll 的判定）进一步
        降级：复用行**跳过内容刷新**（位置/槽位交换仍精确执行），内容留待滚动
        停止后 _refresh_stale_rows 统一补刷——保证单次 flush 的窗口重定位+重绘
        总量压在一帧（16.7ms@60Hz）以内，根除撕裂。
        """
        slot = self._slots[slot_idx]
        frame = slot["frame"]
        cid = slot["cid"]
        has_children = bool(frame.winfo_children())
        if has_children:
            if self._fast_scroll:
                # 快速滚动降级：只挪位置，内容滞后（停止后补刷）
                self._move_slot_into_view(slot, cid, index)
                slot["stale"] = True
                slot["index"] = index
                self._index_to_slot[index] = slot_idx
                self._rendered[index] = (frame, cid)
                return
            # 常速：update_row 增量更新内容（不 destroy）
            try:
                if self._update_row(frame, index, self._items[index]):
                    self._move_slot_into_view(slot, cid, index)
                    slot["stale"] = False
                    slot["index"] = index
                    self._index_to_slot[index] = slot_idx
                    self._rendered[index] = (frame, cid)
                    return
            except Exception:
                pass
        # 首次填充或 update_row 失败/未实现：destroy + build_row
        for c in list(frame.winfo_children()):
            try:
                c.destroy()
            except Exception:
                pass
        self._build_row(frame, index, self._items[index])
        # 仅设列最小宽度，**保留 build_row 内部设置的 weight**（扩展列）。
        for c, w in enumerate(self.column_widths):
            try:
                frame.grid_columnconfigure(c, minsize=w)
            except Exception:
                pass
        self._move_slot_into_view(slot, cid, index)
        slot["stale"] = False
        slot["index"] = index
        self._index_to_slot[index] = slot_idx
        self._rendered[index] = (frame, cid)

    def _recycle_all(self):
        """释放所有已渲染行（换页 / 过滤 / 增删 / 窗口 resize 时调用），仅归还槽位。

        必须同时把 _last_first/_last_last 重置为 None，否则 _check_render 的
        防重入守卫（first==_last_first and last==_last_last）会误判「无变化」并
        提前 return——在「仅横向拉伸窗口（高度/滚动未变）」时，所有行已被隐藏却
        不再重填，表现为「任务行消失」。set_items 在调用本方法后也会重置，这里
        统一处理可覆盖所有调用方（含 _on_canvas_configure 的 resize 路径）。
        """
        for i in list(self._rendered.keys()):
            self._release_slot(i)
        self._last_first = self._last_last = None
        # 复位快速滚动降级标志：重建/换页/resize 后必须显示完整正确的行内容，
        # 不能沿用上一次滚动突发残留的降级状态（否则行内容会与被滚到的数据错位）。
        self._fast_scroll = False

    # ---------- 空状态 ----------
    def _render_empty(self):
        if self._empty_widget is not None:
            return
        # 用 _canvas_w()（带父容器宽度兜底）而非裸 winfo_width()，避免画布尚未布局时
        # 取到 1，把空状态提示文字钉在左上角 (50,50)。
        w = self._canvas_w() or 100
        h = self._canvas.winfo_height() or 100
        # 空状态提示文字居中显示，且因列表为空时滚轮已禁用，不会随滚动移动
        self._empty_widget = ctk.CTkLabel(
            self._canvas, text=tr(self._empty_text), text_color=("#666666", "#aaaaaa"), font=("", 14)
        )
        # 注册到 i18n：切换语言时 retranslate_all() 会刷新该静态文本（如「队列为空」）
        register(self._empty_widget, self._empty_text)
        self._empty_cid = self._canvas.create_window(
            w / 2, h / 2, window=self._empty_widget, anchor="center"
        )
        # 兜底：若画布此刻尚未拿到真实尺寸（winfo 返回 1），等下一个 idle 用实时尺寸
        # 重新居中，彻底避免「队列为空」卡在左上角 / 错位（此前因 _on_canvas_configure
        # 崩溃导致 configure 永远无法把空状态文字归位）。
        self.after_idle(self._reposition_empty)

    def _reposition_empty(self):
        """把空状态提示文字重新居中到画布当前尺寸（configure / 初次布局后兜底）。"""
        try:
            if self._empty_widget is None or not self._empty_widget.winfo_exists():
                return
            if self._empty_cid is None:
                return
            w = self._canvas_w() or (self._canvas.winfo_width() or 100)
            h = self._canvas.winfo_height() or 100
            self._canvas.coords(self._empty_cid, w / 2, h / 2)
        except Exception:
            pass

    def _clear_empty(self):
        if self._empty_widget is not None:
            try:
                self._canvas.delete(self._empty_cid)
            except Exception:
                pass
            try:
                if self._empty_widget.winfo_exists():
                    self._empty_widget.destroy()
            except Exception:
                pass
            self._empty_widget = None

    # ---------- 列宽 ----------
    def set_column_widths(self, widths):
        """外部传入的是逻辑列宽（用户可读值），内部按 DPI 缩放后存储。"""
        self.column_widths = [int(w * self._dpi_scale) for w in widths]
        # 应用到池中所有 frame（含当前未显示的），保证复用后列宽一致
        for slot in self._slots:
            for c, w in enumerate(self.column_widths):
                try:
                    slot["frame"].grid_columnconfigure(c, minsize=w)
                except Exception:
                    pass

    def get_scaled_column_widths(self):
        """返回经 DPI 缩放后的列宽列表，供宿主（如 QueueView 表头）对齐使用。"""
        return list(self.column_widths)

    # ---------- 滚动辅助 ----------
    def scroll_to_top(self):
        self._canvas.yview_moveto(0)
        self._check_render()

    def current_scroll_fraction(self):
        try:
            return self._canvas.yview()[0]
        except Exception:
            return 0.0

    # ---------- 生命周期 ----------
    def destroy(self):
        self._closed = True
        # 取消挂起的 idle 渲染，避免窗口销毁后回调操作已析构的画布
        if self._render_job is not None:
            try:
                self.after_cancel(self._render_job)
            except Exception:
                pass
            self._render_job = None
        # 取消挂起的滚轮合并任务
        if self._scroll_job is not None:
            try:
                self.after_cancel(self._scroll_job)
            except Exception:
                pass
            self._scroll_job = None
        # 取消挂起的滞后内容补刷任务
        if self._stale_job is not None:
            try:
                self.after_cancel(self._stale_job)
            except Exception:
                pass
            self._stale_job = None
        self._pending_scroll = 0
        # 销毁池中所有 frame（仅在列表整体销毁时发生，滚动中不复用销毁）
        for slot in self._slots:
            try:
                f = slot["frame"]
                if f.winfo_exists():
                    f.destroy()
            except Exception:
                pass
        self._slots = []
        self._free = []
        self._rendered = {}
        self._index_to_slot = {}
        super().destroy()


# ---------- 进程级滚轮分发器 ----------
def _global_wheel_dispatch(event):
    """被 root.bind_all 绑定的全局滚轮处理器。

    滚轮事件到达顶层时，不依赖它能否精确路由到光标下的具体子控件（Windows 下
    触控板/嵌入窗口的路由不可靠），直接用指针坐标命中测试找到目标 VirtualList 并滚动。
    仅当指针落在某列表视口内才认领事件并返回 "break"，其余情况返回 None 让 Tk 默认
    行为（如其它可滚动控件的原生滚动）正常生效。
    """
    target = VirtualList._find_under(event.x_root, event.y_root)
    if target is None:
        return None
    return target._do_scroll(event)
