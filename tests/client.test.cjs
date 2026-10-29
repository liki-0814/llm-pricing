const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { createClient, estimate, estimateMedia } = require('../assets/client.js');
const root = path.resolve(__dirname, '..');
const all = JSON.parse(fs.readFileSync(path.join(root, 'api/v1/models.json')));
// Arithmetic and calendar cases use frozen fixtures, not the changing published catalog.
const fixtures = require('./fixtures/estimator-models.json');
const model = id => structuredClone(fixtures[id]);
const mediaFixtures = require('./fixtures/media-models.json');
const media = id => structuredClone(mediaFixtures[id]);
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
  const opus = model('claude-opus-5.5');
  close(estimate(opus, usage(1000, 100, {cachedInputTokens: 500, cacheWriteTokens: 100, cacheWrite1hTokens: 100}), {at: opus.last_updated}).total, 0.0046);
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
  const opus = model('claude-opus-5.5');
  close(estimate(opus, usage(1000, 100), {at: opus.last_updated, serviceTier:'batch', dataResidency:true}).total, 0.0033);
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
test('published snapshots estimate on their verification date and reject earlier dates', () => {
  for (const m of all.data.filter(m => m.modality === 'text')) {
    // Noon UTC is outside the recorded peak windows. An explicit holiday flag
    // also keeps this smoke test independent of which weekday a snapshot uses.
    const at = m.last_updated + 'T12:00:00Z';
    const r = estimate(m,usage(1000,100),{at, isChineseHoliday:false});
    assert.ok(Number.isFinite(r.total) && r.total > 0,m.id);
    assert.equal(r.model_id,m.id);
    const before = new Date(m.last_updated + 'T00:00:00Z');
    before.setUTCDate(before.getUTCDate() - 1);
    assert.throws(() => estimate(m,usage(1000,100),{at:before.toISOString(), isChineseHoliday:false}),
      e => e.code === 'HISTORICAL_PRICE_UNAVAILABLE',m.id);
  }
});

test('historical date guard uses the UTC day at the snapshot boundary', () => {
  const m = model('claude-opus-5.5');
  code(() => estimate(m,usage(1000,100),{at:'2026-10-19T23:59:59.999Z'}),'HISTORICAL_PRICE_UNAVAILABLE');
  code(() => estimate(m,usage(1000,100),{at:'2026-10-20T00:00:00+01:00'}),'HISTORICAL_PRICE_UNAVAILABLE');
  close(estimate(m,usage(1000,100),{at:'2026-10-20T00:00:00Z'}).total,0.006);
  close(estimate(m,usage(1000,100),{at:'2026-10-19T23:00:00-01:00'}).total,0.006);
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
  const modalities=await client.listModalities();
  for(const x of modalities.data) {
    const env=await client.getModality(x.name);
    assert.deepEqual(env.data,full.data.filter(m=>m.modality===x.name));
    assert.equal(env.meta.count,x.model_count);assert.equal(env.meta.data_version,full.meta.data_version);
  }
  const spec=await client.getOpenAPI();assert.equal(Object.keys(spec.paths).length,7);
  const staticPaths=new Set(requests);
  const expected=['index.json','models.json','vendors.json','modalities.json','openapi.json',...modalities.data.map(x=>`modalities/${x.name}.json`),...full.data.map(m=>`models/${m.id}.json`),...vendors.data.map(v=>`vendors/${v.slug}.json`)];
  assert.equal(expected.length,5+modalities.data.length+all.data.length+vendors.data.length);
  assert.deepEqual([...staticPaths].sort(),expected.map(p=>'/api/v1/'+p).sort());
  assert.deepEqual(index.data.models.map(m=>m.id),full.data.map(m=>m.id));
  for (const v of vendors.data) assert.deepEqual(v.model_ids,full.data.filter(m=>m.vendor===v.slug).map(m=>m.id));
  const cheapest=await client.listModels({vendor:'openai',sort:'input',limit:2,priceBasis:'official'});
  assert.equal(cheapest.data[0].id,'gpt-6-luna');assert.equal(cheapest.meta.matched_count,10); // 8 text + 2 image models
  assert.equal((await client.listModels({vendor:'openai',modality:'text',sort:'input',priceBasis:'official'})).meta.matched_count,8);
  const search=await client.listModels({q:'gemini pro'});assert.equal(search.data[0].id,'gemini-3.1-pro-preview');
  const missingLast=await client.listModels({sort:'-cache_write'});assert.equal(missingLast.data.at(-1).pricing.cache_write,null);
  const current = full.data.find(m=>m.id==='gemini-3.1-pro-preview');
  const currentOptions = {at:current.last_updated + 'T12:00:00Z',isChineseHoliday:false};
  assert.deepEqual(await client.estimate(current.id,usage(1000,100),currentOptions),
    estimate(current,usage(1000,100),currentOptions));
  await assert.rejects(client.getModel('unknown-model'),e=>e.code==='NOT_FOUND');
  assert.throws(()=>client.getModel('../prices'),e=>e.code==='INVALID_ARGUMENT');
  await assert.rejects(client.listModels({sort:'bogus'}),e=>e.code==='INVALID_ARGUMENT');
  await assert.rejects(createClient(base+'html/').listModels(),e=>e.code==='INVALID_RESPONSE');
  await assert.rejects(createClient(base+'slow/',{timeoutMs:10}).listModels(),e=>e.code==='TIMEOUT');
  assert.ok(requests.every(url=>!url.includes('?')),'filters are client-side, no fake server query parameters');
});

test('OpenAI 12h TTL cache writes are a separate 2.5x field, tier-aware and service-tier scaled', () => {
  const ids = ['gpt-5.6-sol','gpt-5.6-terra','gpt-5.6-luna','gpt-6-astra','gpt-6-sol','gpt-6-luna','gpt-6.1-sol','gpt-6.1-terra'];
  for (const m of all.data) {
    if (!ids.includes(m.id)) { assert.equal(m.cache_pricing.explicit_write_12h, null, m.id); continue; }
    const c = m.cache_pricing, t = m.pricing_tiers[0];
    close(c.explicit_write_12h, 2.5 * m.pricing.input);
    close(m.pricing.cache_write, 1.25 * m.pricing.input);
    assert.equal(c.explicit_write_1h, null, m.id + ' must not reuse the 1h field');
    close(t.cache_pricing.explicit_write_12h, 2.5 * t.input);
    const at = {at: m.last_updated + 'T12:00:00Z'};
    const short = estimate(m, usage(1000, 0, {cacheWrite12hTokens: 1000}), at);
    close(short.breakdown.cache_write_12h, c.explicit_write_12h / 1000);
    close(short.total, c.explicit_write_12h / 1000);
    const long = estimate(m, usage(300000, 0, {cacheWrite12hTokens: 100000, cacheWriteTokens: 100000}), at);
    close(long.total, 0.1 * (t.input + t.cache_pricing.explicit_write_12h + t.cache_write));
    close(estimate(m, usage(1000, 0, {cacheWrite12hTokens: 1000}), {...at, serviceTier: 'batch'}).total, c.explicit_write_12h / 2000);
    code(() => estimate(m, usage(10, 0, {cacheWrite12hTokens: 6, cacheWriteTokens: 5}), at), 'INVALID_ARGUMENT');
  }
  code(() => estimate(model('claude-opus-5.5'), usage(1000, 0, {cacheWrite12hTokens: 1}), {at: '2026-10-20'}), 'PRICE_UNAVAILABLE');
});

test('every model has a modality; modality files partition the catalog', async () => {
  const names = ['text', 'image', 'video'];
  assert.ok(all.data.every(m => names.includes(m.modality)));
  assert.deepEqual(all.meta.modality_counts, Object.fromEntries(names.map(n => [n, all.data.filter(m => m.modality === n).length])));
  assert.equal(all.meta.count, all.data.length);
  const seen = new Set();
  for (const n of names) {
    const f = JSON.parse(fs.readFileSync(path.join(root, `api/v1/modalities/${n}.json`)));
    assert.equal(f.modality.name, n);
    assert.equal(f.modality.model_count, f.data.length);
    assert.deepEqual(f.modality.model_ids, f.data.map(m => m.id));
    assert.ok(f.data.every(m => m.modality === n));
    assert.deepEqual(f.data, all.data.filter(m => m.modality === n));
    f.data.forEach(m => { assert.ok(!seen.has(m.id), m.id); seen.add(m.id); });
  }
  assert.equal(seen.size, all.data.length);
  // text models keep the legacy shape; media models are neutral in text fields
  for (const m of all.data) {
    if (m.modality === 'text') { assert.equal(m.media_pricing, null, m.id); assert.equal(m.unit, 'per_1M_tokens'); continue; }
    assert.ok(m.media_pricing && m.media_pricing.output_kind === m.modality, m.id);
    assert.equal(m.unit, 'see_media_pricing');
    assert.ok(Object.values(m.pricing).every(v => v === null), m.id);
    assert.ok(Object.values(m.pricing_status).every(v => v === 'not_applicable'), m.id);
  }
});

test('client filters by modality and sorts media models by price', async t => {
  const server = http.createServer((req, res) => {
    const target = path.resolve(root, '.' + new URL(req.url, 'http://localhost').pathname);
    if (!target.startsWith(root + path.sep) || !fs.existsSync(target)) { res.statusCode = 404; res.end('<html>404</html>'); return; }
    res.setHeader('content-type', 'application/json'); res.end(fs.readFileSync(target));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const client = createClient(`http://127.0.0.1:${server.address().port}/api/v1/`);
  const mods = await client.listModalities();
  assert.deepEqual(mods.data.map(m => m.name), ['text', 'image', 'video']);
  for (const m of mods.data) {
    assert.equal((await client.listModels({ modality: m.name })).data.length, m.model_count);
    assert.deepEqual((await client.getModality(m.name)).data.map(x => x.id), m.model_ids);
  }
  const videos = await client.listModels({ modality: 'video', sort: 'media_price' });
  assert.ok(videos.data.length > 0 && videos.data.every(m => m.modality === 'video'));
  await assert.rejects(client.listModels({ modality: 'audio' }), e => e.code === 'INVALID_ARGUMENT');
  await assert.rejects(client.getModality('audio'), e => e.code === 'NOT_FOUND');
  const price = m => Math.min(...m.media_pricing.video_prices.map(p => p.price_per_second).filter(v => v !== null));
  const sorted = videos.data.filter(m => m.media_pricing.video_prices.some(p => p.price_per_second !== null));
  for (let i = 1; i < sorted.length; i++) assert.ok(price(sorted[i - 1]) <= price(sorted[i]));
  const e = await client.estimateMedia('grok-imagine-video-1.5', { seconds: 10, resolution: '720p' });
  close(e.total, 1.4);
  await assert.rejects(client.estimate('grok-imagine-video-1.5', usage(1, 1)), e => e.code === 'UNSUPPORTED_MODALITY');
});

test('estimateMedia: per image, per second, tokens, batch tier, nulls and warnings', () => {
  const grokImg = media('grok-imagine-image-2.0');
  close(estimateMedia(grokImg, { images: 4, size: '1k', quality: 'low' }).total, 0.16);
  close(estimateMedia(grokImg, { images: 2, size: '2k', quality: 'medium', inputImages: 3 }).total, 0.16 + 0.03);
  code(() => estimateMedia(grokImg, { images: 1, size: '1k' }), 'INVALID_ARGUMENT');      // quality is required: low or medium
  code(() => estimateMedia(grokImg, { images: 1, size: '8k', quality: 'low' }), 'PRICE_UNAVAILABLE');
  code(() => estimate(grokImg, usage(1, 1)), 'UNSUPPORTED_MODALITY');
  code(() => estimateMedia(model('claude-opus-5.5'), { images: 1, size: '1k' }), 'UNSUPPORTED_MODALITY');
  code(() => estimateMedia(grokImg, { seconds: 1, resolution: '720p' }), 'INVALID_ARGUMENT');   // seconds is video only
  code(() => estimateMedia(grokImg, { images: 1, size: '1k', quality: 'low', bogus: 1 }), 'INVALID_ARGUMENT');
  code(() => estimateMedia(grokImg, { images: -1, size: '1k', quality: 'low' }), 'INVALID_ARGUMENT');
  code(() => estimateMedia(grokImg, { images: 1, size: '1k', quality: 'low' }, { tier: 'priority' }), 'INVALID_ARGUMENT');
  const video = media('grok-imagine-video-1.5');
  const r = estimateMedia(video, { seconds: 8, resolution: '1080p' });
  close(r.total, 2); assert.equal(r.breakdown.video_seconds, 2); assert.equal(r.currency, 'USD');
  close(estimateMedia(video, { seconds: 8, resolution: '480p', audio: 'with_audio' }).total, 0.64); // audio "any" row applies to both
  code(() => estimateMedia(video, { seconds: 8 }), 'INVALID_ARGUMENT');
  // token-equivalent per-image prices carry a warning; batch tier uses its own rows
  const banana = media('gemini-nano-banana-2.1');
  const std = estimateMedia(banana, { images: 10, size: '4k' });
  close(std.total, 1.13); assert.ok(std.warnings.some(w => w.includes('token-cost equivalent')));
  close(estimateMedia(banana, { images: 10, size: '4k' }, { tier: 'batch' }).total, 0.567);
  close(estimateMedia(banana, { imageOutputTokens: 1000000, textInputTokens: 500000 }).total, 30 + 0.75);
  close(estimateMedia(banana, { imageOutputTokens: 1000000 }, { tier: 'batch' }).total, 15);
  // OpenAI GPT Image publishes tokens only: no per-image price, so per-image estimates must fail rather than guess
  const gpt = media('gpt-image-2.5-flare');
  code(() => estimateMedia(gpt, { images: 1, size: '1k', quality: 'high' }), 'PRICE_UNAVAILABLE');
  close(estimateMedia(gpt, { textInputTokens: 1000, imageOutputTokens: 4000 }).total, 0.005 + 0.12);
  close(estimateMedia(gpt, { textInputTokens: 1000, imageOutputTokens: 4000 }, { tier: 'batch' }).total, (0.005 + 0.12) / 2);
  code(() => estimateMedia(gpt, { videoOutputTokens: 1 }), 'PRICE_UNAVAILABLE');
  // Alibaba list price with a recorded, un-applied limited-time promotion
  const wan = media('wan3.0-video');
  const w = estimateMedia(wan, { seconds: 10, resolution: '720p' });
  close(w.total, 1); assert.ok(w.warnings.some(x => x.includes('promotion')));
  close(estimateMedia(wan, { seconds: 5, resolution: '1080p', inputVideoSeconds: 2 }).total, 1 + 0.4);
  // Google Omni: an unverified resolution is null, never zero; 720p is an approximate listed figure
  const omni = media('gemini-omni-1.1-flash');
  code(() => estimateMedia(omni, { seconds: 5, resolution: '1080p' }), 'PRICE_UNAVAILABLE');
  const o = estimateMedia(omni, { seconds: 5, resolution: '720p' });
  close(o.total, 0.5); assert.ok(o.warnings.some(x => x.includes('approximate')));
  close(estimateMedia(omni, { videoOutputTokens: 1000000 }).total, 17.5);
});
