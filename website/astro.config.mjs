import { defineConfig } from 'astro/config';

// 项目页（project site）路径：https://colever-Beep.github.io/BilibiliDownloader
// base 必须与仓库名一致，否则资源（CSS/JS/图片）会 404。
export default defineConfig({
  site: 'https://colever-Beep.github.io',
  base: '/BilibiliDownloader',
  trailingSlash: 'ignore',
});
