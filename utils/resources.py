"""资源路径解析：开发态与 PyInstaller 冻结态（onefile）通用。

打包后用 --add-data 把 icon.ico 等静态资源塞进 _MEIPASS 临时目录；
开发态则相对项目根目录查找。统一走 resource_path() 即可两种环境兼容。
"""
import os
import sys

# 本文件位于 utils/，项目根 = utils/ 的上级目录
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(rel_path):
    """返回资源在『打包内』或『开发态』下的绝对路径。

    - 冻结态（onefile）：资源由 PyInstaller 解压到 sys._MEIPASS 临时目录。
    - 开发态：相对项目根目录。

    图标类资源已按类别整理到 ``ui/assets/``（brand / avatars / animation / icons）。
    为兼容既有 ``resource_path("icon.ico")`` 等调用，开发态在根目录找不到时，
    自动回退到 ``ui/assets`` 下对应子目录查找；打包态资源仍由 ``--add-data``
    放到 _MEIPASS 根目录，行为不变。
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
        return os.path.join(base, rel_path)
    direct = os.path.join(_BASE_DIR, rel_path)
    if os.path.exists(direct):
        return direct
    # 开发态回退：按文件名到 ui/assets 各分类目录查找
    name = os.path.basename(rel_path)
    for sub in ("brand", "avatars", "animation", "icons", "mascot"):
        candidate = os.path.join(_BASE_DIR, "ui", "assets", sub, name)
        if os.path.exists(candidate):
            return candidate
    return direct


def get_app_icon_path():
    """返回应用图标 icon.ico 的绝对路径（打包内或开发态）。"""
    return resource_path("icon.ico")
