"""软件内反馈页：收集 Bug 反馈 / 功能建议，提交到 GitHub Issues。

设计目标（参照产品流程图）：
1. 选择反馈类型 + 说明问题/建议，填写内容自动存为本地草稿，中途离开不丢失；
2. 点「提交反馈」→ 用 GitHub 的预填参数打开新建 Issue 页（标题/正文/标签已填好），
   用户只需在浏览器点一次「Submit new issue」，无需手动整理格式；
3. 反馈进入公开议题区，由 AI 预筛（若仓库配置密钥）+ 维护者人工决定 open/closed。

本页为内联 QWidget，接入主窗口 content_stack，侧边栏「反馈」项进入。
"""
from __future__ import annotations

import json
import os
import platform
import threading
import urllib.parse

import requests
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel, CaptionLabel, ComboBox, FluentIcon, PrimaryPushButton,
    PushButton, RadioButton, TextEdit, TransparentToolButton, LineEdit,
)

from utils.i18n import tr, register
from utils.helpers import open_in_browser
from utils.main_thread import run_on_main
from utils.version import APP_VERSION
from ui.fluent_dialog import msg_warn, msg_info
from ui.content_pages import _Header

# GitHub 仓库与 Issue 预填入口
_REPO_URL = "https://github.com/colever-Beep/BilibiliDownloader"
_ISSUES_NEW = _REPO_URL + "/issues/new"

# 反馈类型：内部值（不翻译）-> (显示文案翻译键, 标签, 标题前缀)
_FEEDBACK_TYPES = {
    "bug": ("Bug 反馈", "bug", "[Bug]: "),
    "feature": ("功能建议", "enhancement", "[建议]: "),
}
_TYPE_ORDER = ("bug", "feature")

# 草稿文件路径：放在用户配置目录，跟随 config 的目录约定
_DRAFT_FILENAME = "feedback_draft.json"


def _draft_path(config=None):
    """返回草稿文件路径：优先用 config 暴露的配置目录，否则用项目根。"""
    candidate = None
    if config is not None:
        for attr in ("config_dir", "config_path", "data_dir"):
            val = getattr(config, attr, None)
            if isinstance(val, str) and val:
                candidate = os.path.dirname(val) if attr == "config_path" else val
                break
    if candidate and os.path.isdir(candidate):
        return os.path.join(candidate, _DRAFT_FILENAME)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), _DRAFT_FILENAME)


class FeedbackPage(QWidget):
    """软件内反馈页。"""

    def __init__(self, parent=None, config=None, on_back=None):
        super().__init__(parent)
        self.config = config
        self._on_back = on_back
        self._draft_file = _draft_path(config)
        self._loading = False
        self._build()
        self._load_draft()

    # ------------------------------------------------------------------ #
    # 构建
    # ------------------------------------------------------------------ #
    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(14)

        # 页头：返回 + 标题
        self.header = _Header(self, title_key="反馈与建议")
        self.header.backClicked.connect(self._on_back_clicked)
        lay.addWidget(self.header)

        # 三步流程说明（横向卡片，参考产品流程图）
        intro = CaptionLabel(
            tr("填写反馈后将在浏览器打开已填好的 GitHub 议题页，确认无误点发布即可。"
               "内容会先存为本地草稿，中途离开不会丢失。"), self)
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.intro_lbl = intro
        register(intro, "填写反馈后将在浏览器打开已填好的 GitHub 议题页，确认无误点发布即可。"
                        "内容会先存为本地草稿，中途离开不会丢失。")

        # 反馈类型（RadioButton 水平排列）
        type_row = QHBoxLayout()
        type_row.setSpacing(12)
        self.type_buttons = {}
        for key in _TYPE_ORDER:
            text_key = _FEEDBACK_TYPES[key][0]
            rb = RadioButton(tr(text_key), self)
            rb.setChecked(key == "bug")
            rb.clicked.connect(lambda _c=False, k=key: self._on_type_changed(k))
            self.type_buttons[key] = rb
            type_row.addWidget(rb)
            register(rb, text_key)
        type_row.addStretch(1)
        lay.addLayout(type_row)

        # 标题
        self.title_edit = LineEdit(self)
        self.title_edit.setPlaceholderText(tr("一句话概括你的问题或建议"))
        self.title_edit.setFixedHeight(38)
        register(self.title_edit, "一句话概括你的问题或建议", attr="placeholder_text")
        lay.addWidget(self.title_edit)

        # 正文
        self.body_edit = TextEdit(self)
        self.body_edit.setPlaceholderText(
            tr("请详细描述：问题现象 / 复现步骤 / 期望结果，或建议的使用场景与方案"))
        register(self.body_edit, "请详细描述：问题现象 / 复现步骤 / 期望结果，或建议的使用场景与方案",
                 attr="placeholder_text")
        lay.addWidget(self.body_edit, 1)

        # 环境信息（自动附带，只读）
        env = (f"v{APP_VERSION} · {platform.system()} {platform.release()}")
        self.env_lbl = CaptionLabel(tr("将自动附带环境信息：") + env, self)
        lay.addWidget(self.env_lbl)

        # 状态提示（草稿保存状态）
        self.status_lbl = CaptionLabel("", self)
        lay.addWidget(self.status_lbl)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.submit_btn = PrimaryPushButton(tr("提交反馈"), self)
        self.submit_btn.clicked.connect(self._on_submit)
        self.clear_btn = PushButton(tr("清空草稿"), self)
        self.clear_btn.clicked.connect(self._on_clear)
        btn_row.addWidget(self.submit_btn)
        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        register(self.submit_btn, "提交反馈")
        register(self.clear_btn, "清空草稿")

        # 输入变化 -> 自动存草稿
        self.title_edit.textChanged.connect(self._on_input_changed)
        self.body_edit.textChanged.connect(self._on_input_changed)

    # ------------------------------------------------------------------ #
    # 类型 / 输入
    # ------------------------------------------------------------------ #
    def _current_type(self):
        for key in _TYPE_ORDER:
            if self.type_buttons[key].isChecked():
                return key
        return "bug"

    def _on_type_changed(self, _key):
        self._save_draft()

    def _on_input_changed(self, *_args):
        self._save_draft()

    # ------------------------------------------------------------------ #
    # 草稿
    # ------------------------------------------------------------------ #
    def _collect_draft(self):
        return {
            "type": self._current_type(),
            "title": self.title_edit.text(),
            "body": self.body_edit.toPlainText(),
        }

    def _save_draft(self):
        if self._loading:
            return
        try:
            os.makedirs(os.path.dirname(self._draft_file), exist_ok=True)
            with open(self._draft_file, "w", encoding="utf-8") as f:
                json.dump(self._collect_draft(), f, ensure_ascii=False, indent=2)
            self.status_lbl.setText(tr("草稿已自动保存"))
        except Exception:
            self.status_lbl.setText(tr("草稿保存失败（不影响提交）"))

    def _load_draft(self):
        if not os.path.exists(self._draft_file):
            return
        try:
            with open(self._draft_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        self._loading = True
        try:
            ftype = data.get("type", "bug")
            if ftype in self.type_buttons:
                self.type_buttons[ftype].setChecked(True)
            self.title_edit.setText(data.get("title", ""))
            self.body_edit.setPlainText(data.get("body", ""))
            self.status_lbl.setText(tr("已恢复上次的草稿"))
        finally:
            self._loading = False

    def _on_clear(self):
        self._loading = True
        try:
            self.title_edit.clear()
            self.body_edit.clear()
            self.type_buttons["bug"].setChecked(True)
        finally:
            self._loading = False
        try:
            if os.path.exists(self._draft_file):
                os.remove(self._draft_file)
        except Exception:
            pass
        self.status_lbl.setText(tr("草稿已清空"))

    # ------------------------------------------------------------------ #
    # 提交
    # ------------------------------------------------------------------ #
    def _build_issue_url(self, title, body):
        """生成 GitHub 预填 Issue 链接（标题 / 正文 / 标签）。"""
        ftype = self._current_type()
        _text_key, label, prefix = _FEEDBACK_TYPES[ftype]
        full_title = prefix + title
        env = f"v{APP_VERSION} · {platform.system()} {platform.release()}"
        full_body = f"{body}\n\n---\n\n> 由软件内反馈页提交 · 环境：{env}\n"
        query = urllib.parse.urlencode(
            {"title": full_title, "body": full_body, "labels": label}
        )
        return f"{_ISSUES_NEW}?{query}"

    def _proxy_url(self):
        """返回配置的反馈代理端点（可选）；未配置返回空串。"""
        try:
            if self.config is not None:
                return (self.config.get("feedback_proxy_url", "") or "").strip()
        except Exception:
            pass
        return ""

    def _on_submit(self):
        title = self.title_edit.text().strip()
        body = self.body_edit.toPlainText().strip()
        if not title or not body:
            msg_warn(self, tr("请填写标题和详细内容后再提交"), tr("反馈信息不完整"))
            return
        self._save_draft()  # 保留草稿，直到确认发布成功
        ftype = self._current_type()
        proxy = self._proxy_url()
        if proxy:
            self._submit_via_proxy(proxy, ftype, title, body)
        else:
            self._submit_via_browser(ftype, title, body)

    def _submit_via_browser(self, ftype, title, body):
        """回退方案：打开预填好的 GitHub Issue 页，用户手动点发布。"""
        url = self._build_issue_url(title, body)
        open_in_browser(url)  # 守护线程打开，避免 GIL 崩溃
        msg_info(self, tr("已在浏览器打开发布页面，确认无误后点击 Submit new issue 即可。"
                          "你的反馈进入公开议题区后，会由 AI 预筛 + 维护者审核决定是否采纳。"),
                 tr("即将提交反馈"))

    def _submit_via_proxy(self, proxy, ftype, title, body):
        """走代理直接建 Issue（免登录免跳出）；失败自动回退浏览器预填页。"""
        _text_key, label, prefix = _FEEDBACK_TYPES[ftype]
        env = f"v{APP_VERSION} · {platform.system()} {platform.release()}"
        payload = {
            "type": ftype,
            "title": prefix + title,
            "body": f"{body}\n\n---\n\n> 由软件内反馈页提交 · 环境：{env}\n",
            "labels": [label],
        }
        self.submit_btn.setEnabled(False)
        self.status_lbl.setText(tr("正在提交反馈..."))

        def worker():
            ok = False
            issue_url = ""
            try:
                resp = requests.post(proxy, json=payload, timeout=20)
                ok = 200 <= resp.status_code < 300
                try:
                    issue_url = (resp.json() or {}).get("html_url", "")
                except Exception:
                    pass
            except Exception:
                ok = False
            run_on_main(lambda: self._on_proxy_done(ok, issue_url, ftype, title, body))

        threading.Thread(target=worker, daemon=True).start()

    def _on_proxy_done(self, ok, issue_url, ftype, title, body):
        self.submit_btn.setEnabled(True)
        if ok:
            self.status_lbl.setText(tr("提交成功"))
            self._clear_draft_file()
            self.title_edit.clear()
            self.body_edit.clear()
            msg_info(self,
                     (tr("反馈已提交：") + issue_url) if issue_url else tr("反馈已成功提交，感谢你的支持！"),
                     tr("提交成功"))
        else:
            self.status_lbl.setText(tr("代理提交失败，已改为打开浏览器发布页"))
            self._submit_via_browser(ftype, title, body)

    def _clear_draft_file(self):
        try:
            if os.path.exists(self._draft_file):
                os.remove(self._draft_file)
        except Exception:
            pass

    def _on_back_clicked(self):
        if callable(self._on_back):
            self._on_back()

    # ------------------------------------------------------------------ #
    # 多语言
    # ------------------------------------------------------------------ #
    def retranslate(self):
        self.header.retranslate()
        self.title_edit.setPlaceholderText(tr("一句话概括你的问题或建议"))
        self.body_edit.setPlaceholderText(
            tr("请详细描述：问题现象 / 复现步骤 / 期望结果，或建议的使用场景与方案"))
        self.env_lbl.setText(
            tr("将自动附带环境信息：") + f"v{APP_VERSION} · {platform.system()} {platform.release()}")
        self.submit_btn.setText(tr("提交反馈"))
        self.clear_btn.setText(tr("清空草稿"))
        for key, rb in self.type_buttons.items():
            rb.setText(tr(_FEEDBACK_TYPES[key][0]))
