import customtkinter as ctk
import tkinter as tk
from PIL import Image, ImageTk
import requests
from io import BytesIO
import threading
import queue
import math
from tkinter import messagebox
from utils.helpers import optimize_thumbnail_url, format_duration, fit_text
from ui.virtual_list import VirtualList, get_dpi_scale
from utils.i18n import tr, register
from ui.base_dialog import BaseDialog


class VideoSelectDialog(BaseDialog):
    """选择下载视频对话框。

    虚拟滚动采用 VirtualList（Canvas + create_window）：行锚定内容坐标，滚动只移动
    window item 不重绘，帧率高、绝不重叠/撕裂；滚动即时渲染，跟手。
    翻页只重建当前页数据（set_items），checkbox 勾选状态按全局索引即时持久化，
    跨 render/unrender 与翻页保持一致。
    """

    _INSTANCE = None

    PAGE_SIZE = 30
    ROW_HEIGHT = 78
    RENDER_BUFFER = 4
    COL_WIDTHS = [60, 120, 40, 280, 64, 80, 70, 70, 70, 0]
    # 仅存翻译键（简体中文原文），tr() 在构建表头时求值，避免 import 时被默认语言烤死。
    HEADERS = ["选择", "封面", "#", "标题", "时长", "发布时间", "播放", "点赞", "收藏", ""]

    def __init__(self, master, video_list, on_confirm, loader=None, loader_label=""):
        # 单实例：已打开则聚焦复用，避免重复弹窗
        existing = self._singleton(master)
        if existing is not None:
            return
        super().__init__(master)
        self.master = master
        self._loader = loader                # 联网分页 loader(pn) -> (items, total_pages|None, has_more)
        self._loader_label = loader_label
        self._net_page = 1
        self._net_total = None              # None = 总页数未知
        self._net_has_more = False
        self._all_loaded = {}               # url -> item：跨页累计，用于「全选已加载」与「添加选中」
        self._loading = False
        # 分页模式（loader 非空）下不预载全量列表，首屏由 _load_net_page(1) 拉取
        self.full_video_list = video_list if loader is None else []
        self.display_list = self.full_video_list
        self.on_confirm = on_confirm
        self._closed = False
        self._dpi_scale = get_dpi_scale(self)
        self.image_queue = queue.Queue()
        self.image_cache = {}
        self._load_gen = 0

        # 分页
        self.current_page = 1
        self.total_pages = math.ceil(len(self.display_list) / self.PAGE_SIZE) if self.display_list else 1

        # 虚拟滚动 / 勾选状态（按 url 持久化，兼容过滤 / 翻页 / 跨 render）
        self._page_start = 0
        self.page_items = []
        self._selection_states = {}   # url -> 0/1（跨 render/unrender 与翻页持久化）
        self._refreshing = False

        self.title(tr("选择下载视频"))
        self._show(master, "1000x700", resizable=(False, False), grab=True)
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)

        self.build_ui()
        self.start_image_thread()
        if self._loader is not None:
            self._load_net_page(1)     # 首屏只拉第 1 页
        else:
            self.refresh_page()
        VideoSelectDialog._INSTANCE = self

    def close_dialog(self):
        self._closed = True
        self._load_gen += 99999
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def build_ui(self):
        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=12, pady=12)

        # 顶部统计栏 + 列表内搜索
        top_info = ctk.CTkFrame(main)
        top_info.pack(fill="x", pady=(0, 8))
        init_text = tr("正在加载第 1 页…") if self._loader is not None else tr("总计 {} 个视频").format(len(self.full_video_list))
        self.count_label = ctk.CTkLabel(
            top_info, text=init_text, font=("", 12, "bold"))
        self.count_label.pack(side="left")
        self.search_entry = ctk.CTkEntry(top_info, placeholder_text=tr("搜索标题 / UP主 / 类型…"), width=190)
        self.search_entry.pack(side="right")
        self.search_entry.bind("<KeyRelease>", lambda e: self.apply_filter())

        # 表头（固定，不随列表滚动）。标题列改为可扩展（expand），随窗口拉宽显示
        # 更多字；右侧预留 scrollbar 宽度（padx 右 16）使表头与画布逐列对齐。
        header = ctk.CTkFrame(main)
        header.pack(fill="x", pady=(0, 2), padx=(0, 0))
        for col, (key, w) in enumerate(zip(self.HEADERS, self.COL_WIDTHS)):
            if col == 9:   # 末尾列不显示文字（行内占位），跳过
                continue
            txt = tr(key)   # "#" 经 tr() 原样返回
            lab = ctk.CTkLabel(header, text=txt, font=("", 12, "bold"), width=w, anchor="w")
            if col == 3:   # 标题列：扩展填满剩余宽度
                lab.pack(side="left", padx=2, expand=True, fill="x")
            else:
                lab.pack(side="left", padx=2)
            register(lab, key)   # 语言切换时刷新表头

        # 虚拟滚动列表
        self._list = VirtualList(main, column_widths=self.COL_WIDTHS, build_row=self.build_row,
                                update_row=self.update_row, row_height=self.ROW_HEIGHT)
        self._list.pack(fill="both", expand=True, pady=(0, 10))

        # 分页控制栏
        page_bar = ctk.CTkFrame(main)
        page_bar.pack(fill="x", pady=(4, 8))
        self.page_text = ctk.CTkLabel(page_bar, text="")
        self.page_text.pack(side="left", padx=5)
        self.btn_prev = ctk.CTkButton(page_bar, text=tr("上一页"), command=self.page_prev, width=90)
        self.btn_prev.pack(side="left", padx=4)
        self.btn_next = ctk.CTkButton(page_bar, text=tr("下一页"), command=self.page_next, width=90)
        self.btn_next.pack(side="left", padx=4)
        ctk.CTkLabel(page_bar, text=tr("跳转页码：")).pack(side="left", padx=15)
        self.page_input = ctk.CTkEntry(page_bar, width=45)
        self.page_input.pack(side="left")
        ctk.CTkButton(page_bar, text=tr("跳转"), command=self.jump_page, width=50).pack(side="left", padx=4)

        # 底部操作按钮
        btn_bar = ctk.CTkFrame(main)
        btn_bar.pack(fill="x")
        ctk.CTkButton(btn_bar, text=tr("全选当前页"), command=self.select_current, width=110).pack(side="left", padx=4)
        self.btn_select_all = ctk.CTkButton(btn_bar, text=tr("全选全部"), command=self.select_all_video, width=110)
        self.btn_select_all.pack(side="left", padx=4)
        if self._loader is not None:
            # 分页模式下「全选全部」实际含义是「全选已加载（跨页累计）」
            self.btn_select_all.configure(text=tr("全选已加载"))
        ctk.CTkButton(btn_bar, text=tr("清空勾选"), command=self.unselect_all, width=110).pack(side="left", padx=4)
        ctk.CTkButton(btn_bar, text=tr("添加选中到下载队列"), fg_color="#248836", command=self.confirm_add, width=190).pack(side="right")
        self.update_page_status()

    # ---------- 分页 ----------
    def refresh_page(self):
        if self._refreshing:
            return
        self._refreshing = True
        try:
            self._save_rendered_states()
            if self._loader is not None:
                # 分页模式：本页即一次联网拉取的结果，整体展示（不再本地二次分页）
                self.page_items = self.display_list
                self.total_pages = 1
            else:
                self.total_pages = max(1, math.ceil(len(self.display_list) / self.PAGE_SIZE))
                if self.current_page > self.total_pages:
                    self.current_page = self.total_pages
                self._page_start = (self.current_page - 1) * self.PAGE_SIZE
                self.page_items = self.display_list[self._page_start:
                                                   self._page_start + self.PAGE_SIZE]
            while not self.image_queue.empty():
                try:
                    self.image_queue.get_nowait()
                except Exception:
                    break
            self._load_gen += 1

            self._list.set_items(self.page_items, rebuild=True)
            self._list.scroll_to_top()
            self.update_page_status()
        finally:
            self._refreshing = False

    def update_page_status(self):
        if self._loader is not None:
            if self._net_total:
                self.page_text.configure(text=tr("第 {} / {} 页").format(self._net_page, self._net_total))
            else:
                suffix = tr("（还有更多）") if self._net_has_more else ""
                self.page_text.configure(text=tr("第 {} 页{}").format(self._net_page, suffix))
            self.btn_prev.configure(state="normal" if self._net_page > 1 else "disabled")
            self.btn_next.configure(state="normal" if self._net_has_more else "disabled")
        else:
            self.page_text.configure(text=tr("第 {} / {} 页").format(self.current_page, self.total_pages))
            self.btn_prev.configure(state="normal" if self.current_page > 1 else "disabled")
            self.btn_next.configure(state="normal" if self.current_page < self.total_pages else "disabled")

    # ---------- 联网分页：上一页/下一页从网络拉取并替换当前页 ----------
    def _load_net_page(self, pn):
        if self._loading or self._closed:
            return
        self._loading = True
        self._save_rendered_states()
        self.btn_prev.configure(state="disabled")
        self.btn_next.configure(state="disabled")
        self.page_text.configure(text=tr("加载第 {} 页…").format(pn))
        self._list.set_items([], rebuild=True)
        gen = self._load_gen

        def worker():
            try:
                res = self._loader(pn)
                if not res:
                    res = ([], None, False)
                items, total_pages, has_more = res
            except Exception as e:
                if not self._closed:
                    self.after(0, lambda err=str(e): self._on_net_error(pn, err))
                return
            if self._closed:
                return
            items = items or []
            for it in items:
                u = it.get("url")
                if u:
                    self._all_loaded[u] = it
            self.after(0, lambda: self._on_net_done(pn, items, total_pages, has_more))
        threading.Thread(target=worker, daemon=True).start()

    def _on_net_done(self, pn, items, total_pages, has_more):
        self._net_page = pn
        self._net_has_more = bool(has_more)
        if total_pages:
            self._net_total = total_pages
        self.display_list = items
        self._loading = False
        self._load_gen += 1
        self.current_page = 1
        self._list.set_items(items, rebuild=True)
        self._list.scroll_to_top()
        self.count_label.configure(
            text=tr("第 {} 页：{} 个视频").format(pn, len(items))
                 + (tr(" / 共 {} 页").format(self._net_total) if self._net_total else ""))
        self.update_page_status()

    def _on_net_error(self, pn, err):
        self._loading = False
        self.page_text.configure(text=tr("第 {} 页加载失败：{}").format(pn, err))
        self.btn_prev.configure(state="normal" if self._net_page > 1 else "disabled")
        self.btn_next.configure(state="normal" if self._net_has_more else "disabled")

    def page_prev(self):
        if self._loader is not None:
            if self._net_page > 1 and not self._loading:
                self._load_net_page(self._net_page - 1)
        else:
            if self.current_page > 1:
                self.current_page -= 1
                self.refresh_page()

    def page_next(self):
        if self._loader is not None:
            if self._net_has_more and not self._loading:
                self._load_net_page(self._net_page + 1)
        else:
            if self.current_page < self.total_pages:
                self.current_page += 1
                self.refresh_page()

    def jump_page(self):
        try:
            p = int(self.page_input.get().strip())
        except ValueError:
            messagebox.showwarning(tr("提示"), tr("请输入有效页码"))
            return
        if self._loader is not None:
            if p >= 1 and not self._loading:
                self._load_net_page(p)
        else:
            if 1 <= p <= self.total_pages:
                self.current_page = p
                self.refresh_page()

    # ---------- 勾选状态持久化 ----------
    def _save_rendered_states(self):
        # 行已被回收复用，url 必须以 frame 上的实时值（_item_url）为准；
        # page_items[idx] 只作兜底——否则复用后会把勾选写到错误条目上。
        for idx, (frame, _cid) in list(self._list._rendered.items()):
            var = getattr(frame, "_cb_var", None)
            if var is None:
                continue
            url = getattr(frame, "_item_url", "")
            if not url:
                item = self.page_items[idx] if idx < len(self.page_items) else None
                url = (item or {}).get("url", "")
            if url:
                try:
                    self._selection_states[url] = var.get()
                except Exception:
                    pass

    # ---------- 行渲染（VirtualList 钩子）----------
    def _row_palette(self):
        """当前明暗主题下原生 label 的 (背景, 主文字, 次文字) 颜色。

        行容器是原生 tk.Frame（见 VirtualList._acquire_slot），不会像 CTk 控件那样
        自动跟随主题，原生 label 的颜色必须手动刷新（主题切换走
        VirtualList.refresh_appearance -> recycle -> update_row）。
        """
        try:
            bg = self._list._theme_bg()
        except Exception:
            bg = "#f9f9f9"
        if ctk.get_appearance_mode() == "Dark":
            return bg, "#DCE4EE", "#aaaaaa"
        return bg, "#1a1a1a", "#666666"

    def _fonts(self):
        """(主字号, 次字号)：原生 label 用**负像素**字体（设备像素），并手动乘 DPI
        缩放，等价于 CTkLabel 的 font=("", 13) / ("", 12)（CTk 内部会自动缩放）。"""
        dpi = self._dpi_scale
        return ("", -max(8, int(13 * dpi))), ("", -max(8, int(12 * dpi)))

    @staticmethod
    def _fmt_count(v):
        """播放/点赞/收藏的千分位格式化；B站有时返回 None 或非数字，需容错。"""
        try:
            return f"{int(v or 0):,}"
        except Exception:
            return "0"

    def _on_cb_toggle(self, frame):
        """复选框回调。

        行会被回收复用，url **绝不能**烤死在闭包里（旧实现 lambda u=item_url 会把
        复用后的勾选写回上一个 item 的 url）。这里实时从 frame._item_url 取当前行。
        """
        if getattr(frame, "_cb_updating", False):
            return   # update_row 程序化设置选中态，非用户点击
        url = getattr(frame, "_item_url", "")
        var = getattr(frame, "_cb_var", None)
        if url and var is not None:
            try:
                self._selection_states[url] = var.get()
            except Exception:
                pass

    def build_row(self, frame, local_row, item):
        """构建一行（行容器是原生 tk.Frame，见 VirtualList._acquire_slot）。

        性能关键：纯展示字段全部用**原生 tk.Label**而非 CTkLabel（与 QueueView 同款
        修复）。CTkLabel 是 frame+canvas 双层复合控件，每次滚动重定位都会触发内部
        canvas 的 Python 层 _draw（圆角矩形）；本行原本含 8 个 CTkLabel + 1 个
        CTkFrame ≈ 21 个 Tk 窗口，快速滚动时单次 flush 远超一帧（16.7ms@60Hz）
        → DWM 在 flush 中途合成"部分行已移动、部分未动"的中间帧 = 撕裂/错位的根因。
        原生化后降到 ~13 个窗口，并配合 update_row 增量复用（不 destroy）。
        交互件（CTkCheckBox）保留 CTk；颜色手动跟随主题（_row_palette）。
        """
        bg, fg, sub = self._row_palette()
        f_main, f_small = self._fonts()

        # 标题列(3)动态扩展填满可用宽度；末尾列(9)不再吸收（避免右侧留白、
        # 标题被过早截断）。与表头共用列模型，二者对齐。
        try:
            frame.grid_columnconfigure(3, weight=1)
            frame.grid_columnconfigure(9, weight=0)
        except Exception:
            pass

        item_url = item.get("url", "")
        frame._item_url = item_url

        # 复选框（按 url 持久化，勾选即时写回持久化到 _selection_states）
        var = ctk.IntVar(value=self._selection_states.get(item_url, 0))
        cb = ctk.CTkCheckBox(frame, text="", variable=var, width=60,
                            command=lambda f=frame: self._on_cb_toggle(f))
        cb.grid(row=0, column=0, padx=2, sticky="w")
        frame._cb_var = var
        frame._cb_updating = False
        frame._cb_shown = self._selection_states.get(item_url, 0)
        frame._pal = (bg, fg, sub)   # 供 update_row 判断颜色/字体是否需要重写

        # 封面（原生 label + PhotoImage；无图显示占位）
        cover_lab = tk.Label(frame, text="", bg=bg, bd=0, highlightthickness=0)
        cover_lab.grid(row=0, column=1, padx=2, sticky="w")
        frame._cover_label = cover_lab
        thumb = item.get("thumbnail", "")
        if thumb:
            if thumb in self.image_cache:
                cover_lab.configure(image=self.image_cache[thumb])
                cover_lab.image = self.image_cache[thumb]
            else:
                self.image_queue.put((self._load_gen, thumb, cover_lab))
        else:
            cover_lab.configure(text="📺", fg=sub, font=f_main)

        # 序号
        frame._idx_label = tk.Label(frame, text=str(self._page_start + local_row + 1),
                                    anchor="w", bg=bg, fg=fg, font=f_main)
        frame._idx_label.grid(row=0, column=2, padx=2, sticky="w")

        # 标题（含类型徽标）+ UP 主：按标题列实际可用宽度动态截断，
        # 列变宽即显示更多字，不再固定 280px 把长标题过早截掉、右侧留白。
        title_frame = tk.Frame(frame, bg=bg, bd=0, highlightthickness=0)
        title_frame.grid(row=0, column=3, padx=2, sticky="ew")
        frame._title_frame = title_frame

        title = item.get("title", tr("未知"))
        cat = item.get("category", "")
        full_title = f"[{cat}] {title}" if cat else title
        title_w = self._title_text_width()
        fs = max(8, int(13 * self._dpi_scale))
        ufs = max(7, int(12 * self._dpi_scale))
        frame._title_label = tk.Label(title_frame, text=fit_text(full_title, title_w, font_size=fs),
                                      anchor="w", bg=bg, fg=fg, font=f_main)
        frame._title_label.pack(anchor="w", fill="x", expand=True)
        # UP 主：始终创建（update_row 复用时不 destroy/create，直接改文本更高效）
        uploader = item.get("uploader", "")
        frame._uploader_label = tk.Label(
            title_frame, text=fit_text(uploader, title_w, font_size=ufs) if uploader else "",
            anchor="w", bg=bg, fg=sub, font=f_small)
        frame._uploader_label.pack(anchor="w", fill="x", expand=True)

        # 时长 / 发布时间 / 播放 / 点赞 / 收藏（纯展示 -> 原生 label）
        frame._dur_label = tk.Label(frame, text=format_duration(item.get("duration", 0)),
                                    anchor="w", bg=bg, fg=fg, font=f_main)
        frame._dur_label.grid(row=0, column=4, padx=2, sticky="w")
        frame._date_label = tk.Label(frame, text=str(item.get("publish_time", ""))[:10],
                                     anchor="w", bg=bg, fg=fg, font=f_main)
        frame._date_label.grid(row=0, column=5, padx=2, sticky="w")
        frame._view_label = tk.Label(frame, text=self._fmt_count(item.get("view_count", 0)),
                                     anchor="w", bg=bg, fg=fg, font=f_main)
        frame._view_label.grid(row=0, column=6, padx=2, sticky="w")
        frame._like_label = tk.Label(frame, text=self._fmt_count(item.get("like_count", 0)),
                                     anchor="w", bg=bg, fg=fg, font=f_main)
        frame._like_label.grid(row=0, column=7, padx=2, sticky="w")
        frame._fav_label = tk.Label(frame, text=self._fmt_count(item.get("favorite_count", 0)),
                                    anchor="w", bg=bg, fg=fg, font=f_main)
        frame._fav_label.grid(row=0, column=8, padx=2, sticky="w")

    def update_row(self, frame, local_row, item):
        """增量刷新（结构已建立时）：不 destroy，直接 configure 所有字段。

        复用 build_row 已建好的控件对象，只更新内容/状态。这是消除快速滚动撕裂的
        关键——若未实现本方法，VirtualList._fill_slot 每次行回收都会走
        "destroy 全部子控件 + build_row 重建" 的慢路径：销毁期间行内容为空、
        重建有中间状态，DWM 会合成半成品帧 = 撕裂/重叠/错位的根因。
        每次顺带刷新原生控件颜色，保证明暗主题切换后颜色一致。
        """
        bg, fg, sub = self._row_palette()
        f_main, f_small = self._fonts()
        pal = (bg, fg, sub)

        # 勾选状态：**先**更新 _item_url 再设 var，使回调（若被变量 trace 触发）
        # 写回的是当前行 url；_cb_updating 屏蔽程序化赋值产生的回调。
        item_url = item.get("url", "")
        frame._item_url = item_url
        var = getattr(frame, "_cb_var", None)
        if var is not None:
            want = self._selection_states.get(item_url, 0)
            # var.set() 会触发 CTkCheckBox 的变量 trace -> _draw()（canvas 圆角重绘），
            # 实测 2.03ms/次，是整行 update_row 最大的单项开销（约 55%）。行复用时
            # 绝大多数行的勾选态并不变（0 -> 0），用 _cb_shown 做变化检测跳过无谓
            # 重绘，只在实际变化时写。
            if getattr(frame, "_cb_shown", None) != want:
                frame._cb_updating = True
                try:
                    var.set(want)
                except Exception:
                    pass
                frame._cb_updating = False
                frame._cb_shown = want

        # 封面
        try:
            thumb = item.get("thumbnail", "")
            lab = getattr(frame, "_cover_label", None)
            if lab is not None:
                if thumb:
                    if thumb in self.image_cache:
                        lab.configure(image=self.image_cache[thumb], text="", bg=bg)
                        lab.image = self.image_cache[thumb]
                    else:
                        lab.configure(image="", text="📺", fg=sub, font=f_main, bg=bg)
                        self.image_queue.put((self._load_gen, thumb, lab))
                else:
                    lab.configure(image="", text="📺", fg=sub, font=f_main, bg=bg)
        except Exception:
            pass

        # 序号
        try:
            self._cfg(frame, "_idx_label", str(self._page_start + local_row + 1),
                      bg, fg, f_main, pal)
        except Exception:
            pass

        # 标题 + UP 主
        try:
            title = item.get("title", tr("未知"))
            cat = item.get("category", "")
            full_title = f"[{cat}] {title}" if cat else title
            title_w = self._title_text_width()
            fs = max(8, int(13 * self._dpi_scale))
            ufs = max(7, int(12 * self._dpi_scale))
            self._cfg(frame, "_title_label",
                      fit_text(full_title, title_w, font_size=fs),
                      bg, fg, f_main, pal)
            uploader = item.get("uploader", "")
            self._cfg(frame, "_uploader_label",
                      fit_text(uploader, title_w, font_size=ufs) if uploader else "",
                      bg, sub, f_small, pal)
        except Exception:
            pass

        # 时长 / 发布时间 / 播放 / 点赞 / 收藏
        try:
            vals = {
                "_dur_label": format_duration(item.get("duration", 0)),
                "_date_label": str(item.get("publish_time", ""))[:10],
                "_view_label": self._fmt_count(item.get("view_count", 0)),
                "_like_label": self._fmt_count(item.get("like_count", 0)),
                "_fav_label": self._fmt_count(item.get("favorite_count", 0)),
            }
        except Exception:
            vals = {}
        for name, text in vals.items():
            self._cfg(frame, name, text, bg, fg, f_main, pal)
        # 颜色/字体的写入以本行的调色板为准：主题未变时后续复用只写 text
        frame._pal = pal
        return True

    @staticmethod
    def _cfg(frame, name, text, bg, fg, font, pal):
        """配置一个原生 label：文本每次写，颜色/字体只在调色板变化时写。

        原生 label 的 configure 是 Tcl 调用（实测 4 个选项 ≈ 0.058ms/次）。滚动时
        颜色与字体并不变、只有文本变，故仅在主题切换（frame._pal 变化）时才写
        bg/fg/font，把每次调用的选项数从 4 降到 1。
        """
        lbl = getattr(frame, name, None)
        if lbl is None:
            return
        try:
            if getattr(frame, "_pal", None) == pal:
                lbl.configure(text=text)
            else:
                lbl.configure(text=text, bg=bg, fg=fg, font=font)
        except Exception:
            pass

    def _title_text_width(self):
        """标题列实际可用宽度（设备像素），供 fit_text 精确填满该列。

        旧实现用固定 COL_WIDTHS[3]=280 截断，但标题列已改为 weight=1 动态扩展，
        窗口 1000px 下实际可达 ~380px，固定 280 会把长标题过早截掉、右侧 ~100px 留白。
        这里统一从 VirtualList 内部（已按 DPI 缩放）的画布宽度与各列缩放宽度求出
        标题列真实可用宽度，与画布同尺度，标题即填满整列。
        """
        if getattr(self, "_list", None) is None:
            return 280
        total_w = self._list._canvas_w() or 0
        scaled = self._list.column_widths  # VirtualList 内部：已按 DPI 缩放
        if not scaled:
            return 280
        fixed = sum(scaled[i] for i in range(len(scaled)) if i != 3)
        avail = total_w - fixed - 14
        return max(avail, 120)

    # ---------- 勾选操作 ----------
    def select_current(self):
        for it in self.page_items:
            self._selection_states[it["url"]] = 1
        for idx, (frame, _cid) in self._list._rendered.items():
            var = getattr(frame, "_cb_var", None)
            if var is not None:
                try:
                    var.set(1)
                except Exception:
                    pass

    def select_all_video(self):
        src = list(self._all_loaded.values()) if self._loader is not None else self.display_list
        for it in src:
            self._selection_states[it["url"]] = 1
        for idx, (frame, _cid) in self._list._rendered.items():
            var = getattr(frame, "_cb_var", None)
            if var is not None:
                try:
                    var.set(1)
                except Exception:
                    pass

    def unselect_all(self):
        src = list(self._all_loaded.values()) if self._loader is not None else self.display_list
        for it in src:
            self._selection_states[it["url"]] = 0
        for idx, (frame, _cid) in self._list._rendered.items():
            var = getattr(frame, "_cb_var", None)
            if var is not None:
                try:
                    var.set(0)
                except Exception:
                    pass

    # ---------- 列表内搜索 / 过滤 ----------
    def apply_filter(self):
        kw = self.search_entry.get().strip().lower()
        if self._loader is not None:
            base = list(self._all_loaded.values())
        else:
            base = self.full_video_list
        if kw:
            self.display_list = [
                it for it in base
                if kw in (it.get("title", "") or "").lower()
                or kw in (it.get("uploader", "") or "").lower()
                or kw in (it.get("category", "") or "").lower()
            ]
        else:
            self.display_list = base
        self.current_page = 1
        self.count_label.configure(
            text=tr("总计 {} 个视频").format(len(base))
                 + (tr("（匹配 {}）").format(len(self.display_list)) if kw else ""))
        self.refresh_page()

    # ---------- 确认 ----------
    def confirm_add(self):
        self._save_rendered_states()
        if self._loader is not None:
            base = list(self._all_loaded.values())
        else:
            base = self.full_video_list
        selected = [it for it in base if self._selection_states.get(it["url"], 0) == 1]
        if not selected:
            messagebox.showwarning(tr("提示"), tr("请至少勾选一个视频"))
            return
        self._closed = True
        self._load_gen += 99999
        # 先释放 grab 再调用 on_confirm：on_confirm 可能创建新的模态对话框
        # （如 DownloadOptionsDialog），如果当前 grab 未释放，新对话框的 grab_set 会失败
        try:
            self.grab_release()
        except Exception:
            pass
        self.on_confirm(selected)
        self.destroy()

    # ---------- 图片加载线程 ----------
    def start_image_thread(self):
        def img_worker():
            while not self._closed:
                try:
                    gen, url, lab = self.image_queue.get(timeout=1)
                    if self._closed or gen != self._load_gen:
                        continue
                    thumb_url = optimize_thumbnail_url(url)
                    img = self._load_thumb(thumb_url)
                    if img:
                        def render(l=lab, i=img):
                            try:
                                if l.winfo_exists() and l.winfo_toplevel().winfo_exists():
                                    l.configure(image=i)
                                    l.image = i
                            except Exception:
                                pass
                        self.after(0, render)
                except queue.Empty:
                    continue
                except Exception:
                    continue

        for _ in range(4):
            threading.Thread(target=img_worker, daemon=True).start()

    def _load_thumb(self, url):
        if url in self.image_cache:
            return self.image_cache[url]
        try:
            resp = requests.get(url, timeout=3)
            img_raw = Image.open(BytesIO(resp.content))
            # 封面改用原生 PhotoImage（封面 label 已原生化）。CTkImage 会自动按
            # widget_scaling 缩放，原生 PhotoImage 不会，故这里手动乘 DPI 缩放。
            w = max(1, int(120 * self._dpi_scale))
            h = max(1, int(75 * self._dpi_scale))
            img_raw.thumbnail((w, h))
            photo = ImageTk.PhotoImage(img_raw)
            self.image_cache[url] = photo
            return photo
        except Exception:
            return None
