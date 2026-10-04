# BilibiliDownloader（B 站下载器）

基于 **PySide6 + qfluentwidgets** 的 B 站内容下载桌面工具，Fluent / WinUI 风格界面，支持视频、番剧、直播、音频、歌单、收藏夹、UP 主、合集、课程等多种内容的解析与下载，以及直播录制与批量解析。

> 注：本项目的解析逻辑与界面实现参考了 GitHub 上的开源项目 **bili23**，为其衍生 / 二次开发版本，但独立维护、以 **BilibiliDownloader** 命名。

> 仅供学习与技术研究使用，请遵守 B 站用户协议与相关法律法规，勿将本工具用于任何侵权或商业用途。

---

## 发行说明

该版本为 **UI 重构版**（采用 PySide6 + QFluentWidgets 重构整个 GUI 界面），较于上一采用 CustomTkinter 作为 UI 库的 1.0.0 版本更加流畅与现代化。目前软件仅支持 Windows 10 及以上系统，后续会考虑增添多系统支持。

---

## 功能特性

- **多类型解析**：视频 / 番剧 / 直播 / 音频 / 歌单 / 收藏夹 / UP 主空间 / 合集 / 课程。
- **分页浏览**：搜索、收藏夹、历史、稍后再看、UP 主空间等可翻页来源统一走分页选择框，支持「第 N / M 页」显示与跳页（超出总页数自动钳制）。
- **批量解析**：一次性粘贴多个链接，可翻页来源各自弹出统一分页选择框。
- **直播录制**：支持原画/4K/杜比等清晰度，`copy` 直录或 `h264/h265` 实时转码，断流自动重连并分段保存。
- **丰富下载选项**：清晰度、封装格式（mp4/mkv/...）、视频编码（H.264/H.265）、仅音频、弹幕（xml/ass/json）、字幕（srt/ass/...）、封面（jpg/png/webp/avif）、元数据。
- **自动归类**：可按内容种类在下载目录下分文件夹保存（`create_folder`）。
- **列表项「在浏览器中打开」**：每个列表项右侧带有跳转按钮，自动推导对应 B 站页面（视频页 / 个人空间 / 番剧 / 分集 等）。
- **主题与强调色**：明 / 暗主题，强调色可自定义或跟随 Windows 系统强调色；切换带防抖，拖动取色器不卡顿。
- **多语言**：简体中文 / 繁体中文 / English / 日本語（设置内切换，基于 gettext）。
- **登录增强**：放入 `cookies.txt` 可提升解析成功率、解锁更高清晰度、规避部分风控。
- **高 DPI 适配**：Windows 下开启 DPI 感知，高分屏不糊。

---

## 运行环境要求

- **操作系统**：Windows 10 / 11（GUI 基于 Qt，理论上可移植到其它平台，但未做适配验证）。
- **Python**：3.10+（已在 3.13 / 3.14 验证）。
- **FFmpeg**：用于音视频合并与转码，**首次使用会自动从官方构建下载并缓存到 `bin/`**；也可手动把 `ffmpeg.exe` 放到程序同目录的 `bin/` 下（优先级最高）。

---

## 快速开始（源码运行）

1. 克隆仓库：

   ```bash
   git clone https://github.com/colever-Beep/BilibiliDownloader.git
   cd BilibiliDownloader
   ```

2. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

3. 运行：

   ```bash
   python main.py
   ```


### 可选：登录态（cookies）

若部分视频提示限制或清晰度偏低，可将浏览器中的 B 站 `SESSDATA` 等 Cookie 导出为项目根目录的 `cookies.txt`（Netscape 格式或 `key=value` 每行一个），程序会自动读取，或进行扫码登录操作（仅保存在本地）

---

## 打包为可执行文件

打包依赖 [`auto-py-to-exe`](https://pypi.org/project/auto-py-to-exe/)（底层为 PyInstaller）：

```bash
pip install auto-py-to-exe
```

- **安装版（Setup.exe）**：

  ```bash
  # 需先安装 Inno Setup 6（https://jrsoftware.org/isdl.php），并把 ISCC.exe 加入 PATH
  ./installer/build_installer.ps1
  ```

  产物：`dist/BilibiliDownloader-Setup-<版本>.exe`（向导安装，内置 FFmpeg，离线可用）。

- **便携版（文件夹）**：

  ```bash
  python build_portable.py
  ```

  产物：`dist/BilibiliDownloader/`（双击即用，适合压缩分发；首次使用自动下载 FFmpeg）。

- **Linux AppImage**（需在 Linux 上构建）：

  ```bash
  pip install pyinstaller
  python build_linux_appimage.py
  ```

  产物：`dist/BilibiliDownloader-<arch>.AppImage`（`arch` 为 `x86_64` 或 `aarch64`，取决于构建机架构；单文件，`chmod +x` 后直接运行）。

- **macOS DMG**（需在 macOS 上构建）：

  ```bash
  pip install pyinstaller
  python build_macos_dmg.py
  ```

  产物：`dist/BilibiliDownloader-macos-<arch>.dmg` 与 `dist/BilibiliDownloader-macos-<arch>.app.zip`
  （`arch` 为 `arm64` 或 `x86_64`，取决于构建机架构；ad-hoc 签名，拖拽到「应用程序」安装；
  Apple Silicon 上必须签名才能运行）。

> 也可用仓库自带的工作流 `.github/workflows/build-unix.yml` 一键构建：在 Actions
> 页面手动触发（或推送 `v*` tag），分别由 Ubuntu / macOS runner 产出 AppImage 与
> DMG，并作为构建产物（artifact）下载。

> 上述打包均**不内置 FFmpeg**（控制体积），运行时按当前平台自动下载对应版本
> （Windows 走 zip、Linux/macOS 走 tar.xz，来源 [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds/releases)）。
> 便携版/普通 onedir 写入 exe 同目录 `bin/`；macOS `.app`（签名只读包）与 AppImage
> （只读挂载）则写入用户数据目录，避免写入失败。离线环境请手动放置。

---

## 配置说明

配置保存在程序目录下的 `settings.json`，大部分选项可在「设置」界面直接修改。常用字段：

| 配置项 | 说明 |
| --- | --- |
| `download_path` | 下载目录。跨电脑时若旧路径失效，会自动回退到当前用户的「视频」文件夹。 |
| `create_folder` | 是否按内容种类（视频 / 番剧 / 直播 / 音频 / …）分文件夹保存。 |
| `quality` | 默认清晰度：`8K / 4K / 1080p / 720p / 480p / 360p`。 |
| `merge_format` | 封装格式：`mp4` / `mkv` 等。 |
| `audio_only` | 仅下载音频（不下载视频流）。 |
| `download_danmaku` / `danmaku_format` | 下载弹幕及格式（xml / ass / json）。 |
| `download_subtitle` / `subtitle_format` / `subtitle_lang` | 下载字幕、格式与语言范围。 |
| `download_cover` / `embed_cover` / `cover_type` | 下载封面、内嵌封面、封面格式。 |
| `file_conflict_resolution` | 同名文件处理：`auto_rename`（自动重命名）/ `overwrite`（覆盖）。 |
| `max_workers` | 同时下载任务数。 |
| `proxy_type` / `proxy_host` / `proxy_port` / `proxy_user` / `proxy_pass` | HTTP / SOCKS 代理。 |
| `appearance` | 明暗主题：`dark` / `light`。 |
| `accent_color` | 强调色（`#RRGGBB`，或 `"system"` 跟随 Windows 系统强调色）。 |
| `language` | 界面语言：`zh_CN` / `zh_TW` / `en` / `ja`。 |
| `list_layout` | 列表密度：`detailed`（详细）/ `compact`（精简）。 |
| `close_behavior` | 关闭行为：`tray`（最小化到托盘）/ `quit`（直接退出）。 |
| `live_record_*` | 直播录制相关：清晰度 `live_record_qn`、编码 `live_record_codec`、封装 `live_record_format`、断流自动重连 `live_record_auto_reconnect` 等。 |

`settings.json` 采用「默认值 + 用户覆盖」合并策略，新增字段不会影响旧配置。

---

## 目录结构（主要）

```
BilibiliDownloader/
├── main.py                 # 程序入口
├── build_portable.py       # 便携版打包驱动
├── config.py               # 配置默认值与读写
├── bili_api.py             # B 站 API 封装
├── download_engine.py      # 基于 yt-dlp 的下载引擎
├── live_recorder.py        # 直播录制
├── ui/                     # 界面（PySide6 + qfluentwidgets）
│   ├── main_window.py
│   ├── sidebar.py
│   ├── select_dialog.py    # 分页选择对话框
│   ├── select_list_view.py # 列表（含「在浏览器中打开」按钮）
│   ├── settings_window.py
│   ├── theme.py            # 主题 / 强调色（含防抖）
│   └── ...
├── utils/                  # 工具（i18n、cookie、ffmpeg、日志等）
│   ├── qfw_compat.py       # qfluentwidgets 在 Python 3.14 下的崩溃补丁
│   ├── bili_classify.py    # 下载自动归类
│   ├── ffmpeg_provider.py  # FFmpeg 自动下载 / 定位
│   └── ...
├── scripts/i18n_tools.py   # 翻译烘焙（构建前自动执行）
├── translations/           # gettext .po 翻译文件
├── res/                    # 图标 / 资源
└── bin/                    # FFmpeg（运行时自动下载或手动放置）
```

---

## 常见问题

**Q：下载失败 / 清晰度只有 360p？**
多为未登录或登录态失效。放入有效的 `cookies.txt` 后重试。部分内容（如番剧）需大会员才能获取高清晰度。

**Q：合并报错 / 提示「解码不受支持」？**
直播录制默认 `copy` 封装，B 站高清直播流常为 HEVC/AV1。可将 `live_record_codec` 改为 `h264` 实时转码，或改用 `mkv` 封装。

**Q：切换主题 / 强调色卡顿？**
已内置 140ms 防抖，连续拖动取色器不会反复重绘。若仍觉单次切换偏慢，属 Qt 全局样式重设的固有成本，非程序缺陷。

**Q：界面语言如何切换？**
设置 → 语言 选择 `zh_CN / zh_TW / en / ja`，重启后生效（部分动态文案即时刷新）。

---

## 免责声明

本项目为开源学习工具，所有下载内容版权归原作者与 B 站所有。使用者应自行承担因使用本工具产生的一切法律责任与风险。

---

## 许可证

本项目是 GitHub 开源项目 **[Bili23-Downloader](https://github.com/ScottSloan/Bili23-Downloader)**（作者 Scott Sloan，GPL-3.0）的衍生 / 二次开发版本。**作为 GPL-3.0 的衍生作品，本项目同样以 GPL-3.0 许可证发布**，完整文本见仓库根目录的 [`LICENSE`](LICENSE) 文件。

- 上游原作者版权：Copyright (C) Scott Sloan
- 本修改版版权：Copyright (C) 2026 colever-Beep
- 署名与原作者声明见 [`NOTICE`](NOTICE)

> **GPL-3.0 是强 copyleft 许可证**：任何公开分发（含公开源码）都必须保留原作者版权与许可声明、提供完整源码（已满足），且**不得改用更宽松的许可证（如 MIT / Apache）重新发布衍生作品**。若上游后续变更许可证，本衍生版仍需遵循 GPL-3.0 的兼容性约束。
