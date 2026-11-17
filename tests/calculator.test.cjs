// DOM behavior only; real browser re-review must target the new immutable artifact.
const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const sdk=require('../assets/client.js');const root=path.resolve(__dirname,'..');
const load=p=>JSON.parse(fs.readFileSync(path.join(root,'api/v2',p)));
test('calculator defaults current explicit time and renders known promotion without undefined',async()=>{
 const elements=new Map();const el=id=>{
  if(!elements.has(id))elements.set(id,{value:'',textContent:'',innerHTML:'',hidden:false,disabled:false,listeners:{},addEventListener(t,f){this.listeners[t]=f;}});
  return elements.get(id);
 };
 const client={listVendors:async()=>load('vendors.json'),listModalities:async()=>load('modalities.json'),getModel:async id=>load('models/'+id+'.json')};
 const context={URL,Date,LLMPrice:{createClient:()=>client,estimate:sdk.estimate},location:{href:'https://fixture.invalid/api.html'},LP:{esc:x=>String(x??'')},
 document:{getElementById:el,querySelector:()=>el('tabs'),querySelectorAll:()=>[],addEventListener(){}}};
 const start=Date.now();vm.runInNewContext(fs.readFileSync(path.join(root,'assets/api.js'),'utf8'),context);await new Promise(setImmediate);
 assert.ok(Date.parse(el('costAt').value)>=start);
 assert.match(el('costAt').value,/Z$/);
 for(const [id,total] of [['hy4-flash',.075],['hy4',.75],['hy4-preview',1.5]]){
  el('costModel').value=id;await el('costModel').listeners.change();
  for(const k of ['inputTokens','outputTokens','cachedInputTokens','cacheWriteTokens','cacheWrite1hTokens','cacheWrite12hTokens','storageTokenHours'])el(k).value='0';
  el('inputTokens').value='100000';el('outputTokens').value='50000';el('costService').value='standard';
  el('costAt').value='2026-11-17T20:26:37+08:00';el('costForm').listeners.submit({preventDefault(){}});
  assert.ok(!el('costStatus').textContent.includes('undefined'));
  assert.ok(el('costStatus').textContent.includes('CNY'));
  assert.ok(Math.abs(JSON.parse(el('costOut').textContent).total-total)<1e-12);
 }
});
