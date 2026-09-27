"""无头冒烟：迁移为 Fluent 的功能型弹窗（dialogs.py 全部 + 后续选择类）。

覆盖：
  1. 逐个构造 + show + grab（捕获仅绘制期才暴露的崩溃）；
  2. 关键回调契约：批量解析 / 搜索勾选 / 解析记录 / 直播中心 / 收藏夹 / 录制直播；
  3. 模态 exec() 往返（确定=True / 取消=False）；
  4. 消息框助手走桩替换，避免离屏环境下阻塞。

运行：
  QT_QPA_PLATFORM=offscreen python smoke_dialogs_fluent.py
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.getcwd())
_PROJ = os.getcwd()          # 切到临时目录后仍能读回项目文件

# 全部弹窗都在「临时工作目录」里跑：history.txt / download.log / cookies.txt
# 都会写到临时目录，绝不碰真实工作区的文件。
_TMP = tempfile.mkdtemp(prefix="smoke_fluent_")
os.chdir(_TMP)
with open("history.txt", "w", encoding="utf-8") as f:
    f.write("2026-09-25 10:00:00 | https://www.bilibili.com/video/BV1aa | 视频甲 | manual\n"
            "2026-09-25 09:00:00 | https://www.bilibili.com/video/BV1bb | 视频乙 | batch\n")
with open("download.log", "w", encoding="utf-8") as f:
    f.write("[10:00:00] 冒烟日志一行\n")

from PySide6.QtCore import Qt, QTimer                   # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from utils.main_thread import init_main_thread_bridge     # noqa: E402
init_main_thread_bridge()   # 让后台线程的 run_on_main 真正排队回主线程


def pump(ms=600):
    """跑一段时间的事件循环，等待后台线程 + run_on_main 回调落地。"""
    import time
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)

# ---- 消息框桩（避免离屏下 MessageBox.exec() 阻塞） ----
from ui import dialogs as D                              # noqa: E402

_CALLS = []


def _stub_info(parent, content, title=None, ok_text=None):
    _CALLS.append(("info", content))
    return 1


def _stub_warn(parent, content, title=None, ok_text=None):
    _CALLS.append(("warn", content))
    return 1


def _stub_error(parent, content, title=None, ok_text=None):
    _CALLS.append(("error", content))
    return 1


def _stub_confirm(parent, content, title=None, ok_text=None, cancel_text=None):
    _CALLS.append(("confirm", content))
    return True


D.msg_info = _stub_info
D.msg_warn = _stub_warn
D.msg_error = _stub_error
D.msg_confirm = _stub_confirm


class _Api:
    """最小可用桩：不发网络请求。"""
    uid = 1001
    nickname = "tester"

    def __init__(self):
        self.session = None

    def _ensure_buvid(self):
        pass

    def get_favorite_folders(self):
        return [{"id": 11, "title": "默认收藏夹", "media_count": 3},
                {"id": 22, "title": "游戏", "media_count": 8}]

    def get_live_hot(self):
        return [{"roomid": 111, "title": "热门直播A", "uname": "UP甲",
                 "area_name": "单机", "watched_show": "1.2万"},
                {"roomid": 222, "title": "热门直播B", "uname": "UP乙",
                 "area_name": "手游", "watched_show": "8000"}]

    def search_live_rooms(self, kw):
        return [{"roomid": 333, "title": f"搜索:{kw}", "uname": "UP丙",
                 "area_name": "网游", "watched_show": "12"}]


def _grab(dlg, name):
    dlg.show()
    for _ in range(3):
        app.processEvents()
    pm = dlg.grab()
    print(f"  - {name}: {dlg.width()}x{dlg.height()} grab={pm.width()}x{pm.height()} "
          f"{'NULL' if pm.isNull() else 'ok'}")
    return not pm.isNull()


host = QMainWindow()
host.resize(1200, 800)
host.show()
app.processEvents()

fail = []
ok_grab = True

# ------------------------------------------------------------------ #
print("[1] 关于")
d = D.AboutDialog(host)
ok_grab &= _grab(d, "AboutDialog")
d.close()

# ------------------------------------------------------------------ #
print("[2] 批量解析")
lines_got = []
d = D.BatchParseDialog(host, on_parse=lines_got.extend)
d.edit.setPlainText("https://www.bilibili.com/video/BV1xx\n\n  https://b23.tv/abc  \n")
d._on_accept()
ok_grab &= _grab(d, "BatchParseDialog")
if lines_got != ["https://www.bilibili.com/video/BV1xx", "https://b23.tv/abc"]:
    fail.append(f"BatchParse on_parse={lines_got}")
d.close()

# 空输入时只弹提示、不回调
lines_got.clear()
d2 = D.BatchParseDialog(host, on_parse=lines_got.extend)
d2.edit.setPlainText("   \n  ")
n_before = len(_CALLS)
d2._on_accept()
if lines_got or len(_CALLS) == n_before or _CALLS[-1][0] != "info":
    fail.append("BatchParse 空输入未走提示分支")
d2.close()

# ------------------------------------------------------------------ #
print("[3] 日志窗口")
d = D.LogWindow(host, logger=None)
ok_grab &= _grab(d, "LogWindow")
d._load()
d._clear()                     # 走桩 confirm=True → 清空并重载
if _CALLS[-1][0] != "confirm":
    fail.append("LogWindow _clear 未走确认框")
d.close()

# ------------------------------------------------------------------ #
print("[4] 解析记录")
added = []
d = D.ParseRecordsDialog(host, on_add=lambda u, t: added.append((u, t)))
ok_grab &= _grab(d, "ParseRecordsDialog")
if d.table.rowCount() != 2:
    fail.append(f"ParseRecords rowCount={d.table.rowCount()}")
d.table.selectRow(0)          # 列表「最新在前」：row0 = 后写入的视频乙
d._on_add()
if added != [("https://www.bilibili.com/video/BV1bb", "视频乙")]:
    fail.append(f"ParseRecords _on_add={added}")
d._copy()
from PySide6.QtGui import QGuiApplication as _QGA          # noqa: E402
if _QGA.clipboard().text() != "https://www.bilibili.com/video/BV1bb":
    fail.append(f"ParseRecords _copy={_QGA.clipboard().text()!r}")
d._delete()
if d.table.rowCount() != 1:
    fail.append(f"ParseRecords _delete rowCount={d.table.rowCount()}")
if len(D._read_parse_records()) != 1:
    fail.append("ParseRecords _delete 未落盘")
d._clear()
if d.table.rowCount() != 0 or _CALLS[-1][0] != "confirm":
    fail.append("ParseRecords _clear 未生效")
if D._read_parse_records():
    fail.append("ParseRecords _clear 未落盘")
d.close()

# ------------------------------------------------------------------ #
print("[5] 搜索")
_results = [
    {"type": "video", "title": "视频一", "url": "https://b/BV1", "duration": 125,
     "category": "科技"},
    {"type": "user", "title": "UP主", "mid": 5, "duration": 0},
]
confirmed = []
d = D.SearchDialog(host, lambda kw: _results, on_confirm=confirmed.extend,
                   title="搜索 B站")
d._finish_search(_results)
ok_grab &= _grab(d, "SearchDialog")
if d.list.count() != 2:
    fail.append(f"SearchDialog list={d.list.count()}")
d._set_all(True)
row0 = d.list.itemWidget(d.list.item(0))
if not row0._cb.isChecked():
    fail.append("SearchDialog 全选未勾上")
d._on_accept()
if len(confirmed) != 2:
    fail.append(f"SearchDialog confirmed={len(confirmed)}")
# 全不选后确认应拿到空列表
d = D.SearchDialog(host, lambda kw: _results, on_confirm=lambda s: confirmed.clear())
d._finish_search(_results)
d._set_all(False)
d._on_accept()
if confirmed:
    fail.append("SearchDialog 全不选后仍带出勾选项")
d.close()

# ------------------------------------------------------------------ #
print("[6] 直播中心")
recs = []
d = D.LiveCenterDialog(host, api=_Api(), on_record=recs.append, on_open_room=lambda r: None)
ok_grab &= _grab(d, "LiveCenterDialog")
d._fill(_Api().get_live_hot(), "hot")
if d.list.count() != 2:
    fail.append(f"LiveCenter list={d.list.count()}")
d.list.setCurrentRow(0)
d._on_record()
if recs != [_Api().get_live_hot()[0]]:
    fail.append(f"LiveCenter _on_record={recs}")
d.list.setCurrentRow(-1)
n_before = len(_CALLS)
d._on_record()
if len(_CALLS) == n_before or _CALLS[-1][0] != "info":
    fail.append("LiveCenter 未选中时未提示")
d.close()

# ------------------------------------------------------------------ #
print("[7] 录制直播")
rec2 = []
d = D.LiveRecordDialog(host, on_record=rec2.append)
d.input.setText("https://live.bilibili.com/9527")
d._on_accept()
ok_grab &= _grab(d, "LiveRecordDialog")
if rec2 != ["https://live.bilibili.com/9527"]:
    fail.append(f"LiveRecord on_record={rec2}")
d.close()

# ------------------------------------------------------------------ #
print("[8] 收藏夹选择")
sel = []
d = D.FavFolderDialog(host, _Api(), on_select=lambda fid, t: sel.append((fid, t)))
d._render(_Api().get_favorite_folders())
ok_grab &= _grab(d, "FavFolderDialog")
if d.list.count() != 2 or not d.btn_ok.isEnabled():
    fail.append(f"FavFolder list={d.list.count()} ok_enabled={d.btn_ok.isEnabled()}")
d.list.setCurrentRow(1)
d._on_accept()
if sel != [(22, "游戏")]:
    fail.append(f"FavFolder on_select={sel}")
d.close()

# ------------------------------------------------------------------ #
print("[9] 登录（二维码页构造，网络请求预期失败但被吞掉）")
d = D.LoginDialog(host, _Api(), on_success=lambda: None)
ok_grab &= _grab(d, "LoginDialog")
if d.stackedWidget.count() != 2:
    fail.append(f"Login pages={d.stackedWidget.count()}")
# 二维码生成失败路径：错误提示必须真的落到状态标签上
# （回归守卫：延迟回调里引用 except 变量 e 会静默丢掉提示）
pump(600)
if "二维码生成失败" not in d.status_label.text():
    fail.append(f"Login 错误提示未落地 status={d.status_label.text()!r}")
if not d.refresh_btn.isEnabled():
    fail.append("Login 生成失败后未恢复「刷新二维码」按钮")
d.show_page("cookie")
app.processEvents()
d.reject()
if not d._stop.is_set():
    fail.append("LoginDialog reject 未停止轮询")
d.close()

# ------------------------------------------------------------------ #
print("[10] 模态 exec 往返")
d = D.AboutDialog(host)
QTimer.singleShot(80, d.accept)
r_ok = d.exec()
d = D.AboutDialog(host)
QTimer.singleShot(80, d.reject)
r_no = d.exec()
if not (r_ok is True and r_no is False):
    fail.append(f"exec 往返 ok={r_ok} no={r_no}")

# ------------------------------------------------------------------ #
print("[11] 通用选择窗口 SelectDialog")
from ui import select_dialog as SD                       # noqa: E402
from ui import episode_select_dialog as D2               # noqa: E402
SD.msg_info = _stub_info
SD.msg_error = _stub_error

_items = [
    {"url": "https://b/BV1", "title": "视频一", "duration": 60, "thumbnail": ""},
    {"url": "https://b/BV2", "title": "视频二", "duration": 90, "thumbnail": "",
     "uploader": "UP", "view_count": 1000},
]
picked = []
d = SD.SelectDialog(host, _items, lambda s: picked.extend(s))
ok_grab &= _grab(d, "SelectDialog")
if d.list.model().rowCount() != 2:
    fail.append(f"SelectDialog rows={d.list.model().rowCount()}")
if d.btn_ok.isEnabled():
    fail.append("SelectDialog 未选就允许确认")
d._on_row_clicked(d.list.model().index(0, 0))
if not d.btn_ok.isEnabled() or "已选" not in d.count_lab.text():
    fail.append(f"SelectDialog 单行勾选异常 count={d.count_lab.text()!r}")
# 「全选」三态 → 全选 → 应选中 2 项
d.check_all.setCheckState(Qt.CheckState.Checked)
pump(100)
if len(d._selected) != 2:
    fail.append(f"SelectDialog 全选后 selected={len(d._selected)}")

# 回归：无任何勾选时，首次点击全选框（三态首跳 = PartiallyChecked）应直接全选 2 项，
# 而非被误判为「全不选」需连点两次 / 先手选一项。
fresh = SD.SelectDialog(host, _items, lambda s: None)
fresh._on_check_all(Qt.CheckState.PartiallyChecked)  # 模拟首次点击（三态首跳=部分选中）
pump(100)
if len(fresh._selected) != 2:
    fail.append(f"SelectDialog 空选首点全选 selected={len(fresh._selected)}")
fresh.close()
d.accept()
if len(picked) != 2:
    fail.append(f"SelectDialog on_confirm={len(picked)}")
d.close()

# 取消不应回调
picked.clear()
d = SD.SelectDialog(host, _items, lambda s: picked.extend(s))
d._on_row_clicked(d.list.model().index(0, 0))
d.reject()
if picked:
    fail.append("SelectDialog 取消仍回调")

# ------------------------------------------------------------------ #
print("[12] 分页选择窗口 PaginatedSelectDialog")
_pages = {
    1: ([{"url": "https://b/P1", "title": "第一页", "duration": 10, "thumbnail": ""},
         {"url": "https://b/P2", "title": "第一页B", "duration": 20, "thumbnail": ""}], True),
    2: ([{"url": "https://b/P3", "title": "第二页", "duration": 30, "thumbnail": ""}], False),
}
picked2 = []
d = SD.PaginatedSelectDialog(host, lambda pn, ps: _pages[pn], 20,
                             lambda s: picked2.extend(s), title="收藏夹")
pump(800)                       # 等第一页拉取回主线程
ok_grab &= _grab(d, "PaginatedSelectDialog")
if d.list.model().rowCount() != 2 or d.pn != 1:
    fail.append(f"Paginated page1 rows={d.list.model().rowCount()} pn={d.pn}")
d._on_row_clicked(d.list.model().index(0, 0))     # 勾第 1 页第 1 条
d._go_next()
pump(800)
if d.pn != 2 or d.list.model().rowCount() != 1:
    fail.append(f"Paginated page2 pn={d.pn} rows={d.list.model().rowCount()}")
if "https://b/P1" not in d._checked_keys:
    fail.append("Paginated 翻页后丢失已选项")
# 回到第 1 页，勾选态应仍在
d._go_prev()
pump(800)
if "https://b/P1" not in d._checked_keys or not d.btn_ok.isEnabled():
    fail.append("Paginated 回翻后勾选态丢失")
d.accept()
if len(picked2) != 1:
    fail.append(f"Paginated on_confirm={len(picked2)}")
d.close()

# ------------------------------------------------------------------ #
print("[13] 选集窗口 EpisodeSelectDialog")
_eps = [{"url": "https://b/ep1", "title": "第一话", "duration": 1200},
        {"url": "https://b/ep2", "title": "第二话", "duration": 1300},
        {"url": "https://b/ep3", "title": "第三话 特别篇", "duration": 1400}]
picked3 = []
d = D2.EpisodeSelectDialog(host, _eps, lambda s: picked3.extend(s), title="选择分集")
ok_grab &= _grab(d, "EpisodeSelectDialog")
if "总计 3" not in d.count_lab.text():
    fail.append(f"Episode count={d.count_lab.text()!r}")
d.search.setText("第二")
pump(100)
if d.list.model().rowCount() != 1:
    fail.append(f"Episode 搜索过滤 rows={d.list.model().rowCount()}")
d.search.setText("")
pump(100)
d._select_all()
if not d.btn_ok.isEnabled() or len(d._selected) != 3:
    fail.append(f"Episode 全选 selected={len(d._selected)}")
d._unselect_all()
if d.btn_ok.isEnabled():
    fail.append("Episode 清空勾选后仍可确认")
d._select_all()
d.accept()
if len(picked3) != 3:
    fail.append(f"Episode on_confirm={len(picked3)}")
d.close()

# ------------------------------------------------------------------ #
print("[14] 我的关注 FollowingDialog")
from ui import following_dialog as FD                    # noqa: E402
FD._AvatarLoader.start = lambda self: None                # 冒烟不发网络请求
_follows = [{"mid": 1, "uname": "UP主甲", "sign": "签名甲", "face": "https://f/1.png"},
            {"mid": 2, "uname": "UP主乙", "sign": "签名乙", "face": ""}]
opened = []
d = FD.FollowingDialog(host, _follows, opened.append)
ok_grab &= _grab(d, "FollowingDialog")
if d.list.count() != 2:
    fail.append(f"Following rows={d.list.count()}")
if "共 2 位UP主" not in d.title_label.text():
    fail.append(f"Following title={d.title_label.text()!r}")
d.search.setText("乙")
pump(100)
if d.list.count() != 1:
    fail.append(f"Following 搜索过滤 rows={d.list.count()}")
d.search.setText("")
pump(100)
# 头像回填路径（用真实 PNG 字节验证 ImageLabel 更新）
import io as _io                                          # noqa: E402
from PIL import Image as _Image                            # noqa: E402
_buf = _io.BytesIO()
_Image.new("RGB", (56, 56), (200, 120, 60)).save(_buf, format="PNG")
_lab = d._avatar_labels.get("https://f/1.png")
if _lab is None:
    fail.append("Following 未登记头像回调标签")
else:
    d._on_avatar_loaded("https://f/1.png", _buf.getvalue())
    if getattr(_lab, 'image', None) is None:
        fail.append("Following 头像回填失败")
d._open_space(1)
if opened != [1] or not d._closed:
    fail.append(f"Following on_open_space={opened} closed={d._closed}")

# ------------------------------------------------------------------ #
print("[15] 二选一对话框 ChoiceDialog（关闭方式）")
from ui.fluent_dialog import ChoiceDialog                 # noqa: E402
d = ChoiceDialog(host, tr_ := "关闭方式", "关闭程序时：",
                 options=[("直接退出", "quit"), ("最小化到托盘", "tray")],
                 default="tray")
ok_grab &= _grab(d, "ChoiceDialog")
if d.value != "tray":
    fail.append(f"ChoiceDialog 初始值={d.value}")
d.pick("quit")
if d.value != "quit":
    fail.append(f"ChoiceDialog pick 后={d.value}")
d2 = ChoiceDialog(host, "关闭方式", "关闭程序时：",
                  options=[("直接退出", "quit")], default="tray")
d2.reject()
if d2.value != "tray":
    fail.append(f"ChoiceDialog 取消后应保持 default，实际={d2.value}")

# ------------------------------------------------------------------ #
print("[16] 静态检查：主窗口不应再出现 QMessageBox")
import pathlib                                            # noqa: E402
_mw = pathlib.Path(_PROJ, "ui", "main_window.py").read_text(encoding="utf-8")
if "QMessageBox" in _mw:
    fail.append("main_window.py 仍有 QMessageBox 残留")

print()
print("CALLS:", [c[0] for c in _CALLS])
print("grab_all_ok:", ok_grab)
if fail:
    print("FAILURES:")
    for f in fail:
        print("  ✗", f)
    print("DIALOGS_FLUENT_FAIL")
    sys.exit(1)
print("DIALOGS_FLUENT_OK")
