/* Verify every deployed JSON file with both curl and the real Node client. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { promisify } = require('node:util');
const execFile = promisify(require('node:child_process').execFile);
const { createClient, estimate: localEstimate, estimateMedia: localEstimateMedia } = require('../assets/client.js');
const { createDohFetch } = require('../assets/node-doh.cjs');
const root = path.resolve(__dirname, '..');

async function main() {
  const args = process.argv.slice(2);
  const doh = args.includes('--doh');
  const positional = args.filter(arg => arg !== '--doh');
  const base = new URL(positional[0] || 'https://liki-0814.github.io/llm-pricing/api/v1/');
  assert.ok(base.pathname.endsWith('/'), 'base URL must end with /');
  const output = positional[1];
  const files = ['index.json','models.json','vendors.json','modalities.json','openapi.json',
    ...fs.readdirSync(path.join(root,'api/v1/modalities')).filter(p=>p.endsWith('.json')).map(p=>'modalities/'+p),
    ...fs.readdirSync(path.join(root,'api/v1/models')).filter(p=>p.endsWith('.json')).map(p=>'models/'+p),
    ...fs.readdirSync(path.join(root,'api/v1/vendors')).filter(p=>p.endsWith('.json')).map(p=>'vendors/'+p)];
  const fetcher = doh ? createDohFetch(base.href) : globalThis.fetch;
  const metadata = new Map();
  const client = createClient(base.href, { fetch: async (url, init) => {
    const start = Date.now(), response = await fetcher(url, init);
    metadata.set(url, { status:response.status, content_type:response.headers.get('content-type'),
      cors:response.headers.get('access-control-allow-origin'), ms:Date.now()-start });
    return response;
  }});
  async function nodeQuery(file) {
    if(file==='index.json') return client.getIndex();
    if(file==='models.json') {
      const data = await client.listModels();
      delete data.meta.matched_count; delete data.meta.total_count;
      return data;
    }
    if(file==='vendors.json') return client.listVendors();
    if(file==='modalities.json') return client.listModalities();
    if(file.startsWith('modalities/')) return client.getModality(path.basename(file,'.json'));
    if(file==='openapi.json') return client.getOpenAPI();
    const id = path.basename(file,'.json');
    return file.startsWith('models/') ? client.getModel(id) : client.getVendor(id);
  }
  async function curlQuery(file) {
    const argv = ['--silent','--show-error','--connect-timeout','10','--max-time','20'];
    if(doh) argv.push('--doh-url','https://dns.google/dns-query');
    argv.push('--write-out','\n%{http_code}\t%{ssl_verify_result}\t%{content_type}\t%{time_total}',new URL(file,base).href);
    const {stdout} = await execFile('curl',argv,{maxBuffer:4*1024*1024});
    const split = stdout.lastIndexOf('\n');
    const [status,tls,contentType,seconds] = stdout.slice(split+1).split('\t');
    assert.ok(Number.isFinite(Number(seconds)),file+' curl timing is invalid');
    return {body:stdout.slice(0,split),status:Number(status),tls_verified:Number(tls)===0,
      content_type:contentType,ms:Number(seconds)*1000};
  }
  const rows = [];
  let cursor = 0;
  async function worker() {
    while(cursor<files.length) {
      const file=files[cursor++], url=new URL(file,base).href;
      const expected=JSON.parse(fs.readFileSync(path.join(root,'api/v1',file)));
      const [node,curl]=await Promise.all([nodeQuery(file),curlQuery(file)]);
      assert.equal(curl.status,200,file+' curl status');
      assert.equal(curl.tls_verified,true,file+' curl TLS');
      assert.match(curl.content_type,/application\/json/,file+' curl content type');
      assert.match(metadata.get(url).content_type,/application\/json/,file+' Node content type');
      assert.deepEqual(JSON.parse(curl.body),expected,file+' curl differs from local snapshot');
      assert.deepEqual(node,expected,file+' Node differs from local snapshot');
      const {body,...curlMeta}=curl;
      rows.push({file,url,curl:curlMeta,node:metadata.get(url),matches_local:true,
        data_version:expected.meta?.data_version || null});
    }
  }
  await Promise.all(Array.from({length:4},worker));
  const negatives=[];
  for(const file of ['models/unknown-model.json','vendors/unknown-vendor.json','modalities/unknown-modality.json']) {
    const curl=await curlQuery(file);
    assert.equal(curl.status,404);
    await assert.rejects(nodeQuery(file),e=>e.code==='NOT_FOUND');
    negatives.push({file,curl_status:404,node_error:'NOT_FOUND'});
  }
  const search=await client.listModels({vendor:'xai',q:'grok 4.7',sort:'input',priceBasis:'official',limit:1});
  assert.equal(search.data[0].id,'grok-4.7');
  // Date-independent: estimate at each model's own verification date (no hard-coded snapshot day)
  // and compare the live client result with the same estimate over the committed local snapshot.
  const localModel=id=>JSON.parse(fs.readFileSync(path.join(root,'api/v1/models',id+'.json'))).data;
  const atSnapshot=m=>({at:m.last_updated+'T12:00:00Z',isChineseHoliday:false});
  const grok=localModel('grok-4.7');
  const grokUsage={inputTokens:200000,outputTokens:10000,cachedInputTokens:100000};
  const grokOptions={...atSnapshot(grok),serviceTier:'priority',dataResidency:true};
  const estimate=await client.estimate('grok-4.7',grokUsage,grokOptions);
  assert.deepEqual(estimate,localEstimate(grok,grokUsage,grokOptions),'grok-4.7 live estimate differs from local snapshot');
  assert.equal(estimate.pricing_tier,'input_tokens>199999');
  assert.equal(estimate.service_tier,'priority');
  assert.ok(Number.isFinite(estimate.total)&&estimate.total>0);
  const fast=await client.getModel('grok-4.7-build-fast');
  assert.equal(fast.data.billing.channel,'subscription');
  assert.equal(fast.data.price_basis.type,'reference');
  assert.equal(fast.data.pricing_status.input,'reference');
  const fastUsage={inputTokens:200001,outputTokens:10000,cachedInputTokens:100000};
  const fastEstimate=await client.estimate('grok-4.7-build-fast',fastUsage,atSnapshot(fast.data));
  assert.deepEqual(fastEstimate,localEstimate(localModel('grok-4.7-build-fast'),fastUsage,atSnapshot(fast.data)),
    'grok-4.7-build-fast live estimate differs from local snapshot');
  assert.equal(fastEstimate.pricing_tier,'input_tokens>200000');
  assert.ok(fastEstimate.warnings.some(w=>w.includes('not the subscription bill')));
  // Modality counts, per-modality filtering and media estimates over the live API.
  const live=await client.listModalities();
  const modalityCounts=Object.fromEntries(live.data.map(m=>[m.name,m.model_count]));
  assert.deepEqual(modalityCounts,{text:49,image:12,video:9},'live modality counts');
  assert.deepEqual(live.meta.modality_counts,modalityCounts);
  assert.equal(live.meta.count,70);
  for(const name of ['text','image','video']) {
    const filtered=await client.listModels({modality:name});
    const direct=await client.getModality(name);
    assert.equal(filtered.data.length,modalityCounts[name],name+' listModels({modality}) count');
    assert.equal(direct.data.length,modalityCounts[name],name+' modalities/'+name+'.json count');
    assert.ok(direct.data.every(m=>m.modality===name),name+' modality file mixes modalities');
  }
  const mediaUsage={xai_video:{seconds:10,resolution:'720p'},xai_image:{images:4,size:'1k',quality:'low'}};
  const videoModel=localModel('grok-imagine-video-1.5'), imageModel=localModel('grok-imagine-image-2.0');
  const liveVideo=await client.estimateMedia('grok-imagine-video-1.5',mediaUsage.xai_video);
  const liveImage=await client.estimateMedia('grok-imagine-image-2.0',mediaUsage.xai_image);
  assert.deepEqual(liveVideo,localEstimateMedia(videoModel,mediaUsage.xai_video),'live video estimate differs from local snapshot');
  assert.deepEqual(liveImage,localEstimateMedia(imageModel,mediaUsage.xai_image),'live image estimate differs from local snapshot');
  await assert.rejects(client.estimate('grok-imagine-video-1.5',{inputTokens:1,outputTokens:1}),e=>e.code==='UNSUPPORTED_MODALITY');
  const report={checked_at:new Date().toISOString(),base_url:base.href,node_version:process.version,
    dns_mode:doh?'explicit HTTPS DNS; default TLS verification':'system DNS',
    count:rows.length,modality_counts:modalityCounts,rows:rows.sort((a,b)=>a.file.localeCompare(b.file)),negative_checks:negatives,
    grok_query:search.data[0].id,video_estimate:liveVideo,image_estimate:liveImage,grok_estimate:estimate,build_fast_estimate:fastEstimate};
  if(output) fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({count:report.count,modality_counts:modalityCounts,video_estimate_total:liveVideo.total,image_estimate_total:liveImage.total,curl:'all passed',node_client:'all passed',
    negative_checks:'passed',grok_estimate:estimate.total,build_fast_reference_estimate:fastEstimate.total,
    data_version:search.meta.data_version,output},null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
