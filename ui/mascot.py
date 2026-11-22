"""Q 版看板娘（原创角色「小粉」）加载与弹窗注入。

四张表情对应四类消息弹窗：
- ``info``     —— 普通提示 / 警告 / 登录欢迎（挥手微笑）
- ``error``    —— 错误 / 失败提示（慌张冒汗）
- ``success``  —— 完成 / 成功提示（欢呼点赞）
- ``question`` —— 询问 / 确认弹窗（歪头思考、头顶问号）

图片随 Qt 资源系统编译进 ``:/bili/mascot/*.png``，开发与打包态一致。

清晰度：原图 1013×714，弹窗显示高约 110px。直接用 SmoothTransformation
缩到 110 在高 DPI 屏（DPR>1）上会因 QPixmap 未带设备像素比而显模糊。
这里按 ``QApplication.devicePixelRatio()`` 生成 DPR 倍像素再 setDevicePixelRatio，
使逻辑尺寸不变、实际像素密度提高，弹窗里看起来锐利。
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

# 确保资源已注册
import res.resources_rc  # noqa: F401,F403

_MASCOT_PATHS = {
    "info": ":/bili/mascot/info.png",
    "error": ":/bili/mascot/error.png",
    "success": ":/bili/mascot/success.png",
    "question": ":/bili/mascot/question.png",
}
# 别名兼容（warn -> info, complete/done -> success, confirm -> question）
_ALIASES = {
    "warn": "info", "warning": "info", "提示": "info", "警告": "info",
    "complete": "success", "done": "success", "完成": "success",
    "fail": "error", "失败": "error",
    "confirm": "question", "ask": "question", "询问": "question", "确认": "question",
}

# 原图缓存：避免每次弹窗都从 qrc 解码 1MB PNG（如果重复弹会卡）
_RAW_CACHE = {}


def _device_pixel_ratio() -> float:
    try:
        app = QGuiApplication.instance()
        dpr = app.devicePixelRatio() if app is not None else 1.0
        return max(1.0, min(float(dpr), 3.0))
    except Exception:
        return 1.0


def mascot_pixmap(kind="info", height=120) -> QPixmap:
    """返回指定表情的看板娘 QPixmap，按逻辑 height 等比缩放且适配高 DPI。

    返回 QPixmap 的 ``height()`` 是逻辑高度（= ``height``），但其像素密度带
    devicePixelRatio，故在高 DPI 屏上不会被拉伸放大导致模糊。
    """
    kind = _ALIASES.get(kind, kind)
    if kind not in _MASCOT_PATHS:
        kind = "info"
    raw = _RAW_CACHE.get(kind)
    if raw is None:
        raw = QPixmap(_MASCOT_PATHS[kind])
        if raw.isNull():
            return raw
        _RAW_CACHE[kind] = raw
    if not height:
        return raw
    dpr = _device_pixel_ratio()
    # 目标像素高度 = 逻辑高度 × DPR，缩放后再标记 DPR，逻辑尺寸回到 height
    px_h = max(1, int(round(height * dpr)))
    pm = raw.scaledToHeight(px_h, Qt.SmoothTransformation)
    pm.setDevicePixelRatio(dpr)
    return pm


def make_mascot_label(kind="info", height=120, parent=None) -> QLabel:
    """创建显示看板娘的 QLabel（透明背景、居中）。图片缺失时返回空标签。"""
    lab = QLabel(parent)
    lab.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
    lab.setAttribute(Qt.WA_TranslucentBackground, True)
    pm = mascot_pixmap(kind, height)
    if not pm.isNull():
        lab.setPixmap(pm)
        # 用逻辑尺寸固定 QLabel（pm.size() 已含 DPR，需除以 DPR 得逻辑尺寸）
        lab.setFixedSize(pm.width() // pm.devicePixelRatio(),
                         pm.height() // pm.devicePixelRatio())
    return lab


def inject_into_message_box(mb: QWidget, kind="info", height=110) -> bool:
    """把看板娘注入 qfluentwidgets MessageBox，顺序为「标题 → 看板娘 → 正文」。

    MessageBox 内部结构：``mb.textLayout`` 是 QVBoxLayout，含 [titleLabel(0), contentLabel(1)]。
    在索引 1 插入看板娘后：标题(0) → 看板娘(1) → 正文(2)，图片显示于标题下方、
    正文上方居中——符合「先看标题，再看角色表情，最后读正文」的阅读顺序。

    返回是否注入成功；任何结构差异都静默失败，不影响弹窗正常显示。
    """
    try:
        layout = getattr(mb, "textLayout", None)
        pm = mascot_pixmap(kind, height)
        if layout is None or pm.isNull():
            return False
        lab = QLabel(mb)
        lab.setAlignment(Qt.AlignHCenter)
        lab.setPixmap(pm)
        lab.setFixedSize(pm.width() // pm.devicePixelRatio(),
                         pm.height() // pm.devicePixelRatio())
        # 插入到标题(0)之后、正文之前 => 索引 1
        insert_at = 1 if layout.count() >= 2 else 0
        layout.insertWidget(insert_at, lab)
        try:
            # 弹窗默认尺寸偏窄，加图后适当加高，避免正文被挤压
            mb.setFixedHeight(mb.height() + int(height * 0.8))
        except Exception:
            pass
        return True
    except Exception:
        return False
