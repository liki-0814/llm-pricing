// Real app/common rendering in a lightweight DOM harness. NOT browser/Lighthouse.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.join(__dirname,'..');
const source=name=>fs.readFileSync(path.join(root,name),'utf8');
const page=JSON.parse(source('data/page-models.json'));
async function render(query){
 const elements=new Map();
 const el=id=>{
  if(!elements.has(id))elements.set(id,{value:'',innerHTML:'',options:[],listeners:{},hidden:false,
   classList:{toggle(){}},setAttribute(){},addEventListener(t,f){this.listeners[t]=f;}});
  return elements.get(id);
 };
 const attrs={'data-theme':'light'};
 const context={URLSearchParams,URL,console,setTimeout(){},addEventListener(){},
  location:{search:query,pathname:'/',hash:''},history:{replaceState(){}},
  document:{getElementById:el,querySelectorAll:()=>[],addEventListener(){},
   querySelector:s=>s==='.theme-toggle'?el('themeToggle'):{clientWidth:1000,classList:{toggle(){}}},
   documentElement:{style:{setProperty(){}},getAttribute:n=>attrs[n],setAttribute:(n,v)=>{attrs[n]=v;}}},
  LLMAvailability:require('../assets/availability.js'),fetch:async()=>({ok:true,json:async()=>page})};
 context.window=context;
 vm.runInNewContext(source('assets/common.js'),context);
 vm.runInNewContext(source('assets/app.js'),context);
 await new Promise(setImmediate);
 assert.equal(el('error').innerHTML,'');
 let html=source('index.html');
 for(const id of ['tbody','mediaBody','sources']){
  const tag=id==='sources'?'ul':'tbody';
  const re=new RegExp('(<'+tag+' id="'+id+'">)[\\s\\S]*?(</'+tag+'>)');
  html=html.replace(re,(_all,open,close)=>open+el(id).innerHTML+close);
 }
 return {html,el,context};
}
for(const [label,query] of [
 ['text','?q=glm-5.3-flashx-legal&open=glm-5.3-flashx-legal'],
 ['image','?modality=image&open=gpt-image-2.6-flare'],
 ['video','?modality=video&open=minimax-h3-regeneration']
])test('rendered '+label+' details inherit the price-section heading level (DOM harness)',async()=>{
 const {html,el}=await render(query);
 const details=el(label==='text'?'tbody':'mediaBody').innerHTML;
 assert.match(details,/<section class="dblock/);
 assert.match(details,/<h3>[^<]+<\/h3>/);
 assert.doesNotMatch(details,/<h[12456]>/);
 const levels=[...html.matchAll(/<h([1-6])(?:\s|>)/g)].map(m=>Number(m[1]));
 assert.equal(levels[0],1);assert.ok(levels.includes(3));
 for(let i=1;i<levels.length;i++)assert.ok(levels[i]<=levels[i-1]+1,levels.join(','));
 assert.match(html,/<h2 class="sr-only" id="pricesHeading">价格表<\/h2>/);
 assert.match(el('sources').innerHTML,/<li class="v-qwen"><span class="badge">/);
});
test('empty results retain a valid h1/h2 page outline and actionable reset (DOM harness)',async()=>{
 const {html,el}=await render('?q=nonexistent-ui-accessibility-fixture');
 assert.equal(el('empty').hidden,false);
 assert.doesNotMatch(el('tbody').innerHTML,/<h[1-6]>/);
 const levels=[...html.matchAll(/<h([1-6])(?:\s|>)/g)].map(m=>Number(m[1]));
 assert.deepEqual(levels,[1,2,2,2]);assert.match(html,/id="emptyReset"/);
});
