import os
import re
import webbrowser
import threading
import requests
from datetime import datetime


def open_in_browser(url):
    """在独立守护线程中打开浏览器 / 资源管理器。

    不要在主线程直接调用 webbrowser.open：Windows 上它走 os.startfile/ctypes，
    会释放并恢复 GIL；若此时后台图片加载线程(requests/PIL)也在做原生 GIL 操作，
    主线程 GIL 状态可能损坏，触发
    'Fatal Python error: PyEval_RestoreThread: GIL released, thread state NULL' 致命崩溃。
    放到独立线程可隔离该风险。
    """
    def _open():
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"[打开浏览器失败] {url}: {e}")
    threading.Thread(target=_open, daemon=True).start()


def safe_filename(name):
    """替换非法字符为下划线"""
    return re.sub(r'[<>:"/\\|?*]', '_', name)


def resolve_filename_collision(out_dir, base, exts=(".mp4", ".mkv", ".m4a")):
    """同名文件冲突解析（对齐 bili23 的 __resolve_conflict）。

    - 若 ``out_dir`` 下不存在 ``base + 任意候选扩展名``，直接返回原 ``base``（无冲突）。
    - 若存在冲突：
        * overwrite 策略由调用方处理（本函数不负责覆盖，仅返回原 base），
          因此这里只对 auto_rename 场景返回 ``base (n)`` 形式。
    返回 (final_base, collided: bool)。
    """
    collided = any(os.path.exists(os.path.join(out_dir, f"{base}{ext}")) for ext in exts)
    if not collided:
        return base, False
    n = 1
    while True:
        cand = f"{base} ({n})"
        if not any(os.path.exists(os.path.join(out_dir, f"{cand}{ext}")) for ext in exts):
            return cand, True
        n += 1

def resolve_short_url(url):
    """解析 b23.tv 短链"""
    if "b23.tv" not in url:
        return url
    try:
        resp = requests.head(url, allow_redirects=True, timeout=10)
        return resp.url
    except:
        return url
# utils/helpers.py
def optimize_thumbnail_url(url, width=320, height=180):
    """
    为 B站封面图添加缩略图参数，大幅减少图片大小。
    如果 URL 不是 B站域名，则原样返回。
    """
    if not url:
        return url
    # B站图片域名
    bili_domains = ("hdslb.com", "bilibili.com")
    if not any(domain in url for domain in bili_domains):
        return url

    # 去除已有的 @ 后缀参数
    if '@' in url:
        url = url.split('@')[0]
    # 添加缩略图参数，限制宽高，格式为 jpg（webp 部分浏览器支持稍差，用 jpg 更稳）
    # 120x75 的显示区域，用 320x180 足够清晰且文件小
    return f"{url}@{width}w_{height}h_1c.jpg"

def add_history_entry(url, title, source="manual"):
    """将解析记录写入 history.txt（按 URL 去重：同一链接只保留最新一条）"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 格式：时间 | URL | 标题 | 来源
    line = f"{timestamp} | {url} | {title} | {source}\n"
    path = "history.txt"
    try:
        # 读取已有记录，丢弃同 URL 的旧行，再追加最新一条（去重 + 最新优先）
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    old_lines = f.readlines()
                new_lines = []
                for ln in old_lines:
                    parts = ln.strip().split(" | ")
                    if len(parts) >= 2 and parts[1] == url:
                        continue  # 跳过旧的同 URL 记录
                    new_lines.append(ln if ln.endswith("\n") else ln + "\n")
                new_lines.append(line)
                with open(path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                return
            except Exception:
                pass
        # 文件不存在或读写出错时，直接追加
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"写入历史记录失败: {e}")
def format_count(n):
    """把播放/点赞/收藏等大数字格式化为紧凑形式（仿 B 站：万 / 亿）。

    入参可为 int / 数字字符串 / 空值；非法值返回 "0"。
    < 1万：原样（如 "9999"）；< 1亿：保留 1 位小数 + "万"（如 "12.3万"）；
    >= 1亿：保留 1 位小数 + "亿"（如 "1.2亿"）。
    """
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0"
    if n < 0:
        n = 0
    if n < 10000:
        return str(n)
    if n < 100000000:
        v = n / 10000.0
        s = f"{v:.1f}"
        if s.endswith(".0"):
            s = s[:-2]
        return s + "万"
    v = n / 100000000.0
    s = f"{v:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return s + "亿"


def format_duration(value):
    """把时长统一格式化为 'MM:SS' 或 'H:MM:SS'。

    入参可能是：整数秒（如 135）、数字字符串（如 '135'）、
    或已格式化的字符串（如 '02:15' / '1:02:15'）。
    非法 / 空值返回 '--:--'。
    """
    if value in (None, "", 0, "0", "00:00"):
        return "--:--"
    try:
        if isinstance(value, str):
            s = value.strip()
            if ":" in s:                       # 已是 "MM:SS" / "H:MM:SS"
                parts = [int(p) for p in s.split(":")]
                total = 0
                for p in parts:
                    total = total * 60 + p
                secs = total
            else:
                secs = int(s)                 # 数字字符串
        else:
            secs = int(value)                 # 整数（或 float 秒）
    except (ValueError, TypeError):
        return "--:--"
    if secs <= 0:
        return "--:--"
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# 缓存按字号创建的 QFontMetrics，避免每次截断都 new 一个
_FIT_FONTS = {}
# 结果缓存：虚拟列表滚动时同一批 item 反复进出视口，会对同一 (文本, 宽度, 字号)
# 反复求值。fit_text 内部是二分测量，每次约 8 次 Tcl measure 调用（实测长标题
# 0.93ms/次），13 行即 ~12ms —— 足以把一次 flush 推过一帧（16.7ms@60Hz）导致撕裂。
# 记忆化后命中率极高，整行 update_row 的这块开销降到接近 0。
_FIT_CACHE = {}
_FIT_CACHE_MAX = 4000


def fit_text(text, max_px, font_size=13, ellipsis="…", pad=6):
    """把 text 截断到可见像素宽度 max_px 以内，超出部分用 ellipsis 收尾。

    用于列表标题列：标题过长时若直接塞进 grid 列，Tk 会按文字实际宽度把该列撑大，
    导致正文列与表头列对不齐。约定以「逻辑像素」传入（与列宽逻辑值同尺度），
    因为列宽与字体在 DPI 下同比缩放，比例不变，故逻辑空间测量即准确。
    pad 预留左右内边距余量，避免测量偏差导致文字贴边/溢出。
    返回原样（未超宽）或截断后的字符串。

    迁移后测量改用 PySide6 的 QFontMetrics（原 customtkinter 链路用 tkinter 的
    tk.font.Font.measure，现已移除 tkinter 依赖）。结果按
    (text, max_px, font_size, ellipsis, pad) 记忆化：滚动 / 主题切换会
    对同一行反复求值，缓存可把二分的 measure 开销完全消除。
    """
    if not text:
        return ""
    if not isinstance(text, str):
        # 缓存键要求可哈希；且 measure 只接受字符串
        text = str(text)
    key = (text, max_px, font_size, ellipsis, pad)
    cached = _FIT_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        from PySide6.QtGui import QFont, QFontMetrics
        f = _FIT_FONTS.get(font_size)
        if f is None:
            f = QFontMetrics(QFont("Microsoft YaHei UI", font_size))
            _FIT_FONTS[font_size] = f
        max_px = max(1, max_px - pad)
        if f.horizontalAdvance(text) <= max_px:
            result = text
        else:
            ell_w = f.horizontalAdvance(ellipsis)
            budget = max_px - ell_w
            if budget <= 0:
                result = ellipsis
            else:
                # 二分：最大 k 使 text[:k] 测量宽度 <= budget
                lo, hi = 0, len(text)
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if f.horizontalAdvance(text[:mid]) <= budget:
                        lo = mid
                    else:
                        hi = mid - 1
                result = text[:lo] + ellipsis
    except Exception:
        # 测量不可用时退化为按字符数截断，至少保证不无限撑宽
        result = text if len(text) <= 24 else text[:24] + ellipsis
    if len(_FIT_CACHE) >= _FIT_CACHE_MAX:
        _FIT_CACHE.clear()
    _FIT_CACHE[key] = result
    return result


def duration_to_seconds(value):
    """把时长解析为整数秒。

    兼容：整数秒（135）、数字字符串（'135'）、格式化字符串（'02:15' / '1:02:15'）。
    非法 / 空值返回 0。供接口层统一把字符串时长（如 B站空间接口的 length="MM:SS"）
    规整为秒，避免下游做 int() / 算术时崩溃。
    """
    if value in (None, "", 0, "0", "00:00"):
        return 0
    try:
        if isinstance(value, str):
            s = value.strip()
            if ":" in s:
                parts = [int(p) for p in s.split(":")]
                total = 0
                for p in parts:
                    total = total * 60 + p
                return total
            return int(s)
        return int(value)
    except (ValueError, TypeError):
        return 0


def send_windows_notification(title, message, duration=5):
    """
    发送 Windows 原生通知（仅标题、内容、时长）
    """
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(
            title,
            message,
            duration=duration,
            threaded=True
        )
        return True
    except ImportError:
        # win10toast 未安装，打印到控制台
        print(f"[通知] {title}: {message}")
        return False
    except Exception as e:
        print(f"发送通知失败: {e}")
        return False