# -*- coding: utf-8 -*-
"""无头冒烟：下载选项窗口（qfluentwidgets Fluent 版）。

覆盖：
  1. 构造三个导航页 + Pivot 默认页；
  2. 卡片取值来自 config（画质 720p / 同时下载数 4）；
  3. 联动逻辑：仅音频 / 音画分离 / 封面 avif / 字幕关闭；
  4. 确认契约：accept() → 写回 config + 调 on_confirm；reject() → 不调 on_confirm；
  5. 校验分支：视频流音频流都关 → 弹提示且不落盘（用桩替换 MessageBox，避免阻塞）。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class _Cfg:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


def main():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    from ui.download_options_dialog import DownloadOptionsDialog, _combo_value

    # ---------- 1. 构造 ----------
    cfg = _Cfg({"download_path": "C:/tmp/videos", "quality": "720p", "max_workers": 4})
    called = []
    dlg = DownloadOptionsDialog(None, cfg, 3, on_confirm=lambda: called.append(True))
    app.processEvents()
    assert dlg.stackedWidget.count() == 3, dlg.stackedWidget.count()
    assert dlg.pivot.currentRouteKey() == "media", dlg.pivot.currentRouteKey()

    # ---------- 2. 初值 ----------
    assert dlg.quality_combo.currentText() == "720p", dlg.quality_combo.currentText()
    assert dlg.workers_spin.value() == 4, dlg.workers_spin.value()
    assert dlg.path_edit.text() == "C:/tmp/videos", dlg.path_edit.text()
    assert _combo_value(dlg.conflict_combo) == "auto_rename"

    # 默认：视频流/音频流/合并 均开 → 合并可用
    assert dlg.merge_sw.isChecked() and dlg.merge_sw.isEnabled()

    # ---------- 3. 联动 ----------
    # 仅下载音频 → 视频流关闭且禁用、合并与分离禁用
    dlg.audio_only_sw.setChecked(True)
    app.processEvents()
    assert not dlg.video_stream_sw.isChecked() and not dlg.video_stream_sw.isEnabled()
    assert not dlg.merge_sw.isChecked() and not dlg.merge_sw.isEnabled()
    assert not dlg.separate_sw.isChecked() and not dlg.separate_sw.isEnabled()
    assert dlg.audio_format_combo.isEnabled(), "仅音频时音频格式应可用"

    # 取消仅音频 → 恢复
    dlg.audio_only_sw.setChecked(False)
    app.processEvents()
    assert dlg.video_stream_sw.isEnabled() and dlg.separate_sw.isEnabled()

    # 音画分离 → 合并禁用
    dlg.separate_sw.setChecked(True)
    app.processEvents()
    assert not dlg.merge_sw.isChecked() and not dlg.merge_sw.isEnabled()
    dlg.separate_sw.setChecked(False)
    dlg.video_stream_sw.setChecked(True)
    dlg.audio_stream_sw.setChecked(True)
    app.processEvents()
    assert dlg.merge_sw.isEnabled()

    # 封面 avif → 内嵌禁用；改回 jpg → 内嵌可用
    dlg.cover_type_combo.setCurrentText("avif")
    app.processEvents()
    assert not dlg.embed_cover_sw.isEnabled()
    dlg.cover_type_combo.setCurrentText("jpg")
    app.processEvents()
    assert dlg.embed_cover_sw.isEnabled()

    # 字幕关闭 → 格式/语言禁用
    dlg.subtitle_sw.setChecked(False)
    app.processEvents()
    assert not dlg.subtitle_format_combo.isEnabled()
    assert not dlg.subtitle_lang_combo.isEnabled()

    # ---------- 4. 确认契约 ----------
    dlg.danmaku_sw.setChecked(True)
    dlg.merge_sw.setChecked(True)
    dlg.conflict_combo.setCurrentIndex(1)          # 覆盖
    dlg.limit_spin.setValue(2048)
    dlg.workers_spin.setValue(6)
    app.processEvents()

    dlg.accept()
    app.processEvents()
    assert dlg.result is True, dlg.result
    assert called == [True], called
    assert cfg.get("quality") == "720p"
    assert cfg.get("file_conflict_resolution") == "overwrite", cfg.get("file_conflict_resolution")
    assert cfg.get("overwrite") is True
    assert cfg.get("download_limit") == 2048
    assert cfg.get("max_workers") == 6
    assert cfg.get("download_path") == "C:/tmp/videos"
    assert cfg.get("download_danmaku") is True

    # 取消 → 不回调、result False
    called2 = []
    dlg2 = DownloadOptionsDialog(None, _Cfg(), 1, on_confirm=lambda: called2.append(True))
    app.processEvents()
    dlg2.reject()
    app.processEvents()
    assert dlg2.result is False, dlg2.result
    assert called2 == [], "取消不应触发 on_confirm（旧实现会误加入下载队列）"

    # ---------- 5. 校验分支（桩掉 MessageBox，避免模态阻塞） ----------
    dlg3 = DownloadOptionsDialog(None, _Cfg(), 1, on_confirm=lambda: called2.append("bad"))
    app.processEvents()
    alerts = []
    dlg3._alert = lambda title, content: alerts.append(title)
    dlg3.video_stream_sw.setChecked(False)
    dlg3.audio_stream_sw.setChecked(False)
    app.processEvents()
    dlg3.accept()
    assert alerts == ["无法开始"], alerts
    assert dlg3.result is None, "校验未通过不应置为已确认"
    assert called2 == [], called2

    print("DOWNLOAD_OPTIONS_OK pages=%d current=%s" % (
        dlg.stackedWidget.count(), dlg.pivot.currentRouteKey()))


if __name__ == "__main__":
    main()
