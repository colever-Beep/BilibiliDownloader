#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证真实入口 main.py 能在 offscreen 下启动并进入事件循环后正常退出。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer
import PySide6.QtWidgets as W

_orig_exec = W.QApplication.exec

def _patched_exec(self=None):
    # 进入事件循环 300ms 后自动退出，验证事件循环可正常启动/退出
    QTimer.singleShot(300, lambda: W.QApplication.instance().quit())
    return _orig_exec()

W.QApplication.exec = staticmethod(_patched_exec)

import main
main.main()
print("MAIN_ENTRY_OK: 真实入口启动并正常退出")
