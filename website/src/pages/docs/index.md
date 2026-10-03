---
layout: ../../layouts/BaseLayout.astro
title: 使用文档 - BilibiliDownloader
active: 使用文档
prose: true
---

# 使用文档

BilibiliDownloader 是一款基于 **PySide6 + qfluentwidgets** 的 B 站内容下载桌面工具，Fluent / WinUI 风格界面，支持视频、番剧、直播、音频、歌单、收藏夹、UP 主、合集、课程等多种内容的解析与下载。

> 本项目为开源学习工具，所有下载内容版权归原作者与 B 站所有。使用者应自行承担因使用本工具产生的一切法律责任与风险。

## 功能特性

- **多类型解析**：视频、番剧、直播、音频、歌单、收藏夹、UP 主、合集、课程一键解析。
- **统一分页选择**：搜索 / 收藏夹 / 历史 / 稍后再看等列表统一分页弹窗，支持跳页与总页数显示。
- **批量解析**：一次粘贴多个链接，可翻页来源各自走统一分页选择框。
- **直播录制**：支持 B 站直播录制，实时保存为本地视频。
- **下载选项丰富**：清晰度、音质、弹幕、字幕、封面、合集/分 P 处理等可选。
- **自动归类**：按视频种类自动分文件夹存放。
- **列表项一键跳转**：在浏览器中打开对应视频 / UP 主空间页面。
- **主题与强调色**：明暗主题 + 可自定义强调色，切换带防抖优化。
- **多语言**：简体中文、繁体中文、English、日本語等。
- **高 DPI 适配**：高分屏下界面清晰不模糊。

## 运行环境

- 操作系统：Windows 10 / 11、macOS（Apple Silicon / Intel）、Linux（x86_64 / ARM64）
- Python：3.10+（已验证 3.13 / 3.14）
- FFmpeg：首次运行自动下载，也可手动放置

## 快速开始（源码运行）

```bash
git clone https://github.com/colever-Beep/BilibiliDownloader.git
cd BilibiliDownloader
pip install PySide6 qfluentwidgets requests Pillow qrcode segno numpy yt-dlp pyperclip win10toast
python main.py
```

### 登录（可选但推荐）

部分内容（如高清画质、会员视频）需要登录后的 Cookie：

1. 浏览器登录 B 站后，用开发者工具复制 Cookie 字符串；
2. 保存到项目根目录的 `cookies.txt`（纯文本，一行 Cookie）；
3. 重启程序即可生效。

## 打包为可执行文件

项目提供跨平台打包脚本（基于 PyInstaller）：

```bash
python build_exe.py            # Windows：单文件 BilibiliDownloader.exe
python build_portable.py       # Windows：便携版文件夹
python build_macos_dmg.py      # macOS：arm64 / x86_64 的 .dmg 与 .app.zip
python build_linux_appimage.py # Linux：x86_64 / aarch64 的 AppImage
```

GitHub Actions 会在推送 `v*` tag 或手动触发时自动构建上述全部平台的安装包，并发布到 GitHub Releases。

- FFmpeg **不内置**到包中：首次运行自动下载，或手动将 `ffmpeg.exe` 放入 `bin/` 目录。
- 打包产物位于 `dist/`（已在 `.gitignore` 中忽略）。

## 配置说明

配置保存在 `settings.json`，常用字段如下：

| 字段 | 说明 |
| --- | --- |
| `download_path` | 下载根目录 |
| `create_folder` | 是否按视频种类自动分类到子文件夹 |
| `quality` / `audio_quality` | 视频清晰度 / 音频音质 |
| `download_danmaku` | 是否下载弹幕 |
| `download_subtitle` | 是否下载字幕 |
| `download_cover` | 是否下载封面 |
| `auto_rename` | 同名文件处理策略 |
| `proxy` | 网络代理（如 `http://127.0.0.1:7890`） |
| `theme` / `accent` | 明暗主题 / 强调色（`system` 可跟随系统） |
| `language` | 界面语言 |
| `live_record_*` | 直播录制相关选项 |

## 目录结构

| 路径 | 作用 |
| --- | --- |
| `main.py` | 程序入口 |
| `bili_api.py` | B 站 API 封装 |
| `download_engine.py` | 下载引擎（基于 yt-dlp） |
| `live_recorder.py` | 直播录制 |
| `ui/` | 界面（主窗口、对话框、设置、侧边栏、主题） |
| `utils/` | 工具（分类、i18n、qfluentwidgets 兼容补丁等） |
| `translations/` | gettext 翻译文件 |
| `build_exe.py` / `build_portable.py` | 打包脚本 |

## 常见问题

详见 [常见问题](./faq)。

## 许可证

本项目是 GitHub 开源项目 [Bili23-Downloader](https://github.com/ScottSloan/Bili23-Downloader)（Scott Sloan，GPL-3.0）的衍生 / 二次开发版本，同样以 **GPL-3.0** 发布，保留原作者版权与署名。新增源码可标注 `SPDX-License-Identifier: GPL-3.0-or-later`。

- 许可证全文见仓库 `LICENSE`
- 署名与衍生声明见 `NOTICE`
