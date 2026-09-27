"""无头验证：直播中心窗口 详细(封面网格) / 精简(列表) 布局切换。"""
import os
import sys
import tempfile

os.chdir(tempfile.mkdtemp())

from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import requests
from ui.dialogs import LiveCenterDialog, _LiveRoomCard
from ui.list_layout import manager, is_compact


class FakeApi:
    session = requests.Session()

    def get_live_hot(self, *a, **k):
        return [
            {"roomid": i, "title": f"直播间{i}", "uname": f"UP{i}",
             "cover": "", "face": "", "online": 1000 + i,
             "watched_show": f"{1000 + i}", "area_name": "聊天"}
            for i in range(1, 21)
        ]

    def search_live_rooms(self, *a, **k):
        return []


app = QApplication.instance() or QApplication(sys.argv)

dlg = LiveCenterDialog(parent=None, api=FakeApi(), on_record=lambda r: None,
                       on_open_room=lambda r: None)
dlg.show()

# 默认模式（detailed）应渲染网格
assert not is_compact(), "默认应为详细(网格)"
dlg._render()
assert dlg._stack.currentWidget() is dlg.grid_scroll, "详细模式应显示网格页"
cards = dlg._grid_container.findChildren(_LiveRoomCard)
assert len(cards) == 20, f"网格应有 20 张卡片，实际 {len(cards)}"
print("detailed -> grid cards:", len(cards))

# 切到精简(列表)
manager.set_mode("compact")
assert dlg._stack.currentWidget() is dlg.list, "精简模式应显示列表页"
assert dlg.list.count() == 20, f"列表应有 20 项，实际 {dlg.list.count()}"
print("compact -> list items:", dlg.list.count())

# 列表项点击 -> _current_room
dlg.list.setCurrentRow(0)
dlg._on_list_pick(dlg.list.item(0))
assert dlg._current() is not None
print("list pick -> current roomid:", dlg._current().get("roomid"))

# 回到详细，卡片点击选中 + 高亮
manager.set_mode("detailed")
assert dlg._stack.currentWidget() is dlg.grid_scroll
card0 = dlg._card_of(dlg._rooms[0])
dlg._on_card_pick(dlg._rooms[0])
assert dlg._current().get("roomid") == dlg._rooms[0].get("roomid")
assert card0._selected is True, "选中卡片应高亮"
others = [c for c in dlg._grid_container.findChildren(_LiveRoomCard) if c is not card0]
assert all(not c._selected for c in others), "其它卡片不应高亮"
print("grid pick -> selected card roomid:", card0.room.get("roomid"), "highlighted OK")

# LayoutModeToggle 位于底部左侧
from ui.list_layout import LayoutModeToggle
toggles = [w for w in (dlg._leftBtns.itemAt(i).widget() for i in range(dlg._leftBtns.count())) if isinstance(w, LayoutModeToggle)]
assert toggles, "底部左侧应存在 LayoutModeToggle"
print("LayoutModeToggle present at bottom-left: OK")

print("\nSMOKE PASS")
