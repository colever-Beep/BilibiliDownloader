# 翻译与 Weblate 接入指南

本项目使用标准 **gettext `.po`** 格式管理翻译，Weblate 原生支持该格式。
翻译以「简体中文原文」作为 `msgid`（翻译键），运行时由 `scripts/i18n_tools.py`
把各语言 `.po` 烘焙成 `utils/locales_weblate.py`，由 `utils/i18n.py` 的 `tr()`
在运行时查表。

```
translations/
├── messages.pot                         # 模板：所有源字符串（msgid），由 extract 生成
└── <lang>/LC_MESSAGES/messages.po       # 各语言译文（msgstr），Weblate 管理这些文件
      en / ja / zh_TW                    # 已支持的三语
```

> 源语言是简体中文（zh_CN），其文本即 `msgid` 本身，因此**没有** `zh_CN/messages.po`，
> 译文只存在于 `en` / `ja` / `zh_TW` 等目标语言目录。

---

## 一、把仓库推到 Git 托管平台（Weblate 的前置条件）

Weblate 基于 Git 工作，翻译文件必须位于一个 Weblate 可克隆/推送的仓库。
本仓库尚未配置远端，请在 GitHub / GitLab / Gitea 等创建空仓库后：

```bash
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

（`.gitignore` 已排除 cookies、settings.json、日志、构建产物等本地/敏感文件，
首次提交只包含源码、UI、资源与翻译骨架。）

---

## 二、在 Weblate 中注册组件（Component）

在 Weblate 后台「新增项目 → 新增组件」，按下表填写：

| 字段 | 取值 | 说明 |
| --- | --- | --- |
| 版本控制系统 (VCS) | `Git` | 或 GitLab / GitHub（如用对应托管） |
| 仓库地址 (Repository) | `https://github.com/<用户名>/<仓库>.git` | 与第一步一致 |
| 仓库推送地址 (Push URL) | 留空 = 同源 | 让 Weblate 直接推回同一仓库 |
| 推送分支 (Push branch) | 留空（= 默认分支 `main`） | 或填 `weblate` 走 PR 流程 |
| 文件格式 (File format) | **Gettext PO file** | |
| 文件掩码 (File mask) | `translations/*/LC_MESSAGES/messages.po` | `*` 自动匹配各语言目录 |
| 模板 (Template) | `translations/messages.pot` | 源字符串定义 |
| 源语言 (Source language) | `Chinese (Simplified)` / `zh_Hans` | 简体中文 |
| 新语言的文件格式 (New language) | `translations/{{ language_code }}/LC_MESSAGES/messages.po` | 译者新增语言时自动建文件 |
| 翻译许可 | 与项目一致（建议与源码同许可） | — |

保存后 Weblate 会克隆仓库、解析 `messages.pot`，并针对 `en` / `ja` / `zh_TW`
建立翻译单元。后续：

- **译者**在 Weblate 网页上翻译 → Weblate 提交 `.po` 到仓库 `main` 分支。
- **CI（见 `.github/workflows/bake-locales.yml`）**监听到 `translations/**` 变更，
  自动运行 `python scripts/i18n_tools.py bake`，把更新烘焙进
  `utils/locales_weblate.py` 并回写提交，保证运行时字典始终最新。
- **应用构建**（`build_portable.py` / `installer/build_installer.ps1`）在打包前也会跑一次 `bake`，
  因此发布的 exe 一定包含最新译文。

---

## 三、译者新增一种新语言时

Weblate 在「管理 → 新增语言」中选择目标语言后，会按上面的文件掩码自动创建
`translations/<新语言码>/LC_MESSAGES/messages.po`。本工具链**自动发现**该目录：

- `scripts/i18n_tools.py` 的 `cmd_bake` / `cmd_stats` 通过
  `_discover_langs()` 扫描 `translations/*/LC_MESSAGES/messages.po`，
  无需改代码即可把新语言并入 `locales_weblate.py`。
- 若要在应用语言菜单中暴露该语言，请在 `utils/i18n.py` 的 `LANGUAGES` 字典中追加
  对应 `code -> 显示名`（UI 产品决策，按需添加）。

---

## 四、本地工作流（开发者）

```bash
# 1) 从源码抽取最新 tr() 调用，更新 messages.pot 并同步各 .po（--seed 仅首次回填）
python scripts/i18n_tools.py extract [--seed]

# 2) 把 .po 烘焙成运行时字典 utils/locales_weblate.py
python scripts/i18n_tools.py bake

# 3) 查看各语言翻译覆盖率
python scripts/i18n_tools.py stats
```

常规开发只需第 2 步；新增/修改了界面文案后跑第 1 步把新字符串同步进 `.po`，
再提交 `.pot` 与 `.po`（**不要**手改 `utils/locales_weblate.py`，它由 bake 生成）。

---

## 五、约定（红线）

- `msgid` = 简体中文原文；**配置值 / 选项 / 字典查找键（如 `1080p`、`mp4`、`auto_rename`）不翻译**。
- 带占位符的文案写成 `tr("已下载 {}").format(n)`，便于抽取与复数处理。
- `utils/locales_weblate.py` 为生成物，受 CI 与构建脚本自动维护，勿手工编辑。
