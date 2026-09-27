# ui/live_center.py
"""直播中心：浏览较火直播 / 按分区发现 / 关键词搜索直播间，点击即开始录制。

复用：
- BiliAPI.get_live_hot / get_live_areas / search_live_rooms（已含 buvid 风控与 WBI 签名）
- 现有 LiveRecordDialog 取流与录制能力（清晰度 / 自动重连 / 通知），做到「点击即录」
- 封面异步加载沿用 sidebar 的 PIL + CTkImage 范式，避免 image=None 不刷新的坑
"""
import threading

import requests
from io import BytesIO
from PIL import Image

import customtkinter as ctk
from tkinter import messagebox

from utils.i18n import tr, register
from ui.base_dialog import BaseDialog
from ui.dialogs import LiveRecordDialog


class LiveCenterDialog(BaseDialog):
    _INSTANCE = None

    def __init__(self, master, config, logger=None, api=None):
        existing = LiveCenterDialog._singleton(master)
        if existing is not None:
            return
        super().__init__(master)
        self.config = config
        self.logger = logger
        self.api = api
        self.rooms = []
        self.page = 1
        self.area_id = 0
        self.mode = "hot"          # hot | search
        self.keyword = ""
        self._token = 0            # 每次整页刷新自增，作废过期的封面/列表加载
        self._area_options = [(tr("全站热门"), 0)]
        self._pending_covers = []
        self._suppress_area_cb = False
        self.title(tr("直播中心"))
        self._show(master, "980x680", resizable=(True, True))
        self.build()
        LiveCenterDialog._INSTANCE = self
        # 初始加载热门
        self._load()

    def build(self):
        # ---- 顶部控制栏 ----
        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(top, text=tr("分区") + ":").pack(side="left", padx=(0, 4))
        self.area_var = ctk.StringVar(value=tr("全站热门"))
        self.area_menu = ctk.CTkOptionMenu(
            top, variable=self.area_var, width=160, command=self._on_area_select)
        self.area_menu.pack(side="left", padx=(0, 10))

        self.kw_var = ctk.StringVar()
        kw = ctk.CTkEntry(top, textvariable=self.kw_var, width=200,
                          placeholder_text=tr("搜索直播"))
        kw.pack(side="left", padx=(0, 6))
        register(kw, "搜索直播", attr="placeholder_text")
        ctk.CTkButton(top, text=tr("搜索直播"), width=80,
                      command=self._on_search).pack(side="left", padx=(0, 6))
        ctk.CTkButton(top, text=tr("刷新"), width=70,
                      command=self._on_refresh).pack(side="left")

        self.more_btn = ctk.CTkButton(top, text=tr("加载更多"), width=90,
                                      command=self._on_more)
        self.more_btn.pack(side="right")

        # ---- 状态栏 ----
        self.status = ctk.CTkLabel(self, text=tr("正在加载直播列表..."),
                                   text_color="#42a5f5")
        self.status.pack(anchor="w", padx=12, pady=(0, 4))

        # ---- 网格滚动区 ----
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        cols = 3
        self.scroll.grid_columnconfigure(tuple(range(cols)), weight=1)

        # 异步拉取分区下拉
        threading.Thread(target=self._load_areas, daemon=True).start()

    # ---------- 数据加载 ----------
    def _load_areas(self):
        try:
            areas = self.api.get_live_areas() if self.api else []
        except Exception:
            areas = []
        options = [(tr("全站热门"), 0)]
        for p in areas:
            for s in (p.get("list") or []):
                name = s.get("name", "")
                pid = s.get("id")
                if name and pid is not None:
                    options.append((f"{p.get('name', '')}/{name}", pid))
        self._area_options = options
        labels = [o[0] for o in options]
        def _apply():
            self.area_menu.configure(values=labels)
            # 抑制 programmatic 设置引发的回调（避免重复拉取）
            self._suppress_area_cb = True
            self.area_var.set(labels[0])
            self._suppress_area_cb = False
        self.after(0, _apply)

    def _on_area_select(self, label):
        # 程序化设置 area_var（_load_areas 完成时）会触发本回调，需忽略以免重复加载
        if getattr(self, "_suppress_area_cb", False):
            return
        opt = next((o for o in getattr(self, "_area_options", []) if o[0] == label), None)
        if opt is None:
            return
        self.area_id = opt[1]
        self.mode = "hot"
        self.page = 1
        self._load()

    def _on_search(self):
        kw = self.kw_var.get().strip()
        if not kw:
            return
        self.keyword = kw
        self.mode = "search"
        self.page = 1
        self._load()

    def _on_refresh(self):
        self.page = 1
        self._load()

    def _on_more(self):
        self.page += 1
        self._load(append=True)

    def _load(self, append=False):
        if not append:
            self._token += 1
            self.rooms = []
            for w in self.scroll.winfo_children():
                w.destroy()
            self.status.configure(text=tr("正在加载直播列表..."))
        token = self._token
        mode, page, area_id, keyword = self.mode, self.page, self.area_id, self.keyword
        threading.Thread(
            target=self._fetch_thread, args=(token, mode, page, area_id, keyword, append),
            daemon=True).start()

    def _fetch_thread(self, token, mode, page, area_id, keyword, append):
        rooms = []
        try:
            if mode == "search":
                rooms = self.api.search_live_rooms(keyword, page=page) if self.api else []
            else:
                rooms = self.api.get_live_hot(page=page, area_id=area_id) if self.api else []
        except Exception as e:
            if token == self._token:
                msg = str(e)
                self.after(0, lambda m=msg: self.status.configure(
                    text=tr("加载直播列表失败：{}").format(m), text_color="#ef5350"))
            return
        if token != self._token:
            return
        self.after(0, self._render, rooms, append)

    def _render(self, rooms, append):
        if not append:
            for w in self.scroll.winfo_children():
                w.destroy()
            self.rooms = []
        if not rooms and not self.rooms:
            self.status.configure(text=tr("直播列表为空"), text_color="#ffca28")
            return
        cols = 3
        start = len(self.rooms)
        self.rooms.extend(rooms)
        for idx, room in enumerate(rooms):
            r = (start + idx) // cols
            c = (start + idx) % cols
            self._make_card(room, r, c)
        # 启动本批封面异步加载
        batch = self._pending_covers
        self._pending_covers = []
        if batch:
            threading.Thread(target=self._load_covers, args=(self._token, batch),
                             daemon=True).start()
        self.status.configure(
            text=f"{tr('直播中心')} · {len(self.rooms)}", text_color="#42a5f5")

    def _make_card(self, room, r, c):
        card = ctk.CTkFrame(self.scroll, corner_radius=8)
        card.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")

        cover = ctk.CTkLabel(card, text="", width=280, height=158)
        cover.pack(fill="x")
        cover.configure(cursor="hand2")

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(fill="x", padx=8, pady=(4, 2))
        title = ctk.CTkLabel(info, text=room.get("title", "") or tr("未开播"),
                             font=("", 12, "bold"), wraplength=260, justify="left", anchor="w")
        title.pack(anchor="w")
        sub = ctk.CTkLabel(info, text=room.get("uname", ""), font=("", 10),
                           text_color=("#666666", "#aaaaaa"))
        sub.pack(anchor="w")
        meta = ctk.CTkLabel(info, text=self._meta_text(room), font=("", 10),
                            text_color=("#666666", "#aaaaaa"))
        meta.pack(anchor="w")

        btn = ctk.CTkButton(card, text=tr("录制"), height=30,
                            command=lambda rid=room.get("roomid"): self._record(rid, auto_start=True))
        btn.pack(fill="x", padx=8, pady=(4, 8))

        # 点击封面 / 标题：打开录制备用（不自动开始，便于先选清晰度）
        rid = room.get("roomid")
        cover.bind("<Button-1>", lambda e, rid=rid: self._record(rid, auto_start=False))
        title.bind("<Button-1>", lambda e, rid=rid: self._record(rid, auto_start=False))
        cover.configure(cursor="hand2")

        if room.get("cover"):
            self._pending_covers.append((cover, room["cover"]))

    def _meta_text(self, room):
        watched = room.get("watched_show") or ""
        area = room.get("area_name") or room.get("parent_name") or ""
        parts = [p for p in (watched, area) if p]
        return " · ".join(parts) if parts else tr("直播中")

    def _load_covers(self, token, batch):
        for label, url in batch:
            if token != self._token:
                return
            try:
                resp = requests.get(
                    url, timeout=10,
                    headers={"Referer": "https://live.bilibili.com/",
                             "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
                img = Image.open(BytesIO(resp.content)).convert("RGB")
                img = img.resize((280, 158), Image.LANCZOS)
                ctk_img = ctk.CTkImage(img, img, size=(280, 158))
                if token == self._token:
                    self.after(0, self._set_cover, label, ctk_img)
            except Exception:
                pass

    def _set_cover(self, label, ctk_img):
        try:
            label.configure(image=ctk_img, text="")
            label.image = ctk_img  # 防止被 GC
        except Exception:
            pass

    # ---------- 录制 ----------
    def _record(self, roomid, auto_start=True):
        if not roomid:
            return
        LiveRecordDialog.open_with_room(
            self.master, self.config, self.logger, self.api, roomid, auto_start=auto_start)
