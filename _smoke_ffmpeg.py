"""验证 ffmpeg 分发精简：只提取 ffmpeg / ffprobe，跳过 ffplay。

不下载完整 100MB+ 压缩包，而是用「本地构造的小体积 zip」模拟真实归档结构：
- 复刻 gyan essentials 的目录层级 <pkg>/bin/ffmpeg.exe、ffprobe.exe、ffplay.exe
- 复刻 BtbN 的目录层级 <pkg>/bin/*.exe
两种结构都必须只落地 ffmpeg + ffprobe，ffplay 不得出现。
"""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, r"D:/VScode/b")

from utils.ffmpeg_provider import _extract_archive, _download_spec


def make_zip(path, prefix):
    """造一个仿真的 ffmpeg 归档（三个 exe + 杂项）。"""
    with zipfile.ZipFile(path, "w") as z:
        for name in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
            z.writestr(f"{prefix}/bin/{name}", b"X" * 1024)
        z.writestr(f"{prefix}/LICENSE", b"license")
        z.writestr(f"{prefix}/doc/ffmpeg.html", b"doc")
        z.writestr(f"{prefix}/presets/libvpx-720p.ffpreset", b"preset")


tmp = tempfile.mkdtemp()

# ---- 1. gyan 风格层级 ----
z1 = os.path.join(tmp, "gyan.zip")
make_zip(z1, "ffmpeg-9.0.2-essentials_build")
d1 = os.path.join(tmp, "b1")
os.makedirs(d1)
_extract_archive(z1, "zip", d1)
got = sorted(os.listdir(d1))
print("gyan 层级 ->", got)
assert got == ["ffmpeg.exe", "ffprobe.exe"], got
assert "ffplay.exe" not in got

# ---- 2. BtbN 风格层级 ----
z2 = os.path.join(tmp, "btbn.zip")
make_zip(z2, "ffmpeg-master-latest-win64-gpl")
d2 = os.path.join(tmp, "b2")
os.makedirs(d2)
_extract_archive(z2, "zip", d2)
got2 = sorted(os.listdir(d2))
print("BtbN 层级 ->", got2)
assert got2 == ["ffmpeg.exe", "ffprobe.exe"], got2

# ---- 3. 下载源优先级 ----
specs = _download_spec()
print("Windows 候选源:")
for u, k in specs:
    print("   -", k, u)
assert len(specs) >= 2, "应有主源 + 兜底源"
assert specs[0][0].endswith("ffmpeg-release-essentials.zip"), specs[0][0]
assert "gyan.dev" in specs[0][0]
assert "BtbN" in specs[1][0]

# ---- 4. tar.xz 路径同样只取 ffmpeg/ffprobe ----
import tarfile
tp = os.path.join(tmp, "x.tar.xz")
with tarfile.open(tp, "w:xz") as t:
    for name in ("ffmpeg", "ffprobe", "ffplay"):
        p = os.path.join(tmp, name)
        with open(p, "wb") as f:
            f.write(b"Y" * 512)
        t.add(p, arcname=f"ffmpeg-master-latest-linux64-gpl/bin/{name}")
d3 = os.path.join(tmp, "b3")
os.makedirs(d3)
_extract_archive(tp, "tarxz", d3)
got3 = sorted(os.listdir(d3))
print("tar.xz ->", got3)
assert got3 == ["ffmpeg", "ffprobe"], got3
assert "ffplay" not in got3

print("ALL_OK")
