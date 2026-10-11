const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { createClient, estimate } = require('../assets/client.js');
const root = path.resolve(__dirname, '..');
const all = JSON.parse(fs.readFileSync(path.join(root, 'api/v1/models.json')));
const model = id => all.data.find(m => m.id === id);
const opts = { at: '2026-10-11' };
const usage = (inputTokens, outputTokens, more) => Object.assign({ inputTokens, outputTokens }, more);
function close(actual, expected) { assert.ok(Math.abs(actual - expected) < 1e-10, `${actual} != ${expected}`); }
function code(fn, expected) { assert.throws(fn, e => e.code === expected); }

test('long-context threshold includes all cached input; boundary is exclusive', () => {
  const m = model('gemini-3.1-pro-preview');
  close(estimate(m, usage(300000, 10000), opts).total, 1.38);
  assert.equal(estimate(m, usage(200000, 1), opts).pricing_tier, 'base');
  assert.notEqual(estimate(m, usage(200001, 1), opts).pricing_tier, 'base');
  close(estimate(m, usage(300000, 0, {cachedInputTokens: 290000}), opts).total, 0.156);
});
test('cache reads/writes replace ordinary input, including 1h writes', () => {
  close(estimate(model('claude-opus-5.5'), usage(1000, 100, {cachedInputTokens: 500, cacheWriteTokens: 100, cacheWrite1hTokens: 100}), opts).total, 0.0046);
  close(estimate(model('qwen3.8-max'), usage(1000, 0, {cachedInputTokens: 1000}), {...opts, cacheType: 'explicit'}).total, 0.00017);
});
test('Grok 4.7 inclusive 200k tier, cache, priority and US residency', () => {
  const m = model('grok-4.7');
  assert.equal(estimate(m, usage(199999, 1), opts).pricing_tier, 'base');
  const tier = estimate(m, usage(200000, 10000, {cachedInputTokens: 100000}), opts);
  close(tier.total, 0.62);
  assert.equal(tier.pricing_tier, 'input_tokens>199999');
  close(estimate(m, usage(200000, 10000, {cachedInputTokens: 100000}), {...opts, serviceTier:'priority',dataResidency:true}).total, 1.364);
  assert.equal(m.limits.max_output_tokens, null);
  assert.equal(m.limits.status, 'verified');
  assert.deepEqual(m.unverified_fields, []);
  code(() => estimate(m, usage(1, 1), {...opts, serviceTier:'batch'}), 'UNSUPPORTED_SERVICE_TIER');
  code(() => estimate(m, usage(500001, 0), opts), 'LIMIT_EXCEEDED');
});
test('Build Fast is a subscription reference, with its own 200k boundary', () => {
  const m = model('grok-4.7-build-fast');
  const short = estimate(m, usage(200000,10000,{cachedInputTokens:100000}), opts);
  close(short.total, 0.62);
  assert.equal(short.pricing_tier, 'base');
  const long = estimate(m, usage(200001,10000,{cachedInputTokens:100000}), opts);
  close(long.total, 0.930006);
  assert.equal(long.pricing_tier, 'input_tokens>200000');
  assert.equal(long.price_basis.type, 'reference');
  assert.equal(long.price_basis.reference_multiplier, 2);
  assert.equal(long.billing.channel, 'subscription');
  assert.ok(long.warnings.some(w => w.includes('not the subscription bill')));
  assert.equal(m.pricing_status.input, 'reference');
  assert.equal(m.limits.context_length, 256000);
  assert.equal(m.limits.status, 'partial');
  assert.equal(m.reasoning_effort.field_status.can_disable, 'unverified');
  code(() => estimate(m,usage(256001,0),opts), 'LIMIT_EXCEEDED');
  code(() => estimate(m,usage(1,1),{...opts,serviceTier:'priority'}), 'UNSUPPORTED_SERVICE_TIER');
  code(() => estimate(m,usage(1,1),{...opts,dataResidency:true}), 'UNSUPPORTED_SERVICE_TIER');
});
test('per-component service rules and fixed exceptions', () => {
  const lite = model('gemini-3.5-flash-lite');
  close(estimate(lite, usage(1000000, 0, {cachedInputTokens: 1000000}), {...opts, serviceTier:'batch'}).total, 0.02);
  close(estimate(lite, usage(1000000, 0, {cachedInputTokens: 1000000}), {...opts, serviceTier:'priority'}).total, 0.05);
  const pro = model('gemini-3.1-pro-preview');
  close(estimate(pro, usage(300000, 0, {cachedInputTokens:300000, storageTokenHours:1000000}), {...opts, serviceTier:'batch'}).total, 4.62);
  close(estimate(pro, usage(0, 0, {storageTokenHours:1000000}), {...opts, serviceTier:'priority'}).total, 8.1);
  close(estimate(model('claude-opus-5.5'), usage(1000, 100), {...opts, serviceTier:'batch', dataResidency:true}).total, 0.0033);
});
test('future storage and token changes and promotion on long tiers', () => {
  close(estimate(model('gemini-3.8-flash'), usage(1000, 1000, {storageTokenHours:1000000}), {at:'2027-01-01', serviceTier:'batch'}).total, 1.0045);
  close(estimate(model('qwen3.7-plus'), usage(300000, 1000), opts).total, 0.29184);
  code(() => estimate(model('gpt-5.6-sol'), usage(1, 1), {at:'2026-11-22'}), 'PRICE_EXPIRED');
  code(() => estimate(model('gemini-3.8-flash'), usage(1, 1), {at:'2026-10-10'}), 'HISTORICAL_PRICE_UNAVAILABLE');
  const ambiguous = structuredClone(model('gemini-3.1-pro-preview'));
  ambiguous.price_schedule = [{...structuredClone(model('gemini-3.8-flash').price_schedule[0]), input: 5}];
  code(() => estimate(ambiguous,usage(300000,1),{at:'2027-01-01'}),'PRICE_UNAVAILABLE');
  const storage = structuredClone(model('qwen3.7-plus'));
  storage.price_schedule[0].cache_pricing.storage_per_1M_tokens_hour = 1;
  close(estimate(storage,usage(300000,1000,{storageTokenHours:1000000}),opts).total,1.29184);
});
test('DeepSeek boundaries, timezones, weekends and holidays', () => {
  const m = model('deepseek-v4-pro');
  const u = usage(1000000,0);
  close(estimate(m,u,{at:'2026-10-12T09:00:00+08:00',isChineseHoliday:false}).total,1.32);
  close(estimate(m,u,{at:'2026-10-12T12:00:00+08:00'}).total,0.66);
  close(estimate(m,u,{at:'2026-10-12T01:00:00Z',isChineseHoliday:true}).total,0.66);
  close(estimate(m,u,{at:'2026-10-11T01:00:00Z'}).total,0.66);
  code(() => estimate(m,u,{at:'2026-10-12T01:00:00Z'}), 'HOLIDAY_REQUIRED');
  code(() => estimate(m,u,opts), 'TIME_REQUIRED');
});
test('reference estimates retain provenance and distinguish subscription billing', () => {
  const r = estimate(model('kimi-for-coding'),usage(1000,100),opts);
  assert.equal(r.price_basis.type,'reference');
  assert.equal(r.price_basis.reference_model_id,'kimi-k2.7-code');
  assert.equal(r.billing.channel,'subscription');
  assert.ok(r.warnings.some(w => w.includes('subscription bill')));
});
test('missing prices and invalid inputs never become free or silently coerce', () => {
  const m = model('qwen3.8-omni-flash');
  code(() => estimate(m,usage(100,0,{cacheWriteTokens:100}),opts),'PRICE_UNAVAILABLE');
  for (const bad of [-1,1.5,NaN,Infinity,'1',true]) code(() => estimate(m,usage(bad,0),opts),'INVALID_ARGUMENT');
  code(() => estimate(m,usage(1,0,{cachedInputTokens:2}),opts),'INVALID_ARGUMENT');
  code(() => estimate(m,{inputTokens:1},opts),'INVALID_ARGUMENT');
  code(() => estimate(m,usage(1,0),{at:'2026-02-31'}),'INVALID_ARGUMENT');
  code(() => estimate(m,usage(1,0),{...opts,serviceTier:'batch'}),'UNSUPPORTED_SERVICE_TIER');
  code(() => estimate(m,usage(1,9999999),opts),'LIMIT_EXCEEDED');
  code(() => estimate(m,usage(1,0),{...opts,unexpected:true}),'INVALID_ARGUMENT');
  code(() => estimate(m,usage(1,0),{at:0}),'INVALID_ARGUMENT');
  code(() => estimate(m,usage(1,0),{...opts,serviceTier:0}),'INVALID_ARGUMENT');
  const huge = structuredClone(model('gemini-3.1-pro-preview'));
  huge.cache_pricing.storage_per_1M_tokens_hour = Number.MAX_VALUE;
  code(() => estimate(huge,usage(0,0,{storageTokenHours:Number.MAX_VALUE}),opts),'INVALID_ARGUMENT');
});
test('all model snapshots estimate standard text usage', () => {
  for (const m of all.data) {
    const r = estimate(m,usage(1000,100),{at:'2026-10-11T12:00:00Z'});
    assert.ok(Number.isFinite(r.total) && r.total > 0,m.id);
  }
});

test('real HTTP queries cover every static endpoint, IDs, filters and errors', async t => {
  const requests=[];
  const server=http.createServer((req,res) => {
    requests.push(req.url);
    if(req.url==='/api/v1/slow/models.json') { setTimeout(()=>res.end('{}'),100);return; }
    if(req.url==='/api/v1/html/models.json') { res.setHeader('content-type','text/html');res.end('<html>error</html>');return; }
    const target=path.resolve(root,'.'+new URL(req.url,'http://localhost').pathname);
    if(!target.startsWith(root+path.sep) || !fs.existsSync(target)) {res.statusCode=404;res.end('<html>404</html>');return;}
    res.setHeader('content-type','application/json');res.end(fs.readFileSync(target));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(()=>new Promise(resolve=>server.close(resolve)));
  const base=`http://127.0.0.1:${server.address().port}/api/v1/`;
  const client=createClient(base);
  const index=await client.getIndex(), vendors=await client.listVendors(), full=await client.listModels();
  assert.equal(full.data.length,all.data.length);
  assert.equal(index.data.models.length,full.data.length);
  assert.equal(vendors.data.length,new Set(all.data.map(m=>m.vendor)).size);
  for(const v of vendors.data) {
    const envelope=await client.getVendor(v.slug);
    assert.deepEqual(envelope.data,full.data.filter(m=>m.vendor===v.slug));
    assert.equal(envelope.meta.count,v.model_count);
    assert.equal(envelope.meta.data_version,full.meta.data_version);
  }
  for(const m of full.data) {
    const envelope=await client.getModel(m.id);
    assert.deepEqual(envelope.data,m);
    assert.equal(envelope.meta.data_version,full.meta.data_version);
    const linked=await (await fetch(new URL(m.links.self,base))).json();assert.deepEqual(linked,envelope);
  }
  const spec=await client.getOpenAPI();assert.equal(Object.keys(spec.paths).length,5);
  const staticPaths=new Set(requests);
  const expected=['index.json','models.json','vendors.json','openapi.json',...full.data.map(m=>`models/${m.id}.json`),...vendors.data.map(v=>`vendors/${v.slug}.json`)];
  assert.equal(expected.length,4+all.data.length+vendors.data.length);
  assert.deepEqual([...staticPaths].sort(),expected.map(p=>'/api/v1/'+p).sort());
  assert.deepEqual(index.data.models.map(m=>m.id),full.data.map(m=>m.id));
  for (const v of vendors.data) assert.deepEqual(v.model_ids,full.data.filter(m=>m.vendor===v.slug).map(m=>m.id));
  const cheapest=await client.listModels({vendor:'openai',sort:'input',limit:2,priceBasis:'official'});
  assert.equal(cheapest.data[0].id,'gpt-6-luna');assert.equal(cheapest.meta.matched_count,7);
  const search=await client.listModels({q:'gemini pro'});assert.equal(search.data[0].id,'gemini-3.1-pro-preview');
  const missingLast=await client.listModels({sort:'-cache_write'});assert.equal(missingLast.data.at(-1).pricing.cache_write,null);
  close((await client.estimate('gemini-3.1-pro-preview',usage(300000,10000),opts)).total,1.38);
  await assert.rejects(client.getModel('unknown-model'),e=>e.code==='NOT_FOUND');
  assert.throws(()=>client.getModel('../prices'),e=>e.code==='INVALID_ARGUMENT');
  await assert.rejects(client.listModels({sort:'bogus'}),e=>e.code==='INVALID_ARGUMENT');
  await assert.rejects(createClient(base+'html/').listModels(),e=>e.code==='INVALID_RESPONSE');
  await assert.rejects(createClient(base+'slow/',{timeoutMs:10}).listModels(),e=>e.code==='TIMEOUT');
  assert.ok(requests.every(url=>!url.includes('?')),'filters are client-side, no fake server query parameters');
});
