import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {convert} from '../scripts/render.mjs';

const bio='我是梦哥，十年程序员，爱折腾 AI。分享实用 AI 工具、有趣玩法和实操心得，一起把想法做出来。';
const text=html=>html.replace(/<[^>]*>/g,'').trim();
function article(t,body){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'wechat-bio-'));
  t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const file=path.join(dir,'article.md');fs.writeFileSync(file,body);return file;
}

test('四主题末尾加入原样简介，跟随正文指标且源稿不变',t=>{
  const body='# 标题\n\n原始正文。\n\n[来源](https://example.com)',file=article(t,body);
  for(const theme of ['晴蓝手记','雾蓝气泡','薄荷气泡','青山绿水']){
    const html=convert(file,{theme,linkFootnotes:true}).html;
    assert.ok(text(html).endsWith(bio));assert.equal(text(html).split(bio).length-1,1);
    assert.ok(html.indexOf(bio)>html.indexOf('参考资料'));
    const rule=convert(article(t,'正文。\n\n---'),{theme,authorBio:false,brandIntro:false}).html.replace(/^.*?<\/p>/s,'').replace(/<\/section>\s*$/,'').trim();
    assert.ok(html.includes(rule));
    assert.match(html,/<p style="[^"]*font-size:15px;line-height:(25.5|28.5)px;[^"]*">我是梦哥/);
    assert.equal(fs.readFileSync(file,'utf8'),body);
  }
});

test('原文已经以同一句简介结尾时不重复，支持行内加粗',t=>{
  for(const ending of [bio,bio.replace('梦哥','**梦哥**')]){
    const html=convert(article(t,'正文。\n\n'+ending)).html;
    assert.equal(text(html).split(bio).length-1,1);
  }
});

test('个人简介与开头GIF可独立关闭，CLI同样生效',t=>{
  const file=article(t,'正文。');
  const noBio=convert(file,{authorBio:false}).html;
  assert.ok(!noBio.includes(bio));assert.ok(noBio.includes('data:image/gif;base64,'));
  const noIntro=convert(file,{brandIntro:false}).html;
  assert.ok(noIntro.includes(bio));assert.ok(!noIntro.includes('data:image/gif;base64,'));
  const cli=fileURLToPath(new URL('../scripts/render.mjs',import.meta.url));
  const result=JSON.parse(execFileSync(process.execPath,[cli,file,'--no-author-bio','--out',path.join(path.dirname(file),'out')],{encoding:'utf8'}));
  assert.ok(!fs.readFileSync(result.fragment,'utf8').includes(bio));
});

test('简介作为普通正文呈现，显式字号调整仍生效',t=>{
  const html=convert(article(t,'正文。'),{fontSize:18}).html;
  assert.match(html,/<p style="[^"]*font-size:18px;line-height:30.6px;[^"]*">我是梦哥/);
  assert.ok(!html.includes('关于我'));
  assert.ok(!html.includes('<h2>我是梦哥'));
});


test('简介前使用Markdown分隔线，已有简介或分隔线时不重复',t=>{
  for(const theme of ['晴蓝手记','雾蓝气泡','薄荷气泡','青山绿水']){
    const rule=convert(article(t,'正文。\n\n---'),{theme,authorBio:false,brandIntro:false}).html.replace(/^.*?<\/p>/s,'').replace(/<\/section>\s*$/,'').trim();
    for(const ending of ['',bio,bio.replace('梦哥','**梦哥**'),'---\n\n'+bio,'---']){
      const body='正文。\n\n'+ending,file=article(t,body);
      const html=convert(file,{theme,brandIntro:false}).html;
      assert.equal(text(html).split(bio).length-1,1);
      assert.equal(html.split(rule).length-1,1);
      assert.ok(html.indexOf(rule)<html.lastIndexOf('我是'));
      assert.doesNotMatch(html,/border-top:1px solid #e3eaf0/);
      assert.doesNotMatch(text(html),/---/);
      assert.equal(fs.readFileSync(file,'utf8'),body);
    }
  }
});
