// Behavioral DOM harness only; not browser rendering / visual / a11y approval.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const path = require("node:path");
const availability = require("../assets/availability.js");

test("page single-currency filter controls rows, symbols, cheapest and v2 details together", async () => {
  const elements = new Map();
  function el(id) {
    if (!elements.has(id)) elements.set(id, { value: "", innerHTML: "", options: [], listeners: {},
      hidden: false, classList: { toggle() {} }, setAttribute() {},
      addEventListener(type, fn) { this.listeners[type] = fn; } });
    return elements.get(id);
  }
  const page = JSON.parse(fs.readFileSync(path.join(__dirname, "../data/page-models.json"), "utf8"));
  const context = { URLSearchParams, URL, console,
    location: { search: "", pathname: "/", hash: "" }, history: { replaceState() {} },
    document: { getElementById: el, querySelectorAll: () => [], addEventListener() {},
      querySelector: () => ({ clientWidth: 1000, classList: { toggle() {} } }),
      documentElement: { style: { setProperty() {} } } },
    window: { addEventListener() {} }, setTimeout() {},
    LLMAvailability: availability, LP: { slug: x => x, esc: x => String(x ?? "") },
    fetch: async () => ({ ok: true, json: async () => page }) };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../assets/app.js"), "utf8"), context);
  await new Promise(setImmediate);
  assert.equal(el("error").innerHTML, "");
  assert.ok(el("statAsOf").textContent.includes("2026-11-18 08:27:00"));
  assert.ok(el("statAsOf").textContent.includes("UTC+08:00"));
  assert.ok(el("footUpdated").textContent.includes("快照时点"));
  assert.ok(el("footUpdated").textContent.includes("公开原文价格事实 " + page.public_price_evidence.price_verified_count));
  assert.ok(el("footUpdated").textContent.includes("非目录全集/当前可用性认证"));
  assert.ok(el("footUpdated").innerHTML.includes('href="api/v2/price-facts.json"'));
  assert.ok(el("tbody").innerHTML.includes("qwen4-max"));
  assert.ok(!el("tbody").innerHTML.includes('data-id="hy4"'));
  assert.ok(el("statCheapest").innerHTML.includes("USD"));
  el("currencySelect").value = "CNY";
  el("currencySelect").listeners.change.call(el("currencySelect"));
  assert.ok(el("tbody").innerHTML.includes("¥"));
  assert.ok(el("tbody").innerHTML.includes('data-id="hy4"'));
  assert.ok(!el("tbody").innerHTML.includes("qwen4-max"));
  assert.ok(!el("tbody").innerHTML.includes('<span class="cur">$'));
  assert.ok(el("statCheapest").innerHTML.includes("CNY"));
  assert.ok(el("tbody").innerHTML.includes("2026-12-07"));
  assert.ok(el("tbody").innerHTML.includes("具体时刻及时区待确认"));
});


test("page details disclose field observation, tier schedule, and per-task image basis (DOM harness only)", async () => {
  for (const [query, checks] of [
    ['?open=qwen4-max,gpt-6.2-astra,claude-opus-4.8', ['观察前未知历史拒绝估价','America/Los_Angeles','2027-03-01T00:00:00-08:00','基准×3','档状态 deprecated']],
    ['?modality=video&open=minimax-h3-regeneration', ['每任务前 5 张输入图免费','传入总张数','不需手减']]
  ]) {
    const elements = new Map();
    const el = id => {
      if (!elements.has(id)) elements.set(id, {value:'',innerHTML:'',options:[],listeners:{},hidden:false,classList:{toggle(){}},setAttribute(){},addEventListener(t,f){this.listeners[t]=f;}});
      return elements.get(id);
    };
    const page=JSON.parse(fs.readFileSync(path.join(__dirname,'../data/page-models.json'),'utf8'));
    const ctx={URLSearchParams,URL,console,location:{search:query,pathname:'/',hash:''},history:{replaceState(){}},
      document:{getElementById:el,querySelectorAll:()=>[],addEventListener(){},querySelector:()=>({clientWidth:1000,classList:{toggle(){}}}),documentElement:{style:{setProperty(){}}}},
      window:{addEventListener(){}},setTimeout(){},LLMAvailability:availability,LP:{slug:x=>x,esc:x=>String(x??'')},fetch:async()=>({ok:true,json:async()=>page})};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../assets/app.js'),'utf8'),ctx);
    await new Promise(setImmediate);
    assert.equal(el('error').innerHTML,'');
    const html=[...elements.values()].map(e=>e.innerHTML).join('');
    for(const value of checks) assert.ok(html.includes(value),value);
  }
});
