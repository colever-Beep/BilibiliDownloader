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
from PySide6.QtCore import QTimer

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

# 主题切换防抖：set_accent / apply_appearance / apply_theme 的「重成本副作用」
# （重建全局 QSS + qfluentwidgets setThemeColor，各约 200ms）集中在 _commit 中，
# 通过 _schedule_commit 在短时间窗口内合并为一次执行。这能消除颜色选择器拖动 /
# 连续快速切换时每次都触发全应用 re-polish 造成的明显卡顿；首次（基线尚未建立）
# 或无 QApplication 实例时仍同步立即提交，避免启动闪默认样式或测试环境丢主题。
_DEBOUNCE_MS = 140
_commit_timer = None
# 已真正提交到 UI 的最近一次状态（内存值可能与之一致也可能超前：连续切换时
# 内存立即更新、UI 延后合并），_commit 据此判断是否需要重建 QSS / 切换 Fluent 主题。
_committed_accent = DEFAULT_ACCENT
_committed_appearance = "dark"


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
    # 也会被拒（只接受全局 QSS 里的类型选择器），因此悬停样式统一放在全局 QSS。
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
        border-radius:8px; padding:6px 10px; color:{palette['fg']};
    }}
    QPushButton {{
        background-color:{palette['panel2']};
        border:1px solid {palette['border']};
        border-radius:8px; padding:7px 14px; color:{palette['fg']};
    }}
    QPushButton:hover {{ background-color:{palette['border']}; }}
    QPushButton:disabled {{ color:{palette['sub']}; background-color:{palette['panel2']}; }}
    QPushButton#accentBtn {{
        background-color:{accent}; border:none; border-radius:8px; color:#ffffff;
    }}
    QPushButton#accentBtn:hover {{ background-color:{accent_hover}; }}
    QPushButton#accentBtn:disabled {{ background-color:{accent}; color:#999999; }}
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
    QFrame#mainToolbar, QFrame#progressCard, QFrame#actionCard,
    QWidget#queueCard {{
        background-color:{palette['panel']};
        border:1px solid {palette['border']};
        border-radius:14px;
    }}
    QWidget#toolbarUrlRow, QFrame#toolbarActionsRow,
    QFrame#parseButtonGroup {{
        background-color:transparent;
        border:none;
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
    # object-name 标记（accentBtn）一次性设好即可，由全局 QSS 的 #accentBtn 规则
    # 驱动其背景/悬停样式，无需在每次切换强调色时重复遍历重设。
    _style_accent(widget, ACCENT)


def _schedule_commit():
    """把主题重成本副作用调度为一个防抖提交（详见模块顶部 _DEBOUNCE_MS 说明）。"""
    global _commit_timer
    from PySide6.QtWidgets import QApplication
    # 首次（基线尚未写入）或无 QApplication 实例时，必须同步立即提交：
    # 否则启动会闪默认样式，或在无 GUI 的测试环境下主题永不生效。
    if (not _QSS_READY) or (QApplication.instance() is None):
        _flush_commit()
        return
    if _commit_timer is None:
        _commit_timer = QTimer()
        _commit_timer.setSingleShot(True)
        _commit_timer.timeout.connect(_flush_commit)
    # 连续调用只重置计时，窗口内仅真正提交一次（颜色选择器拖动场景的关键优化）
    _commit_timer.start(_DEBOUNCE_MS)


def _flush_commit():
    """防抖窗口到点：执行一次真正的主题提交。"""
    global _commit_timer
    _commit_timer = None
    _commit()


def _commit():
    """真正执行主题重成本副作用（全局 QSS 重设 + qfluentwidgets 主题色同步）。

    根据内存当前状态与已提交状态的差异决定是否重建 QSS / 切换 Fluent 主题；
    无差异且基线已建立时走快速路径，仅确保图标主题同步（轻量）。
    """
    global _committed_accent, _committed_appearance, _QSS_READY
    accent_changed = ACCENT != _committed_accent
    appearance_changed = _APPEARANCE != _committed_appearance
    # 快速路径：值与已提交态一致且基线已建立 —— 不重建 QSS、不触发 Fluent 全量
    # 重绘，仅确保图标主题同步（开销极低）。
    if not accent_changed and not appearance_changed and _QSS_READY:
        try:
            from ui.icons import set_fluent_theme
            set_fluent_theme(_APPEARANCE == "dark")
        except Exception:
            pass
        return
    was_ready = _QSS_READY
    _apply_qss()  # 全局 QSS 含强调色，accent / appearance 任一变化都需重建
    _QSS_READY = True
    # 同步给 qfluentwidgets 主题色：使 Fluent 控件（侧边栏导航按钮、设置窗口）的
    # 强调色与 app 强调色一致——否则停留在 Fluent 默认蓝，与整体主题脱节。
    try:
        from qfluentwidgets import setThemeColor
        setThemeColor(QColor(ACCENT))
    except Exception:
        pass
    # 首次建立或明暗变化时才 setTheme（强制 Fluent 控件重新按当前 themeColor 取色）；
    # 仅强调色变化无需 setTheme，避免多余的全量重绘。
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
    _committed_accent = ACCENT
    _committed_appearance = _APPEARANCE


def set_accent(color):
    """设置全局强调色（内存立即生效，UI 在防抖窗口内合并提交一次）。

    颜色会先经 `_norm_color` 校验归一化；非法值（缺 #、坏 hex、None）直接
    拒绝并保留上一有效强调色，避免污染全局 QSS。

    性能：重建全局 QSS + setThemeColor 各约 200ms，单次切换无可避免；但本函数
    把重成本副作用交给 _schedule_commit 防抖合并——颜色选择器拖动 / 连续快速
    切换时只真正提交最后一次，避免每次 re-polish 累积成明显卡顿。颜色支持
    "system"（跟随 Windows 系统强调色）。
    """
    global ACCENT
    color = resolve_accent(color)
    color = _norm_color(color)
    if not color:
        return
    if color != ACCENT:
        ACCENT = color
    # 即便值未变也调度一次（轻量快速路径），确保首次 / 外部漏应用时 UI 已同步。
    _schedule_commit()


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
    """切换明暗模式（内存立即生效，UI 在防抖窗口内合并提交一次）。

    旧版需在切换后手动刷新 VirtualList 行容器背景色；PySide6 下 QSS 全局驱动，
    列表/控件自动跟随，无需任何手动重绘。mode 支持 "system"（跟随 Windows）。

    性能：重成本副作用经 _schedule_commit 防抖合并，连续/快速切换只真正重绘一次。
    """
    global _APPEARANCE
    resolved = resolve_appearance(mode)
    if resolved != _APPEARANCE:
        _APPEARANCE = resolved
    # 即便值未变也调度一次（轻量快速路径），确保首次 / 外部漏应用时 UI 已同步。
    _schedule_commit()


def palette():
    """返回当前调色板（供需要手工绘制颜色的组件取色，如 QueueView delegate）。"""
    return _PALETTES.get(_APPEARANCE, _PALETTES["dark"])


def apply_theme(accent=None, appearance=None):
    """一次性应用强调色 + 明暗模式（内存立即生效，UI 在防抖窗口内合并提交一次）。

    set_accent 与 apply_appearance 各自都会触发一次全应用 re-polish（各约 200ms+）；
    本函数把两者的重成本副作用统一交给 _schedule_commit 防抖合并——多次连续调用
    （如拖动取色器同时切明暗）只在窗口末尾真正提交一次，避免双倍甚至 N 倍卡顿。

    accent / appearance 支持 "system"（跟随 Windows），解析后才参与变更比较，
    因此系统设置变化时重复调用本函数即可自动跟随。

    返回 True 表示内存状态相对上次有变化（供调用方决定是否做轻量重绘，如侧边栏）。
    """
    global ACCENT, _APPEARANCE
    accent = _norm_color(resolve_accent(accent)) or ACCENT
    appearance = resolve_appearance(appearance or _APPEARANCE)

    accent_changed = accent != ACCENT
    appearance_changed = appearance != _APPEARANCE
    if accent_changed:
        ACCENT = accent
    if appearance_changed:
        _APPEARANCE = appearance
    # 防抖合并重成本副作用；首次（_QSS_READY 为 False）会同步立即提交基线主题，
    # 后续连续调用只在窗口末尾提交一次，保护系统主题 10s 轮询与拖动取色器性能。
    _schedule_commit()
    return accent_changed or appearance_changed


def is_dark():
    """当前是否为暗色主题（供 delegate 绘制悬停/进度等叠加层时判断明暗）。"""
    return _APPEARANCE == "dark"
