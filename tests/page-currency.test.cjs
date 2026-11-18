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
