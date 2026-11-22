# 反馈代理端点协议（可选）

软件内「反馈」页支持一个**可选的代理端点**。配置后，用户点「提交反馈」会直接由代理调用
GitHub API 创建 Issue，用户无需登录 GitHub、也不用跳出软件；未配置时回退到「打开预填好的
GitHub Issue 页」，由用户手动点发布。

## 请求

`POST <feedback_proxy_url>`，`Content-Type: application/json`：

```json
{
  "type": "bug",
  "title": "[Bug]: 下载进度卡住",
  "body": "问题描述……\n\n---\n\n> 由软件内反馈页提交 · 环境：v2.2.0 · Windows 11",
  "labels": ["bug"]
}
```

- `type`：`bug` 或 `feature`
- `title`：已带 `[Bug]: ` / `[建议]: ` 前缀
- `body`：Markdown 正文，已含环境信息
- `labels`：字符串数组（`bug` 或 `enhancement`）

## 响应

成功返回 `2xx`，建议回 JSON：

```json
{ "html_url": "https://github.com/colever-Beep/BilibiliDownloader/issues/123" }
```

软件用它显示"反馈已提交：<链接>"。非 2xx 或网络失败时，软件自动回退到浏览器预填页。

## 部署要点

- Token 只放服务端 Secret（细粒度 PAT，仅本仓库 `Issues: write`），**绝不下发到客户端**。
- 务必加防刷：每 IP 限流、honeypot 隐藏字段、正文长度上限。
- 建议用 Cloudflare Workers（免费额度足够），也可用任意能调 GitHub API 的服务。

## 客户端配置

在软件 `settings.json` 中填：

```json
{ "feedback_proxy_url": "https://your-worker.example.com/api/feedback" }
```

留空即不启用代理。
