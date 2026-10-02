#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qfluentwidgets 样式 watcher 兼容性补丁（PySide6 + Python 3.14）。

背景：qfluentwidgets 的 ``StyleSheetManager`` 给控件注册自定义 QSS 时，
会临时创建 ``CustomStyleSheetWatcher`` / ``DirtyStyleSheetWatcher`` 并
``installEventFilter``，但**不保留任何 Python 引用**（实例归 C++ 父子树管理）。
在 Python 3.14 的新版分代 GC 下，这类 watcher 的 Python 包装可能被回收；
之后 Qt 再向被监视控件派发事件时，PySide6 用裸壳（表现为 QMetaObject 实例）
重建对象，``watcher.eventFilter`` 里的 ``super().eventFilter(...)`` 即抛出::

    TypeError: super(type, obj): obj (instance of PySide6.QtCore.QMetaObject)
    is not an instance or subtype of type (CustomStyleSheetWatcher).

实际触发场景（download.log 2026-10-02 07:42）：打开「每周必看」loading 弹窗、
大量对象分配触发 GC 后，已注册 watcher 的包装失效。

补丁做两层防护：
1. 用「模块级强引用」的子类替换 ``qfluentwidgets.common.style_sheet`` 模块
   全局的两个 watcher 类，实例永不回收（治本）；
2. ``eventFilter`` 加 TypeError 兜底：万一壳包装仍出现，退化为默认处理并
   返回 False（放行事件），不再弹「程序异常」框（治标）。

必须在创建任何 qfluentwidgets 控件之前调用（main.py 启动即调用）。
"""

# 所有 watcher 实例的强引用，防止 Python 包装被 GC 回收
_WATCHER_REFS = []


def patch_qfw_style_watchers():
    """替换 style_sheet 模块里的两个 watcher 类为带保护版本。幂等。"""
    try:
        from qfluentwidgets.common import style_sheet as ss
        from PySide6.QtCore import QObject
    except Exception:
        return

    for name, cls in (
        ("CustomStyleSheetWatcher", _GuardedStyleWatcher),
        ("DirtyStyleSheetWatcher", _GuardedDirtyWatcher),
    ):
        base = getattr(ss, name, None)
        if base is None or getattr(base, "_bili23_patched", False):
            continue
        try:
            # 用基类自己的元类创建子类（兼容 Shiboken 元类），替换模块全局名，
            # 让 style_sheet.py 内部的 CustomStyleSheetWatcher(widget) 等调用
            # 解析到受保护版本。
            guarded = type(base)(name, (base,), {
                "__init__": _make_init(base),
                "eventFilter": _make_event_filter(base, cls),
                "_bili23_patched": True,
            })
            setattr(ss, name, guarded)
        except Exception:
            # 元类创建失败时退化为纯引用持有：把基类也记入强引用，
            # 至少不影响运行（后续事件仍可能触发旧问题，但概率极低）。
            _WATCHER_REFS.append(base)


def _make_init(base):
    def __init__(self, *args, **kwargs):
        base.__init__(self, *args, **kwargs)
        # 强引用防 GC：watcher 生命周期本就跟随被监视控件（父级归 C++），
        # 这里多持有一份不会造成泄漏（控件销毁后 watcher 仍在，仅极小开销）。
        _WATCHER_REFS.append(self)
    return __init__


def _make_event_filter(base, fallback_cls):
    def eventFilter(self, obj, e):
        try:
            return base.eventFilter(self, obj, e)
        except TypeError:
            # 壳包装兜底：super() 解析失败时退化为默认事件过滤（放行事件）。
            try:
                return fallback_cls._default_event_filter(self, obj, e)
            except Exception:
                return False
    return eventFilter


class _GuardedStyleWatcher:
    """占位标记类：仅用于区分两类 watcher 的兜底入口。"""

    @staticmethod
    def _default_event_filter(self, obj, e):
        from PySide6.QtCore import QObject
        return QObject.eventFilter(self, obj, e)


class _GuardedDirtyWatcher:
    @staticmethod
    def _default_event_filter(self, obj, e):
        from PySide6.QtCore import QObject
        return QObject.eventFilter(self, obj, e)
