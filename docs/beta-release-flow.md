# Beta / 预发布版发布流程

本项目用 `.github/workflows/build-unix.yml` 统一处理构建与 Release 发布。所有触发方式都经过 `prepare` job 判定模式，再决定要不要构建、用什么版本号、发到哪个 Release。

## 四种模式一览

| 模式 | 触发方式 | Release tag | prerelease | 说明 |
| --- | --- | --- | --- | --- |
| 正式版 | 推送 `v*` tag（如 `v2.2.0`） | `v2.2.0` | 否 | 正式发布，用户默认通道 |
| **Beta** | **main 提交信息含 `[beta]` 或 `beta:`** | `v2.3.0-beta` | 是 | 滚动预发布，只保留最新一个 beta Release |
| 持续构建 | Actions 页面手动 Run workflow | `continuous` | 是 | 滚动覆盖，日常测试用 |
| 跳过 | 普通 main 提交（无标记） | — | — | 不构建、不发布，不浪费 Actions 额度 |

## 怎么发一个 Beta（推荐流程）

**核心：以 commit 为契机——提交信息里加标记即可，不用手动打 tag。**

### 1. 准备发行说明（可选）

把本次 beta 的变更写进 `release_notes/beta.md`（会被附到 Release 正文最前面）。这个文件是滚动共用的，每次发 beta 前更新内容即可。不写也能发，只是没有「更新说明」段落。

### 2. 提交并推送到 main

提交信息里带上标记，**并在标记后写三段式版本号**：

```bash
git add -A
git commit -m "feat: 新增批量选集功能 [beta 2.3.0]"
git push origin main
```

标记写法二选一，大小写均可识别：
- `[beta 2.3.0]` —— 方括号形式
- `beta: 2.3.0 新增批量选集` —— 冒号形式

版本号必须是 `数字.数字.数字`（如 `2.3.0`）。**如果没写版本号**，会回退读取 `utils/version.py` 里的 `APP_VERSION`——这意味着 beta 版本号会和正式版一样，不建议，请务必写明。

### 3. 等待构建

推送后自动触发，五个平台并行构建（Windows 安装版+便携版、Linux 双架构 AppImage、macOS 双架构 DMG），完成后自动发布到 `v2.3.0-beta` Release。

可以在 Actions 页面看进度，或用命令：

```bash
gh run list --limit 3
```

### 4. 验证

打开 `https://github.com/colever-Beep/BilibiliDownloader/releases/tag/v2.3.0-beta`，确认：
- 标记为 **Pre-release**
- 标题形如 `BilibiliDownloader 2.3.0 Beta (abc1234)`
- 五个平台的产物齐全
- 旧的 beta Release 已被自动删除（始终只有一个 beta）

## Beta 与正式版的关系

- **tag 互不干扰**：beta 用 `v2.3.0-beta`，正式版用 `v2.3.0`，是两个独立 Release。beta 转正时照常打正式版 tag，beta Release 不会自动消失，可手动删除。
- **滚动覆盖**：同一个 beta 版本号重复提交时，覆盖更新该 Release 的资源和正文；新版本号（如 `2.3.1`）会删除旧 beta 的 Release 和 tag，只留最新的。
- **更新检查**：应用内「测试版」通道按发布时间取最新 Release（含 prerelease），会自动指向最新 beta；「稳定版」通道只看 `prerelease=false` 的 Release，完全看不到 beta。所以 beta 用户不会被正式版通道干扰，反之亦然。

## 版本号约定

沿用项目规范：三段式纯数字，语义为 `主.次.修`。

- beta 版本号建议比当前正式版**大一位修订号**（如正式版 `2.2.0` → beta `2.2.1`），或按规划中的下个版本（如 `2.3.0`）。
- 安装包的实际版本号就是 commit 信息里写的数字，Inno Setup 只接受纯数字，带 `-beta` 后缀的只是 Release tag，不影响安装包版本。
- **`utils/version.py` 的 `APP_VERSION` 不需要为 beta 改动**——它代表正式版基线，beta 的版本号由 workflow 从 commit 信息解析后直接传给打包脚本。

## 回滚 / 清理

- **删掉某个 beta Release**（连同 tag）：

  ```bash
  gh release delete v2.3.0-beta --cleanup-tag --yes
  ```

- **紧急停发**：把 commit 信息里的 `[beta ...]` 标记去掉即可，普通提交不会触发构建。

## 常见问题

**Q：为什么不用固定的 `beta` tag？**
A：应用内更新检查从 Release 的 tag 解析版本号（`normalize_version`），固定 `beta` 会被解析成 `0.0.0.0`，测试版通道就永远显示「已是最新」。用 `v2.3.0-beta` 既能表达版本，又不污染正式版 tag 序列。

**Q：普通 main 提交也会触发 workflow 吗？**
A：会触发，但 `prepare` job 判定为 `skip` 后，所有构建和发布 job 都跳过，只消耗几秒的判定时间。

**Q：能同时在 commit 里写多个版本号吗？**
A：取信息里第一个三段式数字。建议只写一个，避免歧义。
