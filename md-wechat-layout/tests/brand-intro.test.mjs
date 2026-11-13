import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {convert} from '../scripts/render.mjs';

const asset=fileURLToPath(new URL('../assets/brand-intro/intro.gif',import.meta.url));
const original=fs.readFileSync(asset);
const src='data:image/gif;base64,'+original.toString('base64');
function article(t,body){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'wechat-brand-'));
  t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const input=path.join(dir,'article.md');fs.writeFileSync(input,body);return input;
}

test('默认片头是用户选定的粒子GIF，在所有主题中位于正文标题之前且不改稿',t=>{
  assert.equal(createHash('sha256').update(original).digest('hex'),'8e2946f77888873814187b6525c2e8d5925d2d49a042eb9f476e28eda17d64d6');
  assert.equal(original.subarray(0,6).toString(),'GIF89a');
  assert.equal(original.readUInt16LE(6),1200);assert.equal(original.readUInt16LE(8),360);
  const body='# 正文标题\n\n保留原始AI正文。',input=article(t,body);
  for(const theme of ['晴蓝手记','雾蓝气泡','薄荷气泡','青山绿水']){
    const result=convert(input,{theme}),html=result.html;
    assert.ok(html.startsWith('<section'));
    const first=html.match(/<img\b[^>]*>/)[0];assert.ok(first.includes(`src="${src}"`));
    assert.ok(html.indexOf(first)<html.indexOf('<h1'));
    assert.ok(first.includes('width:100%;max-width:100%;height:auto;'));
    assert.equal((html.match(/data:image\/gif;base64,/g)||[]).length,1);
    assert.ok(result.warnings.some(w=>w.includes('检查微信转存和动画播放')));
    assert.equal(fs.readFileSync(input,'utf8'),body);
  }
});

test('原文已有同一个片头时不重复添加',t=>{
  for(const image of [`![片头](<${asset.replaceAll('\\','/')}>)`,`![片头](${src})`]){
    const input=article(t,image+'\n\n正文。');
    const html=convert(input).html;
    assert.equal((html.match(/data:image\/gif;base64,/g)||[]).length,1);
    assert.ok(html.includes(src));
  }
});

test('明确关闭片头时API和CLI均不插入默认GIF',t=>{
  const input=article(t,'## 正文\n\n测试内容。');
  const result=convert(input,{brandIntro:false});
  assert.ok(!result.html.includes('data:image/gif'));
  assert.ok(!result.warnings.some(w=>w.includes('默认像素粒子片头')));
  const cli=fileURLToPath(new URL('../scripts/render.mjs',import.meta.url));
  const output=JSON.parse(execFileSync(process.execPath,[cli,input,'--no-brand-intro','--out',path.join(path.dirname(input),'off')],{encoding:'utf8'}));
  assert.ok(!fs.readFileSync(output.fragment,'utf8').includes('data:image/gif'));
});

test('CLI从文章目录执行仍能找到技能内资源并交付完整预览与正文',t=>{
  const input=article(t,'# 标题\n\n真实正文保持完整。');
  const cli=fileURLToPath(new URL('../scripts/render.mjs',import.meta.url));
  const output=JSON.parse(execFileSync(process.execPath,[cli,input,'--out',path.join(path.dirname(input),'out')],{cwd:path.dirname(input),encoding:'utf8'}));
  const html=fs.readFileSync(output.fragment,'utf8'),page=fs.readFileSync(output.preview,'utf8');
  assert.ok(html.includes(src));assert.ok(html.includes('真实正文保持完整'));
  assert.ok(page.includes('<article id="content">'+html+'</article>'));
  const decoded=Buffer.from(html.match(/data:image\/gif;base64,([^"\s]+)/)[1],'base64');
  assert.ok(decoded.equals(original));
});
