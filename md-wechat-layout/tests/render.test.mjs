import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { convert, normalizeObsidian, preview } from '../scripts/render.mjs';

test('两种主题保留正文、内联样式、代码高亮，外链转参考资料', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wechat-test-'));
  const input = path.join(dir, '文章.md');
  fs.writeFileSync(input, '---\ntitle: 隐藏属性\n---\n# 测试标题\n\n正文 **强调**\n\n## 小节\n\n[来源](https://example.com)\n\n```js\nconst x = 1;\n```\n\n|甲|乙|\n|--|--|\n|1|2|');
  for (const theme of ['青山绿水', '薄荷气泡']) {
    const result = convert(input, { theme, linkFootnotes: true });
    assert.match(result.html, /测试标题/);
    assert.match(result.html, /style="/);
    assert.match(result.html, /<table/);
    assert.match(result.html, /参考资料/);
    assert.match(result.html, /<\/span> \[1\]/);
    assert.doesNotMatch(result.html, /vertical-align:super/);
    assert.match(result.html, /const/);
    assert.match(result.html, /background-color:#ff5f56/);
    assert.match(result.html, /background-color:#ffffff;padding:14px 16px/);
    assert.doesNotMatch(result.html, /隐藏属性|data-line=/);
    assert.doesNotMatch(result.html, /<span[^>]*background-image:[^>]*gradient/);
    assert.match(result.html, /<p[^>]*line-height:30.4px/);
  }
  assert.notEqual(convert(input).html, convert(input, { theme: '薄荷气泡' }).html);
  assert.doesNotMatch(convert(input).html, /参考资料/);
  assert.match(convert(input).html, /font-size:16px;line-height:30.4px/);
  assert.match(convert(input, { theme: '青山绿水' }).html, /<p[^>]*font-weight:700[^>]*>正文 强调<\/p>/);
  assert.equal(convert(input).theme, '雾蓝气泡');
  assert.match(convert(input).html, /background-color:#f0f5fa;border:1px dashed #b8cee2/);
  assert.match(convert(input).html, /color:#315b83/);
  assert.equal(convert(input).html, convert(input, { theme: '雾蓝气泡' }).html);
  assert.doesNotMatch(convert(input).html, /<strong/);
  const mint = convert(input, { theme: '薄荷气泡' }).html;
  assert.match(mint, /<h2[^>]*font-size:18.4px;line-height:34.96px;[^>]*>✧ 小节<\/h2>/);
  assert.doesNotMatch(mint, /<h2[^>]*><span/);
});

test('Obsidian图片找到库附件并内嵌，缺失及重名报错', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wechat-vault-'));
  fs.mkdirSync(path.join(dir, '附件'));
  fs.writeFileSync(path.join(dir, '附件', '图.png'), Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==', 'base64'));
  const input = path.join(dir, '文章.md');
  fs.writeFileSync(input, '![[图.png]]');
  const imageHtml = convert(input, { vault: dir }).html;
  assert.match(imageHtml, /src="data:image\/png;base64,/);
  assert.match(imageHtml, /border-radius:6px/);
  assert.doesNotMatch(imageHtml, />图\.png</);
  fs.mkdirSync(path.join(dir, '另一个'));
  fs.copyFileSync(path.join(dir, '附件', '图.png'), path.join(dir, '另一个', '图.png'));
  assert.throws(() => convert(input, { vault: dir }), /不唯一/);
  fs.writeFileSync(input, '![[不存在.png]]');
  assert.throws(() => convert(input, { vault: dir }), /找不到图片/);
});

test('Obsidian语法转换保护代码，HTML脚本不执行', () => {
  const warnings = [];
  const normalized = normalizeObsidian('[[笔记|名称]]\n> [!note] 提示\n%%隐藏%%\n`[[代码]]`\n```md\n![[代码.png]]\n```', warnings);
  assert.match(normalized, /名称\n> \*\*提示\*\*/);
  assert.doesNotMatch(normalized, /隐藏/);
  assert.match(normalized, /`\[\[代码\]\]`/);
  assert.match(normalized, /!\[\[代码.png\]\]/);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wechat-safe-'));
  const input = path.join(dir, '文章.md');
  fs.writeFileSync(input, '<script>alert(1)</script>');
  assert.doesNotMatch(convert(input).html, /<script>/);
  assert.match(preview('<p>正文</p>', '<测试>', []), /&lt;测试&gt;/);
});

test('列表及段落行内代码统一文本尺寸，围栏代码保持独立窗口', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wechat-inline-'));
  const input = path.join(dir, '文章.md');
  fs.writeFileSync(input, '- **Schema：工作规范。**本文写进 `AGENTS.md`。\n\n可用 `[[笔记名]]`，安装到[官网](https://example.com)。\n\n```js\nconst x = 1;\n```');
  const html = convert(input).html;
  assert.doesNotMatch(html, /\*\*Schema|font-size:0.86em/);
  assert.match(html, /本文写进 AGENTS.md。/);
  assert.match(html, /可用 \[\[笔记名\]\]，安装到官网。/);
  assert.doesNotMatch(html, /<a\b|<span[^>]*>AGENTS.md/);
  assert.match(html, /<section[^>]*font-size:16px;line-height:30.4px[^>]*>•&nbsp;Schema/);
  assert.match(html, /<code[^>]*font-size:13px;line-height:1.7/);
});
