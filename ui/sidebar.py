"""导航栏（PySide6 版，参照 bili23 导航栏风格重构）。

结构（自上而下）：
  1. 用户区：头像 / 昵称 / 登录·登出（未登录时）
  2. 导航区（可滚动）：分组「我的」「发现」，每项 = 图标 + 文字，
     选中态有左侧强调色指示条 + 强调色文字/图标，hover 有底色高亮。
     每个导航项带 routeKey，通过 setCurrentItem(key) 反映当前选中。
  3. 底部：界面语言切换 + 设置 + 关于。

导航项完全自绘（paintEvent 读取 ui.theme 的调色板/强调色），因此：
  - 不依赖任何外部图标资源；
  - 跨 Qt 风格安全（不写 widget 局部 :hover 样式表）；
  - 随明暗模式 / 强调色切换自动重绘。

对外契约（与旧 Sidebar 兼容，main_window 无需大改）：
  __init__(master, api, on_nav_click, config=, on_language_change=,
           on_login=, on_about=, on_settings=)
  .refresh()              —— 登录状态/语言变化后重建
  .lang_combo             —— QComboBox 属性，外部可直接 setCurrentText
  .setCurrentItem(key)    —— 高亮当前导航项
"""
import threading
from io import BytesIO

import requests
from PIL import Image, ImageDraw

from PySide6.QtCore import Qt, QByteArray, Signal, QRect
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QScrollArea, QComboBox,
    QFrame, QSizePolicy,
)

from utils.i18n import tr, get_language, LANGUAGES
from ui.theme import palette, get_accent
from ui.icons import draw_nav_icon, FluentIcon

# 侧边栏导航项改用 qfluentwidgets 的 NavigationPushButton（Fluent 风格），
# 与设置窗口的 MSFluentWindow 同一套视觉语言（选中竖条/圆角背景/hover 全由库驱动）。
from qfluentwidgets import NavigationPushButton


# 导航结构定义（routeKey, 显示名, 图标名）
_NAV_GROUPS = [
    (lambda: tr("我的"), [
        ("folder", lambda: tr("我的收藏夹"), "folder"),
        ("toview", lambda: tr("稍后再看"), "toview"),
        ("history", lambda: tr("历史记录"), "history"),
        ("following", lambda: tr("我的关注"), "following"),
        ("season", lambda: tr("我的追番"), "season"),
    ]),
    (lambda: tr("发现"), [
        ("popular", lambda: tr("每周必看"), "popular"),
        ("ranking", lambda: tr("排行榜"), "ranking"),
        ("search", lambda: tr("搜索 B站"), "search"),
        ("music", lambda: tr("bilibili音乐"), "music"),
        ("live_center", lambda: tr("直播中心"), "live_center"),
    ]),
]


def _nav_fluent_icon(name):
    """侧边栏语义名 -> FluentIcon 成员。

    qfluentwidgets 1.11.2 的 FluentIcon 没有 STAR/FIRE/TROPHY 等，缺失项用存在的
    近似成员替代（season->LIBRARY / popular->TAG / ranking->PEOPLE），保证每一项都用
    FluentIconBase 以随明暗与选中态自动着色，与设置窗口的 MSFluentWindow 同一套视觉。
    """
    mapping = {
        "folder": "FOLDER", "toview": "CALENDAR", "history": "HISTORY",
        "following": "HEART", "season": "LIBRARY", "popular": "TAG",
        "ranking": "PEOPLE", "search": "SEARCH", "music": "MUSIC",
        "live_center": "VIDEO", "settings": "SETTING", "about": "INFO",
    }
    member = mapping.get(name, "TAG")
    return getattr(FluentIcon, member, FluentIcon.TAG)


class NavItem(NavigationPushButton):
    """单个导航项：基于 qfluentwidgets 的 NavigationPushButton（Fluent 风格）。

    选中态（左侧强调色竖条 + 圆角背景）、hover 底色、明暗与强调色全部由
    qfluentwidgets 主题驱动，与设置窗口的 MSFluentWindow 导航项完全一致。
    routeKey 用于外部高亮（setCurrentItem）。
    """

    def __init__(self, route_key, text, icon_name, selectable=True, parent=None):
        super().__init__(_nav_fluent_icon(icon_name), text,
                         isSelectable=selectable, parent=parent)
        self._route = route_key
        self._selectable = selectable
        self._selected = False
        # ⚠️ 关键：qfluentwidgets 的 NavigationWidget 默认 isCompacted=True
        #    （只画图标、固定 40x36），且其 paintEvent 在 compacted 时直接 return，
        #    「文字」整段不执行。平时是 NavigationInterface 内部帮它 setCompacted(False)，
        #    我们独立使用没人管，所以必须手动展开，否则导航项就退化成图 1 那种小方块。
        self.setCompacted(False)
        # setCompacted 会施加 setFixedSize(EXPAND_WIDTH=312, 36)——312 是 320px 宽标准
        # Fluent 导航的宽度，对 220px 侧边栏太宽。这里解除宽度限制交给布局拉伸，
        # 只固定行高（图标绘制在 y=10 处，40 高时视觉居中）。
        self.setMinimumWidth(0)
        self.setMaximumWidth(16777215)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(40)

    def route_key(self):
        return self._route

    def is_selectable(self):
        return self._selectable

    def set_selected(self, v):
        self._selected = bool(v) and self._selectable
        self.setSelected(self._selected)

    def set_text(self, t):
        self.setText(t)


class NavigationBar(QWidget):
    def __init__(self, master, api, on_nav_click, config=None, on_language_change=None,
                 on_login=None, on_about=None, on_settings=None):
        super().__init__(master)
        self.api = api
        self.on_nav_click = on_nav_click
        self.config = config
        self.on_language_change = on_language_change
        self.on_login = on_login
        self.on_about = on_about
        self.on_settings = on_settings
        self.setObjectName("navShell")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(220)
        self._avatar_token = 0
        self._current_route = None
        self._items = {}          # routeKey -> NavItem
        self._build()

    # ---------- 构建 ----------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 10, 8, 10)
        root.setSpacing(6)

        # 用户区
        self._build_profile(root)

        # 导航滚动区
        self.scroll = QScrollArea()
        self.scroll.setObjectName("navScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav = QWidget()
        self.nav.setObjectName("navContent")
        self.nav_lay = QVBoxLayout(self.nav)
        self.nav_lay.setContentsMargins(8, 0, 8, 0)
        self.nav_lay.setSpacing(3)
        self.scroll.setWidget(self.nav)
        root.addWidget(self.scroll, 1)

        # 底部：语言 + 设置 + 关于
        self._build_footer(root)

        self.refresh()

    def _build_profile(self, root):
        user = QFrame()
        user.setObjectName("navProfile")
        ul = QVBoxLayout(user)
        ul.setContentsMargins(0, 0, 0, 0)
        ul.setSpacing(6)
        self.avatar = QLabel()
        self.avatar.setFixedSize(56, 56)
        self.avatar.setAlignment(Qt.AlignCenter)
        self._set_avatar_placeholder()
        ul.addWidget(self.avatar, alignment=Qt.AlignCenter)
        self.user_label = QLabel(tr("未登录"))
        self.user_label.setAlignment(Qt.AlignCenter)
        self.user_label.setWordWrap(True)
        self.user_label.setStyleSheet("font-weight:600; font-size:12px;")
        ul.addWidget(self.user_label)
        self.login_btn = QPushButton(tr("登录"))
        self.login_btn.setObjectName("accentBtn")
        self.login_btn.setFixedHeight(30)
        self.login_btn.clicked.connect(self.do_login)
        ul.addWidget(self.login_btn)
        root.addWidget(user)

    def _build_footer(self, root):
        bottom = QFrame()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(4)

        self.lang_label = QLabel(tr("界面语言"))
        bl.addWidget(self.lang_label)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(list(LANGUAGES.values()))
        self.lang_combo.setCurrentText(LANGUAGES.get(get_language(), "简体中文"))
        self.lang_combo.currentTextChanged.connect(self._on_lang_select)
        bl.addWidget(self.lang_combo)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("navSep")
        bl.addWidget(sep)

        # 设置 / 关于 作为底部动作项（不可选中高亮，仅触发回调）
        self.settings_item = self._action_item("settings", tr("设置"), self._on_settings)
        bl.addWidget(self.settings_item)
        self.about_item = self._action_item("about", tr("关于"), self._on_about)
        bl.addWidget(self.about_item)

        root.addWidget(bottom)

    def _action_item(self, icon, text, slot):
        item = NavItem("__action_" + icon, text, icon, selectable=False)
        item.clicked.connect(lambda _checked=False: slot())
        return item

    # ---------- 导航项 ----------
    def _add_group(self, title_text, divider=False):
        """分组标题；divider=True 时先画一条分隔线（ClassIsland 风格的分组分隔）。"""
        if divider:
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setObjectName("navSep")
            self.nav_lay.addWidget(sep)
        label = QLabel(title_text)
        label.setObjectName("navGroupLabel")
        label.setContentsMargins(12, 8, 0, 2)
        self.nav_lay.addWidget(label)

    def refresh(self):
        """根据登录状态重建导航项与用户区。"""
        # 清空旧的导航项
        for i in reversed(range(self.nav_lay.count())):
            w = self.nav_lay.itemAt(i).widget()
            if w:
                w.deleteLater()
        self._items.clear()
        self._avatar_token += 1

        if not self.api.uid:
            self.user_label.setText(tr("未登录"))
            self.login_btn.setText(tr("登录"))
            self._safe_connect(self.login_btn, self.do_login)
            self._set_avatar_placeholder()
        else:
            self.user_label.setText(self.api.nickname or tr("已登录"))
            self.login_btn.setText(tr("登出"))
            self._safe_connect(self.login_btn, self.do_logout)
            self._load_avatar(self.api.avatar, self._avatar_token)

        for gi, (title_fn, items) in enumerate(_NAV_GROUPS):
            self._add_group(title_fn(), divider=gi > 0)
            for route_key, text_fn, icon in items:
                item = NavItem(route_key, text_fn(), icon, selectable=True)
                item.clicked.connect(lambda _checked=False, rk=route_key: self._on_item_clicked(rk))
                self._items[route_key] = item
                self.nav_lay.addWidget(item)

        # 恢复选中态
        if self._current_route in self._items:
            self._items[self._current_route].set_selected(True)

        self.nav_lay.addStretch(1)

    def retranslate(self):
        """语言切换时刷新 footer / 用户区中一次性创建的文案。

        refresh() 仅重建导航区与用户区，footer（界面语言标签、设置、关于）只在
        _build_footer() 创建一次，不会被 refresh 触及，故这里单独刷新它们。
        """
        self.lang_label.setText(tr("界面语言"))
        # 用户区：未登录态文案（已登录态昵称不翻译）
        if not self.api.uid:
            self.user_label.setText(tr("未登录"))
            self.login_btn.setText(tr("登录"))
        else:
            self.login_btn.setText(tr("登出"))
        self.settings_item.set_text(tr("设置"))
        self.about_item.set_text(tr("关于"))

    def _on_item_clicked(self, route_key):
        item = self._items.get(route_key)
        if item is None or not item.is_selectable():
            return
        self.setCurrentItem(route_key)
        self.on_nav_click(route_key, None)

    def setCurrentItem(self, route_key):
        if route_key not in self._items:
            return
        self._current_route = route_key
        for k, it in self._items.items():
            it.set_selected(k == route_key)

    # ---------- 头像 ----------
    def _set_avatar_placeholder(self):
        self.avatar.clear()
        self.avatar.setText("👤")
        self.avatar.setStyleSheet("font-size:26px; border-radius:28px;")

    def _load_avatar(self, url, token=None):
        if not url:
            self._set_avatar_placeholder()
            return
        threading.Thread(target=self._fetch_avatar, args=(url, token), daemon=True).start()

    def _fetch_avatar(self, url, token):
        try:
            resp = requests.get(url, timeout=8)
            img = Image.open(BytesIO(resp.content)).convert("RGBA")
            img = img.resize((112, 112), Image.LANCZOS)
            mask = Image.new("L", img.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, img.size[0], img.size[1]), fill=255)
            img.putalpha(mask)
            buf = BytesIO()
            img.save(buf, format="PNG")
            if token == self._avatar_token:
                self._apply_avatar(QByteArray(buf.getvalue()))
        except Exception:
            if token == self._avatar_token:
                self._apply_avatar(QByteArray())

    def _apply_avatar(self, ba):
        if not ba.size():
            self._set_avatar_placeholder()
            return
        pm = QPixmap()
        if pm.loadFromData(ba):
            self.avatar.setPixmap(pm.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.avatar.setStyleSheet("border-radius:28px;")

    # ---------- 登录 / 登出 / 设置 / 关于 ----------
    def do_login(self):
        if self.api.uid:
            self.do_logout()
            return
        if self.on_login:
            self.on_login()

    def do_logout(self):
        self.on_nav_click("logout", None)
        self.refresh()

    def _on_settings(self):
        if self.on_settings:
            self.on_settings()

    def _on_about(self):
        if self.on_about:
            self.on_about()

    def _on_lang_select(self, display_name):
        code = {v: k for k, v in LANGUAGES.items()}.get(display_name)
        if code is None:
            return
        if self.on_language_change:
            self.on_language_change(code)

    @staticmethod
    def _safe_connect(btn, slot):
        try:
            btn.clicked.disconnect()
        except Exception:
            pass
        btn.clicked.connect(slot)


# 兼容旧名称：main_window 等仍可 ``from ui.sidebar import Sidebar``
Sidebar = NavigationBar
