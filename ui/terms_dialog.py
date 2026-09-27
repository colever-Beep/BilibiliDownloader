"""用户协议窗口（参照 bili23 的 gui/dialog/main_window/terms.py，改用项目 Fluent 风格）。

- 首次启动（``config["accepted_terms"]`` 为 False）由 ``MainWindow.show_terms_of_use``
  弹出；点「同意并继续」写回 ``accepted_terms=True``，点「不同意并退出」/关闭窗口则
  由调用方退出程序。
- 「关于」窗口里的「用户协议」按钮也会复用本窗口做只读查看，此时拒绝/关闭不退出程序。

实现要点：沿用 bili23 的 ``TermsOfUseDialog`` 结构（标题 + 只读 ``TextBrowser`` + 透明
背景），外壳换成项目的 ``FluentContentDialog``（无边框 + Fluent 标题栏）。
"""
from __future__ import annotations

from qfluentwidgets import TextBrowser, setCustomStyleSheet

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

_TERMS_HTML = tr("""<html>本软件仅供个人学习与研究使用。通过本程序下载的任何内容
<b>仅限于个人非商业用途，不得用于任何商业目的、公开传播、分享、转售或非法牟利。</b>
<br><br>
本软件完全基于您本人合法的账号访问权限运行，<b>不会绕过任何付费内容、会员限制或技术保护措施。</b>
您仅可下载通过您在目标平台的正常登录所授权访问的内容。若您的账号无权访问某些内容，不得使用本软件获取之。
<br><br>
<b>请勿使用本软件进行批量抓取、未经授权的再分发，或任何违反目标平台服务条款的行为。</b>
您须对使用本软件所产生的全部后果自行承担责任，包括但不限于账号封禁、版权纠纷或其他法律问题。
<br><br>
在任何情况下，开发者均不对因使用或无法使用本软件所导致的任何直接、间接、附带或后果性损害承担责任。
继续使用本软件即表示您已阅读、理解并自愿接受上述全部条款与风险。
<br><br>
<b>继续使用本软件即表示您已阅读、理解并同意遵守以上全部条款。</b></html>""")


class TermsOfUseDialog(FluentContentDialog):
    def __init__(self, parent=None, config=None):
        super().__init__((640, 520), parent, title=tr("用户协议"))
        # 没有显式传入时回退到默认实例（避免 About 等入口缺失 config 时崩溃）
        self._config = config or ConfigManager("settings.json")

        browser = TextBrowser(self)
        browser.setReadOnly(True)
        browser.setOpenExternalLinks(False)
        browser.setHtml(_TERMS_HTML)
        setCustomStyleSheet(browser, _QSS, _QSS)
        self.add_widget(browser, 1)

        # 左侧「不同意并退出」→ reject；右侧「同意并继续」(primary) → accept
        self.add_button(tr("不同意并退出"), slot=self.reject, right=False)
        self.add_button(tr("同意并继续"), primary=True, slot=self.accept)

    def accept(self):
        # 仅在明确「同意」时落盘，保证「仅首次弹、不接受则退出」语义
        self._config.set("accepted_terms", True)
        super().accept()
