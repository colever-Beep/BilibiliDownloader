# utils/bili_qrcode.py
"""B站二维码登录（passport 接口）。

参照 bili23_example 的招牌二维码登录能力，封装两个 passport 接口：
  - 生成二维码：/x/passport-login/web/qrcode/generate
  - 轮询扫码状态：/x/passport-login/web/qrcode/poll

成功时，passport 会在响应的 ``Set-Cookie`` 中写入会话 Cookie，并把最终跳转地址
放在 ``data.url``（含 SESSDATA / bili_jct / DedeUserID 等查询参数）。两者都会
同步进传入的 ``requests.Session``，供上层 ``BiliAPI.session`` 直接使用。

二维码图像用 ``qrcode`` 库渲染（已安装）；若该库缺失则回退到 ``segno``。
"""
from __future__ import annotations

from urllib.parse import urlencode, urlparse, parse_qs

import requests

# 扫码状态码（poll 响应 data.code）
SCAN_SUCCESS = 0            # 登录成功
SCAN_EXPIRED = 86038        # 二维码已失效
SCAN_CONFIRMED = 86090      # 已扫码，待用户在手机端确认
SCAN_WAITING = 86101        # 未扫码，等待扫描

# 成功登录后需要落盘的关键 Cookie 名
_COOKIE_KEYS = ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5")

_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"


def _render(text, box_size=8, border=4):
    """把二维码文本渲染成黑白 PIL.Image。优先 qrcode，缺失则回退 segno。"""
    try:
        import qrcode
        qr = qrcode.QRCode(
            box_size=box_size,
            border=border,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
        )
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
    except Exception:
        import segno
        qr = segno.make(text, error="m")
        img = qr.to_pil(scale=box_size, border=border, dark="black", light="white")
    # 统一转成 RGB，确保 customtkinter 的 CTkImage 能正常接收
    if getattr(img, "mode", None) != "RGB":
        img = img.convert("RGB")
    return img


def generate_qr(session, timeout=15):
    """生成登录二维码。

    参数
    ----
    session: requests.Session（建议传 ``api.session``，自动带上 UA / verify=False）

    返回
    ----
    ``(pil_image, qrcode_key, url)``

    异常
    ----
    任何网络 / 接口错误都以 ``RuntimeError`` 抛出。
    """
    params = {
        "source": "main-fe-header",
        "go_url": "https://www.bilibili.com/",
        "web_location": "333.1007",
    }
    url = _GENERATE_URL + "?" + urlencode(params)
    resp = session.get(url, timeout=timeout)
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError("二维码生成失败：%s" % payload.get("message", "未知错误"))
    d = payload.get("data") or {}
    qr_url = d.get("url")
    key = d.get("qrcode_key")
    if not qr_url or not key:
        raise RuntimeError("二维码生成失败：服务端未返回 url / qrcode_key")
    return _render(qr_url), key, qr_url


def poll_qr(session, qrcode_key, timeout=15):
    """轮询一次扫码状态。

    参数
    ----
    session: requests.Session
    qrcode_key: 生成二维码时拿到的 key

    返回
    ----
    状态码 int（见上方 ``SCAN_*`` 常量；其它正数表示未知状态）

    副作用
    ----
    成功时把 Cookie 同步进 session（Set-Cookie 自动应用 + 解析 data.url 兜底）。
    """
    url = _POLL_URL + "?qrcode_key=" + qrcode_key
    resp = session.get(url, timeout=timeout)
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError("扫码轮询失败：%s" % payload.get("message", "未知错误"))
    data = payload.get("data") or {}
    status = data.get("code")
    if status == SCAN_SUCCESS:
        _sync_cookies_from_url(session, data.get("url") or "")
    return status


def _sync_cookies_from_url(session, redirect_url):
    """从成功跳转地址的查询参数中兜底提取关键 Cookie。

    passport 通常已通过 ``Set-Cookie`` 写入（域为 ``.bilibili.com``，可被后续
    api.bilibili.com 请求携带）；这里显式按 ``.bilibili.com`` 域兜底设置，避免个别
    环境下漏写导致登录校验（nav 接口）拿不到 SESSDATA。
    """
    if not redirect_url:
        return
    try:
        qs = parse_qs(urlparse(redirect_url).query)
    except Exception:
        return
    for name in _COOKIE_KEYS:
        vals = qs.get(name)
        if vals:
            try:
                session.cookies.set(name, vals[0], domain=".bilibili.com", path="/")
            except Exception:
                pass
