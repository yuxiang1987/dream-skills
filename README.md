# Skills

个人 Codex 技能集合。

## md-wechat-layout

将 Obsidian 或普通 Markdown 转换为可复制到微信公众号的富文本 HTML。

- 默认：雾蓝气泡，无衬线字体、四芒星标题、浅蓝虚线卡片。
- 可选：青山绿水、薄荷气泡。
- 自动解析 Obsidian 本地图片；图片采用小圆角及柔和阴影。
- 长代码窗口在预览中滚动，复制时保留完整正文。

### 安装

将 `md-wechat-layout` 文件夹复制到 Codex 的 skills 目录，然后在该文件夹运行 `npm ci`（Node.js 18+）。

### 使用

```sh
node md-wechat-layout/scripts/render.mjs "文章.md" --vault "Obsidian库路径" --out "输出目录"
node md-wechat-layout/scripts/render.mjs "文章.md" --theme "薄荷气泡" --out "输出目录"
```

打开生成的 `.preview.html`，点击「复制公众号排版」，粘贴到公众号草稿正文。源文件不会修改；本地检查通过不代表微信粘贴验收通过。

### 测试

```sh
npm --prefix md-wechat-layout test
```

上游为 [md-wechat](https://github.com/laogou717/md-wechat)，MIT 许可证保留在 `md-wechat-layout/assets/upstream/LICENSE`。详细来源见技能的 `references/upstream.md`。
