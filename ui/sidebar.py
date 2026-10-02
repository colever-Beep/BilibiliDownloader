"""可折叠导航栏（qfluentwidgets NavigationInterface 原生实现）。

直接继承 ``NavigationInterface``，因此天然具备：
  - 左上角菜单按钮：点击在「紧凑（48px 纯图标）↔ 展开（220px 含文字）」间平滑切换；
  - 紧凑模式下导航项仅显示图标，并自动弹出 tooltip；
  - 强调色 / 明暗主题由 qfluentwidgets 全局主题驱动，与设置窗口（MSFluentWindow）完全一致；
  - 折叠状态持久化到 config 的 ``sidebar_collapsed``。

结构：
  - 用户卡片（addUserCard）：头像 + 昵称 / 状态，点击触发登录 / 登出；
  - 分组标题（addItemHeader）：我的 / 发现；
  - 导航项（addItem，可点击选中）；
  - 底部分组（BOTTOM）：界面语言（点击弹 RoundMenu）/ 设置 / 关于。

对外契约（与旧 Sidebar 兼容，main_window 无需大改）：
  __init__(master, api, on_nav_click, config=, on_language_change=,
           on_login=, on_about=, on_settings=)
  .refresh()              —— 登录状态 / 语言变化后重建用户卡片
  .setCurrentItem(key)    —— 高亮当前导航项
  .retranslate()          —— 刷新所有可翻译文案
"""
import threading
from io import BytesIO

import requests
from PIL import Image, ImageDraw

from PySide6.QtCore import Qt, QByteArray, QPoint
from PySide6.QtGui import QPixmap, QImage

from qfluentwidgets import (
    NavigationInterface, NavigationItemPosition, FluentIcon, RoundMenu, Action,
)
from qfluentwidgets.components.navigation.navigation_panel import NavigationDisplayMode
from qfluentwidgets.components.navigation.navigation_widget import (
    NavigationItemHeader, NavigationWidget,
)

from utils.i18n import tr, get_language, LANGUAGES
from utils.resources import resource_path


# 导航结构定义（routeKey, 显示名函数, 图标名）
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
    """导航语义名 -> FluentIcon 成员。

    qfluentwidgets 1.11.2 的 FluentIcon 没有 STAR/FIRE/TROPHY 等，缺失项用存在的
    近似成员替代（season->LIBRARY / popular->TAG / ranking->PEOPLE），保证每一项都随
    明暗与选中态自动着色，与设置窗口的 MSFluentWindow 同一套视觉。
    """
    mapping = {
        "folder": "FOLDER", "toview": "CALENDAR", "history": "HISTORY",
        "following": "HEART", "season": "LIBRARY", "popular": "TAG",
        "ranking": "PEOPLE", "search": "SEARCH", "music": "MUSIC",
        "live_center": "VIDEO", "settings": "SETTING", "about": "INFO",
        "language": "LANGUAGE",
    }
    member = mapping.get(name, "TAG")
    return getattr(FluentIcon, member, FluentIcon.TAG)


class NavigationBar(NavigationInterface):
    """Fluent 风格的可折叠导航栏（NavigationInterface 子类）。"""

    def __init__(self, master, api, on_nav_click, config=None, on_language_change=None,
                 on_login=None, on_about=None, on_settings=None):
        super().__init__(master, showMenuButton=True, showReturnButton=False, collapsible=True)

        self.api = api
        self.on_nav_click = on_nav_click
        self.config = config
        self.on_language_change = on_language_change
        self.on_login = on_login
        self.on_about = on_about
        self.on_settings = on_settings

        self._current_route = None
        self._avatar_token = 0
        self._items = {}  # routeKey -> NavigationTreeWidget

        # 展开宽度（面板宽度）；minimumExpandWidth=0 保证始终「停靠」而非浮动浮层。
        # ⚠️ 不调用 setExpandWidth()：它会改写全局类属性 NavigationWidget.EXPAND_WIDTH，
        # 连带破坏设置窗口 MSFluentWindow 的导航项宽度（其依赖默认 322）。
        # 这里只改实例属性：面板 expandWidth=220，各导航项 EXPAND_WIDTH=210（见 _build 之后）。
        self.panel.expandWidth = 220
        self.setMinimumExpandWidth(0)
        self.setAcrylicEnabled(False)

        # 折叠（紧凑）模式：点击导航项不自动收起，避免误关
        self.setUpdateIndicatorPosOnCollapseFinished(False)

        self._build()

        # 导航项宽度按实例设置（210 = 面板 220 - 10），不触碰全局类属性
        for w in self.findChildren(NavigationWidget):
            w.EXPAND_WIDTH = 210

        # 未登录占位头像（根目录 not_logged_in.jpeg，随包走 _MEIPASS）
        self._set_placeholder_avatar()

        # 依据配置决定初始展开 / 折叠
        self._collapsed = bool(config.get("sidebar_collapsed", False)) if config else False
        if not self._collapsed:
            # 窗口已存在（central 已设为中央部件），直接停靠展开，无动画
            self.expand(False)
            # 立即固定宽度，避免首帧从 48 闪到 220（expand 的几何更新需事件循环派发）
            self.setFixedWidth(self.panel.expandWidth)
            # 分组标题立即到位（不依赖高度动画时序，避免启动瞬间标题缺失）
            for h in self.findChildren(NavigationItemHeader):
                h.setCompacted(False)
                h.heightAni.stop()
                h.setFixedHeight(h._targetHeight)

        # 折叠状态持久化
        self.displayModeChanged.connect(self._on_display_mode_changed)

    # ---------- 构建 ----------
    def _build(self):
        # 用户卡片（头像 + 昵称 + 点击登录 / 登出）
        self.user_card = self.addUserCard(
            "user", avatar=None, title=tr("未登录"), subtitle=tr("登录以使用更多功能"),
            onClick=self._on_user_card_click,
            position=NavigationItemPosition.TOP, aboveMenuButton=False,
        )

        # 分组：我的
        self._header_my = self.addItemHeader(tr("我的"))
        for route_key, text_fn, icon in _NAV_GROUPS[0][1]:
            self._add_nav_item(route_key, text_fn, icon)

        # 分隔 + 分组：发现
        self.addSeparator()
        self._header_discover = self.addItemHeader(tr("发现"))
        for route_key, text_fn, icon in _NAV_GROUPS[1][1]:
            self._add_nav_item(route_key, text_fn, icon)

        # 底部：界面语言 / 设置 / 关于
        self.lang_item = self.addItem(
            "language", _nav_fluent_icon("language"), tr("界面语言"),
            onClick=self._open_language_menu, selectable=False,
            position=NavigationItemPosition.BOTTOM, tooltip=tr("界面语言"),
        )
        self.settings_item = self.addItem(
            "settings", _nav_fluent_icon("settings"), tr("设置"),
            onClick=self.on_settings, selectable=False,
            position=NavigationItemPosition.BOTTOM, tooltip=tr("设置"),
        )
        self.about_item = self.addItem(
            "about", _nav_fluent_icon("about"), tr("关于"),
            onClick=self.on_about, selectable=False,
            position=NavigationItemPosition.BOTTOM, tooltip=tr("关于"),
        )

    def _add_nav_item(self, route_key, text_fn, icon):
        item = self.addItem(
            route_key, _nav_fluent_icon(icon), text_fn(),
            onClick=lambda _checked=False, rk=route_key: self._on_item(rk),
            selectable=True, tooltip=text_fn(),
        )
        self._items[route_key] = item

    # ---------- 交互 ----------
    def _on_item(self, route_key):
        self.setCurrentItem(route_key)
        if self.on_nav_click:
            self.on_nav_click(route_key, None)

    def _on_user_card_click(self):
        if self.api.uid:
            # 已登录 -> 登出
            if self.on_nav_click:
                self.on_nav_click("logout", None)
            self.refresh()
        else:
            if self.on_login:
                self.on_login()

    def _open_language_menu(self):
        menu = RoundMenu(tr("界面语言"), self)
        current = get_language()
        for code, display in LANGUAGES.items():
            action = Action(display, triggered=lambda _a=None, c=code: self._on_lang_select(c))
            if code == current:
                action.setCheckable(True)
                action.setChecked(True)
            menu.addAction(action)
        # 在语言项右侧弹出（紧凑模式下也始终可用）
        pos = self.lang_item.mapToGlobal(QPoint(self.lang_item.width(), 0))
        menu.exec(pos)

    def _on_lang_select(self, code):
        if self.on_language_change:
            self.on_language_change(code)

    # ---------- 高亮 ----------
    def setCurrentItem(self, route_key):
        self._current_route = route_key
        # NavigationInterface.setCurrentItem 对不存在的 routeKey 直接忽略，安全
        super().setCurrentItem(route_key)

    # ---------- 登录态刷新 ----------
    def refresh(self):
        """根据登录状态刷新用户卡片（头像 / 昵称 / 状态）。"""
        self._avatar_token += 1
        if not self.api.uid:
            self.user_card.setTitle(tr("未登录"))
            self.user_card.setSubtitle(tr("请登录以使用更多功能"))
            self._set_placeholder_avatar()
        else:
            self.user_card.setTitle(self.api.nickname or tr("已登录"))
            self.user_card.setSubtitle(tr("已登录"))
            self._load_avatar(self.api.avatar, self._avatar_token)

    def _set_placeholder_avatar(self):
        """未登录占位头像：根目录 not_logged_in.jpeg（开发/打包均经 resource_path 解析）。

        AvatarWidget 会自动中心裁剪 + 椭圆裁剪为圆形，故 jpeg 直接传入即可；
        文件缺失时回退到 FluentIcon.PEOPLE 图标占位。
        """
        pix = QPixmap(resource_path("not_logged_in.jpeg"))
        if not pix.isNull():
            self.user_card.setAvatar(pix)
            self._restore_avatar_geometry()
        else:
            self.user_card.setAvatarIcon(FluentIcon.PEOPLE)
            self._restore_avatar_geometry()

    # ---------- 语言刷新 ----------
    def set_language_display(self, lang):
        """语言切换后供外部调用（菜单每次打开都会按当前语言打勾，这里仅做占位兼容）。"""
        self.lang_item.setToolTip(LANGUAGES.get(lang, tr("界面语言")))

    # ---------- 文案刷新 ----------
    def retranslate(self):
        # 用户卡片（已登录态昵称不翻译）
        if not self.api.uid:
            self.user_card.setTitle(tr("未登录"))
            self.user_card.setSubtitle(tr("请登录以使用更多功能"))
        else:
            self.user_card.setSubtitle(tr("已登录"))

        # 分组标题
        self._header_my.setText(tr("我的"))
        self._header_discover.setText(tr("发现"))

        # 导航项
        for route_key, text_fn, _icon in _NAV_GROUPS[0][1] + _NAV_GROUPS[1][1]:
            w = self._items.get(route_key)
            if w is not None:
                w.setText(text_fn())
                w.setToolTip(text_fn())

        # 底部项
        self.lang_item.setText(tr("界面语言"))
        self.lang_item.setToolTip(tr("界面语言"))
        self.settings_item.setText(tr("设置"))
        self.settings_item.setToolTip(tr("设置"))
        self.about_item.setText(tr("关于"))
        self.about_item.setToolTip(tr("关于"))

    # ---------- 折叠持久化 ----------
    def _on_display_mode_changed(self, mode):
        collapsed = mode in (NavigationDisplayMode.COMPACT, NavigationDisplayMode.MINIMAL)
        self._collapsed = collapsed
        if self.config is not None:
            try:
                self.config.set("sidebar_collapsed", bool(collapsed))
            except Exception:
                pass

    # ---------- 头像加载 ----------
    def _load_avatar(self, url, token=None):
        if not url:
            return
        threading.Thread(target=self._fetch_avatar, args=(url, token), daemon=True).start()

    def _fetch_avatar(self, url, token):
        try:
            resp = requests.get(url, timeout=8)
            img = Image.open(BytesIO(resp.content)).convert("RGBA")
            img = img.resize((128, 128), Image.LANCZOS)
            # 圆形遮罩
            mask = Image.new("L", img.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, img.size[0], img.size[1]), fill=255)
            img.putalpha(mask)
            buf = BytesIO()
            img.save(buf, format="PNG")
            if token == self._avatar_token:
                self._apply_avatar(QByteArray(buf.getvalue()))
        except Exception:
            pass

    def _apply_avatar(self, ba):
        if not ba.size():
            return
        pix = QPixmap()
        if pix.loadFromData(ba):
            self.user_card.setAvatar(pix)
            self._restore_avatar_geometry()

    def _restore_avatar_geometry(self):
        """qfluentwidgets 的 NavigationUserCard.setAvatar/setAvatarIcon 会把头像半径
        硬重置为紧凑态（12 -> 24px），在已展开状态下导致头像显示为折叠尺寸。

        这里按当前「展开 / 折叠」态恢复正确半径（32 / 12）与位置（展开垂直居中、
        紧凑左上角），避免再展开后登录头像变成小图。
        """
        card = self.user_card
        radius = 32 if not card.isCompacted else 12
        card.avatar.setRadius(radius)
        if card.isCompacted:
            card.avatar.move(8, 6)
        else:
            card.avatar.move(16, (card.height() - card.avatar.height()) // 2)
        card.update()


# 兼容旧名称：main_window 等仍可 ``from ui.sidebar import Sidebar``
Sidebar = NavigationBar
