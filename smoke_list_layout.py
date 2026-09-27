"""无头冒烟测试：验证「详细 / 精简」列表布局切换不崩溃且 compact 路径可绘制。

- 全局模式单例：set_mode / is_compact / 持久化。
- SelectListView：detailed -> compact -> detailed 切换并实时重绘。
- SelectDialog / EpisodeSelectDialog / QueueView：构造 + 切换布局。
- LayoutModeToggle：独立构造 + 切换。
仅构造 + 事件循环级验证（QT_QPA_PLATFORM=offscreen），不依赖真实显示。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from config import ConfigManager
from ui.list_layout import (
    set_config, set_mode, is_compact, get_mode, LayoutModeToggle, manager,
)
from ui.select_list_view import SelectListView
from ui.select_dialog import SelectDialog
from ui.episode_select_dialog import EpisodeSelectDialog
from ui.queue_view import QueueView


def _app():
    return QApplication.instance() or QApplication(sys.argv)


def main():
    app = _app()
    cfg = ConfigManager("settings.json")
    set_config(cfg)

    items = [
        {"url": "https://bilibili.com/video/BV1",
         "title": "测试视频标题很长很长很长很长很长很长很长很长很长很长",
         "uploader": "UP主A", "duration": 125, "view_count": 1000,
         "like_count": 200, "favorite_count": 50, "thumbnail": "",
         "category": "番剧"},
        {"url": "https://bilibili.com/video/BV2", "title": "另一个视频",
         "uploader": "UP主B", "duration": 60, "thumbnail": ""},
    ]

    # --- SelectListView ---
    slv = SelectListView(set(), None)
    slv.set_items(items)
    slv.show()
    slv.resize(700, 300)
    app.processEvents()
    assert get_mode() == "detailed"
    set_mode("compact")
    app.processEvents()
    assert is_compact(), "compact 模式未生效"
    set_mode("detailed")
    app.processEvents()
    slv.close()
    app.processEvents()

    # --- SelectDialog ---
    dlg = SelectDialog(None, items, lambda x: None, title="选择视频")
    dlg.show()
    app.processEvents()
    set_mode("compact")
    app.processEvents()
    set_mode("detailed")
    app.processEvents()
    dlg.close()
    app.processEvents()

    # --- EpisodeSelectDialog ---
    eps = [
        {"url": "https://bilibili.com/video/BV1?p=1", "title": "第1集", "duration": 120},
        {"url": "https://bilibili.com/video/BV1?p=2", "title": "第2集", "duration": 130},
    ]
    ed = EpisodeSelectDialog(None, eps, lambda x: None, title="选择分集")
    ed.show()
    app.processEvents()
    set_mode("compact")
    app.processEvents()
    ed.close()
    app.processEvents()

    # --- QueueView（精简需隐藏 cover/pub/view/like/fav 列）---
    class StubEngine:
        def __init__(self):
            self.queue = [
                {"id": 1, "url": "https://bilibili.com/video/BV1",
                 "title": "队列视频标题", "uploader": "UP主A", "duration": 125,
                 "publish_time": "2024-01-01", "view_count": 100,
                 "like_count": 10, "favorite_count": 5, "thumbnail": "",
                 "status": "downloading", "progress": 0.5},
                {"id": 2, "url": "https://bilibili.com/video/BV2",
                 "title": "已完成视频", "uploader": "UP主B", "duration": 60,
                 "status": "completed", "progress": 1.0},
            ]
            self.status_callbacks = []
            self.progress_callbacks = []
            self.finish_callbacks = []
            self.stop_callbacks = []

        def save_tasks(self):
            pass

        def pause_task(self, u):
            pass

        def resume_task(self, u):
            pass

        def retry_task(self, u):
            pass

    qv = QueueView(None, StubEngine(), cfg)
    qv.show()
    qv.resize(900, 400)
    app.processEvents()
    set_mode("compact")
    app.processEvents()
    hidden = qv.column_layout.hidden()
    assert hidden == {"cover", "pub", "view", "like", "fav"}, f"隐藏列错误: {hidden}"
    active = [c["key"] for c in qv.column_layout.active_columns()]
    assert "cover" not in active and "view" not in active, "活动列仍含隐藏列"
    set_mode("detailed")
    app.processEvents()
    assert qv.column_layout.hidden() == set(), "恢复详细后仍有隐藏列"
    qv.close()
    app.processEvents()

    # --- LayoutModeToggle 独立 ---
    t = LayoutModeToggle()
    t.show()
    app.processEvents()
    set_mode("compact")
    app.processEvents()
    set_mode("detailed")
    app.processEvents()
    t.close()

    # 恢复默认，避免污染 settings.json
    set_mode("detailed")

    print("LIST_LAYOUT_SMOKE_OK final_mode=", get_mode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
