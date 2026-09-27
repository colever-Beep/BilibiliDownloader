"""主题管理模块（PySide6 版）。

- 强调色（accent）：通过全局 QSS 变量实现，切换时即时重设样式表。
- 明暗模式：dark / light 两套调色板，切换即重设全局 QSS。
- 注册强调色控件（register_accent_widget）：主操作按钮（解析/开始下载）随强调色变。

相比旧版（CustomTkinter + 递归遍历控件树重上色），PySide6 下主题由 QSS 统一驱动，
无需任何「遍历树 / 对象池回收」之类的 hack——这正是迁移的核心收益之一。
"""
import colorsys
import weakref

from PySide6.QtGui import QColor

DEFAULT_ACCENT = "#1f8a4c"

# 预设强调色（色板）
PRESET_ACCENTS = [
    "#1f8a4c",  # 绿（默认）
    "#2f80ed",  # 蓝
    "#9b51e0",  # 紫
    "#eb5757",  # 红
    "#f2994a",  # 橙
    "#219653",  # 翠绿
    "#1abc9c",  # 青
    "#e91e63",  # 粉
]

# 明暗调色板
_PALETTES = {
    "dark": {
        "bg": "#1e1e1e", "panel": "#252526", "panel2": "#2d2d30",
        "fg": "#e6e6e6", "sub": "#9aa0a6", "border": "#3a3a3a",
        "input_bg": "#2d2d30", "scroll": "#4a4a4a",
    },
    "light": {
        "bg": "#f3f3f3", "panel": "#ffffff", "panel2": "#e9e9ec",
        "fg": "#1a1a1a", "sub": "#666666", "border": "#d0d0d0",
        "input_bg": "#ffffff", "scroll": "#b0b0b0",
    },
}

ACCENT = DEFAULT_ACCENT
_APPEARANCE = "dark"
_ACCENT_WIDGETS = weakref.WeakSet()
# 根窗口（保持接口兼容；PySide6 下主题由全局 QSS 驱动，无需遍历树）
_ROOT = None
# 是否已向 QApplication 写入过全局 QSS。模块默认值只存内存，并未真正应用——
# 若首次 apply_theme 时配置恰等于默认值，旧逻辑会因「无变更」提前返回而跳过
# _apply_qss()/setThemeColor，导致启动后强调色/Fluent 主题色全未建立，必须进
# 设置改动一次才显示。此标记确保「基线主题」在进程内至少应用一次。
_QSS_READY = False


def _darken(hex_color, factor=0.85):
    """按比例压暗颜色，用于计算悬停色。"""
    hex_color = (hex_color or "").lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    if len(hex_color) != 6:
        return hex_color
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        l = max(0.0, l * factor)
        r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
        return "#%02x%02x%02x" % (int(r2 * 255), int(g2 * 255), int(b2 * 255))
    except Exception:
        return hex_color


def set_root_window(window):
    """登记根窗口（兼容旧接口，PySide6 下无需遍历控件树）。"""
    global _ROOT
    _ROOT = window


def _norm_color(c):
    """把任意来源的颜色归一化为合法的 #rrggbb；非法则返回 None。

    用于防御：旧配置 / 脏值可能把 accent 存成 "1f8a4c"（缺 #）、
    "abc"（3 位）、或 RGB 元组字符串等。一旦这种非法值被注入全局 QSS 的
    `selection-background-color:{accent}`，整段样式表会解析失败，进而所有控件
    回退默认字体（pointSize=-1）并批量报 "Could not parse stylesheet"。
    因此 set_accent 入口必须先归一化，非法值直接拒绝（保留上一有效值）。
    """
    if not c:
        return None
    c = str(c).strip()
    if not c.startswith("#"):
        # 可能是 3/6 位 hex 漏了 #，先补上再校验
        if len(c) in (3, 6) and all(ch in "0123456789abcdefABCDEF" for ch in c):
            c = "#" + c
        else:
            return None
    col = QColor(c)
    if not col.isValid():
        return None
    return col.name()  # 规范为 #rrggbb


def _base_qss(palette, accent):
    scroll = palette["scroll"]
    # 强调色按钮的悬停色（更深的同色），随强调色实时变化。
    accent_hover = _darken(accent)
    # 注意：QPushButton / QScrollBar 等复合控件在 Windows(windowsvista) 风格下
    # 会拒绝 `background:` 简写属性，必须用 `background-color:`，否则整条规则解析
    # 失败并批量报 "Could not parse stylesheet"。故此处一律用 background-color。
    # 另：widget 局部样式表里的 `:hover` / `QPushButton:hover` 在 windowsvista 下
    # 也会被拒（只接受全局 QSS 里的类型选择器）。因此强调色/幽灵按钮的样式与悬停
    # 全部改由全局 QSS 的 object-name 选择器驱动（见下方 #accentBtn / #ghostBtn）。
    return f"""
    QWidget {{
        background-color:{palette['bg']};
        color:{palette['fg']};
        font-family:"Microsoft YaHei UI","Microsoft YaHei","Segoe UI",sans-serif;
        font-size:13px;
    }}
    QFrame, QWidget#central {{ background-color:{palette['bg']}; }}
    QLabel {{ background-color:transparent; color:{palette['fg']}; }}
    QLineEdit {{
        background-color:{palette['input_bg']};
        border:1px solid {palette['border']};
        border-radius:6px; padding:6px 10px; color:{palette['fg']};
    }}
    QPushButton {{
        background-color:{palette['panel2']};
        border:1px solid {palette['border']};
        border-radius:6px; padding:6px 12px; color:{palette['fg']};
    }}
    QPushButton:hover {{ background-color:{palette['border']}; }}
    QPushButton:disabled {{ color:{palette['sub']}; background-color:{palette['panel2']}; }}
    QPushButton#accentBtn {{
        background-color:{accent}; border:none; border-radius:6px; color:#ffffff;
    }}
    QPushButton#accentBtn:hover {{ background-color:{accent_hover}; }}
    QPushButton#accentBtn:disabled {{ background-color:{accent}; color:#999999; }}
    QPushButton#ghostBtn {{
        background-color:transparent; border:1px solid {palette['border']};
        border-radius:6px; color:{palette['fg']};
    }}
    QPushButton#ghostBtn:hover {{ background-color:{palette['border']}; }}
    QPushButton#cancelBtn {{ background-color:#b02c2c; border:none; border-radius:6px; color:#ffffff; }}
    QPushButton#cancelBtn:hover {{ background-color:#c53a3a; }}
    QPushButton#clearBtn {{ background-color:#6b2a2a; border:none; border-radius:6px; color:#ffffff; }}
    QPushButton#clearBtn:hover {{ background-color:#833434; }}
    QListView {{ background-color:{palette['panel']}; border:none; outline:0; }}
    QScrollBar:vertical {{ background-color:{palette['bg']}; width:10px; }}
    QScrollBar::handle:vertical {{ background-color:{scroll}; border-radius:5px; }}
    QScrollBar::handle:vertical:hover {{ background-color:#6a6a6a; }}
    QScrollBar:horizontal {{ background-color:{palette['bg']}; height:10px; }}
    QScrollBar::handle:horizontal {{ background-color:{scroll}; border-radius:5px; }}
    QComboBox {{
        background-color:{palette['input_bg']};
        border:1px solid {palette['border']};
        border-radius:6px; padding:4px 8px; color:{palette['fg']};
    }}
    QComboBox QAbstractItemView {{
        background-color:{palette['panel']}; color:{palette['fg']};
        selection-background-color:{accent};
    }}
    QMenu {{ background-color:{palette['panel']}; color:{palette['fg']}; border:1px solid {palette['border']}; }}
    QMenu::item:selected {{ background-color:{accent}; }}
    QWidget#navShell {{
        background-color:{palette['panel']};
        border:1px solid {palette['border']};
        border-radius:18px;
    }}
    QScrollArea#navScroll {{
        background:transparent; border:none;
    }}
    QWidget#navContent {{
        background:transparent;
    }}
    QFrame#mainToolbar {{
        background-color:{palette['panel']};
        border:1px solid {palette['border']};
        border-radius:12px;
    }}
    QFrame#navProfile {{
        background-color:{palette['panel2']};
        border:1px solid {palette['border']};
        border-radius:14px;
    }}
    QLabel#navGroupLabel {{ color:{palette['sub']}; font-size:11px; font-weight:600; margin:8px 8px 0; }}
    QFrame#navSep {{
        color:{palette['border']}; margin:4px 8px;
    }}
    QComboBox {{
        border-radius:8px;
    }}
    """


def _apply_qss():
    """把当前调色板 + 强调色应用到全局 QSS。"""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return
        pal = _PALETTES.get(_APPEARANCE, _PALETTES["dark"])
        app.setStyleSheet(_base_qss(pal, ACCENT))
    except Exception:
        pass


def _style_accent(widget, color):
    """给注册的主操作按钮打上 object-name 标记（accentBtn）。

    真正的背景/悬停样式由全局 QSS 的 `QPushButton#accentBtn` 规则驱动，
    既能随强调色实时变化，又跨所有 Qt 风格安全（widget 局部样式表里的
    `:hover` / `QPushButton:hover` 在 Windows(windowsvista) 下会被拒）。
    """
    try:
        widget.setObjectName("accentBtn")
    except Exception:
        pass


def register_accent_widget(widget):
    """注册一个应随强调色变化的控件（通常是主操作按钮）。"""
    _ACCENT_WIDGETS.add(widget)
    _style_accent(widget, ACCENT)


def set_accent(color):
    """设置全局强调色并即时应用到所有相关控件，同时更新全局 QSS。

    颜色会先经 `_norm_color` 校验归一化；非法值（缺 #、坏 hex、None）直接
    拒绝并保留上一有效强调色，避免污染全局 QSS。

    性能注意：_apply_qss + setThemeColor 会触发全应用 re-polish（数百 ms），
    因此颜色与当前值相同时直接跳过，避免重复刷新。颜色支持 "system"
    （跟随 Windows 系统强调色）。
    """
    global ACCENT, _QSS_READY
    color = resolve_accent(color)
    color = _norm_color(color)
    if not color:
        return
    if color == ACCENT:
        return
    ACCENT = color
    _apply_qss()
    _QSS_READY = True
    for w in list(_ACCENT_WIDGETS):
        _style_accent(w, ACCENT)
    # 同步给 qfluentwidgets 主题色：使 Fluent 控件（侧边栏导航按钮、设置窗口）的
    # 强调色与 app 强调色一致——否则停留在 Fluent 默认蓝，与整体主题脱节。
    try:
        from qfluentwidgets import setThemeColor
        setThemeColor(QColor(ACCENT))
    except Exception:
        pass


def get_accent():
    return ACCENT


# --------------------------------------------------------------------------- #
# 跟随系统（Windows 注册表读取：应用明暗模式 + 系统强调色）
# --------------------------------------------------------------------------- #
def _system_appearance():
    """读取 Windows「应用模式」深浅设置；非 Windows / 读取失败返回 None。"""
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            light, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return "light" if int(light) else "dark"
    except Exception:
        return None


def _system_accent():
    """读取 Windows 系统强调色（Explorer\\Accent\\AccentColorMenu，ABGR 布局）。

    失败（非 Windows / 键不存在）返回 None，由调用方回退默认强调色。
    """
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent") as k:
            v, _ = winreg.QueryValueEx(k, "AccentColorMenu")
        v = int(v) & 0xFFFFFF  # 丢弃 Alpha；低字节在前：RR GG BB
        return "#{:02x}{:02x}{:02x}".format(v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF)
    except Exception:
        return None


def resolve_appearance(mode):
    """把存储的明暗模式解析为具体值："system" -> 跟随 Windows 应用模式。"""
    mode = mode or "dark"
    if mode == "system":
        return _system_appearance() or "dark"
    return mode


def resolve_accent(color):
    """把存储的强调色解析为具体 hex："system" -> 跟随 Windows 系统强调色。"""
    color = color or ""
    if color == "system":
        return _system_accent() or DEFAULT_ACCENT
    return color


def apply_appearance(mode):
    """切换明暗模式并重设全局 QSS。

    旧版需在切换后手动刷新 VirtualList 行容器背景色；PySide6 下 QSS 全局驱动，
    列表/控件自动跟随，无需任何手动重绘。mode 支持 "system"（跟随 Windows）。
    """
    global _APPEARANCE, _QSS_READY
    resolved = resolve_appearance(mode)
    if resolved != _APPEARANCE:
        _APPEARANCE = resolved
        _apply_qss()
        _QSS_READY = True
    # 即使应用主题值未变，也要修正启动时可能尚未同步的 Fluent 主题。
    try:
        from ui.icons import set_fluent_theme
        set_fluent_theme(_APPEARANCE == "dark")
    except Exception:
        pass


def palette():
    """返回当前调色板（供需要手工绘制颜色的组件取色，如 QueueView delegate）。"""
    return _PALETTES.get(_APPEARANCE, _PALETTES["dark"])


def apply_theme(accent=None, appearance=None):
    """一次性应用强调色 + 明暗模式（只做一次全局 QSS 重设）。

    set_accent 与 apply_appearance 各自都会触发一次全应用 re-polish
    （各约 200ms+）；当两者需要同时更新（如启动、设置变更回调）时，
    使用本函数合并为一次，避免双倍卡顿。

    accent / appearance 支持 "system"（跟随 Windows），解析后才参与变更比较，
    因此系统设置变化时重复调用本函数即可自动跟随。
    """
    global ACCENT, _APPEARANCE, _QSS_READY
    accent = _norm_color(resolve_accent(accent)) or ACCENT
    appearance = resolve_appearance(appearance or _APPEARANCE)

    accent_changed = accent != ACCENT
    appearance_changed = appearance != _APPEARANCE
    # 基线主题尚未写入（进程首次）：即便配置恰等于模块默认值、看似「无变更」，
    # 也必须真正跑一次 _apply_qss()/setThemeColor，否则启动后强调色/Fluent 主题色
    # 全未建立，需进设置改动一次才显示。已建立过且值未变则跳过，保护 10s 轮询性能。
    if not accent_changed and not appearance_changed and _QSS_READY:
        try:
            from ui.icons import set_fluent_theme
            set_fluent_theme(_APPEARANCE == "dark")
        except Exception:
            pass
        return False

    was_ready = _QSS_READY
    ACCENT = accent
    _APPEARANCE = appearance
    _apply_qss()  # 合并为一次全局重设
    _QSS_READY = True
    for w in list(_ACCENT_WIDGETS):
        _style_accent(w, ACCENT)
    # 先 setThemeColor 把主题色设对（qconfig.themeColor 实时生效，全局 QSS 的
    # #accentBtn / selection 等立即变），再在「首次建立或明暗变化」时 setTheme
    # 强制 Fluent 控件（侧边栏 NavigationInterface 等）重新按当前 themeColor 取色。
    # 顺序要点：必须先把 themeColor 设绿，再 setTheme 重新初始化，否则 setTheme
    # 那一刻 themeColor 仍是默认蓝，侧边栏 indicator 会被缓存成蓝、之后不再回退，
    # 表现即「启动强调色停在默认蓝，进设置（无条件 setTheme）才正常」。
    try:
        from qfluentwidgets import setThemeColor
        setThemeColor(QColor(ACCENT))
    except Exception:
        pass
    if not was_ready or appearance_changed:
        try:
            from qfluentwidgets import setTheme, Theme
            setTheme(Theme.DARK if _APPEARANCE == "dark" else Theme.LIGHT)
        except Exception:
            pass
    try:
        from ui.icons import set_fluent_theme
        set_fluent_theme(_APPEARANCE == "dark")
    except Exception:
        pass
    return True


def is_dark():
    """当前是否为暗色主题（供 delegate 绘制悬停/进度等叠加层时判断明暗）。"""
    return _APPEARANCE == "dark"
