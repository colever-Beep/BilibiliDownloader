"""跨线程把回调调度到主线程执行。

Qt 的 ``QTimer.singleShot(0, cb)`` 定时器线程亲和性绑定在「调用它的线程」上。
若从工作线程（解析 / 下载 / 网络线程）调用，而该线程没有运行事件循环，
定时器永远不会触发 —— 表现为「弹窗不出现 / UI 不刷新 / 队列不动」等诡异故障。

本项目所有「回主线程更新 UI」的调用都应走 ``run_on_main()``。它把回调交给
活在【主线程】的 QObject 桥接器，以 QueuedConnection 排队到主线程事件循环执行，
无论从哪个线程调用都安全。
"""
from PySide6.QtCore import QObject, Signal, QTimer, QThread

_bridge = None
_main_thread = None


class _MainThreadBridge(QObject):
    _run = Signal(object)

    def __init__(self):
        super().__init__()
        self._run.connect(self._do)

    def _do(self, cb):
        try:
            cb()
        except Exception as e:  # 回调内异常不应静默拖垮事件循环
            print(f"[run_on_main] 回调异常: {e}")

    def schedule(self, cb):
        # 由工作线程 emit；桥接器住在主线程 -> AutoConnection 退化为 QueuedConnection
        self._run.emit(cb)


def init_main_thread_bridge():
    """在【主线程】创建桥接器（QApplication 之后调用一次即可，幂等）。"""
    global _bridge, _main_thread
    if _bridge is None:
        _bridge = _MainThreadBridge()
        _main_thread = QThread.currentThread()


def run_on_main(cb):
    """把 cb 调度到主线程执行。可在任意线程调用。

    - 已在主线程：用 QTimer.singleShot(0, cb) 保持原有「下一轮事件循环」异步语义。
    - 在工作线程：经桥接器排队到主线程事件循环执行。
    """
    if _main_thread is not None and QThread.currentThread() == _main_thread:
        QTimer.singleShot(0, cb)
    elif _bridge is not None:
        _bridge.schedule(cb)
    else:
        # 兜底：桥接器尚未初始化（理论上不会发生，MainWindow.__init__ 会初始化）。
        # 直接执行以免任务丢失，仅在主线程场景下安全。
        try:
            cb()
        except Exception as e:
            print(f"[run_on_main] 兜底执行异常: {e}")
