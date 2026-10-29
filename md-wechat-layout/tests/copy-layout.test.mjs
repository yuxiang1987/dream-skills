import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {convert,preview} from '../scripts/render.mjs';
function article(t,source){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'wechat-copy-'));
  t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const input=path.join(dir,'article.md');fs.writeFileSync(input,source);return input;
}
const sample='正文保持完整。\n\n```prompt\n'+('中文提示词 K3.1 PRO 保持原样。\n'.repeat(80))+'```';
async function copy(html,fallback=false){
  let payload,command;
  const nodes={content:{innerHTML:html,innerText:'完整正文'},copy:{},status:{}};
  const document={getElementById:id=>nodes[id],createRange:()=>({selectNodeContents(){}}),execCommand:cmd=>{command=cmd;payload=nodes.content.innerHTML;return true;}};
  const context={document,Blob,ClipboardItem:class{constructor(data){this.data=data;}},navigator:{clipboard:{write:async items=>{if(fallback)throw new Error('无Clipboard API');payload=await items[0].data['text/html'].text();}}},getSelection:()=>({removeAllRanges(){},addRange(){}})};
  vm.runInNewContext(preview(html,'预览',[]).match(/<script>([\s\S]*?)<\/script>/)[1],context);
  await nodes.copy.onclick();return {payload,command,status:nodes.status.textContent};
}
test('完整复制实际携带正文中的内联滚动样式与全部提示词',async t=>{
  const html=convert(article(t,sample)).html;
  assert.match(html,/max-height:320px;overflow:auto;box-sizing:border-box/);
  const copied=await copy(html);assert.equal(copied.payload,html);assert.match(copied.status,/已复制富文本/);
  assert.match(copied.payload,/text-align:justify;text-align-last:left;/);
  assert.match(copied.payload,/<p[^>]*font-size:15px;line-height:25.5px/);
  assert.equal((copied.payload.match(/中文提示词/g)||[]).length,80);
});
test('备用复制不解除限高，也不裁掉长代码内容',async t=>{
  const html=convert(article(t,sample)).html;
  const copied=await copy(html,true);assert.equal(copied.command,'copy');assert.equal(copied.payload,html);
  assert.match(copied.payload,/text-align:justify;text-align-last:left;/);
  assert.match(copied.payload,/<p[^>]*font-size:15px;line-height:25.5px/);
  assert.doesNotMatch(preview(html,'预览',[]),/max-height:none|body\.copying/);
});
test('代码窗口可显式展开或调整限高，非法高度报错',t=>{
  const input=article(t,sample);
  assert.doesNotMatch(convert(input,{codeMaxHeight:0}).html,/max-height:/);
  assert.match(convert(input,{codeMaxHeight:400}).html,/max-height:400px;overflow:auto/);
  for(const value of [-1,NaN,Infinity])assert.throws(()=>convert(input,{codeMaxHeight:value}),/高度/);
});
test('防孤字按需开启，缓存切换正确，不处理代码、链接、标题或列表',t=>{
  const source='## 这是一个标题测试。\n\n这个案例整体中规中矩，也能正常跑完一场比赛。\n\n普通**加粗结尾保持原样。**\n\n- 列表末尾保持原样。\n\n> 引用末尾保持原样。\n\n带`API`代码的段落保持原样。\n\n[链接保持原样。](https://example.com)\n\n```prompt\n原始提示词结尾保持原样。\n```';
  const input=article(t,source);
  const initial=convert(input).html;assert.doesNotMatch(initial,/data-reading-tail/);
  const html=convert(input,{avoidOrphans:true}).html;
  assert.equal((html.match(/data-reading-tail/g)||[]).length,2);
  assert.match(html,/nowrap[^>]*>跑完一场比赛。<\/span>/);
  assert.match(html,/<strong[^>]*>[^<]*<span data-reading-tail/);
  assert.equal(convert(input).html,initial);
  assert.equal(fs.readFileSync(input,'utf8'),source);
});
test('CLI一次生成完整预览和正文，防孤字与限高选项均进入导出',t=>{
  const input=article(t,'这是完整正文的段尾测试。\n\n```prompt\n完整提示词\n```');
  const output=path.join(path.dirname(input),'out');
  const cli=fileURLToPath(new URL('../scripts/render.mjs',import.meta.url));
  const result=JSON.parse(execFileSync(process.execPath,[cli,input,'--out',output,'--avoid-orphans','--code-max-height','240'],{encoding:'utf8'}));
  const html=fs.readFileSync(result.fragment,'utf8');
  assert.match(html,/data-reading-tail/);assert.match(html,/max-height:240px;overflow:auto/);
  const page=fs.readFileSync(result.preview,'utf8');
  assert.ok(page.includes('<article id="content">'+html+'</article>'));assert.match(page,/复制完整公众号排版/);
});
