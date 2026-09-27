"""Headless regression check for duplicate modal message re-entry."""
import os
import sys
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

app = QApplication.instance() or QApplication(sys.argv)

import ui.fluent_dialog as fluent_dialog
from ui.main_window import MainWindow

parent = QMainWindow()
results = {}


def nested_message_exec(self):
    results["duplicate"] = fluent_dialog.msg_info(
        parent, "second popup", "test")
    return 1


with patch.object(fluent_dialog._MaskMessageBox, "exec", nested_message_exec):
    results["first"] = fluent_dialog.msg_info(parent, "first popup", "test")

assert results == {"duplicate": 0, "first": 1}, results
assert fluent_dialog._message_dialog_active is False
print("PASS: nested duplicate message is suppressed and the active message completes")

parent.show()
app.processEvents()
for _ in range(2):
    popup = fluent_dialog._MaskMessageBox("test", "modal lifecycle", parent)
    popup.show()
    app.processEvents()
    assert popup.isVisible()
    popup.accept()
    app.processEvents()
    assert not popup.isVisible()
    assert app.activeModalWidget() is None
    assert parent.isEnabled()
print("PASS: consecutive real message boxes release modality and re-enable parent")

original_dialog_exec = QDialog.exec


def dismiss_real_message(self):
    QTimer.singleShot(50, self.yesButton.click)
    return original_dialog_exec(self)


with patch.object(fluent_dialog._MaskMessageBox, "exec", dismiss_real_message):
    for _ in range(2):
        assert fluent_dialog.msg_info(parent, "real exec", "test") == 1
        app.processEvents()
        assert app.activeModalWidget() is None
        assert parent.isEnabled()
print("PASS: consecutive real MessageBox.exec calls finish without a modal blocker")

window = MainWindow.__new__(MainWindow)
window.api = type("API", (), {"uid": 1})()
window.logger = type("Logger", (), {"log": lambda self, message: None})()
window._season_list_loading = False
with patch("ui.main_window.threading.Thread") as thread:
    window.load_season_list()
    window.load_season_list()
    assert thread.call_count == 1, thread.call_count
    assert window._season_list_loading is True
    observed = []
    window.show_season_select = lambda items: observed.append(
        (items, window._season_list_loading))
    window._on_season_list_loaded([])
    assert observed == [([], True)], observed
    assert window._season_list_loading is False
print("PASS: repeated season-list action starts only one fetch")
