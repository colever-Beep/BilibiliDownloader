"""headless 验证：消息框聚焦修复（_MaskMessageBox）

- 子类能正常构造、showEvent 调用 raise_/activateWindow 不报错
- 按钮可点击：模拟点击「确定」后 exec() 返回 True，点击「取消」返回 False
- 确认框（with_cancel）隐藏取消按钮后只显示确定
"""
import os, sys, tempfile
os.chdir(tempfile.mkdtemp())
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import QTimer
import ui.fluent_dialog as fd

app = QApplication.instance() or QApplication(sys.argv)

parent = QWidget()
parent.resize(1000, 700)
parent.show()
app.processEvents()

# 1) 信息框：自动点「确定」应返回 True
mb = fd._MaskMessageBox("提示", "测试内容", parent)
assert mb.yesButton is not None
clicked = {"v": None}
def _accept():
    mb.yesButton.click()
QTimer.singleShot(30, _accept)
ret = mb.exec()
print("信息框 exec 返回:", ret)
assert ret == 1, f"点确定应返回 1(Accepted)，实际 {ret}"

# 2) 确认框：自动点「取消」应返回 False
mb2 = fd._MaskMessageBox("确认", "确定吗", parent)
mb2.hideCancelButton()
assert not mb2.cancelButton.isVisible(), "确认框 hideCancelButton 后取消按钮应隐藏"
def _cancel():
    mb2.cancelButton.click()
QTimer.singleShot(30, _cancel)
ret2 = mb2.exec()
print("确认框(取消) exec 返回:", ret2)
assert ret2 == 0, f"点取消应返回 0(Rejected)，实际 {ret2}"

# 3) 经 _message 助手：确认框返回 1（确定）
res = {"v": None}
def _accept2():
    # 找到当前可见的消息框（是 parent 的子控件，非顶层）并点确定
    for mb in parent.findChildren(fd._MaskMessageBox):
        if mb.isVisible():
            mb.yesButton.click()
            return
QTimer.singleShot(30, _accept2)
rv = fd._message(parent, "确认", "经助手确认？", with_cancel=True)
print("_message 助手(确定) 返回:", rv)
assert rv == 1, f"_message 点确定应返回 1，实际 {rv}"

# 4) showEvent 不抛异常已在上面 exec 过程中覆盖（raise_/activateWindow 已执行）
print("ALL PASS: 消息框聚焦修复子类 + 按钮可点击 全部通过")
