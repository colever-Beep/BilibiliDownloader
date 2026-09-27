import customtkinter as ctk
from PIL import Image
import requests
from io import BytesIO
import threading
import queue

from ui.virtual_list import VirtualList, get_dpi_scale
from ui.episode_select_dialog import EpisodeSelectDialog
from utils.helpers import optimize_thumbnail_url, fit_text
from utils.i18n import tr
from ui.theme import register_accent_widget, get_accent
from ui.base_dialog import BaseDialog


class SearchDialog(BaseDialog):
    """B 站综合搜索对话框。

    mode="all"  ：综合搜索（视频 / 番剧 / UP主 混合结果），调用 api.get_search_results。
    mode="music"：bilibili 音乐搜索（音乐 / MV 视频），调用 api.get_music_search_results。

    输入关键词 → 调用对应 API → 虚拟列表分组展示。视频/番剧行可「添加」到下载队列，
    UP主行可「打开TA的空间」浏览其视频。音乐模式下结果均为视频（MV），下载流程与普通视频一致。

    仿 bili23 的搜索入口，但结果解析与交互适配本应用的 CustomTkinter + VirtualList 架构。
    """

    # 单实例：按模式分别维护（综合搜索 / 音乐搜索 互不抢占）
    _INSTANCES = {}

    ROW_HEIGHT = 78
    RENDER_BUFFER = 4
    COL_WIDTHS = [120, 44, 320, 150, 70]
    # 仅存翻译键（本对话框未渲染可见表头，但保持与 queue_view / video_select 一致）
    HEADERS = ["封面", "#", "标题 / UP主", "操作", ""]

    def __init__(self, master, api, engine, logger, on_add=None, on_open_space=None,
                 on_add_select=None, mode="all"):
        # 单实例：已打开则聚焦复用
        existing = SearchDialog._INSTANCES.get(mode)
        if existing is not None:
            try:
                alive = existing.winfo_exists()
            except Exception:
                alive = False
            if alive:
                # 兜底：若窗口曾被 withdraw（如主题切换时序问题），先恢复显示再置顶
                try:
                    if existing.state() == "withdrawn":
                        existing.deiconify()
                except Exception:
                    pass
                existing.lift()
                existing.focus_force()
                return
            SearchDialog._INSTANCES[mode] = None

        super().__init__(master)
        self.master = master
        self.api = api
        self.engine = engine
        self.logger = logger
        self.on_add = on_add
        self.on_open_space = on_open_space
        self.on_add_select = on_add_select
        self.mode = mode if mode in ("all", "music") else "all"
        self._closed = False
        self._dpi_scale = get_dpi_scale(self)

        # 模式相关文案 / 数据
        if self.mode == "music":
            self._title_text = tr("bilibili音乐")
            self._placeholder = tr("搜索音乐 / MV / 歌单…")
            self._empty_text = tr("未找到音乐相关视频")
            self._video_badge = tr("音乐")
        else:
            self._title_text = tr("搜索 B站")
            self._placeholder = tr("搜索视频 / 番剧 / UP主…")
            self._empty_text = tr("暂无搜索结果")
            self._video_badge = tr("视频")

        self.image_queue = queue.Queue()
        self.image_cache = {}
        self._load_gen = 0

        self.title(self._title_text)
        self._show(master, "820x640", resizable=(True, True),
                   grab=True, minsize=(680, 460))
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)

        self.build_ui()
        self.start_image_thread()
        SearchDialog._INSTANCES[self.mode] = self

    # ---------- 生命周期 ----------
    def close_dialog(self):
        self._closed = True
        self._load_gen += 99999
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            if SearchDialog._INSTANCES.get(self.mode) is self:
                SearchDialog._INSTANCES[self.mode] = None
        except Exception:
            pass
        self.destroy()

    # ---------- UI ----------
    def build_ui(self):
        main = ctk.CTkFrame(self)
        main.pack(fill="both", expand=True, padx=12, pady=12)

        # 搜索栏
        top = ctk.CTkFrame(main)
        top.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(top, text="🔍", font=("", 16)).pack(side="left", padx=(2, 4))
        self.keyword_var = ctk.StringVar()
        self.keyword_entry = ctk.CTkEntry(
            top, textvariable=self.keyword_var,
            placeholder_text=self._placeholder, height=34)
        self.keyword_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.keyword_entry.bind("<Return>", lambda e: self.do_search())
        search_btn = ctk.CTkButton(top, text=tr("搜索"), command=self.do_search,
                      width=80, fg_color=get_accent())
        search_btn.pack(side="left", padx=(4, 0))
        register_accent_widget(search_btn)

        # 提示 / 统计
        self.status_label = ctk.CTkLabel(main, text=tr("输入关键词后点击搜索"), text_color=("#666666", "#aaaaaa"))
        self.status_label.pack(anchor="w", pady=(0, 4))

        # 结果列表
        self._list = VirtualList(main, column_widths=self.COL_WIDTHS,
                                empty_text=self._empty_text, build_row=self.build_row,
                                row_height=self.ROW_HEIGHT)
        self._list.pack(fill="both", expand=True, pady=(0, 8))

        # 底栏
        bottom = ctk.CTkFrame(main)
        bottom.pack(fill="x")
        self.add_all_btn = ctk.CTkButton(
            bottom, text=tr("添加全部音乐结果") if self.mode == "music" else tr("添加全部视频结果"),
            width=170, fg_color="#248836",
            command=self.add_all_videos, state="disabled")
        self.add_all_btn.pack(side="left", padx=4)
        ctk.CTkButton(bottom, text=tr("关闭"), width=90,
                      command=self.close_dialog).pack(side="right", padx=4)

    # ---------- 搜索 ----------
    def do_search(self):
        keyword = self.keyword_var.get().strip()
        if not keyword:
            return
        if not getattr(self.api, "uid", None):
            from tkinter import messagebox
            messagebox.showwarning(tr("未登录"), tr("搜索需要登录（用于签名校验），请先登录。"))
            return
        self.status_label.configure(text=tr("正在搜索：{} …").format(keyword))
        self._list.set_items([], rebuild=True)
        threading.Thread(target=self._search_thread, args=(keyword,), daemon=True).start()

    def _search_thread(self, keyword):
        try:
            if self.mode == "music":
                results = self.api.get_music_search_results(keyword, page=1)
            else:
                results = self.api.get_search_results(keyword, page=1)
        except Exception as e:
            self.after(0, lambda err=e: self.status_label.configure(
                text=tr("搜索异常：{}").format(err), text_color="#ef5350"))
            return
        if not results:
            if self.mode == "music":
                self.after(0, lambda: self.status_label.configure(
                    text=tr("未找到与「{}」相关的音乐视频").format(keyword), text_color=("#666666", "#aaaaaa")))
            else:
                self.after(0, lambda: self.status_label.configure(
                    text=tr("未找到与「{}」相关的结果").format(keyword), text_color=("#666666", "#aaaaaa")))
            self.after(0, lambda: self._list.set_items([], rebuild=True))
            return
        # 统计类型分布
        n_video = sum(1 for r in results if r["type"] == "video")
        n_bangumi = sum(1 for r in results if r["type"] == "bangumi")
        n_user = sum(1 for r in results if r["type"] == "user")
        if self.mode == "music":
            self.after(0, lambda: self.status_label.configure(
                text=tr("「{}」：{} 音乐视频").format(keyword, n_video),
                text_color="#42a5f5"))
        else:
            self.after(0, lambda: self.status_label.configure(
                text=tr("「{}」：{} 视频 / {} 番剧 / {} UP主").format(keyword, n_video, n_bangumi, n_user),
                text_color="#42a5f5"))
        self.after(0, lambda: self.add_all_btn.configure(
            state="normal" if n_video else "disabled"))
        self.after(0, lambda: self._list.set_items(results, rebuild=True))
        self.after(0, self._list.scroll_to_top)

    # ---------- 行渲染 ----------
    def build_row(self, frame, local_row, item):
        try:
            frame.grid_columnconfigure(2, weight=1)
        except Exception:
            pass

        # 封面
        cover_lab = ctk.CTkLabel(frame, text="", width=120, height=72)
        cover_lab.grid(row=0, column=0, padx=2, sticky="w")
        thumb = item.get("thumbnail", "")
        if thumb:
            if thumb in self.image_cache:
                cover_lab.configure(image=self.image_cache[thumb])
            else:
                self.image_queue.put((self._load_gen, thumb, cover_lab))
        else:
            cover_lab.configure(text="📺" if item["type"] != "user" else "👤")

        # 序号
        ctk.CTkLabel(frame, text=str(local_row + 1), width=44).grid(
            row=0, column=1, padx=2, sticky="w")

        # 标题 + 类型徽标 + UP主：按标题列实际可用宽度动态截断，列变宽即显示更多字，
        # 不再固定 320px 把长标题过早截掉、右侧留白。
        title_frame = ctk.CTkFrame(frame, fg_color="transparent")
        title_frame.grid(row=0, column=2, padx=2, sticky="ew")
        _badge_map = {"video": self._video_badge, "bangumi": tr("番剧"), "user": tr("UP主")}
        badge = _badge_map.get(item["type"], "")
        fs = max(8, int(13 * self._dpi_scale))
        ufs = max(7, int(11 * self._dpi_scale))
        title_w = self._title_text_width()
        full_title = f"[{badge}] {item.get('title', '')}" if badge else item.get("title", "")
        ctk.CTkLabel(title_frame, text=fit_text(full_title, title_w, font_size=fs),
                     anchor="w", font=("", 13)).pack(anchor="w", fill="x", expand=True)
        uploader = item.get("uploader", "")
        if uploader:
            ctk.CTkLabel(title_frame, text=fit_text(uploader, title_w, font_size=ufs),
                         anchor="w", font=("", 11), text_color=("#666666", "#aaaaaa")).pack(anchor="w", fill="x", expand=True)

        # 操作按钮
        if item["type"] in ("video", "bangumi"):
            add_btn = ctk.CTkButton(frame, text=tr("添加"), width=140, fg_color=get_accent(),
                          command=lambda it=item: self._add_one(it))
            add_btn.grid(row=0, column=3, padx=4, sticky="w")
            register_accent_widget(add_btn)
        elif item["type"] == "user":
            open_btn = ctk.CTkButton(frame, text=tr("打开TA的空间"), width=140, fg_color=get_accent(),
                          command=lambda it=item: self._open_space(it))
            open_btn.grid(row=0, column=3, padx=4, sticky="w")
            register_accent_widget(open_btn)

    def _title_text_width(self):
        """标题列实际可用宽度（设备像素），供 fit_text 精确填满该列。

        旧实现用固定 COL_WIDTHS[2]=320 截断，但标题列已 weight=1 动态扩展，
        窗口更宽时该列超出 320 却仍按 320 截断，右侧留白。这里从 VirtualList
        内部（已按 DPI 缩放）的画布宽度与列宽求出真实可用宽度，标题即填满整列。
        """
        if getattr(self, "_list", None) is None:
            return 320
        total_w = self._list._canvas_w() or 0
        scaled = self._list.column_widths
        if not scaled:
            return 320
        fixed = sum(scaled[i] for i in range(len(scaled)) if i != 2)
        avail = total_w - fixed - 14
        return max(avail, 120)

    # ---------- 操作 ----------
    def _add_one(self, item):
        if item.get("type") == "bangumi":
            self._add_bangumi(item)
            return
        bvid = item.get("bvid")
        if bvid:
            # 先判断是否多分P / 合集：是则在搜索窗口之上弹「选集窗口」选分P，
            # 否则走单视频流程
            self.status_label.configure(text=tr("正在检查分P…"), text_color="#42a5f5")

            def worker():
                episodes = None
                try:
                    info = self.api.get_video_pages(bvid)
                    if info:
                        pages = info.get("pages") or []
                        coll = info.get("collection") or []
                        if len(pages) > 1:
                            episodes = pages
                        elif coll:
                            episodes = coll
                except Exception:
                    episodes = None

                def handoff():
                    if episodes:
                        # 在搜索窗口之上弹选集窗口（保留搜索窗口），确认后再关闭搜索窗口
                        EpisodeSelectDialog(self, episodes, on_confirm=self._on_episodes_confirmed,
                                            title=tr("选择分集"))
                    else:
                        self._add_single_video(item)

                self.after(0, handoff)

            threading.Thread(target=worker, daemon=True).start()
            return
        self._add_single_video(item)

    def _add_single_video(self, item):
        """单视频（非多分P）：补全元数据后关闭搜索框（释放 grab），
        再交由主窗口弹「下载选项」对话框确认入队。"""
        self.status_label.configure(text=tr("正在补全信息…"), text_color="#42a5f5")

        def worker():
            try:
                self.api.enrich_videos([item])
            except Exception:
                pass

            def handoff():
                self.close_dialog()
                if callable(self.on_add):
                    self.on_add([item])

            self.after(0, handoff)

        threading.Thread(target=worker, daemon=True).start()

    def _add_bangumi(self, item):
        """番剧：先解析整季分集，再在搜索窗口之上弹「选集窗口」列出分集勾选下载
        （不再直接批量入队，也不对分集调用 enrich_videos——分集自带 bvid/cid/
        标题/时长，enrich 会把分集当普通视频补全，可能把标题/统计错乱，正是此前
        触发 BUG 的根因）。"""
        sid = item.get("season_id")
        if not sid:
            # 兜底：从番剧 url 里提取 ss 号（如 https://www.bilibili.com/bangumi/play/ss12345）
            import re
            m = re.search(r"ss(\d+)", item.get("url", ""))
            sid = int(m.group(1)) if m else None
        if not sid:
            from tkinter import messagebox
            messagebox.showwarning(tr("提示"), tr("无法获取该番剧的 season_id，无法解析分集"))
            return
        self.status_label.configure(text=tr("正在解析并补全番剧分集…"), text_color="#42a5f5")

        def worker():
            try:
                episodes = self.api.get_season_episodes(ssid=sid)
            except Exception as e:
                self.after(0, lambda err=str(e): self.status_label.configure(
                    text=tr("番剧解析失败：{}").format(err), text_color="#ef5350"))
                return
            if not episodes:
                self.after(0, lambda: self.status_label.configure(
                    text=tr("该番剧没有可下载的分集"), text_color="#ef5350"))
                return

            def handoff():
                # 在搜索窗口之上弹选集窗口（保留搜索窗口），确认后再关闭搜索窗口
                EpisodeSelectDialog(self, episodes, on_confirm=self._on_episodes_confirmed,
                                    title=tr("选择番剧分集"))

            self.after(0, handoff)

        threading.Thread(target=worker, daemon=True).start()

    def _on_episodes_confirmed(self, selected):
        """选集窗口确认回调：把勾选的分集交回主流程（统一走下载选项 → 入队），
        随后关闭搜索窗口。"""
        if selected and callable(self.on_add):
            self.on_add(selected)
        self.close_dialog()

    def _open_space(self, item):
        mid = item.get("mid")
        self.close_dialog()
        if callable(self.on_open_space) and mid:
            self.on_open_space(mid)
        elif not callable(self.on_open_space):
            from tkinter import messagebox
            messagebox.showwarning(tr("提示"), tr("无法通过搜索打开 UP 主空间"))

    def add_all_videos(self):
        items = self._list._items
        videos = [it for it in items if it.get("type") == "video"]
        if not videos:
            return
        # 补全元数据后关闭搜索框（释放 grab），再交由主窗口弹「下载选项」确认入队
        self.status_label.configure(text=tr("正在补全信息…"), text_color="#42a5f5")

        def worker():
            try:
                self.api.enrich_videos(videos)
            except Exception:
                pass

            def handoff():
                self.close_dialog()
                if callable(self.on_add):
                    self.on_add(videos)

            self.after(0, handoff)

        threading.Thread(target=worker, daemon=True).start()

    # ---------- 图片加载 ----------
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
            img_raw.thumbnail((120, 72))
            ctk_img = ctk.CTkImage(img_raw, img_raw, size=(120, 72))
            self.image_cache[url] = ctk_img
            return ctk_img
        except Exception:
            return None
