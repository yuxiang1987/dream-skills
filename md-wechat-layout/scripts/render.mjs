import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import MarkdownIt from 'markdown-it';
import { themes, buildStyles } from '../assets/upstream/themes.js';
import { blueJournal } from './blue-journal.mjs';
import { renderMarkdown, stripPreviewMeta, setImageResolver } from '../assets/upstream/renderer.js';

const brandIntroAsset = new URL('../assets/brand-intro/intro-wechat.gif', import.meta.url);
const originalBrandIntroAsset = new URL('../assets/brand-intro/intro.gif', import.meta.url);
const gifDataUri = bytes => `data:image/gif;base64,${bytes.toString('base64')}`;

const authorBioText = '我是梦哥，十年程序员，爱折腾 AI。分享实用 AI 工具、有趣玩法和实操心得，一起把想法做出来。';

const aliases = { '青山绿水': 'cyan-scape', '青绿山水': 'cyan-scape', '薄荷气泡': 'mint-soda', '雾蓝': 'mist-blue', '雾蓝气泡': 'mist-blue', '晴蓝手记': 'blue-journal', '洛洛蓝': 'blue-journal' };
const mime = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp' };
const escape = s => s.replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));

export function normalizeObsidian(source, warnings = []) {
  source = source.replace(/^\uFEFF/, '').replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/, '');
  // Protect fenced and inline code before converting Obsidian-only notation.
  const protectedParts = [];
  source = source.replace(/^( {0,3})(`{3,}|~{3,})[^\n]*\n[\s\S]*?^\1\2[^\n]*(?:\n|$)|(`+)[^\n]*?\3/gm, s => {
    const key = `\u0000CODE${protectedParts.length}\u0000`;
    protectedParts.push(s); return key;
  });
  source = source.replace(/%%[\s\S]*?%%/g, '');
  source = source.replace(/!\[\[([^\]]+)\]\]/g, (_, target) => {
    const [file, caption] = target.split('|');
    if (!mime[path.extname(file).toLowerCase()]) {
      warnings.push(`未展开嵌入文件：${file}，请在公众号后台处理。`);
      return `（嵌入文件：${file}）`;
    }
    const alt = caption && !/^\d+(?:x\d+)?$/.test(caption) ? caption : '';
    return `![${alt.replace(/[\[\]]/g, '')}](<${file}>)`;
  });
  source = source.replace(/\[\[([^\]]+)\]\]/g, (_, target) => {
    const [file, label] = target.split('|');
    warnings.push(`双链已转成文字：${file}`);
    return label || file;
  });
  source = source.replace(/^(\s*>\s*)\[!([^\]]+)\][+-]?\s*(.*)$/gm, (_, prefix, type, title) => `${prefix}**${title || type}**`);
  // Obsidian accepts closing bold punctuation immediately followed by Chinese.
  // Match each valid bold pair first so adjacent "**A**、**B**" never pairs across "、".
  source = source.replace(/\*\*(?!\s)(?:[^*\n]|\*(?!\*))+?(?<!\s)\*\*/gu, (match, offset, str) => {
    const next = str.slice(offset + match.length);
    return /^[\p{L}\p{N}]/u.test(next) ? `${match} ` : match;
  });
  return source.replace(/\u0000CODE(\d+)\u0000/g, (_, i) => protectedParts[Number(i)]);
}

export function convert(input, { theme = 'blue-journal', vault, fontSize = 15, linkFootnotes = false, codeMaxHeight = 320, avoidOrphans = false, brandIntro = true, introSvg = null, authorBio = true } = {}) {
  const mistBlue = (aliases[theme] || theme) === 'mist-blue';
  const selected = [...themes, blueJournal].find(t => t.id === (mistBlue ? 'mint-soda' : (aliases[theme] || theme)));
  if (!selected || !['cyan-scape', 'mint-soda', 'blue-journal'].includes(selected.id)) throw new Error(`不支持的主题：${theme}`);
  if (!Number.isFinite(fontSize) || fontSize < 12 || fontSize > 24) throw new Error('字号须为 12–24');
  if (!Number.isFinite(codeMaxHeight) || codeMaxHeight < 0) throw new Error('代码窗口高度须为非负数，0表示完整展开');
  const warnings = [];
  let source = normalizeObsidian(fs.readFileSync(input, 'utf8'), warnings);
  const root = vault ? path.resolve(vault) : null;
  let files;
  function inventory(dir) {
    return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
      if (entry.name.startsWith('.') || entry.name === 'node_modules') return [];
      const full = path.join(dir, entry.name);
      return entry.isDirectory() ? inventory(full) : entry.isFile() ? [full] : [];
    });
  }
  const resolved = new Map();
  function image(src) {
    if (/^https?:\/\//i.test(src)) return src;
    if (/^data:image\/(png|jpeg|gif|webp);base64,/i.test(src)) return src;
    if (resolved.has(src)) return resolved.get(src);
    let name;
    try { name = decodeURIComponent(src); } catch { throw new Error(`图片路径编码无效：${src}`); }
    let candidates = [path.resolve(path.dirname(input), name)];
    if (root) candidates.push(path.resolve(root, name));
    let found = [...new Set(candidates)].find(f => fs.existsSync(f) && fs.statSync(f).isFile());
    if (!found && root) {
      files ||= inventory(root);
      candidates = files.filter(f => path.relative(root, f).split(path.sep).join('/').endsWith(name.replaceAll('\\', '/')));
      if (candidates.length > 1) throw new Error(`图片路径不唯一：${src}，请使用相对路径`);
      found = candidates[0];
    }
    if (!found) throw new Error(`找不到图片：${src}，可传入 --vault Obsidian库路径`);
    const type = mime[path.extname(found).toLowerCase()];
    if (!type) throw new Error(`图片格式不支持：${src}，请转为 PNG/JPEG/GIF/WebP`);
    warnings.push(`本地图片已内嵌：${src}；粘贴后检查微信是否成功转存。`);
    const result = `data:${type};base64,${fs.readFileSync(found).toString('base64')}`;
    resolved.set(src, result); resolved.set(escape(src), result); return result;
  }
  // Pre-resolve every image so missing attachments cannot silently produce broken output.
  let tokens = new MarkdownIt({ linkify: true }).parse(source, {});
  // 源稿末尾已有同一句简介（普通段落、加粗或 > 引用块）时，剥离后统一按「上方横线 + 纯加粗段落」输出，避免变成引用卡片或重复横线。
  if (authorBio) {
    const normBio = s => s.replace(/\s+/g, '');
    const targetBio = normBio(authorBioText);
    let bioStartLine = null;
    let prevToken = null;
    if (tokens.at(-3)?.type === 'paragraph_open' && tokens.at(-3).level === 0
        && tokens.at(-2)?.type === 'inline' && tokens.at(-1)?.type === 'paragraph_close'
        && normBio(tokens.at(-2).children.map(t => t.content).join('')) === targetBio) {
      bioStartLine = tokens.at(-3).map[0];
      prevToken = tokens.at(-4);
    } else if (tokens.at(-5)?.type === 'blockquote_open' && tokens.at(-5).level === 0
        && tokens.at(-4)?.type === 'paragraph_open' && tokens.at(-3)?.type === 'inline'
        && tokens.at(-2)?.type === 'paragraph_close' && tokens.at(-1)?.type === 'blockquote_close'
        && normBio(tokens.at(-3).children.map(t => t.content).join('')) === targetBio) {
      bioStartLine = tokens.at(-5).map[0];
      prevToken = tokens.at(-6);
    }
    if (bioStartLine !== null) {
      const cutLine = (prevToken?.type === 'hr' && prevToken.level === 0) ? prevToken.map[0] : bioStartLine;
      source = source.split('\n').slice(0, cutLine).join('\n');
      tokens = new MarkdownIt({ linkify: true }).parse(source, {});
    }
  }
  function visit(items) { for (const token of items) { if (token.type === 'image') image(token.attrGet('src')); if (token.children) visit(token.children); } }
  visit(tokens);
  setImageResolver(image);
  try {
    // Explicit unitless line heights survive editor rewrites of the outer section.
    const base = buildStyles(selected, { fontSize });
    const custom = Object.fromEntries(['p', 'liP', 'bqP', 'strong', 'em', 's', 'mark', 'a', 'code', 'caption', 'th', 'td'].map(key => [key, `${base[key]}line-height:1.8;`]));
    // WeChat may reparent paragraphs into its own font-sized wrappers on paste.
    // Set both dimensions on each body paragraph instead of inheriting the root.
    custom.li = base.li;
    const withoutTextMetrics = style => style.split(';').filter(property => property.trim() && !/^\s*(font-family|font-size|line-height|vertical-align):/.test(property)).join(';') + ';';
    if (selected.id === 'mint-soda') {
      const headingSize = Number((fontSize * 1.15).toFixed(2));
      custom.h2 = `${withoutTextMetrics(base.h2)}font-size:${headingSize}px;line-height:${Number((headingSize * 1.9).toFixed(2))}px;`;
      custom.h2WrapOpen = '✧ ';
      custom.h2WrapClose = '';
      custom.h2 += 'margin:1.8em 8px 0.9em;border-bottom:1px dotted #d5eae3;';
      for (const key of ['th', 'td']) custom[key] += 'font-size:14px;line-height:26px;word-break:normal;overflow-wrap:break-word;';
    }
    for (const key of ['p', 'liP', 'bqP', 'li']) custom[key] = `${withoutTextMetrics(custom[key])}font-size:${fontSize}px;line-height:${fontSize * 1.9}px;`;
    if (selected.id === 'blue-journal') {
      for (const key of ['p', 'liP', 'bqP', 'li']) custom[key] = `${withoutTextMetrics(custom[key])}font-size:${fontSize}px;line-height:${Number((fontSize * 1.7).toFixed(2))}px;`;
      for (const key of ['th', 'td']) custom[key] += 'font-size:14px;line-height:26px;overflow-wrap:break-word;';
    }
    if (selected.id === 'mint-soda') for (const key of ['p', 'liP', 'bqP', 'li']) custom[key] += 'text-align:left;';
    const paragraphGap = Number((fontSize * (selected.id === 'blue-journal' ? 1.7 : 1.9)).toFixed(2));
    for (const key of ['p', 'liP', 'bqP']) custom[key] += `text-indent:0;margin-bottom:${paragraphGap}px;white-space:normal;`;
    custom.p = custom.p.replace(/text-align:[^;]*;/g, '') + 'text-align:justify;text-align-last:left;';
    for (const key of ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']) custom[key] = `${custom[key] || base[key]}margin-bottom:${paragraphGap}px;`;
    custom.gallery = `${base.gallery}margin-top:${paragraphGap}px;margin-bottom:${paragraphGap}px;`;
    for (const key of ['strong', 'em', 's', 'mark', 'a', 'code']) {
      custom[key] = `${withoutTextMetrics(custom[key])}font-family:inherit;font-size:inherit;line-height:inherit;vertical-align:baseline;`;
    }
    custom.code += 'font-weight:inherit;';
    const imageFinish = selected.id === 'blue-journal'
      ? 'border-radius:6px;box-shadow:0 5px 16px rgba(40,65,90,0.12),0 1px 4px rgba(40,65,90,0.06);'
      : selected.id === 'mint-soda'
      ? 'border-radius:6px;box-shadow:0 3px 10px rgba(35,65,55,0.10),0 1px 3px rgba(35,65,55,0.05);'
      : 'border-radius:6px;box-shadow:0 5px 16px rgba(35,65,55,0.16),0 1px 4px rgba(35,65,55,0.08);';
    custom.img = `${base.img}${imageFinish}`;
    custom.galleryImg = `${base.galleryImg}${imageFinish}`;
    custom.pre = 'background-color:#ffffff;border:1px solid #e3e8e7;border-radius:10px;margin:1.2em 8px;overflow:hidden;';
    custom.preHeader = 'padding:10px 14px;background-color:#f4f6f5;border-bottom:1px solid #e3e8e7;font-size:12px;line-height:20px;';
    custom.preLabel = "font-family:Menlo,Consolas,monospace;color:#75827e;font-size:12px;line-height:20px;margin-left:10px;vertical-align:middle;";
    custom.preBody = 'background-color:#ffffff;padding:14px 16px;margin:0;overflow-x:auto;';
    custom.preCode = 'color:#34413c;white-space:pre-wrap;word-break:break-word;overflow-wrap:anywhere;';
    if (selected.id === 'blue-journal') {
      for (const key of ['pre', 'preHeader', 'preLabel']) custom[key] = base[key];
    }
    if (codeMaxHeight > 0) custom.preBody += `max-height:${codeMaxHeight}px;overflow:auto;box-sizing:border-box;-webkit-overflow-scrolling:touch;`;
    const renderTheme = { ...selected, codeTheme: 'light', codeChrome: 'mac' };
    let html = stripPreviewMeta(renderMarkdown(source, renderTheme, { fontSize, linkFootnotes, galleryMode: 'stack', macCode: true, plainInlineText: true, readingTypography: true, avoidOrphans, custom }));
    // Keep Markdown emphasis inline. A fully bold paragraph is still ordinary
    // body copy; only an explicit Markdown blockquote should become a card.
    if (/\$\$|\$[^\n$]+\$/.test(source)) warnings.push('数学公式未转换为图片，请检查预览。');
    if (selected.id === 'mint-soda') html = html.replace(/<(th|td) style="([^"]*)">/g, '<$1 style="$2min-width:5.5em;">');
    // 正文中的英文单词/技术标识符（如 WorkBuddy、huashu-design、_design）自动加粗，跳过代码块、标题、已有 strong、URL 与 HTML 实体。
    const inlineStrongOpen = `<strong style="${escape(custom.strong || base.strong)}">`;
    html = html.replace(
      /<svg\b[\s\S]*?<\/svg>|<code\b[\s\S]*?<\/code>|<h[1-6]\b[\s\S]*?<\/h[1-6]>|<strong\b[\s\S]*?<\/strong>|<section\b[^>]*font-weight:700[^>]*>[\s\S]*?<\/section>|<p\b[^>]*aria-hidden="true"[^>]*>[\s\S]*?<\/p>|<a\b[\s\S]*?<\/a>|<[^>]+>|https?:\/\/[^\s<]+|(&[a-zA-Z0-9#]+;)|(_?[A-Za-z][A-Za-z0-9_.-]*(?: +[A-Za-z][A-Za-z0-9_.-]*)*)/g,
      (match, _entity, eng) => {
        if (!eng || (eng.match(/[A-Za-z]/g) || []).length < 2) return match;
        return `${inlineStrongOpen}${eng}</strong>`;
      }
    );
    // 个人简介仅加在导出末尾，默认上方带分隔横线并整句加粗（不套引用卡片）；源稿已有同一句结尾时不重复。
    if (authorBio && !html.replace(/<[^>]*>/g, '').trim().endsWith(authorBioText)) {
      const separator = base.hrHtml || `<hr style="${escape(base.hr)}"/>`;
      const hasSeparator = html.replace(/<\/section>\s*$/, '').trimEnd().endsWith(separator);
      const strongStyle = custom.strong || base.strong;
      const closing = `${hasSeparator ? '' : separator}<p style="${custom.p}margin:0;"><strong style="${strongStyle}">${escape(authorBioText)}</strong></p>`;
      html = html.replace(/<\/section>\s*$/, closing + '</section>');
    }
    if (mistBlue) {
      const family = "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',Arial,sans-serif;";
      html = html.replace(/<(section|p|h[1-6]|blockquote|th|td|span)\b([^>]*?)style="([^"]*)"/g, (tag, element, attrs, style) => {
        if (/font-family:[^;]*(?:Menlo|Consolas|monospace)/i.test(style)) return tag;
        return `<${element}${attrs}style="${style.replace(/font-family:[^;]*;?/gi, '')}${family}"`;
      });
      const colors = { '#1e6b5a':'#315b83', '#2fbf9b':'#6d9fc8', '#9fdcc9':'#adc9e2', '#d5eae3':'#dbe6f0', '#e8f8f3':'#f0f5fa', '#4a8a7a':'#56718b', '#7ab3a5':'#7898b5', '#c9f2e6':'#e1edf7', '#bfe8dc':'#d1dfed' };
      html = html.replace(/style="([^"]*)"/g, (_, style) => `style="${style.replace(/#[0-9a-f]{6}\b/gi, color => colors[color.toLowerCase()] || color).replaceAll('rgba(35,65,55,', 'rgba(40,65,90,')}"`);
      html = html.replace(/<p style="([^"]*)">/g, (tag, style) => {
        if (!style.includes('border-left:3px solid #adc9e2')) return tag;
        const clean = style.split(';').filter(property => !/^\s*(border-left|padding-left):/.test(property)).join(';');
        return `<p style="${clean};background-color:#f0f5fa;border:1px dashed #b8cee2;border-radius:6px;padding:12px 16px;">`;
      });
    }
    // 兼容版及原版均视为同一片头，源稿已插入时不再添加；传入 introSvg 时使用内嵌 SVG+SMIL 替换默认 GIF。
    if (introSvg) {
      let rawSvg = fs.existsSync(introSvg) && fs.statSync(introSvg).isFile()
        ? fs.readFileSync(introSvg, 'utf8').trim()
        : String(introSvg).trim();
      const match = rawSvg.match(/<svg\b[\s\S]*<\/svg>/i);
      if (!match) throw new Error('自定义 SVG 片头内容无效，需包含完整的 <svg>...</svg>');
      const svgMarkup = match[0];
      if (!html.includes('<svg ')) {
        const introFrameStyle = 'margin:0 0 24px;padding:8px 10px;background-color:#ffffff;border:1.5px solid #7ec8ff;border-radius:12px;box-sizing:border-box;box-shadow:0 4px 14px rgba(70,183,255,0.10);text-align:center;';
        const opening = `<section style="${introFrameStyle}">${svgMarkup}</section>`;
        html = html.replace(/^<section\b[^>]*>/, tag => tag + opening);
      }
      warnings.push('已启用自定义 SVG+SMIL 片头；粘贴后检查微信公众号保存重载与手机端动画播放。');
    } else if (brandIntro) {
      const src = gifDataUri(fs.readFileSync(brandIntroAsset));
      if (!html.includes(src) && !html.includes(gifDataUri(fs.readFileSync(originalBrandIntroAsset)))) {
        const opening = `<section style="margin:0 0 24px;padding:0;text-align:center;font-size:0;line-height:0;"><img src="${src}" alt="程序员梦哥：分享AI、少踩坑" width="1000" height="300" style="display:inline-block;width:100%;max-width:100%;height:auto;vertical-align:middle;${imageFinish}"></section>`;
        html = html.replace(/^<section\b[^>]*>/, tag => tag + opening);
      }
      warnings.push('已启用像素粒子片头；粘贴后检查微信转存和动画播放。片头失败时，仅单独插入随预览导出的 GIF。');
    }
    return { html, theme: mistBlue ? '雾蓝气泡' : selected.name, warnings: [...new Set(warnings)] };
  } finally { setImageResolver(null); }
}

export function preview(html, title, warnings, introFile) {
  const introLink = introFile ? ` <a href="${escape(encodeURIComponent(path.basename(introFile)))}" download>单独下载片头 GIF</a>` : '';
  return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(title)}</title>
<style>body{margin:0;background:#f3f5f4;font-family:system-ui}header{position:sticky;top:0;background:white;padding:16px;z-index:1;border-bottom:1px solid #ddd}button{padding:10px 18px;cursor:pointer}article{max-width:677px;margin:24px auto;background:white;padding:24px}aside{max-width:720px;margin:auto;color:#765b16;font-size:14px}</style>
<style>article section[style*="max-height:"][style*="overflow:auto"]{scrollbar-gutter:stable;scrollbar-color:#8bb7d7 #edf5fa}article section[style*="max-height:"][style*="overflow:auto"]::-webkit-scrollbar{width:8px}article section[style*="max-height:"][style*="overflow:auto"]::-webkit-scrollbar-track{background:#edf5fa}article section[style*="max-height:"][style*="overflow:auto"]::-webkit-scrollbar-thumb{background:#8bb7d7;border-radius:4px}</style>
<header><button id="copy">复制完整公众号排版</button> <span id="status">复制保留全文与内联样式；图片、滚动效果需在微信粘贴后确认</span>${introLink}</header>
<aside><details><summary>排版提示（${warnings.length}项）</summary>${warnings.map(w => `<p>${escape(w)}</p>`).join('')}</details></aside><article id="content">${html}</article>
<script>
document.getElementById('copy').onclick=async()=>{
const content=document.getElementById('content'),status=document.getElementById('status');
let ok=false;
try{await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([content.innerHTML],{type:'text/html'}),'text/plain':new Blob([content.innerText],{type:'text/plain'})})]);ok=true}catch{
const selection=getSelection(),range=document.createRange();range.selectNodeContents(content);selection.removeAllRanges();selection.addRange(range);
try{ok=document.execCommand('copy')}catch{}selection.removeAllRanges();}
status.textContent=ok?'已复制富文本，去公众号正文粘贴':'复制失败：请选中下方文章并按 Ctrl+C';};
</script></html>`;
}

function main() {
  const args = process.argv.slice(2);
  const input = args.shift();
  if (!input || input === '--help') {
    console.log('node scripts/render.mjs article.md [--theme 雾蓝气泡|青山绿水|薄荷气泡|晴蓝手记] [--vault 库目录] [--out 输出目录] [--font-size 15] [--code-max-height 320] [--avoid-orphans] [--link-footnotes] [--intro-svg 片头.svg] [--no-brand-intro] [--no-author-bio]'); return;
  }
  const options = {};
  let out = path.join(path.dirname(path.resolve(input)), 'wechat-output');
  while (args.length) {
    const key = args.shift();
    if (key === '--no-author-bio') { options.authorBio = false; continue; }
    if (key === '--no-brand-intro') { options.brandIntro = false; continue; }
    if (key === '--avoid-orphans') { options.avoidOrphans = true; continue; }
    if (key === '--keep-links') { options.linkFootnotes = false; continue; }
    if (key === '--link-footnotes') { options.linkFootnotes = true; continue; }
    if (!['--theme','--vault','--out','--font-size','--code-max-height','--intro-svg'].includes(key)) throw new Error(`未知参数：${key}`);
    const value = args.shift();
    if (!value || value.startsWith('--')) throw new Error(`参数缺少值：${key}`);
    if (key === '--out') out = path.resolve(value);
    else if (key === '--intro-svg') options.introSvg = path.resolve(value);
    else if (key === '--code-max-height') options.codeMaxHeight = Number(value);
    else if (key === '--font-size') options.fontSize = Number(value);
    else options[key.slice(2)] = value;
  }
  const result = convert(path.resolve(input), options);
  const name = path.basename(input, path.extname(input));
  fs.mkdirSync(out, { recursive: true });
  const fragment = path.join(out, `${name}.wechat.html`);
  const page = path.join(out, `${name}.preview.html`);
  const report = path.join(out, `${name}.report.json`);
  const introGif = (options.brandIntro === false || options.introSvg) ? null : path.join(out, `${name}.intro.gif`);
  if (introGif) fs.copyFileSync(brandIntroAsset, introGif);
  fs.writeFileSync(fragment, result.html);
  fs.writeFileSync(page, preview(result.html, `${name} · ${result.theme}`, result.warnings, introGif));
  fs.writeFileSync(report, JSON.stringify({ input: path.resolve(input), theme: result.theme, fragment, preview: page, introGif, warnings: result.warnings }, null, 2));
  console.log(JSON.stringify({ theme: result.theme, fragment, preview: page, report, introGif, warnings: result.warnings }, null, 2));
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try { main(); } catch (error) { console.error(error.message); process.exitCode = 1; }
}
