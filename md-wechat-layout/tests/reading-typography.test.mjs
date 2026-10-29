import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { convert } from '../scripts/render.mjs';

function article(t, source) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wechat-reading-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const input = path.join(dir, '文章.md');
  fs.writeFileSync(input, source);
  return input;
}

const themes = ['晴蓝手记', '雾蓝气泡', '薄荷气泡', '青山绿水'];
const textOf = html => html.replace(/<[^>]+>/g, '').replace(/&quot;/g, '"').replace(/&#39;/g, "'");

test('普通文字转换引号与中英间距，覆盖行内样式和各块级场景，源文不变', t => {
  const source = '## 标题AI。\n\n\u3000\u3000使用“AI工具”需要3天，已有 AI 空格。中文**GPT**模型与`API`接口。\n\n- 第2项“说明”\n\n> 引用AI\n\n|项目AI|数量|\n|---|---|\n|模型3|2天|\n\n访问[官网AI](https://example.com/中文AI?q=1)';
  const input = article(t, source);
  for (const theme of themes) {
    const html = convert(input, { theme }).html;
    const text = textOf(html);
    for (const expected of ['标题 AI。', '使用「AI 工具」需要 3 天，已有 AI 空格。',
      '中文 GPT 模型与 API 接口。', '第 2 项「说明」', '引用 AI', '项目 AI', '模型 3', '2 天', '官网 AI']) {
      assert.ok(text.includes(expected), `${theme}: ${expected}`);
    }
    assert.doesNotMatch(text, /\u3000|“|”|已有  AI/);
    assert.equal(fs.readFileSync(input, 'utf8'), source);
  }
});

test('代码与自动网址保持原文，只在行内代码外补边界空格', t => {
  const source = '中文`中AI“原样”`结束；中文`API`接口。英文 "quotes"。\n\nhttps://example.com/中文AI?q=3\n\n```text\n  中文AI“原样”3天\n```';
  const input = article(t, source);
  const text = textOf(convert(input).html);
  for (const expected of ['中AI“原样”', '中文 API 接口。', '英文 "quotes"。', 'https://example.com/中文AI?q=3', '  中文AI“原样”3天']) {
    assert.ok(text.includes(expected), expected);
  }
});

test('字间距处理不把标题正文中的数字误判为章节编号，链接目标保持完整', t => {
  const input = article(t, '## 3天复盘。\n\n[中文AI](https://example.com/中文AI?q=1)');
  const html = convert(input, { linkFootnotes: true }).html;
  assert.match(html, /<h2[^>]*>3 天复盘。<\/h2>/);
  assert.ok(textOf(html).includes('https://example.com/%E4%B8%AD%E6%96%87AI?q=1'));
});

test('标题与普通段落留一行间距，首行不缩进，段落不按字数自动拆分', t => {
  const longParagraph = '这是一句完整的话。'.repeat(35);
  const input = article(t, `# 一级。\n\n## 二级。\n\n### 三级。\n\n#### 四级。\n\n##### 五级。\n\n###### 六级。\n\n${longParagraph}\n\n下一段。`);
  for (const theme of themes) {
    for (const fontSize of [12, 16, 24]) {
      const html = convert(input, { theme, fontSize }).html;
      const gap = Number((fontSize * (theme === '晴蓝手记' ? 1.6 : 1.9)).toFixed(2));
      for (const heading of html.matchAll(/<h[1-6][^>]*style="([^"]*)"/g)) {
        assert.ok(heading[1].includes(`margin-bottom:${gap}px;`));
      }
      const paragraphs = [...html.matchAll(/<p[^>]*style="([^"]*)">([^<]+)<\/p>/g)];
      const body = paragraphs.find(p => p[2] === longParagraph);
      assert.ok(body, '完整段落保留，交给语义和手机预览检查');
      assert.ok(body[1].includes('text-indent:0;'));
      assert.ok(body[1].includes(`margin-bottom:${gap}px;`));
      assert.match(html, /一级。<\/h1>/);
    }
  }
});

test('独立图、单列图库和混排图上下留白，图片地址与尺寸不变', t => {
  const url = 'https://example.com/中文AI.png';
  const input = article(t, `图片前AI\n![](${url})\n图片后3天`);
  for (const theme of themes) {
    let html = convert(input, { theme }).html;
    assert.match(html, /<span style="display:block;margin:1.9em 0;[^>]*><img/);
    assert.equal(decodeURI(html.match(/<img[^>]*src="([^"]+)"/)[1]), url);
    assert.match(textOf(html), /图片前 AI/);
    fs.writeFileSync(input, `![](${url})\n\n![](${url})`);
    html = convert(input, { theme }).html;
    assert.equal((html.match(/<img\b/g) || []).length, 2);
    assert.match(html, /<section[^>]*margin-top:[\d.]+px;margin-bottom:[\d.]+px;/);
    fs.writeFileSync(input, `![](${url})`);
    html = convert(input, { theme }).html;
    assert.match(html, /margin:(?:1.9em 0|[\d.]+px 0|0 [^;]+;[^>]*margin-bottom:[\d.]+px;)/);
    fs.writeFileSync(input, `图片前AI\n![](${url})\n图片后3天`);
  }
});
