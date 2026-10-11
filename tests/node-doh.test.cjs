const test = require('node:test');
const assert = require('node:assert/strict');
const { createClient } = require('../assets/client.js');
const { createDohFetch } = require('../assets/node-doh.cjs');
const base = 'https://example.com/api/v1/';

test('DoH is explicit, HTTPS-only and confined to the selected origin', async () => {
  assert.throws(()=>createDohFetch('http://example.com/'),/HTTPS/);
  const transport=createDohFetch(base,{resolverFetch:()=>{throw new Error('must not resolve foreign origins');}});
  await assert.rejects(transport('https://other.example/index.json'),/restricted/);
  await assert.rejects(transport('http://example.com/index.json'),/restricted/);
});
test('DoH rejects resolver failures and malformed/empty DNS answers', async () => {
  for(const answer of [{Status:3,Answer:[]},{Status:0,Answer:[]},
    {Status:0,Answer:[{type:1,data:'not-an-IP',TTL:60}]}]) {
    const transport=createDohFetch(base,{resolverFetch:async url=>{
      assert.equal(url.hostname,'dns.google');
      assert.equal(url.searchParams.get('name'),'example.com');
      return new Response(JSON.stringify(answer));
    }});
    await assert.rejects(transport(new URL('index.json',base)),/no IPv4/);
  }
  const transport=createDohFetch(base,{resolverFetch:async()=>new Response('{}',{status:503})});
  await assert.rejects(transport(new URL('index.json',base)),/HTTP 503/);
});
test('client timeout cancels DNS resolution as well as the HTTPS request', async () => {
  let aborted=false;
  const transport=createDohFetch(base,{resolverFetch:(_url,{signal})=>new Promise((_resolve,reject)=>{
    signal.addEventListener('abort',()=>{aborted=true;reject(signal.reason);},{once:true});
  })});
  await assert.rejects(createClient(base,{fetch:transport,timeoutMs:20}).getIndex(),e=>e.code==='TIMEOUT');
  assert.equal(aborted,true);
});
