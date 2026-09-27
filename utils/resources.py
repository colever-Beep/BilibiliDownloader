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
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    else:
        base = _BASE_DIR
    return os.path.join(base, rel_path)


def get_app_icon_path():
    """返回应用图标 icon.ico 的绝对路径（打包内或开发态）。"""
    return resource_path("icon.ico")
