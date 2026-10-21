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

test('晴蓝手记保留内容和源文，编号分块，只有显式高亮铺浅蓝底', t => {
  const source = '# 演示标题\n\n普通正文 **黑色粗体** 与 ==跨行也保留的浅蓝重点==。\n\n## 开始实操\n\n段落内容\n\n### 局部细节\n\n## 02 观察结果\n\n> 引用说明\n\n| 项目 | 结果 |\n| --- | --- |\n| 配色 | 蓝色 |\n\n```js\nconst value = 1;\n```';
  const input = article(t, source);
  const { html, theme } = convert(input, { theme: '晴蓝手记' });
  assert.equal(theme, '晴蓝手记');
  assert.equal(fs.readFileSync(input, 'utf8'), source);
  assert.match(html, /<p[^>]*font-size:72px;line-height:84px[^>]*color:#91bfe3[^>]*>01<\/p><h2/);
  assert.match(html, /<h2[^>]*>开始实操<\/h2><\/section>/);
  assert.match(html, />02<\/p><h2[^>]*>观察结果<\/h2>/);
  assert.equal((html.match(/aria-hidden="true"/g) || []).length, 2);
  assert.match(html, /<strong[^>]*color:#1a1a1a[^>]*>黑色粗体<\/strong>/);
  assert.match(html, /<mark[^>]*background-color:#dfedfa[^>]*font-size:inherit[^>]*>跨行也保留的浅蓝重点<\/mark>/);
  assert.match(html, /<p[^>]*font-size:16px;line-height:28px/);
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
  assert.match(expected, />03<\/p><h2[^>]*>最后一节<\/h2>/);
  assert.match(expected, /<h3[^>]*>不编号<\/h3>/);
  for (const fontSize of [12, 18, 24]) {
    const html = convert(input, { theme: '晴蓝手记', fontSize }).html;
    assert.match(html, new RegExp(`font-size:${fontSize * 4.5}px;line-height:${fontSize * 5.25}px`));
  }
});

test('旧主题继续不自动编号，普通加粗不产生高亮', t => {
  const input = article(t, '## 开始\n\n**只加粗**');
  assert.equal(convert(input).theme, '雾蓝气泡');
  for (const theme of ['雾蓝气泡', '薄荷气泡', '青山绿水']) {
    const html = convert(input, { theme }).html;
    assert.doesNotMatch(html, /aria-hidden="true"|>01<|#91bfe3|#dfedfa/);
  }
  assert.doesNotMatch(convert(input, { theme: '晴蓝手记' }).html, /<mark/);
});
