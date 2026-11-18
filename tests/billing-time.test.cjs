const test = require('node:test');
const assert = require('node:assert/strict');
const {estimate, estimateMedia} = require('../assets/client.js');
const all = require('../api/v2/models.json').data;
const get = id => structuredClone(all.find(m => m.id === id));
const observed = '2026-11-18T08:27:00+08:00';
const before = '2026-11-18T08:26:59.999+08:00';
const after = '2026-11-18T08:27:00.001+08:00';
const near = (a,b) => assert.ok(Math.abs(a-b)<1e-12, `${a} != ${b}`);
const code = (fn,c) => assert.throws(fn,e=>e.code===c);

test('new cache/long-tier evidence has an exact observation boundary, without disabling old short prices', () => {
  const q=get('qwen4-max'), law=get('gpt-6-astra-law');
  for(const at of ['2026-11-17T12:00:00+08:00','2026-11-17T21:00:00+08:00','2026-11-18T01:00:00+08:00','2026-11-17T17:00:00Z',before,'2026-11-18T00:26:59.999Z']) {
    near(estimate(q,{inputTokens:1000,outputTokens:100},{at}).total,.00195);
    near(estimate(law,{inputTokens:1000,outputTokens:100},{at}).total,.015);
    for(const key of ['cachedInputTokens','cacheWriteTokens','cacheWrite1hTokens'])
      code(()=>estimate(q,{inputTokens:1000,outputTokens:0,[key]:1000},{at}),'HISTORICAL_PRICE_UNAVAILABLE');
    code(()=>estimate(law,{inputTokens:300000,outputTokens:1000},{at}),'HISTORICAL_PRICE_UNAVAILABLE');
  }
  for(const at of [observed,after,'2026-11-18T00:27:00Z']) {
    for(const [key,price] of [['cachedInputTokens',.000075],['cacheWriteTokens',.001875],['cacheWrite1hTokens',.003]])
      near(estimate(q,{inputTokens:1000,outputTokens:0,[key]:1000},{at}).total,price);
    near(estimate(law,{inputTokens:300000,outputTokens:1000},{at}).total,6.075);
    code(()=>estimate(law,{inputTokens:1000,outputTokens:0,cacheWriteTokens:1000},{at}),'PRICE_UNAVAILABLE');
  }
  // Date-only input must not accidentally choose a side of the observation instant.
  code(()=>estimate(q,{inputTokens:1000,outputTokens:0,cachedInputTokens:1000},{at:'2026-11-18'}),'TIME_REQUIRED');
});

test('Ultrafast changes at midnight Pacific (PST in March 1, not UTC midnight)', () => {
  for(const id of ['gpt-6.2-astra','gpt-6.2-sol']) {
    const m=get(id), base=id.endsWith('astra')?.012:.003;
    const u={inputTokens:1000,outputTokens:100};
    for(const at of ['2027-03-01T07:59:59.999Z','2027-03-01T00:00:00Z'])
      near(estimate(m,u,{at,serviceTier:'ultrafast'}).total,base*3);
    for(const at of ['2027-03-01T08:00:00Z','2027-03-01T08:00:00.001Z','2027-03-02T12:00:00-08:00','2027-07-01T12:00:00-07:00'])
      near(estimate(m,u,{at,serviceTier:'ultrafast'}).total,base*6);
    near(estimate(m,u,{at:'2027-03-02T12:00:00-08:00'}).total,base);
    near(estimate(m,u,{at:'2027-03-02T12:00:00-08:00',serviceTier:'batch'}).total,base*.5);
    code(()=>estimate(m,u,{at:'2027-03-01',serviceTier:'ultrafast'}),'TIME_REQUIRED');
  }
});

test('Regeneration counts raw input images per single task; first five are included', () => {
  const m=get('minimax-h3-regeneration');
  for(const inputImages of [0,1,4,5,6]) {
    const r=estimateMedia(m,{seconds:5,inputVideoSeconds:5,resolution:'2k',inputImages},{at:observed});
    near(r.total,.5+Math.max(0,inputImages-5)*.025);
    assert.equal(r.billing_quantities.input_images.billable,Math.max(0,inputImages-5));
    assert.equal(r.billing_quantities.input_images.included,Math.min(inputImages,5));
    if(inputImages>5) near(r.unit_prices.input_images.rate,.025);
  }
  near(estimateMedia(m,{seconds:1,inputVideoSeconds:1,resolution:'2k',inputImages:5},{at:observed}).total,.1);
  // Two independent calls each receive the per-task allowance; not an account balance.
  for(let i=0;i<2;i++) near(estimateMedia(m,{seconds:1,inputVideoSeconds:1,resolution:'2k',inputImages:6},{at:observed}).total,.125);
});

const newIds = ['gpt-6.2-astra','gpt-6.2-sol','gpt-6.2-astra-law','claude-fable-5-2','claude-mythos-5-2','gemini-4-carbon','gemini-4-hydrogen','glm-5.3-flashx-legal','gpt-image-2.6-sunburst','gpt-image-2.6-flare','minimax-h3-image','minimax-h3-image-highspeed','minimax-h3-context-ir','minimax-h3-regeneration'];
test('every newly added model is guarded before its precise observation, not just its calendar date', () => {
  for(const id of newIds) {
    const m=get(id), fn=m.modality==='text'?estimate:estimateMedia;
    const usage=m.modality==='text'?{inputTokens:0,outputTokens:0}:{};
    assert.equal(m.price_observations[0].observed_at,observed,id);
    assert.equal(m.price_observations[0].valid_from,null,id);
    for(const at of [before,'2026-11-18T00:26:59.999Z'])
      code(()=>fn(m,usage,{at}),'HISTORICAL_PRICE_UNAVAILABLE');
    for(const at of [observed,after]) near(fn(m,usage,{at}).total,0);
  }
});

test('explicit evidence intervals are half-open; only proven valid_from can authorize earlier history', () => {
  const m=get('qwen4-max');
  m.price_observations[0].valid_from='2026-11-17T20:00:00+08:00';
  m.price_observations[0].valid_until='2026-11-19T00:00:00+08:00';
  const u={inputTokens:1000,outputTokens:0,cachedInputTokens:1000};
  code(()=>estimate(m,u,{at:'2026-11-17T19:59:59.999+08:00'}),'HISTORICAL_PRICE_UNAVAILABLE');
  near(estimate(m,u,{at:'2026-11-17T20:00:00+08:00'}).total,.000075);
  code(()=>estimate(m,u,{at:'2026-11-19T00:00:00+08:00'}),'PRICE_EXPIRED');
});

test('Fast deprecation is an observed tier state, not a retroactive model retirement', () => {
  const m=get('claude-opus-4.8'), u={inputTokens:1000,outputTokens:100};
  const previous=estimate(m,u,{at:before,serviceTier:'fast'});
  assert.ok(!previous.warnings.some(s=>s.includes('deprecated')));
  for(const at of [observed,after]) {
    const current=estimate(m,u,{at,serviceTier:'fast'});
    near(current.total,.015);
    assert.ok(current.warnings.some(s=>s.includes('deprecated')));
    assert.ok(!estimate(m,u,{at}).warnings.some(s=>s.includes('deprecated')));
  }
});

test('scheduled multiplier scales long context, every used cache component, and residency exactly once', () => {
  for(const id of ['gpt-6.2-astra','gpt-6.2-sol']) {
    const m=get(id), u={inputTokens:300000,outputTokens:1000,cachedInputTokens:50000,cacheWriteTokens:50000,cacheWrite12hTokens:50000};
    for(const [at,multiple] of [['2027-03-01T07:59:59.999Z',3],['2027-03-01T08:00:00Z',6],['2027-07-01T19:00:00Z',6]]) {
      const base=estimate(m,u,{at});
      near(estimate(m,u,{at,serviceTier:'ultrafast'}).total,base.total*multiple);
      near(estimate(m,u,{at,serviceTier:'ultrafast',dataResidency:true}).total,base.total*multiple*1.1);
      code(()=>estimate(m,{inputTokens:1,outputTokens:0,cacheWrite1hTokens:1},{at,serviceTier:'ultrafast'}),'PRICE_UNAVAILABLE');
    }
  }
});

test('v1/v2/page carry the same evidence, state, schedule and per-task allowance', () => {
  const v1=require('../api/v1/models.json').data;
  const page=require('../data/page-models.json').models;
  for(const m of all) {
    const counterparts=[...v1.filter(x=>x.id===m.id),...page.filter(x=>x.model_id===m.id)];
    for(const other of counterparts) {
      assert.deepEqual(other.price_observations||[],m.price_observations||[],m.id);
      assert.deepEqual(other.service_tiers||[],m.service_tiers||[],m.id);
      assert.deepEqual(other.media_pricing?.input_image_allowance,m.media_pricing?.input_image_allowance,m.id);
    }
  }
});

test('isolated copied one-file SDK enforces the new contracts without a helper or network', () => {
  const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'billing-sdk-'));
  try {
    const file=path.join(dir,'standalone.cjs');
    fs.copyFileSync(require.resolve('../assets/client.js'),file);
    const sdk=require(file);
    const sandbox={module:{exports:{}},fetch:()=>{throw Error('must not fetch');}};
    vm.runInNewContext(fs.readFileSync(file,'utf8'),sandbox);
    for(const isolated of [sdk,sandbox.module.exports]) {
      code(()=>isolated.estimate(get('qwen4-max'),{inputTokens:1000,outputTokens:0,cachedInputTokens:1000},{at:before}),'HISTORICAL_PRICE_UNAVAILABLE');
      near(isolated.estimate(get('qwen4-max'),{inputTokens:1000,outputTokens:0,cachedInputTokens:1000},{at:observed}).total,.000075);
      near(isolated.estimate(get('gpt-6.2-astra'),{inputTokens:1000,outputTokens:100},{at:'2027-03-01T08:00:00Z',serviceTier:'ultrafast'}).total,.072);
      for(const n of [0,5,6]) near(isolated.estimateMedia(get('minimax-h3-regeneration'),{seconds:5,inputVideoSeconds:5,resolution:'2k',inputImages:n},{at:observed}).total,.5+Math.max(0,n-5)*.025);
    }
  } finally { fs.rmSync(dir,{recursive:true,force:true}); }
});
