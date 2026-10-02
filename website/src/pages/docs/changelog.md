---
layout: ../../layouts/BaseLayout.astro
title: 更新日志 - BilibiliDownloader
active: 常见问题
prose: true
---

# 更新日志

完整的版本更新记录请查看 GitHub Releases：

👉 [github.com/colever-Beep/BilibiliDownloader/releases](https://github.com/colever-Beep/BilibiliDownloader/releases)

近期重要变更：

- **UI 重构版（发行说明）**：本版本采用 PySide6 + QFluentWidgets 重构整个 GUI 界面，相较上一采用 CustomTkinter 作为 UI 库的 1.0.0 版本更加流畅与现代化；目前软件仅支持 Windows 10 及以上系统，后续会考虑增添多系统支持。
- **统一分页与浏览器跳转**：搜索 / 各列表复用分页逻辑，列表项新增「在浏览器中打开」跳转按钮。
- **加载顺序优化**：每周必看 / 排行榜改为先弹窗显示「加载中」再后台拉取，消除卡顿错觉。
- **批量解析统一**：UP 主空间等可翻页来源统一走分页选择框。
- **跳页增强**：分页栏显示「第 N / M 页」总页数，输入超范围自动钳制到末页。
- **主题防抖**：强调色 / 明暗切换加 140ms 防抖提交器，缓解拖动取色器造成的卡顿。
- **项目更名**：统一为 BilibiliDownloader（打包产物名、窗口标题、应用名一致）。
- **许可证合规**：补齐 GPL-3.0 的 LICENSE / NOTICE，明确衍生作品署名与许可。
