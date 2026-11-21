import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {convert} from '../scripts/render.mjs';

const asset=fileURLToPath(new URL('../assets/brand-intro/intro-wechat.gif',import.meta.url));
const compatible=fs.readFileSync(asset);
const src='data:image/gif;base64,'+compatible.toString('base64');
const legacy=fileURLToPath(new URL('../assets/brand-intro/intro.gif',import.meta.url));
const legacySrc='data:image/gif;base64,'+fs.readFileSync(legacy).toString('base64');
function article(t,body){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'wechat-brand-'));
  t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const input=path.join(dir,'article.md');fs.writeFileSync(input,body);return input;
}

test('默认片头是用户选定的粒子GIF，在所有主题中位于正文标题之前且不改稿',t=>{
  assert.equal(createHash('sha256').update(compatible).digest('hex'),'01a3000a59713fdbb0242e833bf7a96aa1d06a0b143b5118682101dacd10080f');
  assert.equal(compatible.subarray(0,6).toString(),'GIF89a');
  assert.equal(compatible.readUInt16LE(6),1000);assert.equal(compatible.readUInt16LE(8),300);
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

test('原文已有兼容版或原版片头时不重复添加',t=>{
  for(const [file,data] of [[asset,src],[legacy,legacySrc]]){
    for(const image of [`![片头](<${file.replaceAll('\\','/')}>)`,`![片头](${data})`]){
      const input=article(t,image+'\n\n正文。');
      const html=convert(input).html;
      assert.equal((html.match(/data:image\/gif;base64,/g)||[]).length,1);
      assert.ok(html.includes(data));
    }
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
  assert.equal(output.introGif,null);
  assert.ok(!fs.readFileSync(output.preview,'utf8').includes('单独下载片头 GIF'));
  assert.ok(!fs.readdirSync(path.dirname(output.fragment)).some(name=>name.endsWith('.gif')));
});

test('CLI交付独立片头，下载入口位于复制正文之外',t=>{
  const input=article(t,'# 标题\n\n真实正文保持完整。');
  const cli=fileURLToPath(new URL('../scripts/render.mjs',import.meta.url));
  const output=JSON.parse(execFileSync(process.execPath,[cli,input,'--out',path.join(path.dirname(input),'out')],{cwd:path.dirname(input),encoding:'utf8'}));
  const html=fs.readFileSync(output.fragment,'utf8'),page=fs.readFileSync(output.preview,'utf8');
  assert.ok(html.includes(src));assert.ok(html.includes('真实正文保持完整'));
  assert.ok(page.includes('<article id="content">'+html+'</article>'));
  const decoded=Buffer.from(html.match(/data:image\/gif;base64,([^"\s]+)/)[1],'base64');
  assert.ok(decoded.equals(compatible));
  assert.ok(fs.readFileSync(output.introGif).equals(decoded));
  assert.equal(JSON.parse(fs.readFileSync(output.report,'utf8')).introGif,output.introGif);
  assert.ok(page.includes(`href="${encodeURIComponent(path.basename(output.introGif))}" download>单独下载片头 GIF</a>`));
  assert.ok(page.indexOf('单独下载片头 GIF')<page.indexOf('<article id="content">'));
  assert.ok(!html.includes('单独下载片头 GIF'));
});

test('传入自定义 --intro-svg 时内嵌 SVG+SMIL 片头并替换默认 GIF',t=>{
  const input=article(t,'# 标题\n\n正文内容。');
  const svgFile=path.join(path.dirname(input),'custom-intro.svg');
  const sampleSvg='<svg xmlns="http://www.w3.org/2000/svg" width="1246" height="220" viewBox="0 0 1246 220" aria-label="定制SVG片头"><rect x="0" y="0" width="100" height="50" fill="#1E6FFF"/></svg>';
  fs.writeFileSync(svgFile,sampleSvg,'utf8');
  const result=convert(input,{introSvg:svgFile});
  assert.ok(result.html.includes('aria-label="定制SVG片头"'));
  assert.ok(!result.html.includes('data:image/gif;base64,'));
  assert.ok(result.warnings.some(w=>w.includes('自定义 SVG+SMIL 片头')));
  const cli=fileURLToPath(new URL('../scripts/render.mjs',import.meta.url));
  const output=JSON.parse(execFileSync(process.execPath,[cli,input,'--intro-svg',svgFile,'--out',path.join(path.dirname(input),'svg-out')],{encoding:'utf8'}));
  assert.ok(fs.readFileSync(output.fragment,'utf8').includes('aria-label="定制SVG片头"'));
  assert.equal(output.introGif,null);
});
