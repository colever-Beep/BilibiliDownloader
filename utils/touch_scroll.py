"""触屏滚动支持（Windows 触摸设备）。

qtfluentwidgets / Qt 默认不会为 ``QAbstractItemView`` / ``QScrollArea`` 启用手指滑动
滚动手势——必须显式 ``QScroller.grabGesture``。此前全仓库均缺失，导致触屏设备下列表
无法滑动。集中在此处，避免各视图重复实现与踩坑。
"""
from PySide6.QtWidgets import QScroller, QScrollArea


def enable_touch_scroll(widget):
    """为可滚动控件（``QListView`` / ``QListWidget`` / ``QScrollArea`` 等）启用触摸滚动手势。

    - ``QScrollArea``：手势抓在其 ``viewport`` 上最可靠（触摸事件路由到视口）；
    - 其它控件：直接抓在自身。

    包在 try 中，任何异常都不影响正常鼠标 / 滚轮滚动。
    """
    try:
        target = widget
        if isinstance(widget, QScrollArea):
            vp = widget.viewport()
            if vp is not None:
                target = vp
        QScroller.grabGesture(target, QScroller.TouchGesture)
    except Exception:
        pass
