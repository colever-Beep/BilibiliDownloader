"""窗口前台激活助手。

解决 Windows 下「弹窗失焦无法点击 + 播放系统提示音（叮）」这一对共生症状：

- Qt 的 ``widget.activateWindow()`` / ``widget.raise_()`` 在底层调用
  ``SetForegroundWindow``。当调用进程**不是**当前前台进程（例如弹窗由后台
  定时器 / 子线程信号触发，或主窗口刚失去焦点）时，Windows 的「前台锁」
  （foreground lock）会拒绝这次前台切换，并播放系统提示音，同时弹窗虽可见
  却拿不到焦点、被遮罩盖住主窗口 → 用户看到「看得见点不动」。

- 经典绕过法：用 ``AttachThreadInput`` 把**本线程**与**当前前台线程**的输入
  队列接起来，使随后的 ``SetForegroundWindow`` 被视为「同一前台线程」而放行
  （不再响叮），再把窗口真正置顶并抢焦点。``SetWindowPos(HWND_TOPMOST)`` 再
  复位到 ``HWND_NOTOPMOST`` 作为兜底——即使前台切换仍被拒，窗口也已位于 Z
  序最前、可见可点，不再出现「被压在下面点不动」。

非 Windows 平台（或取不到句柄 / 调用异常）优雅回退到 Qt 原生
``raise_()`` / ``activateWindow()``。
"""
from __future__ import annotations

import sys

_user32 = None


def _get_user32():
    global _user32
    if _user32 is None and sys.platform == "win32":
        try:
            _user32 = __import__("ctypes").windll.user32
        except Exception:
            _user32 = None
    return _user32


def bring_to_foreground(widget):
    """把窗口带到前台并抢焦点，且不触发 Windows 前台锁提示音。

    适用于模态弹窗、设置窗口、子窗口等任何需要「显示即获得焦点、可立即点击」
    的顶层窗口。失败不抛异常。
    """
    if widget is None:
        return
    u = _get_user32()
    if u is None:                      # 非 Windows：走 Qt 原生
        _qt_raise(widget)
        return
    try:
        hwnd = int(widget.winId())
    except Exception:
        hwnd = 0
    if hwnd == 0:
        _qt_raise(widget)
        return
    try:
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2

        foreground_hwnd = u.GetForegroundWindow()
        my_thread = u.GetCurrentThreadId()
        fg_thread = 0
        if foreground_hwnd:
            try:
                fg_thread = u.GetWindowThreadProcessId(foreground_hwnd, None)
            except Exception:
                fg_thread = 0

        attached = False
        if fg_thread and fg_thread != my_thread:
            try:
                # 接上前台线程输入队列：让 SetForegroundWindow 被放行（不响叮）
                if u.AttachThreadInput(my_thread, fg_thread, True):
                    attached = True
            except Exception:
                attached = False

        # 兜底：先置顶再复位，确保位于 Z 序最前、可见可点
        try:
            u.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                           SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            u.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                           SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        except Exception:
            pass

        try:
            u.SetForegroundWindow(hwnd)
            u.SetFocus(hwnd)
        except Exception:
            pass

        if attached:
            try:
                u.AttachThreadInput(my_thread, fg_thread, False)
            except Exception:
                pass
    except Exception:
        _qt_raise(widget)


def _qt_raise(widget):
    try:
        widget.raise_()
        widget.activateWindow()
    except Exception:
        pass
