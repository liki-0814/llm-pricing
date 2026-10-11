/* Verify every deployed JSON file with both curl and the real Node client. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { promisify } = require('node:util');
const execFile = promisify(require('node:child_process').execFile);
const { createClient } = require('../assets/client.js');
const { createDohFetch } = require('../assets/node-doh.cjs');
const root = path.resolve(__dirname, '..');

async function main() {
  const args = process.argv.slice(2);
  const doh = args.includes('--doh');
  const positional = args.filter(arg => arg !== '--doh');
  const base = new URL(positional[0] || 'https://liki-0814.github.io/llm-pricing/api/v1/');
  assert.ok(base.pathname.endsWith('/'), 'base URL must end with /');
  const output = positional[1];
  const files = ['index.json','models.json','vendors.json','openapi.json',
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
  for(const file of ['models/unknown-model.json','vendors/unknown-vendor.json']) {
    const curl=await curlQuery(file);
    assert.equal(curl.status,404);
    await assert.rejects(nodeQuery(file),e=>e.code==='NOT_FOUND');
    negatives.push({file,curl_status:404,node_error:'NOT_FOUND'});
  }
  const search=await client.listModels({vendor:'xai',q:'grok 4.7',sort:'input',priceBasis:'official',limit:1});
  assert.equal(search.data[0].id,'grok-4.7');
  const estimate=await client.estimate('grok-4.7',{inputTokens:200000,outputTokens:10000,cachedInputTokens:100000},
    {at:'2026-10-11',serviceTier:'priority',dataResidency:true});
  assert.ok(Math.abs(estimate.total-1.364)<1e-10);
  const fast=await client.getModel('grok-4.7-build-fast');
  assert.equal(fast.data.billing.channel,'subscription');
  assert.equal(fast.data.price_basis.type,'reference');
  assert.equal(fast.data.pricing_status.input,'reference');
  const fastEstimate=await client.estimate('grok-4.7-build-fast',
    {inputTokens:200001,outputTokens:10000,cachedInputTokens:100000},{at:'2026-10-11'});
  assert.ok(Math.abs(fastEstimate.total-0.930006)<1e-10);
  assert.ok(fastEstimate.warnings.some(w=>w.includes('not the subscription bill')));
  const report={checked_at:new Date().toISOString(),base_url:base.href,node_version:process.version,
    dns_mode:doh?'explicit HTTPS DNS; default TLS verification':'system DNS',
    count:rows.length,rows:rows.sort((a,b)=>a.file.localeCompare(b.file)),negative_checks:negatives,
    grok_query:search.data[0].id,grok_estimate:estimate,build_fast_estimate:fastEstimate};
  if(output) fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({count:report.count,curl:'all passed',node_client:'all passed',
    negative_checks:'passed',grok_estimate:estimate.total,build_fast_reference_estimate:fastEstimate.total,
    data_version:search.meta.data_version,output},null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
