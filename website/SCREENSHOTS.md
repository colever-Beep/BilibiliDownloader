# 官网截图说明

把官网首页「界面预览」区要用的截图放到本目录（`website/public/screenshots/`），
然后在 `website/src/pages/index.astro` 的「界面预览」小节，将占位框替换为真实 `<img>`。

## 建议文件名与对应占位

| 文件 | 说明 | 对应占位 |
| --- | --- | --- |
| `main.png` | 主界面 / 下载队列 | 主界面 / 下载队列 |
| `settings.png` | 设置窗口 | 设置窗口 |
| `select.png` | 解析选择对话框（分页 + 跳转按钮） | 解析选择对话框 |
| `theme.png` | 明暗主题对比 | 明暗主题对比 |

## 替换方式

在 `index.astro` 中，把：

```astro
<figure class="shot">
  <div class="ph">截图占位 · {s.cap}</div>
  <figcaption>{s.cap}</figcaption>
</figure>
```

改为（注意：图片放在 `public/screenshots/`，引用路径以 `/screenshots/` 开头，Astro 会自动加上站点 base）：

```astro
<figure class="shot">
  <img src="/screenshots/main.png" alt="主界面 / 下载队列" loading="lazy" />
  <figcaption>主界面 / 下载队列</figcaption>
</figure>
```

截图小贴士：统一窗口尺寸（建议 1280×800 左右）、亮/暗主题同尺寸；注意不要泄露 cookie、私人收藏夹名等隐私信息。
