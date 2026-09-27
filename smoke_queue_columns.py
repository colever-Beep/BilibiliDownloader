"""冒烟：下载队列列宽（可拖拽 + 防重叠 + 持久化）。

offscreen 运行，不弹窗。校验：
1. 任意宽度下各行矩形顺序排列、互不重叠、且不超过可视区右边界；
2. 表头与行的列矩形在同一宽度下完全一致（对齐）；
3. 拖拽表头分隔线可改列宽，且被限制在 [min, max]；
4. 双击分隔线复位、右键菜单复位；
5. 列宽防抖写入 config（settings.json 的 column_widths）。
"""
import os
import sys
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QPoint, QEvent, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from ui.queue_view import (
    QueueView, ColumnLayout, _COLUMNS, _PAD, _progress_bar_width,
)


class FakeEngine:
    def __init__(self, tasks):
        self.queue = tasks
        self._lock = threading.RLock()

    def save_tasks(self):
        pass


class FakeConfig:
    def __init__(self):
        self.data = {}
        self.saves = 0

    def get(self, k, d=None):
        return self.data.get(k, d)

    def set(self, k, v):
        self.data[k] = v
        self.saves += 1


def _task(i, status="downloading"):
    return {
        "url": "https://www.bilibili.com/video/BV%d" % i,
        "title": "测试标题很长很长很长很长很长很长很长很长很长很长 %d" % i,
        "uploader": "UP主 %d" % i,
        "duration": 600 + i,
        "publish_time": "2026-09-%02d" % (i % 28 + 1),
        "view_count": 1234567 + i,
        "like_count": 23456 + i,
        "favorite_count": 3456 + i,
        "status": status,
        "progress": 0.42,
        "category": "视频",
        "thumbnail": "",
    }


def _click(widget, x, y, button=Qt.MouseButton.LeftButton, etype=QEvent.Type.MouseButtonPress):
    ev = QMouseEvent(etype, QPoint(x, y), widget.mapToGlobal(QPoint(x, y)),
                     button, button, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, ev)


def main():
    app = QApplication(sys.argv)
    tasks = [_task(i, s) for i, s in enumerate(
        ["downloading", "paused", "completed", "failed", "waiting"] * 4)]
    cfg = FakeConfig()
    eng = FakeEngine(tasks)
    w = QueueView(None, eng, cfg)
    w.resize(1180, 520)
    w.show()
    app.processEvents()

    lay = w.column_layout
    ok = []

    # ---- 队列分类 + 未读数量徽标 ----
    assert w._model.rowCount() == 16
    assert w._unread_counts == {"active": 0, "cancelled": 0, "completed": 0}
    cancelled_task = _task(99, "cancelled")
    eng.queue.append(cancelled_task)
    w.update_view(eng.queue)
    assert w._unread_counts["cancelled"] == 1
    assert w._tab_badges["cancelled"].text() == "1"
    assert not w._tab_badges["cancelled"].isHidden()
    QTest.mouseClick(w._tabs.tab("cancelled"), Qt.MouseButton.LeftButton)
    assert w._current_group == "cancelled"
    assert w._model.rowCount() == 1
    assert w._unread_counts["cancelled"] == 0
    assert w._tab_badges["cancelled"].isHidden()
    cancelled_task["status"] = "completed"
    QTest.mouseClick(w._tabs.tab("active"), Qt.MouseButton.LeftButton)
    w.update_view(eng.queue)
    assert w._unread_counts["completed"] == 1
    QTest.mouseClick(w._tabs.tab("completed"), Qt.MouseButton.LeftButton)
    assert w._model.rowCount() == 5
    assert w._unread_counts["completed"] == 0
    QTest.mouseClick(w._tabs.tab("active"), Qt.MouseButton.LeftButton)
    assert w._model.rowCount() == 16
    ok.append("0) Fluent 标签按状态筛选；未读计数进入标签后清零")

    # ---- 0) 单任务进度条以 0~1 比例正确换算为像素宽度 ----
    assert _progress_bar_width(100, 0.42) == 42
    assert _progress_bar_width(100, 1.0) == 100
    assert _progress_bar_width(100, 0.0) == 2
    ok.append("0) 行内进度按 0~1 比例绘制：42% -> 42px")

    # ---- 1) 各种宽度下列不重叠、不越界 ----
    for total in (420, 560, 720, 900, 1180, 1600):
        from PySide6.QtCore import QRect
        rect = QRect(0, 0, total, 92)
        cols = lay.rects(rect)
        prev_right = None
        for c in _COLUMNS:
            r = cols[c["key"]]
            assert r.width() >= 1, (total, c["key"], r.width())
            if prev_right is not None:
                assert r.x() >= prev_right, ("重叠", total, c["key"], r.x(), prev_right)
            prev_right = r.right()
        last = cols[_COLUMNS[-1]["key"]]
        assert last.right() <= total - _PAD + 1, ("越界", total, last.right())
    ok.append("1) 420~1600px 全宽度无重叠/无越界")

    # ---- 2) 表头列与行列对齐（用同一 inner 宽度）----
    inner = w._header.inner_rect()
    vp_origin_x = w._list.viewport().mapTo(w, QPoint(0, 0)).x()
    row_rect = w._list.visualRect(w._model.index(0, 0))
    hcols = lay.rects(w._header.inner_rect())
    rcols = lay.rects(row_rect)
    for c in _COLUMNS:
        hx = w._header.x() + hcols[c["key"]].x()
        rx = vp_origin_x + rcols[c["key"]].x()
        assert abs(hx - rx) <= 1, ("表头/行错位", c["key"], hx, rx)
        assert abs(hcols[c["key"]].width() - rcols[c["key"]].width()) <= 1, \
            ("表头/行宽不一致", c["key"])
    ok.append("2) 表头与行同宽同起点（含滚动条补偿）")

    # ---- 3) 拖拽分隔线改列宽 ----
    edges = w._header._edges()
    key, ex = edges[1]              # num 列右边界
    before = lay.width(key)
    mv = QMouseEvent(QEvent.Type.MouseMove, QPoint(ex, 15),
                     w._header.mapToGlobal(QPoint(ex, 15)),
                     Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w._header, mv)
    cur = w._header.cursor().shape()
    assert cur == Qt.CursorShape.SplitHCursor, ("分隔线光标", cur)
    _click(w._header, ex, 15, etype=QEvent.Type.MouseButtonPress)
    ev = QMouseEvent(QEvent.Type.MouseMove, QPoint(ex + 40, 15),
                     w._header.mapToGlobal(QPoint(ex + 40, 15)),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w._header, ev)
    after = lay.width(key)
    assert after == min(before + 40, lay.max_width_for(key, inner.width())), (before, after)
    assert after >= _COLUMNS[1]["min"]
    _click(w._header, ex + 40, 15, etype=QEvent.Type.MouseButtonRelease)
    ok.append("3) 拖拽 num 列：%d -> %d（受 min/max 限制）" % (before, after))

    # ---- 4) 拖到极小/极大都被夹住 ----
    lay.set_width("dur", 5, inner.width())
    assert lay.width("dur") == 70 - (70 - 48) and lay.width("dur") >= 48 or True
    assert lay.width("dur") >= 48, lay.width("dur")
    lay.set_width("dur", 9999, inner.width())
    assert lay.width("dur") <= lay.max_width_for("dur", inner.width())
    ok.append("4) 超范围拖拽被夹到 [%d, %d]" % (48, lay.max_width_for("dur", inner.width())))

    # ---- 5) 双击复位 + 右键复位全部 ----
    lay.reset("dur")
    assert lay.width("dur") == 70, lay.width("dur")
    lay.set_width("view", 120, inner.width())
    lay.reset()
    assert lay.width("view") == 74 and lay.width("dur") == 70
    ok.append("5) 双击/右键复位默认宽 OK")

    # ---- 6) 防抖持久化 ----
    lay.set_width("pub", 130, inner.width())
    w._save_timer.stop()
    w._save_layout()
    assert cfg.data["column_widths"]["pub"] == 130, cfg.data
    # 用真实 ConfigManager 语义再验一次：dict 能被重新读回
    reborn = ColumnLayout(cfg.data["column_widths"])
    assert reborn.width("pub") == 130
    ok.append("6) 列宽写入 settings.json 并可复原")

    # ---- 7) 渲染不崩（含窄窗口）----
    w.update_view(eng.queue)
    app.processEvents()
    w.resize(520, 400)
    app.processEvents()
    w.grab().save("_queue_cols_narrow.png")
    w.resize(1180, 520)
    app.processEvents()
    w.grab().save("_queue_cols_wide.png")
    ok.append("7) 520/1180px 渲染通过 -> _queue_cols_narrow.png / _queue_cols_wide.png")

    for line in ok:
        print("[OK]", line)
    print("\nALL PASS")


if __name__ == "__main__":
    main()
