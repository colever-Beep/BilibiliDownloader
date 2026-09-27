# utils/i18n.py
"""极简 i18n 框架（无第三方依赖）。

设计要点
--------
* 以「简体中文原文」作为翻译键（lookup key）。
  - 简体中文 (zh_CN) 直接返回原文，无需单独字典。
  - 繁体中文 (zh_TW) / English (en) / 日本語 (ja) 由 locales 片段文件提供映射。
* 翻译片段文件命名规则：``utils/locales_*.py``，每个文件导出 ``FRAGMENT`` 字典：
  ``{ "简体中文": {"zh_TW": "...", "en": "...", "ja": "..."}, ... }``
  build() 会自动发现并合并所有片段，无需集中注册。
* 支持带占位符的模板：``tr("已添加 {} 个视频").format(n)``。

用法
----
    from utils.i18n import tr, register, retranslate_all, set_language, get_language, LANGUAGES

    label = ctk.CTkLabel(frame, text=tr("开始下载"))
    register(label, "开始下载")          # 语言切换时自动刷新该控件

    # 带占位符
    tr("已添加 {} 个视频").format(n)
"""
from __future__ import annotations

import glob
import importlib
import os
from weakref import ref

# 支持的语言：code -> 显示名（显示名使用各语言自称）
LANGUAGES = {
    "zh_CN": "简体中文",
    "zh_TW": "繁體中文",
    "en": "English",
    "ja": "日本語",
}

# 默认语言
_DEFAULT_LANG = "zh_CN"

_CURRENT = _DEFAULT_LANG
_LOCALES: dict = {}          # lang -> {zh_key: translation}
_REGISTRY: list = []         # [(weakref, key, attr, fmt_kwargs), ...]
_loaded = False


def _ensure_loaded() -> None:
    global _LOCALES, _loaded
    if _loaded:
        return
    _LOCALES = _build_locales()
    _loaded = True


def _build_locales() -> dict:
    """自动发现并合并所有 utils/locales_*.py 片段。"""
    merged = {lang: {} for lang in LANGUAGES}
    here = os.path.dirname(os.path.abspath(__file__))
    for path in glob.glob(os.path.join(here, "locales_*.py")):
        modname = "utils." + os.path.splitext(os.path.basename(path))[0]
        try:
            mod = importlib.import_module(modname)
        except Exception:
            continue
        frag = getattr(mod, "FRAGMENT", None)
        if not isinstance(frag, dict):
            continue
        for zh, trans in frag.items():
            if not isinstance(trans, dict):
                continue
            for lang, text in trans.items():
                if lang in merged and isinstance(text, str):
                    merged[lang][zh] = text
    return merged


def get_language() -> str:
    return _CURRENT


def set_language(lang: str) -> None:
    """切换当前语言（仅接受 LANGUAGES 中的 code）。"""
    global _CURRENT
    if lang in LANGUAGES:
        _CURRENT = lang


def tr(key, *args, **kwargs) -> str:
    """翻译键（简体中文原文）。

    返回当前语言文本；缺失或为非字符串时回退到简体中文原文。
    支持 ``tr("a {} b").format(x)`` 形式的占位符。
    """
    if not isinstance(key, str):
        return key
    _ensure_loaded()
    if _CURRENT == "zh_CN":
        text = key
    else:
        text = _LOCALES.get(_CURRENT, {}).get(key, key)
    try:
        if kwargs:
            text = text.format(**kwargs)
        elif args:
            text = text.format(*args)
    except (KeyError, IndexError, ValueError):
        pass
    return text


def register(widget, key: str, attr: str = "text", **fmt) -> None:
    """注册一个需要随语言切换刷新的控件。

    widget: 任意支持 ``configure(attr=...)`` 的控件
    key:    简体中文原文（与 tr 的键一致）
    attr:   刷新的属性名，默认 "text"（CTkEntry 可用 "placeholder_text"）
    fmt:    可选 .format 占位参数（静态内容）；动态内容请勿注册
    """
    try:
        _REGISTRY.append((ref(widget), key, attr, fmt))
    except Exception:
        pass


def unregister_widget(widget) -> None:
    """从注册表中移除某控件（控件销毁时调用，避免悬挂引用）。"""
    for item in list(_REGISTRY):
        if item[0]() is widget:
            _REGISTRY.remove(item)


def _apply_text(widget, attr: str, value: str) -> None:
    """把翻译文本写入控件。

    优先 PySide6 的 setText / setPlaceholderText（新 GUI），失败再回退到
    tk/ctk 的 configure（旧控件），保证迁移过渡期两种控件都能刷新。
    """
    if attr == "placeholder_text":
        try:
            widget.setPlaceholderText(value)
            return
        except Exception:
            pass
    try:
        widget.setText(value)
        return
    except Exception:
        pass
    try:
        widget.configure(**{attr: value})
    except Exception:
        pass


def retranslate_all() -> None:
    """刷新所有已注册且仍然存活的控件文本。"""
    for item in list(_REGISTRY):
        wref, key, attr, fmt = item
        w = wref()
        if w is None:
            _REGISTRY.remove(item)
            continue
        _apply_text(w, attr, tr(key, **fmt))
