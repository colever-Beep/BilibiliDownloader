# base_dialog.py
"""所有对话框的公共基类。

集中处理 CustomTkinter / Windows 窗口管理的已知坑，避免每个对话框重复踩坑：

1. _deactivate_windows_window_header_manipulation = True
   CustomTkinter 6.0 在 Windows 上切换明暗主题时，会对每个 CTkToplevel 调用
   withdraw() 重绘系统标题栏、再 after(5ms) 还原。带 transient 的子窗口其还原
   计时器经常失效，导致窗口被永久隐藏——表现为“切主题后对话框消失且再也打不开”。
   该开关从源头关闭这条 withdraw/重绘流程（只跳过系统标题栏配色，控件仍随主题重绘）。

2. _singleton(master)
   单例复用：已存在存活实例则聚焦返回它；否则清空陈旧引用并返回 None。

3. _show(master, geometry, resizable=None, grab=False, minsize=None)
   安全显示：先 deiconify 确保映射，再 transient 建立父子关系，最后把 lift/focus
   推迟到 idle 之后，避开与 CTk 主题重绘 / Windows 窗口管理器的时序冲突。

4. destroy()
   自动清空本类的 _INSTANCE，避免“关闭后无法再次打开”的陈旧单例引用。
"""
import customtkinter as ctk


class BaseDialog(ctk.CTkToplevel):
    _deactivate_windows_window_header_manipulation = True
    _INSTANCE = None

    @classmethod
    def _singleton(cls, master):
        """返回已存在的存活实例（并聚焦），否则清空陈旧引用并返回 None。"""
        existing = cls._INSTANCE
        if existing is not None:
            try:
                alive = existing.winfo_exists()
            except Exception:
                alive = False
            if alive:
                # 兜底：若窗口曾被 withdraw（如主题切换时序问题），先恢复显示再置顶
                try:
                    if existing.state() == "withdrawn":
                        existing.deiconify()
                except Exception:
                    pass
                existing.lift()
                existing.focus_force()
                return existing
            cls._INSTANCE = None
        return None

    def _show(self, master, geometry, resizable=None, grab=False, minsize=None):
        """统一、安全地完成“置顶父窗口之上并聚焦”的显示流程。"""
        try:
            self.geometry(geometry)
        except Exception:
            pass
        if resizable is not None:
            try:
                self.resizable(*resizable)
            except Exception:
                pass
        if minsize is not None:
            try:
                self.minsize(*minsize)
            except Exception:
                pass
        try:
            self.deiconify()
        except Exception:
            pass
        if master is not None:
            try:
                self.transient(master)
            except Exception:
                pass
        if grab:
            try:
                self.grab_set()
            except Exception:
                pass
        # 延迟到 idle 后置顶 / 聚焦，避开 CTk 主题重绘与窗口管理器的时序冲突
        self.after(0, lambda: (self.lift(), self.focus_force()))

    def destroy(self):
        if type(self)._INSTANCE is self:
            type(self)._INSTANCE = None
        try:
            super().destroy()
        except Exception:
            pass
