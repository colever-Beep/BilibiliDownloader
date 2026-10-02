---
layout: ../../layouts/BaseLayout.astro
title: 常见问题 - BilibiliDownloader
active: 常见问题
prose: true
---

# 常见问题

### 解析失败 / 报错 -352

多为风控或 `buvid` 校验失效，建议在 yt-dlp 链路补充登录 Cookie（见[使用文档](./)的登录说明），或将 `cookies.txt` 更新为最新值。

### 清晰度受限，只有 360P / 720P

B 站对未登录或 Cookie 失效的账号限制最高清晰度。请登录后在浏览器复制最新 Cookie 保存到 `cookies.txt` 并重启程序。

### 合并报错 / FFmpeg 缺失

程序首次运行会尝试自动下载 FFmpeg。若网络受限失败，可手动将 `ffmpeg.exe` 放入 `bin/` 目录，或在 `settings.json` 的 `proxy` 中配置代理后重试。

### 主题 / 强调色切换卡顿

切换已做 140ms 防抖，连续拖动取色器只会触发一次重绘。若仍觉得单次切换偏慢，属 Qt 全局重绘固有限制；后续可把强调色从全局 QSS 抽离进一步优化。

### 语言切换后部分标题未刷新

这是 qfluentwidgets 标题接口不一致导致的已知边界情况，已在代码中对设置窗口标题做了兜底刷新。如仍遇到，重启程序即可。

### 下载路径如何跨用户自动定位？

程序会自动检测系统标准视频目录（如 `Videos`），不硬编码 Windows 用户路径，避免换机后失效。

### 这是 bili23 吗？

不是。本项目的名字是 **BilibiliDownloader**，bili23（Bili23-Downloader）是 GitHub 上的独立开源项目，本仓库是其衍生 / 二次开发版本，已在 `NOTICE` 中保留原作者署名。
