# Dream Skills

[中文](README.md) | **English**

My personal collection of Codex skills. All custom skills live in a dedicated top-level directory in this repository; `~/.codex/skills/` is the local installed copy.

## Available skills

| Skill | Purpose |
| --- | --- |
| [gzh-webchat-cover](gzh-webchat-cover/SKILL.md) | Turn long Chinese article titles into cinematic, product-tech, or editorial-diagram covers |
| [md-wechat-layout](md-wechat-layout/SKILL.md) | Convert Markdown to WeChat rich text, defaulting to Blue Journal numbered sections and pale blue highlights |
| [gzh-final-check](gzh-final-check/SKILL.md) | Review language, test claims, media integrity, case explanations, and reader promises; inspect covers and previews when supplied; read-only by default |
| [wechat-article-writing](wechat-article-writing/SKILL.md) | Plan cases, gather genuine author reactions as needed, explain evidence-based judgments, and revise AI articles without concealing sponsored-content limitations |

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

The default **Blue Journal** (`晴蓝手记`) style uses black body text on white, large pale blue italic section numbers, centered black headings, and pale blue `==highlights==`. H2 headings receive numbers automatically; ordinary bold stays black. **Mist Blue Bubble** (four-point star headings and pale blue cards with dashed borders), **Cyan Landscape**, and green **Mint Soda** remain available. See the [theme reference](md-wechat-layout/references/blue-journal.md).

- Resolve and embed local Obsidian images with small rounded corners and soft shadows.
- Render fenced code in light browser-style windows; previews scroll, while copied content remains fully expanded.
- Convert links and inline code to display text by default, without adding references.
- Blue Journal uses the WeChat system font stack, 16px body text, 25.6px line height, 1px letter spacing, pale blue highlights, sky blue section labels, and pale blue prompt/code window headers. The final label becomes a smaller END (60px by default versus 72px numbers), with its title intact. Images return to natural responsive sizing without percentage scaling, using 32px padding on both sides of a full-width border-box container; verify by pasting again into WeChat.
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

Omitting the theme selects Blue Journal. Explicit theme names accepted by the CLI include `雾蓝气泡` (Mist Blue Bubble), `青山绿水` (Cyan Landscape), `薄荷气泡` (Mint Soda), and `晴蓝手记` (Blue Journal, alias `洛洛蓝`, ID `blue-journal`).

### CLI usage

Run from the repository root:

```sh
node md-wechat-layout/scripts/render.mjs "article.md" --vault "Obsidian vault path" --out "output directory"
node md-wechat-layout/scripts/render.mjs "article.md" --theme "薄荷气泡" --vault "Obsidian vault path" --out "output directory"
node md-wechat-layout/scripts/render.mjs "article.md" --theme "晴蓝手记" --vault "Obsidian vault path" --out "output directory"
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
