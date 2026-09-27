"""我的关注 —— Fluent 版。

以列表形式列出用户关注的全部 UP 主，每位一行：头像 + 昵称 + 签名 +
「打开TA的个人空间」按钮（+ 浏览器打开主页）。头像在后台线程异步加载，避免阻塞主线程。

风格与 bili23 的「关注」浏览窗口一致：信息浏览型窗口（非勾选列表），点击即跳转，
而非先勾选再批量处理。点击「打开TA的个人空间」会回调 on_open_space(mid)，
由主界面加载该 UP 的视频列表并弹出选择窗口。

外壳为 `ui.fluent_dialog.FluentContentDialog`（Fluent 标题栏 + 内容区 + 底部按钮排），
行内头像用 Fluent 的 `ImageLabel`（圆角），按钮用 Fluent 的 PushButton / 图标按钮。
"""
import requests

from PySide6.QtCore import Qt, QThread, Signal, QByteArray
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QListWidgetItem, QVBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel, CaptionLabel, FluentIcon, ImageLabel, ListWidget, PrimaryPushButton,
    SearchLineEdit, TransparentToolButton,
)

from utils.helpers import optimize_thumbnail_url, open_in_browser
from utils.i18n import tr
from ui.fluent_dialog import FluentContentDialog
from ui.list_layout import LayoutModeToggle, manager, is_compact


class _AvatarLoader(QThread):
    """后台线程：逐个下载头像缩略图，下载完成用信号把字节回传主线程转 QPixmap。"""
    loaded = Signal(str, bytes)

    def __init__(self, urls):
        super().__init__()
        self.urls = list(urls)
        self._stop = False

    def run(self):
        for url in self.urls:
            if self._stop:
                break
            try:
                thumb = optimize_thumbnail_url(url, width=120, height=120)
                resp = requests.get(thumb, timeout=4)
                if resp.status_code == 200:
                    self.loaded.emit(url, resp.content)
            except Exception:
                continue

    def stop(self):
        self._stop = True


class FollowingDialog(FluentContentDialog):
    def __init__(self, parent, following_list, on_open_space):
        super().__init__((880, 660), parent, title=tr("我的关注"))
        self.full_list = list(following_list or [])
        self.on_open_space = on_open_space
        self._closed = False

        self._avatar_labels = {}   # url -> ImageLabel，供线程回调更新
        self._avatar_cache = {}    # url -> QPixmap，已下载头像缓存（搜索重建行时立即复用）
        self._load_gen = 0

        self._build_content()
        self._apply_filter()
        self._start_loader()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_content(self):
        top = QHBoxLayout()
        top.setSpacing(12)
        self.title_label = CaptionLabel("", self)
        top.addWidget(self.title_label)
        top.addStretch(1)
        self.search = SearchLineEdit(self)
        self.search.setPlaceholderText(tr("搜索UP主昵称 / 签名…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        top.addWidget(self.search)
        self.add_layout(top)

        self.list = ListWidget(self)
        self.list.setSpacing(4)
        self.add_widget(self.list, 1)

        # 底部：左侧提示文字 + 右侧「关闭」
        hint = CaptionLabel(tr("点击「打开TA的个人空间」浏览并下载该UP的视频"), self)
        self._leftBtns.addWidget(hint)
        self._leftBtns.insertWidget(0, LayoutModeToggle(self))
        self._closed = False
        self._unsub = manager.connect(lambda _m: self._apply_filter())
        self.close_btn = self.add_button(tr("关闭"), primary=True,
                                        slot=self._do_close)

    # ------------------------------------------------------------------ #
    # 过滤 / 重建行
    # ------------------------------------------------------------------ #
    def _apply_filter(self):
        kw = self.search.text().strip().lower()
        if kw:
            filtered = [
                u for u in self.full_list
                if kw in (u.get("uname", "") or "").lower()
                or kw in (u.get("sign", "") or "").lower()
            ]
        else:
            filtered = list(self.full_list)
        self.title_label.setText(
            tr("我的关注 · 共 {total} 位UP主").format(total=len(self.full_list))
            + (tr("（匹配 {matched}）").format(matched=len(filtered)) if kw else ""))

        self._avatar_labels.clear()
        self.list.clear()
        for u in filtered:
            item = QListWidgetItem()
            row = self._make_row(u)
            item.setSizeHint(row.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, row)

    def _make_row(self, u):
        mid = u.get("mid")
        face = u.get("face", "") or ""
        if face.startswith("//"):
            face = "https:" + face

        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(12)

        avatar = ImageLabel(row)
        avatar.setFixedSize(56, 56)
        avatar.setBorderRadius(28, 28, 28, 28)
        avatar.setText("👤")
        if face:
            self._avatar_labels[face] = avatar
            # 搜索重建行时，若头像此前已下载则立即复用，避免头像消失
            cached = self._avatar_cache.get(face)
            if cached is not None:
                avatar.setImage(cached)
                avatar.setFixedSize(56, 56)
        h.addWidget(avatar)

        info = QVBoxLayout()
        info.setSpacing(2)
        uname = u.get("uname", tr("未知UP主"))
        name = BodyLabel(uname if len(uname) <= 22 else uname[:22] + "…", row)
        sign = u.get("sign", "") or ""
        sign_lab = CaptionLabel((sign[:42] + "…") if len(sign) > 42 else sign, row)
        info.addWidget(name)
        info.addWidget(sign_lab)
        if is_compact():
            sign_lab.hide()
        h.addLayout(info, stretch=1)

        open_btn = PrimaryPushButton(tr("打开TA的个人空间"), row)
        open_btn.clicked.connect(lambda _=False, m=mid: self._open_space(m))
        h.addWidget(open_btn)

        browser_btn = TransparentToolButton(FluentIcon.LINK, row)
        browser_btn.setFixedWidth(36)
        browser_btn.setToolTip(tr("在浏览器中打开主页"))
        browser_btn.clicked.connect(
            lambda _=False, m=mid: open_in_browser(f"https://space.bilibili.com/{m}"))
        h.addWidget(browser_btn)
        return row

    # ------------------------------------------------------------------ #
    # 头像异步加载
    # ------------------------------------------------------------------ #
    def _start_loader(self):
        urls = [u.get("face", "") for u in self.full_list if u.get("face")]
        urls = [("https:" + u) if u.startswith("//") else u for u in urls]
        self._load_gen += 1
        self._worker = _AvatarLoader(urls)
        self._worker.loaded.connect(self._on_avatar_loaded)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_avatar_loaded(self, url, data):
        img = QImage.fromData(QByteArray(data))
        if img.isNull():
            return
        # qfluentwidgets 的 ImageLabel.setImage() 末尾会 setFixedSize(原图尺寸)，
        # 若不先缩放，头像会被撑回 120x120 溢出 56px 圆框导致显示不全。
        pix = QPixmap.fromImage(img).scaled(
            56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._avatar_cache[url] = pix
        lab = self._avatar_labels.get(url)
        if lab is None:
            return
        lab.setImage(pix)
        lab.setFixedSize(56, 56)  # 兜底：强制约束回 56x56 圆框

    # ------------------------------------------------------------------ #
    # 打开空间
    # ------------------------------------------------------------------ #
    def _open_space(self, mid):
        if mid is None or self._closed:
            return
        self.close()
        if callable(self.on_open_space):
            self.on_open_space(mid)

    def _do_close(self):
        self._closed = True
        self.accept()

    def closeEvent(self, event):
        self._closed = True
        try:
            self._unsub()
        except Exception:
            pass
        super().closeEvent(event)

    def closeEvent(self, event):
        self._closed = True
        if getattr(self, "_worker", None) is not None:
            self._worker.stop()
        super().closeEvent(event)
