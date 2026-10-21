import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { convert, preview } from '../scripts/render.mjs';

function article(t, source) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'blue-journal-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const input = path.join(dir, '文章.md');
  fs.writeFileSync(input, source);
  return input;
}

test('晴蓝手记恢复自适应图片，用固定左右间距，保留原图内容', t => {
  const input = article(t, '![[图.png]]');
  const bytes = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==', 'base64');
  const filename = path.join(path.dirname(input), '图.png');
  fs.writeFileSync(filename, bytes);
  const html = convert(input, { theme: '晴蓝手记' }).html;
  assert.match(html, /<p[^>]*margin:1.2em 20px;padding:0;box-sizing:border-box;[^>]*><img/);
  assert.match(html, /<img[^>]*style="[^"]*width:auto;height:auto;max-width:100%;margin:0 auto/);
  assert.match(html, /border-radius:6px/);
  assert.match(html, /box-shadow:/);
  assert.ok(html.includes(bytes.toString('base64')));
  assert.deepEqual(fs.readFileSync(filename), bytes);
  assert.doesNotMatch(html, /max-width:92%|padding:0 4%/);
  assert.doesNotMatch(convert(input, { theme: '雾蓝气泡' }).html, /margin:1.2em 20px/);
  fs.writeFileSync(input, '![[图.png]]\n\n![[图.png]]');
  const gallery = convert(input, { theme: '晴蓝手记' }).html;
  assert.equal((gallery.match(/margin-left:20px;margin-right:20px;box-sizing:border-box/g) || []).length, 2);
  fs.writeFileSync(input, '图片前\n![[图.png]]\n图片后');
  const mixed = convert(input, { theme: '晴蓝手记' }).html;
  assert.match(mixed, /<span[^>]*margin:1.2em 20px;padding:0;box-sizing:border-box;[^>]*><img/);
  assert.match(mixed, /图片前/);
  assert.match(mixed, /图片后/);
  assert.equal((mixed.match(/margin:1.2em 20px;padding:0;box-sizing:border-box/g) || []).length, 1);
});

test('晴蓝手记提示词和代码窗口采用浅蓝标题栏，其他主题保留浅灰栏', t => {
  const input = article(t, '```提示词\n拿出全部本事。\n```\n\n```js\nconst value = 1;\n```');
  const html = convert(input, { theme: '晴蓝手记' }).html;
  assert.equal((html.match(/background-color:#e1f3ff/g) || []).length, 2);
  assert.match(html, /color:#4c87b3[^>]*>提示词<\/span>/);
  assert.match(html, /background-color:#ffffff;padding:14px 16px/);
  assert.match(html, /background-color:#ff5f56/);
  assert.match(html, /拿出全部本事。/);
  assert.match(html, /const/);
  assert.doesNotMatch(html, /background-color:#f4f6f5/);
  for (const theme of ['雾蓝气泡', '薄荷气泡', '青山绿水']) {
    const legacy = convert(input, { theme }).html;
    assert.match(legacy, /background-color:#f4f6f5/);
    assert.doesNotMatch(legacy, /background-color:#e1f3ff/);
  }
});

test('晴蓝手记保留内容和源文，编号分块，只有显式高亮铺浅蓝底', t => {
  const source = '# 演示标题\n\n普通正文 **黑色粗体** 与 ==跨行也保留的浅蓝重点==。\n\n## 开始实操\n\n段落内容\n\n### 局部细节\n\n## 02 观察结果\n\n> 引用说明\n\n| 项目 | 结果 |\n| --- | --- |\n| 配色 | 蓝色 |\n\n```js\nconst value = 1;\n```';
  const input = article(t, source);
  const { html, theme } = convert(input, { theme: '晴蓝手记' });
  assert.equal(theme, '晴蓝手记');
  assert.equal(fs.readFileSync(input, 'utf8'), source);
  assert.match(html, /<p[^>]*font-size:72px;line-height:84px[^>]*color:#8dd6ff[^>]*>01<\/p><h2/);
  assert.match(html, /<h2[^>]*>开始实操<\/h2><\/section>/);
  assert.match(html, />END<\/p><h2[^>]*>观察结果<\/h2>/);
  assert.equal((html.match(/aria-hidden="true"/g) || []).length, 2);
  assert.match(html, /<strong[^>]*color:#1a1a1a[^>]*>黑色粗体<\/strong>/);
  assert.match(html, /<mark[^>]*background-color:#e8f7ff[^>]*font-size:inherit[^>]*>跨行也保留的浅蓝重点<\/mark>/);
  assert.match(html, /<p[^>]*font-size:16px;line-height:25.6px/);
  assert.match(html, /<blockquote/);
  assert.match(html, /<table/);
  assert.match(html, /const/);
  assert.doesNotMatch(html, /✧|data-line=|<style|<script|#ddf7cb|#1e6b5a|#2fbf9b/);
  assert.match(preview(html, '蓝色预览', []), /<article id="content">/);
});

test('别名一致、重复渲染重置编号、格式化标题与多级标题内容完整', t => {
  const input = article(t, '## **第一节**\n\n## `第二节`\n\n### 不编号\n\n## 03、 最后一节');
  const expected = convert(input, { theme: '晴蓝手记' }).html;
  for (const theme of ['blue-journal', '洛洛蓝', '晴蓝手记']) {
    assert.equal(convert(input, { theme }).html, expected);
  }
  assert.equal((expected.match(/aria-hidden="true"/g) || []).length, 3);
  assert.match(expected, />02<\/p><h2[^>]*>第二节<\/h2>/);
  assert.match(expected, />END<\/p><h2[^>]*>最后一节<\/h2>/);
  assert.match(expected, /<h3[^>]*>不编号<\/h3>/);
  for (const fontSize of [12, 18, 24]) {
    const html = convert(input, { theme: '晴蓝手记', fontSize }).html;
    assert.match(html, new RegExp(`font-size:${fontSize * 4.5}px;line-height:${fontSize * 5.25}px`));
  }
});

test('最后一节自动标小号END，标题和章节顺序保留，高亮恢复浅蓝', t => {
  const input = article(t, '## 第一节\n\n==重点==\n\n## 09 **收尾**\n\n### 补充细节');
  const source = fs.readFileSync(input, 'utf8');
  const html = convert(input, { theme: '晴蓝手记' }).html;
  assert.match(html, />01<\/p><h2/);
  assert.match(html, />END<\/p><h2[^>]*><strong[^>]*>收尾<\/strong><\/h2>/);
  assert.doesNotMatch(html, />09<\/p>|>02<\/p>/);
  assert.equal((html.match(/>END<\/p>/g) || []).length, 1);
  assert.equal(fs.readFileSync(input, 'utf8'), source);
  const numberColor = html.match(/<p[^>]*aria-hidden="true"[^>]*color:(#[0-9a-f]{6})/)[1];
  const highlightColor = html.match(/<mark[^>]*background-color:(#[0-9a-f]{6})/)[1];
  assert.equal(highlightColor, '#e8f7ff');
  assert.equal(numberColor, '#8dd6ff');
  assert.match(html, /<p[^>]*font-size:72px;line-height:84px[^>]*>01<\/p>/);
  assert.match(html, /<p[^>]*font-size:60px;line-height:72px[^>]*>END<\/p>/);
  for (const fontSize of [12, 18, 24]) {
    const resized = convert(input, { theme: '晴蓝手记', fontSize }).html;
    assert.match(resized, new RegExp(`<p[^>]*font-size:${fontSize * 3.75}px;line-height:${fontSize * 4.5}px[^>]*>END</p>`));
  }
  fs.writeFileSync(input, '## 只有一节');
  assert.match(convert(input, { theme: '晴蓝手记' }).html, />END<\/p><h2[^>]*>只有一节/);
  fs.writeFileSync(input, '正文\n\n### 只有三级标题');
  assert.doesNotMatch(convert(input, { theme: '晴蓝手记' }).html, />END<\/p>/);
  fs.writeFileSync(input, source);
  for (const theme of ['雾蓝气泡', '薄荷气泡', '青山绿水']) {
    assert.doesNotMatch(convert(input, { theme }).html, />END<\/p>/);
  }
});

test('旧主题继续不自动编号，普通加粗不产生高亮', t => {
  const input = article(t, '## 开始\n\n**只加粗**');
  assert.equal(convert(input).theme, '雾蓝气泡');
  for (const theme of ['雾蓝气泡', '薄荷气泡', '青山绿水']) {
    const html = convert(input, { theme }).html;
    assert.doesNotMatch(html, /aria-hidden="true"|>01<|#8dd6ff|#e8f7ff/);
  }
  assert.doesNotMatch(convert(input, { theme: '晴蓝手记' }).html, /<mark/);
});

test('晴蓝手记使用参考微信字体栈与1.6倍正文行高，保留等宽代码', t => {
  const input = article(t, '正文 **强调**\n\n- 列表内容\n\n> 引用内容\n\n```js\nconst x = 1;\n```');
  for (const fontSize of [12, 16, 18, 24]) {
    const html = convert(input, { theme: '晴蓝手记', fontSize }).html;
    assert.match(html, /font-family:&quot;PingFang SC NEW&quot;,system-ui,-apple-system,BlinkMacSystemFont,&quot;Helvetica Neue&quot;,&quot;Hiragino Sans GB&quot;,&quot;Microsoft YaHei UI&quot;,&quot;Microsoft YaHei&quot;,Arial,sans-serif/);
    const lineHeight = Number((fontSize * 1.6).toFixed(2));
    for (const content of ['正文', '列表内容', '引用内容']) {
      assert.match(html, new RegExp(`<(?:p|section)[^>]*font-size:${fontSize}px;line-height:${lineHeight}px[^>]*>[^<]*${content}`));
    }
    assert.match(html, /<code[^>]*font-family:[^;]*(?:Menlo|Consolas|monospace)/);
    assert.doesNotMatch(html, /#91bfe3|#dfedfa|#397bb5/);
  }
});
