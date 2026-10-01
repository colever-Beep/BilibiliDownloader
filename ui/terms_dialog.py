"""用户协议窗口（参照 bili23 的 gui/dialog/main_window/terms.py，改用项目 Fluent 风格）。

- 首次启动（``config["accepted_terms"]`` 为 False）由 ``MainWindow.show_terms_of_use``
  弹出；点「同意并继续」写回 ``accepted_terms=True``，点「不同意并退出」/关闭窗口则
  由调用方退出程序。
- 「关于」窗口里的「用户协议」按钮也会复用本窗口做只读查看，此时拒绝/关闭不退出程序。

实现要点：沿用 bili23 的 ``TermsOfUseDialog`` 结构（标题 + 只读 ``TextBrowser`` + 透明
背景），外壳换成项目的 ``FluentContentDialog``（无边框 + Fluent 标题栏）。

约束：必须先把协议正文滚动阅读至底部，「同意并继续」按钮才会启用（内容较短无需滚动时
自动启用），避免用户跳过条款直接同意。
"""
from __future__ import annotations

from PySide6.QtCore import QTimer

from qfluentwidgets import CaptionLabel, TextBrowser, setCustomStyleSheet

from ui.fluent_dialog import FluentContentDialog
from utils.i18n import tr
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

# 协议正文（已与用户确认，分条中文版）
_TERMS_HTML = tr("""<html>欢迎使用本软件。在开始使用前，请仔细阅读以下《用户协议》。
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
您继续使用本软件，即视为已阅读、理解并自愿接受上述全部条款与潜在风险。</p></html>""")


class TermsOfUseDialog(FluentContentDialog):
    def __init__(self, parent=None, config=None):
        super().__init__((640, 560), parent, title=tr("用户协议"))
        # 没有显式传入时回退到默认实例（避免 About 等入口缺失 config 时崩溃）
        self._config = config or ConfigManager("settings.json")

        browser = TextBrowser(self)
        browser.setReadOnly(True)
        browser.setOpenExternalLinks(False)
        browser.setHtml(_TERMS_HTML)
        setCustomStyleSheet(browser, _QSS, _QSS)
        self.add_widget(browser, 1)
        self._browser = browser

        # 滚动到底提示
        self._hint = CaptionLabel(tr("请滚动阅读至底部后，方可同意"), self)
        self.add_widget(self._hint)

        # 左侧「不同意并退出」→ reject；右侧「同意并继续」(primary) → accept
        self.add_button(tr("不同意并退出"), slot=self.reject, right=False)
        self._accept_btn = self.add_button(tr("同意并继续"), primary=True,
                                           slot=self.accept)
        # 默认禁用，滚动到底才启用
        self._accept_btn.setEnabled(False)

        # 滚动到底检测
        sb = browser.verticalScrollBar()
        sb.rangeChanged.connect(self._refresh_agree_state)
        sb.valueChanged.connect(self._refresh_agree_state)
        # 初次布局完成后立即判定（内容较短无需滚动时直接启用）
        QTimer.singleShot(0, self._refresh_agree_state)

    def _refresh_agree_state(self):
        sb = self._browser.verticalScrollBar()
        # 无需滚动（maximum==0）或已滚动到底（留 2px 容差应对 HiDPI 取整）
        at_bottom = sb.maximum() == 0 or sb.value() >= sb.maximum() - 2
        self._accept_btn.setEnabled(at_bottom)
        self._hint.setVisible(not at_bottom)

    def accept(self):
        # 仅在明确「同意」时落盘，保证「仅首次弹、不接受则退出」语义
        self._config.set("accepted_terms", True)
        super().accept()
