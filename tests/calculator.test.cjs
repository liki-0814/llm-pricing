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
 const fetched=[];
 const fetch=async url=>{const u=new URL(url);assert.equal(u.origin,'https://fixture.invalid');assert.ok(u.pathname.startsWith('/api/v2/price-models'));
   fetched.push(u.pathname);if(u.pathname.endsWith('/missing.json'))return {ok:false,status:404,headers:{get:()=> 'application/json'},text:async()=>JSON.stringify({error:'model not found'})};const data=load(u.pathname.slice('/api/v2/'.length));return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>data,text:async()=>JSON.stringify(data)};};
 const context={URL,Date,fetch,Blob,performance,LLMPrice:{createClient:()=>client,estimate:sdk.estimate},location:{href:'https://fixture.invalid/api.html'},LP:{esc:x=>String(x??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')},
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
 // New source-price querying is separate from, and cannot rewrite, the old calculator.
 el('tryPreset').value='price-model';el('tryPreset').listeners.change();
 const expected=load('price-models.json').data.models.map(m=>m.model_id);
 const actual=Array.from(el('tryParam').innerHTML.matchAll(/<option value="([^"]+)">([^<]*)<\/option>/g),m=>[m[1],m[2]]);
 assert.ok(expected.length>0);assert.deepEqual(actual,expected.map(id=>[id,id]));
 assert.equal(new Set(actual.map(x=>x[0])).size,expected.length);assert.equal(el('tryParam').hidden,false);
 for(const [mid] of actual) {
   el('tryParam').value=mid;el('tryParam').listeners.change();
   assert.equal(new URL(el('tryUrl').value).pathname,'/api/v2/price-models/'+mid+'.json');
   el('trySend').listeners.click();await new Promise(setImmediate);
   assert.ok(el('tryStatus').innerHTML.includes('HTTP 200'));
   assert.ok(el('tryOut').innerHTML.includes(mid));assert.ok(el('tryOut').innerHTML.includes('selector_complete'));
 }
 assert.ok(fetched.includes('/api/v2/price-models.json'));
 assert.deepEqual(fetched.filter(p=>p.startsWith('/api/v2/price-models/')),expected.map(id=>'/api/v2/price-models/'+encodeURIComponent(id)+'.json'));
 // A missing per-ID resource is an HTTP result, not a successful price.
 el('tryUrl').value='https://fixture.invalid/api/v2/price-models/missing.json';
 el('trySend').listeners.click();assert.equal(el('trySend').disabled,true);await new Promise(setImmediate);
 assert.match(el('tryStatus').innerHTML,/class="err">HTTP 404/);assert.match(el('tryOut').innerHTML,/model not found/);assert.equal(el('trySend').disabled,false);

});

// Failure-state component fixtures: real API script, controlled transport, no browser claim.
for(const mode of ['missing-index','malformed-index','network-index'])test('price index '+mode+' has no invented options and reports failure',async()=>{
 const elements=new Map(),el=id=>{if(!elements.has(id))elements.set(id,{value:id==='tryPreset'?'price-model':'',textContent:'',innerHTML:'',hidden:false,disabled:false,listeners:{},addEventListener(t,f){this.listeners[t]=f;}});return elements.get(id);};
 const client={listVendors:async()=>load('vendors.json'),listModalities:async()=>load('modalities.json'),getModel:async id=>load('models/'+id+'.json')};
 const fetch=async url=>{assert.equal(new URL(url).pathname,'/api/v2/price-models.json');if(mode==='network-index')throw new Error('offline fixture');return {ok:mode!=='missing-index',status:404,json:async()=>{throw new Error('invalid JSON fixture');}};};
 const context={URL,Date,fetch,Blob,performance,LLMPrice:{createClient:()=>client,estimate:sdk.estimate},location:{href:'https://fixture.invalid/api.html'},LP:{esc:x=>String(x??'')},document:{getElementById:el,querySelector:()=>el('tabs'),querySelectorAll:()=>[],addEventListener(){}}};
 vm.runInNewContext(fs.readFileSync(path.join(root,'assets/api.js'),'utf8'),context);await new Promise(setImmediate);
 assert.equal(el('tryParam').innerHTML,'');assert.match(el('tryStatus').textContent,/原文价格索引加载失败/);assert.match(el('tryStatus').textContent,mode==='missing-index'?/HTTP 404/:mode==='network-index'?/offline fixture/:/invalid JSON fixture/);
});
