# Dream Skills

**中文** | [English](README.en.md)

我的个人 Codex 技能集合。后续自定义技能统一收录在本仓库，每个技能使用独立目录。

## 技能列表

| 技能 | 用途 |
| --- | --- |
| [md-wechat-layout](md-wechat-layout/SKILL.md) | 将 Obsidian / Markdown 文章排版成可复制到微信公众号的富文本 |

## 公众号排版

默认使用「雾蓝气泡」：系统无衬线字体、四芒星标题、浅蓝底虚线卡片。也支持「青山绿水」与绿色「薄荷气泡」。

- 解析 Obsidian 本地图片，内嵌附件，统一小圆角和柔和阴影。
- 围栏代码使用浅色浏览器窗口；预览限高并滚动，复制时保留完整内容。
- 默认将链接和行内代码转换为显示文字，不新增参考资料。
- 保留原 Markdown 文件；兼容输出可能扩大强调范围。

### 安装

需要 Node.js 18+。将 `md-wechat-layout` 文件夹复制到 `~/.codex/skills/`（Windows 通常是 `%USERPROFILE%\.codex\skills\`），在技能目录运行：

```sh
npm ci
```

### 在 Codex 中调用

```text
$md-wechat-layout 给 /你的路径/文章.md 做公众号排版
```

不声明主题时使用雾蓝气泡，也可以明确指定「青山绿水」或「薄荷气泡」。

### 命令行使用

在仓库根目录运行：

```sh
node md-wechat-layout/scripts/render.mjs "文章.md" --vault "Obsidian库路径" --out "输出目录"
node md-wechat-layout/scripts/render.mjs "文章.md" --theme "薄荷气泡" --vault "Obsidian库路径" --out "输出目录"
```

输出 `.preview.html`、`.wechat.html` 和 `.report.json`。打开预览，点击「复制公众号排版」，粘贴到公众号草稿正文。复制 HTML 源码文本无法获得富文本排版。

微信粘贴效果需要实际检查，本地预览或结构检测通过不代表微信验收通过。图片转存失败时，请在公众号后台上传替换。本技能不自动保存草稿或发布。

### 测试

安装依赖后运行：

```sh
npm --prefix md-wechat-layout test
```

## 来源与许可证

公众号渲染器基于 [md-wechat](https://github.com/laogou717/md-wechat)。上游 MIT 许可证完整保留于 [LICENSE](md-wechat-layout/assets/upstream/LICENSE)，版本和适配说明见 [上游来源](md-wechat-layout/references/upstream.md)。
