# Dream Skills

[中文](README.md) | **English**

My personal collection of Codex skills. Future custom skills live in this repository, each in its own directory.

## Available skills

| Skill | Purpose |
| --- | --- |
| [md-wechat-layout](md-wechat-layout/SKILL.md) | Convert Obsidian / Markdown articles into rich-text HTML for WeChat Official Accounts |

## WeChat article layout

The default **Mist Blue Bubble** style uses system sans-serif fonts, four-point star headings, and pale blue cards with dashed borders. **Cyan Landscape** and the green **Mint Soda** theme are also available.

- Resolve and embed local Obsidian images with small rounded corners and soft shadows.
- Render fenced code in light browser-style windows; previews scroll, while copied content remains fully expanded.
- Convert links and inline code to display text by default, without adding references.
- Keep the source Markdown unchanged; compatibility formatting may extend emphasis to an entire paragraph.

### Installation

Requires Node.js 18+. Copy `md-wechat-layout` into `~/.codex/skills/` (usually `%USERPROFILE%\.codex\skills\` on Windows), then run inside the skill directory:

```sh
npm ci
```

### Invoke in Codex

```text
$md-wechat-layout Format /your/path/article.md for a WeChat Official Account
```

Omitting the theme selects Mist Blue Bubble. Explicit theme names accepted by the CLI include `雾蓝气泡` (Mist Blue Bubble), `青山绿水` (Cyan Landscape), and `薄荷气泡` (Mint Soda).

### CLI usage

Run from the repository root:

```sh
node md-wechat-layout/scripts/render.mjs "article.md" --vault "Obsidian vault path" --out "output directory"
node md-wechat-layout/scripts/render.mjs "article.md" --theme "薄荷气泡" --vault "Obsidian vault path" --out "output directory"
```

The command generates `.preview.html`, `.wechat.html`, and `.report.json`. Open the preview, click its rich-text copy button, and paste into your WeChat draft body. Copying the HTML source as plain text will not preserve formatting.

Verify the result after pasting into WeChat. A successful local preview or structure check is not a WeChat acceptance test. If embedded images fail to transfer, upload replacements in the WeChat editor. This skill does not automatically save drafts or publish articles.

### Tests

After installing dependencies:

```sh
npm --prefix md-wechat-layout test
```

## Attribution and license

The article renderer is based on [md-wechat](https://github.com/laogou717/md-wechat). The upstream MIT license is preserved in [LICENSE](md-wechat-layout/assets/upstream/LICENSE). See [upstream references](md-wechat-layout/references/upstream.md) for the pinned revision and adaptations.
