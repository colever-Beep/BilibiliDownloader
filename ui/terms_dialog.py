"""用户协议窗口（参照 bili23 的 gui/dialog/main_window/terms.py，改用项目 Fluent 风格）。

- 首次启动（``config["accepted_terms"]`` 为 False）由 ``MainWindow.show_terms_of_use``
  弹出；点「同意并继续」写回 ``accepted_terms=True``，点「不同意并退出」/关闭窗口则
  由调用方退出程序。
- 「关于」窗口里的「用户协议」按钮也会复用本窗口做只读查看，此时拒绝/关闭不退出程序。

2.2.0 起：顶部用**水平布局管理器**（QHBoxLayout）罗列简体中文 / 繁體中文 / English /
日本語 四种语言按钮；点选任一语言即把**同一份协议正文**切换为对应语言版本，并自动
切换软件界面语言（set_language + 配置持久化 + on_language_change 回调），无需再到
设置页手动切换。

约束：必须先把「当前选中语言」的协议正文滚动阅读至底部，「同意并继续」才启用
（内容较短无需滚动时自动启用），避免用户跳过条款直接同意。切换语言后正文已更换，
需重新滚动阅读该语言版本才能再次启用。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout

from qfluentwidgets import (
    CaptionLabel, PushButton, SubtitleLabel, TextBrowser, setCustomStyleSheet,
)

from ui.fluent_dialog import FluentDialogBase
from ui.mascot import make_mascot_label
from utils.i18n import (
    tr, set_language, get_language, retranslate_all, LANGUAGES,
)
from config import ConfigManager

# 透明背景，贴合 Fluent 主题（bili23 同款做法）
_QSS = """TextBrowser {
    border: none;
    background-color: transparent;
}

TextBrowser:hover {
    background-color: transparent;
}

TextBrowser:focus {
    background-color: transparent;
}"""

# 协议正文（按语言 code 索引；同一时刻只显示其中一份）
_TERMS_BY_LANG = {
    "zh_CN": """<html>欢迎使用本软件。在开始使用前，请仔细阅读以下《用户协议》。
当您点击「同意并继续」时，即表示您已阅读、理解并同意遵守全部条款。

<p><b>一、使用目的</b><br>
本软件仅供个人学习、研究与非商业用途。通过本软件获取的任何内容，
<b>仅限于您个人合理使用，不得用于任何商业目的、公开传播、分享、转售或非法牟利。</b></p>

<p><b>二、访问权限</b><br>
本软件基于您本人合法的账号登录状态运行，<b>不绕过任何付费内容、会员限制或技术保护措施</b>。
您仅可访问通过正常登录所授权的内容；对无权限的内容，不得借助本软件获取。</p>

<p><b>三、禁止行为</b><br>
<b>请勿使用本软件进行批量抓取、未经授权的再分发，或任何违反目标平台服务条款的行为。</b>
您须对自身使用行为负全部责任，包括但不限于账号封禁、版权纠纷及由此引发的法律责任。</p>

<p><b>四、责任限制</b><br>
在任何情况下，开发者均不对因使用或无法使用本软件造成的任何直接、间接、附带或后果性损害承担责任。</p>

<p><b>五、协议生效</b><br>
您继续使用本软件，即视为已阅读、理解并自愿接受上述全部条款与潜在风险。</p></html>""",

    "zh_TW": """<html>歡迎使用本軟體。在開始使用前，請仔細閱讀以下《使用者協議》。
當您點擊「同意並繼續」時，即表示您已閱讀、理解並同意遵守全部條款。

<p><b>一、使用目的</b><br>
本軟體僅供個人學習、研究與非商業用途。透過本軟體取得的任何內容，
<b>僅限於您個人合理使用，不得用於任何商業目的、公開傳播、分享、轉售或非法牟利。</b></p>

<p><b>二、存取權限</b><br>
本軟體基於您本人合法的帳號登入狀態運行，<b>不繞過任何付費內容、會員限制或技術保護措施</b>。
您僅可存取透過正常登入所授權的內容；對無權限的內容，不得借助本軟體取得。</p>

<p><b>三、禁止行為</b><br>
<b>請勿使用本軟體進行批量抓取、未經授權的再散發，或任何違反目標平台服務條款的行為。</b>
您須對自身使用行為負全部責任，包括但不限於帳號封禁、版權糾紛及由此引發的法律責任。</p>

<p><b>四、責任限制</b><br>
在任何情況下，開發者均不對因使用或無法使用本軟體造成的任何直接、間接、附帶或後果性損害承擔責任。</p>

<p><b>五、協議生效</b><br>
您繼續使用本軟體，即視為已閱讀、理解並自願接受上述全部條款與潛在風險。</p></html>""",

    "en": """<html>Welcome to this software. Before you begin, please read the following User Agreement carefully.
By clicking "Agree and Continue", you confirm that you have read, understood, and agreed to comply with all terms.

<p><b>1. Purpose of Use</b><br>
This software is intended only for personal study, research, and non-commercial use. Any content obtained through it
<b>is for your personal, reasonable use only and must not be used for any commercial purpose, public distribution, sharing, resale, or illegal profit.</b></p>

<p><b>2. Access Rights</b><br>
This software operates based on your own lawful logged-in account, and <b>does not bypass any paid content, membership restrictions, or technical protection measures</b>.
You may only access content authorized through normal login; you must not use this software to obtain content you are not entitled to.</p>

<p><b>3. Prohibited Conduct</b><br>
<b>Do not use this software for bulk scraping, unauthorized redistribution, or any action that violates the target platform's terms of service.</b>
You are fully responsible for your own use, including but not limited to account suspension, copyright disputes, and resulting legal liability.</p>

<p><b>4. Limitation of Liability</b><br>
Under no circumstances shall the developer be liable for any direct, indirect, incidental, or consequential damages arising from the use or inability to use this software.</p>

<p><b>5. Effectiveness</b><br>
Your continued use of this software constitutes that you have read, understood, and voluntarily accepted all of the above terms and potential risks.</p></html>""",

    "ja": """<html>本ソフトウェアへようこそ。ご利用前に、以下の「利用規約」をよくお読みください。
「同意して続ける」をクリックした時点で、すべての条項を読み、理解し、遵守することに同意したものとみなされます。

<p><b>1. 利用目的</b><br>
本ソフトウェアは個人の学習・研究・非商用目的にのみ使用できます。本ソフトウェアで取得したコンテンツは
<b>個人の合理的な利用に限定され、商業目的、公開配布、共有、転売、違法な利益目的での利用は禁止されています。</b></p>

<p><b>2. アクセス権限</b><br>
本ソフトウェアはご自身の合法的なログイン状態に基づいて動作し、<b>有料コンテンツ、会員制限、技術的保護手段を回避しません</b>。
通常のログインで許可されたコンテンツにのみアクセスでき、権限のないコンテンツを取得してはなりません。</p>

<p><b>3. 禁止行為</b><br>
<b>本ソフトウェアを用いた一括スクレイピング、無許可の再配布、または対象プラットフォームの利用規約に違反する行為は行わないでください。</b>
アカウント停止、著作権紛争、およびそれに伴う法的責任を含む、利用行為に対する全責任はご自身にあります。</p>

<p><b>4. 責任制限</b><br>
本ソフトウェアの使用または使用不能により生じる直接・間接・付随・結果的損害について、開発者は一切の責任を負いません。</p>

<p><b>5. 規約の発効</b><br>
本ソフトウェアを継続して使用することは、上記のすべての条項および潜在的なリスクを読み、理解し、自主的に受け入れたものとみなされます。</p></html>""",
}


class TermsOfUseDialog(FluentDialogBase):
    def __init__(self, parent=None, config=None, on_language_change=None):
        # MessageBoxBase 是真正的 QDialog，无自制标题栏；标题用 SubtitleLabel 呈现
        super().__init__(parent, minimum_size=(1000, 620))
        # 没有显式传入时回退到默认实例（避免 About 等入口缺失 config 时崩溃）
        self._config = config or ConfigManager("settings.json")
        self._on_language_change = on_language_change

        saved = self._config.get("language", None) or get_language()
        self._current = saved if saved in _TERMS_BY_LANG else "zh_CN"

        # ---- 标题（MessageBoxBase 无标题栏）----
        self._title_lbl = SubtitleLabel(tr("用户协议"), self.widget)
        self.viewLayout.addWidget(self._title_lbl)

        # ---- 顶部：语言选择按钮（水平布局管理器罗列）----
        lang_row = QHBoxLayout()
        lang_row.setSpacing(6)
        self._lang_buttons = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for code, label in LANGUAGES.items():
            btn = PushButton(label, self.widget)
            btn.setCheckable(True)
            btn.setChecked(code == self._current)
            btn.clicked.connect(lambda _=False, c=code: self._select_language(c))
            group.addButton(btn)
            self._lang_buttons[code] = btn
            lang_row.addWidget(btn)
        lang_row.addStretch(1)
        self.viewLayout.addLayout(lang_row)

        # ---- 看板娘：欢迎表情，位于标题下方、协议正文上方 ----
        # 顺序与消息弹窗一致（标题 → 看板娘 → 正文），让首次启动的欢迎页同样有角色陪伴。
        self.mascot_lbl = make_mascot_label("info", 96, self.widget)
        if self.mascot_lbl.pixmap() is None or self.mascot_lbl.pixmap().isNull():
            self.mascot_lbl.hide()
        self.viewLayout.addWidget(self.mascot_lbl, 0, Qt.AlignHCenter)

        # ---- 主体：同一时刻只有一份协议正文，点语言按钮切换其内容 ----
        self._browser = TextBrowser(self.widget)
        self._browser.setReadOnly(True)
        self._browser.setOpenExternalLinks(False)
        setCustomStyleSheet(self._browser, _QSS, _QSS)
        self._browser.setHtml(_TERMS_BY_LANG.get(self._current, _TERMS_BY_LANG["zh_CN"]))
        self.viewLayout.addWidget(self._browser, 1)
        # 滚动到底检测只绑定这一份正文；切换语言时 setHtml 会复位滚动条
        sb = self._browser.verticalScrollBar()
        sb.rangeChanged.connect(self._refresh_agree_state)
        sb.valueChanged.connect(self._refresh_agree_state)

        # 滚动到底提示
        self._hint = CaptionLabel(tr("请滚动阅读至底部后，方可同意"), self.widget)
        self.viewLayout.addWidget(self._hint)

        # 左侧「不同意并退出」→ reject；右侧「同意并继续」(primary) → accept
        # MessageBoxBase 的 yesButton/cancelButton 默认已连 accept/reject，仅改文案。
        # validate() 在 accept 前校验必须滚动到底，比单纯禁用按钮更可靠。
        self.yesButton.setText(tr("同意并继续"))
        self.cancelButton.setText(tr("不同意并退出"))
        self._disagree_btn = self.cancelButton
        self._accept_btn = self.yesButton
        # 默认禁用，滚动到底才启用
        self._accept_btn.setEnabled(False)

        # 初次布局完成后立即判定（内容较短无需滚动时直接启用）
        QTimer.singleShot(0, self._refresh_agree_state)

    # ------------------------------------------------------------------ #
    # 语言切换
    # ------------------------------------------------------------------ #
    def _select_language(self, code):
        """点选语言：把同一份正文切换为该语言版本，并自动切换软件界面语言。"""
        if code not in _TERMS_BY_LANG or code == self._current:
            return
        self._current = code
        for c, btn in self._lang_buttons.items():
            btn.setChecked(c == code)

        # 只切换这一份正文的内容（不是并排显示多份）
        self._browser.setHtml(_TERMS_BY_LANG[code])
        self._browser.verticalScrollBar().setValue(0)
        # 正文已更换：需重新滚动阅读该语言版本才能再次启用同意
        self._accept_btn.setEnabled(False)
        self._hint.setVisible(True)

        # 切换全局语言 + 持久化
        set_language(code)
        try:
            self._config.set("language", code)
        except Exception:
            pass
        # 通知主窗口即时重译（若调用方提供回调）；否则直接刷新已注册控件
        if callable(self._on_language_change):
            try:
                self._on_language_change(code)
            except Exception:
                retranslate_all()
        else:
            retranslate_all()

        # 本对话框自身静态文案（未走 register()，手动刷新）
        # 无边框对话框 setWindowTitle 不可见，改为刷新内部标题标签
        self._title_lbl.setText(tr("用户协议"))
        self._hint.setText(tr("请滚动阅读至底部后，方可同意"))
        self._disagree_btn.setText(tr("不同意并退出"))
        self._accept_btn.setText(tr("同意并继续"))

        # 等新正文布局完成后再判定（setHtml 后 maximum 可能暂时为 0）
        QTimer.singleShot(0, self._refresh_agree_state)

    # ------------------------------------------------------------------ #
    # 滚动到底检测
    # ------------------------------------------------------------------ #
    def _at_bottom(self) -> bool:
        sb = self._browser.verticalScrollBar()
        # 无需滚动（maximum==0）或已滚动到底（留 2px 容差应对 HiDPI 取整）
        return sb.maximum() == 0 or sb.value() >= sb.maximum() - 2

    def _refresh_agree_state(self):
        at_bottom = self._at_bottom()
        self._accept_btn.setEnabled(at_bottom)
        self._hint.setVisible(not at_bottom)

    def validate(self) -> bool:
        """MessageBoxBase 在 yesButton 点击时调用；未读到底则拦截 accept。"""
        if not self._at_bottom():
            self._hint.setVisible(True)
            return False
        return True

    def accept(self):
        # 仅在明确「同意」时落盘，保证「仅首次弹、不接受则退出」语义
        self._config.set("accepted_terms", True)
        # 界面语言已在 _select_language 时持久化，这里兜底确保一致
        self._config.set("language", self._current)
        super().accept()
