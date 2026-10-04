# Dream Skills

[中文](README.md) | **English**

My personal collection of Codex skills. All custom skills live in a dedicated top-level directory in this repository; `~/.codex/skills/` is the local installed copy.

## Available skills

| Skill | Purpose |
| --- | --- |
| [gzh-webchat-cover](gzh-webchat-cover/SKILL.md) | Turn long Chinese article titles into cinematic, product-tech, or editorial-diagram covers |
| [md-wechat-layout](md-wechat-layout/SKILL.md) | Convert Obsidian / Markdown articles into rich-text HTML for WeChat Official Accounts |
| [gzh-final-check](gzh-final-check/SKILL.md) | Review final WeChat article drafts for language, generic filler, faux insights, over-editing, test claims, and media integrity; read-only by default |
| [wechat-article-writing](wechat-article-writing/SKILL.md) | Plan cases, write evidence-based AI articles, and revise drafts with scoped edits and four-layer editorial checks |

## WeChat article covers

`gzh-webchat-cover` extracts the subject, action, visible result, and emotion from a title, then compresses the article into one visual proposition. It selects a composition mode for creative work, product technology, feature comparisons, tutorials, industry analysis, or mechanism explainers.

- Outputs a `900 × 383` landscape PNG by default.
- Generates a text-free background first, then adds reliable Chinese typography with a helper script.
- Includes 12 reference covers, title-to-cover mappings, and a distilled visual guide.
- Keeps the visual claim within what the article actually demonstrates.

Invoke it in Codex:

```text
$gzh-webchat-cover Create a WeChat article cover from my title and article summary
```

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
