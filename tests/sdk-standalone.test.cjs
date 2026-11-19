const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const script = fs.readFileSync(path.join(root, 'assets/client.js'), 'utf8');
const envelope = JSON.parse(fs.readFileSync(path.join(root, 'api/v1/models.json')));
const model = () => structuredClone(envelope.data.find(m => m.id === 'qwen4-max'));
const usage = {inputTokens:1000, outputTokens:100};
const opts = {at:'2026-11-17T12:26:37Z'};
function browser() {
  const calls=[];
  const context = vm.createContext({URL, AbortController, setTimeout, clearTimeout,
    fetch: async url => {calls.push(url);return {ok:true,json:async()=>structuredClone(envelope)};}});
  vm.runInContext(script, context, {filename:'client.js'});
  assert.equal(context.LLMAvailability, undefined, 'no prerequisite or leaked engine global');
  assert.deepEqual(calls, [], 'loading standalone SDK must not perform network requests');
  return {sdk:context.LLMPrice,calls};
}
test('legacy browser single script: USD quote and v1 list without a helper', async()=>{
  const {sdk,calls}=browser();
  assert.ok(Math.abs(sdk.estimate(model(),usage,opts).total-0.00195)<1e-15);
  assert.equal(sdk.estimate(model(),usage,opts).currency,'USD');
  const legacySol=structuredClone(envelope.data.find(m=>m.id==='gpt-5.6-sol'));
  assert.ok(Math.abs(sdk.estimate(legacySol,usage,opts).total-.006)<1e-15,'unchanged legacy Sol USD quote');
  assert.equal(calls.length,0,'direct estimation is offline');
  const list=await sdk.createClient('https://fixture.invalid/api/v1/').listModels();
  assert.ok(list.data.length>0 && list.data.every(m=>m.currency==='USD'));
  assert.deepEqual(calls,['https://fixture.invalid/api/v1/models.json']);
});
test('standalone browser enforces every non-estimable shared lifecycle fixture',()=>{
  const {sdk}=browser();
  const cases=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/lifecycle-cases.json')));
  for(const c of cases.filter(c=>!c.estimable)) {
    const m=model();m.lifecycle=c.lifecycle;
    const expected=c.status==='history_unknown'?'HISTORICAL_PRICE_UNAVAILABLE':'MODEL_RETIRED';
    assert.throws(()=>sdk.estimate(m,usage,{at:c.at}),e=>e.code===expected,c.name);
  }
});
test('copied single-file CommonJS SDK needs no sibling and refuses expired quote',()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'standalone-sdk-'));
  try {
    fs.writeFileSync(path.join(dir,'client.js'),script);
    const m=model();
    const result=JSON.parse(execFileSync(process.execPath,['-e',`
      const sdk=require(${JSON.stringify(path.join(dir,'client.js'))});
      const m=${JSON.stringify(m)};
      const q=sdk.estimate(m,${JSON.stringify(usage)},${JSON.stringify(opts)});
      m.lifecycle={status:'retired',retired_at:null,precision:'unknown',scope:'entity',routes_to:'replacement',observed_at:'2026-11-17T12:00:00Z'};
      let code;try{sdk.estimate(m,${JSON.stringify(usage)},${JSON.stringify(opts)})}catch(e){code=e.code}
      console.log(JSON.stringify({total:q.total,currency:q.currency,code}));
    `],{encoding:'utf8'}));
    assert.ok(Math.abs(result.total-0.00195)<1e-15);
    assert.equal(result.currency,'USD');assert.equal(result.code,'MODEL_RETIRED');
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
