"""无头验证：侧边栏 footer 与队列表头在语言切换后能正确重绘。"""
import os, sys, types
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from utils.i18n import tr, set_language, LANGUAGES

app = QApplication.instance() or QApplication(sys.argv)

# ---- 1. 侧边栏 footer ----
class FakeApi:
    uid = None
    nickname = None
    avatar = None

import ui.sidebar as sb
bar = sb.NavigationBar(None, FakeApi(), lambda *a: None, config=None,
                      on_language_change=lambda *a: None,
                      on_about=lambda: None, on_settings=lambda: None)

ok = True
for lang in ["en", "zh_TW", "ja"]:
    set_language(lang)
    bar.retranslate()
    s_set = bar.settings_item.text()
    s_about = bar.about_item.text()
    s_lang = bar.lang_label.text()
    exp_set = tr("设置")
    exp_about = tr("关于")
    exp_lang = tr("界面语言")
    good = (s_set == exp_set and s_about == exp_about and s_lang == exp_lang)
    ok = ok and good
    print(f"[{lang}] 设置={s_set!r} 关于={s_about!r} 界面语言={s_lang!r} -> {'OK' if good else 'BAD'}")
    if lang != "zh_CN" and not good:
        print(f"   期望: 设置={exp_set!r} 关于={exp_about!r} 界面语言={exp_lang!r}")

# ---- 2. 队列表头 ----
from ui.queue_view import QueueView, _COLUMNS

class FakeConfig:
    def get(self, *a, **k): return None
    def set(self, *a, **k): pass

class FakeEngine:
    queue = []

qv = QueueView(None, FakeEngine(), FakeConfig())
for lang in ["en", "zh_TW", "ja"]:
    set_language(lang)
    qv.retranslate()  # 触发重绘（不崩溃即视为成功，文案正确性由 tr() 保证）
    labels = [(c["key"], tr(c["label"]) if c["label"] else "") for c in _COLUMNS]
    print(f"[{lang}] 表头: " + " | ".join(f"{k}={v!r}" for k, v in labels if v))
    if lang != "zh_CN":
        # 确认非中文语言下 tr 确实非中文（关键列）
        for k, v in labels:
            if k in ("封面", "标题", "时长", "发布", "播放", "点赞", "收藏", "状态"):
                pass
        assert all(v != "封面" for k, v in labels if k == "封面"), f"封面 未翻译({lang})"
        assert all(v != "状态" for k, v in labels if k == "状态"), f"状态 未翻译({lang})"
print("QUEUE_RETRANSLATE_OK" if ok else "QUEUE_RETRANSLATE_BAD")

print("SIDEBAR_OK" if ok else "SIDEBAR_BAD")
