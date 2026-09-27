"""验证 BUG：软件启动时强调色未正常显示（需进设置调整后才正常）。

根因：apply_theme 在配置恰等于模块默认值时「无变更」提前返回，跳过
_apply_qss()/setThemeColor，导致全局 QSS 强调色规则与 Fluent 主题色从未建立。

本脚本模拟「启动 + 默认配置」路径，断言：
1) 首次 apply_theme(默认,默认) 必须真正应用（返回 True）并写入 QSS + 调用 setThemeColor；
2) 之后相同值重复调用应跳过（返回 False，性能保护），但 QSS 仍在；
3) 切换非默认强调色能正确刷新 QSS。
"""
import os, sys, tempfile
os.chdir(tempfile.mkdtemp())
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor
import ui.theme as th

app = QApplication.instance() or QApplication(sys.argv)

# spy setThemeColor / setTheme（保留透传到原函数，否则 qconfig.theme 不更新会误判）
import qfluentwidgets
orig_stc = qfluentwidgets.setThemeColor
orig_st = qfluentwidgets.setTheme
calls = []
theme_calls = []
_timeline = []
def _spy_stc(c, **k):
    calls.append(c)
    _timeline.append("color")
    return orig_stc(c, **k)
def _spy_st(t, **k):
    theme_calls.append(t)
    _timeline.append("theme")
    return orig_st(t, **k)
qfluentwidgets.setThemeColor = _spy_stc
qfluentwidgets.setTheme = _spy_st


def cur_ss():
    return app.styleSheet() or ""


print("=== 启动路径：配置恰好等于模块默认值（绿 + 暗）===")
print("启动前 QSS 长度:", len(cur_ss()), "| 强调色:", th.get_accent())
ret = th.apply_theme(th.DEFAULT_ACCENT, "dark")  # 模拟 apply_theme_from_config()
print("apply_theme(默认,默认) ->", ret, "(期望 True：必须建立基线主题)")
ss = cur_ss().lower()
assert ret is True, "默认配置启动必须应用主题，旧逻辑会提前返回 False"
assert len(ss) > 0, "启动后全局 QSS 必须已写入"
assert th.DEFAULT_ACCENT.lower() in ss, "QSS 必须含默认强调色规则(#accentBtn 等)"
assert len(calls) > 0, "启动必须调用 setThemeColor 给 Fluent 控件上色"
assert len(theme_calls) > 0, "首次建立必须调用 setTheme（强制 Fluent 导航重新取色）"
assert _timeline[:2] == ["color", "theme"], f"顺序必须 setThemeColor 先于 setTheme，实际 {_timeline[:2]}"
print("PASS: 启动即写入 QSS + setThemeColor(先) + setTheme(后)，强调色/Fluent 主题色已建立")

print("\n=== 性能保护：相同值重复调用应跳过 re-polish（不调 setTheme），但 QSS 仍在 ===")
calls.clear(); theme_calls.clear()
ret2 = th.apply_theme(th.DEFAULT_ACCENT, "dark")
print("apply_theme(默认,默认) 再次 ->", ret2, "(期望 False：跳过)")
assert ret2 is False
assert len(cur_ss()) > 0, "跳过后仍保留已写入的 QSS"
assert len(theme_calls) == 0, "重复相同值不应再调 setTheme（保护 10s 轮询性能）"
print("PASS: 重复相同值跳过 re-polish，QSS 保留且不再 setTheme")

print("\n=== 切换非默认强调色应正确刷新（仅 setThemeColor，不重复 setTheme）===")
calls.clear(); theme_calls.clear()
ret3 = th.apply_theme("#2f80ed", "dark")
ss3 = cur_ss().lower()
print("apply_theme(蓝,暗) ->", ret3, "| 强调色:", th.get_accent())
assert ret3 is True
assert "#2f80ed" in ss3, "QSS 应含新强调色"
assert len(calls) > 0
assert len(theme_calls) == 0, "仅改强调色不应重复 setTheme"
print("PASS: 切换强调色正确刷新 QSS + setThemeColor，不重复 setTheme")

# 恢复
qfluentwidgets.setThemeColor = orig_stc
print("\nALL PASS")
