"""CustomTkinter 运行期补丁。

集中修复官方库在「快速销毁 / 重建复合控件」场景下的已知缺陷，避免界面出现
无害但吓人的 TclError（表现为 download.log 里的 [UI异常] 或弹出的错误框）。

已知问题（CTk 6.0.0，Windows）：
- 虚拟列表（VirtualList）滚动 / 增删任务时，会销毁并重建立即复用的行内控件
  （CTkButton / CTkLabel 等）。这些复合控件内部各自持有一个 ``_canvas`` 子部件。
- Tk 的事件队列里可能残留一个指向「旧行按钮」的 ``<Configure>`` 事件；控件整体
  被销毁后该事件仍被派发，触发 ``CTkBaseClass._update_dimensions_event`` ->
  ``CTkButton._draw`` -> 对已销毁的内部 ``_canvas`` 调用 ``delete``，抛出
  ``_tkinter.TclError: invalid command name "...!ctkcanvas"``。
- 该错误对功能毫无影响（控件都销毁了，没必要再重绘），却被 ``report_callback_exception``
  当作未处理异常记录并弹窗。

修复方式：在进入 ``_update_dimensions_event`` 时检查控件内部绘制层是否仍然存在，
若已销毁则直接跳过（与"正常重绘"行为一致——都不再绘制已不存在的控件）。该守卫
对存活控件完全透明，不影响任何正常渲染。
"""

import customtkinter as ctk

_INSTALLED = False


def _find_base_class_with(method_name):
    """从某个具体 CTk 控件的 MRO 中找到定义了该方法的基类（即 CTkBaseClass）。"""
    try:
        for klass in ctk.CTkButton.__mro__:
            if method_name in klass.__dict__:
                return klass
    except Exception:
        pass
    return None


def install_ctk_event_guard():
    """安装防御性守卫，杜绝「控件已销毁后残留 <Configure> 事件」引发的 TclError。

    幂等：多次调用只会生效一次。
    """
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    base = _find_base_class_with("_update_dimensions_event")
    if base is None:
        return
    orig = base._update_dimensions_event

    def _guarded_update_dimensions_event(self, event=None):
        # 若控件内部绘制层（CTk 复合控件各自的 _canvas 子部件）已被销毁，
        # 说明本事件来自于控件销毁前的残留，直接跳过——没有可重绘的对象。
        try:
            canvas = getattr(self, "_canvas", None)
            if canvas is None or not canvas.winfo_exists():
                return
        except Exception:
            # 任何探查异常都视为「已不可绘」，安全跳过
            return
        return orig(self, event)

    try:
        base._update_dimensions_event = _guarded_update_dimensions_event
    except Exception:
        # 万一无法写入（理论上不会），不阻塞主流程
        _INSTALLED = False
