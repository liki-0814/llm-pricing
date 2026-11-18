const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { availability } = require("../assets/availability.js");
const { estimate, estimateMedia, createClient } = require("../assets/client.js");
const load = p => JSON.parse(fs.readFileSync(path.join(__dirname, "..", p), "utf8"));
const model = id => load("api/v2/models/" + id + ".json").data;
const checkCode = (fn, code) => assert.throws(fn, e => e.code === code);
const usage = { inputTokens: 1000, outputTokens: 100 };

test("shared lifecycle cases: exact >=T, timezone, uncertainty and routed entity", () => {
  for (const c of load("tests/fixtures/lifecycle-cases.json")) {
    const a = availability({ lifecycle: c.lifecycle }, c.at);
    assert.equal(a.status, c.status, c.name);
    assert.equal(a.estimable, c.estimable, c.name);
  }
});

test("ordinary Qwen4 quote is USD; Singapore cache rates are explicit and 12h/storage stay unpublished", () => {
  const m = model("qwen4-max");
  const historic = { at: "2026-11-17T21:00:00+08:00" };
  const at = { at: "2026-11-18T08:27:00+08:00" };
  for (const key of ["cachedInputTokens", "cacheWriteTokens", "cacheWrite1hTokens"])
    checkCode(() => estimate(m, { inputTokens: 1000, outputTokens: 0, [key]: 1000 }, historic), "HISTORICAL_PRICE_UNAVAILABLE");
  assert.ok(Math.abs(estimate(m, usage, historic).total - 0.00195) < 1e-12);
  const q = estimate(m, usage, at);
  assert.equal(q.currency, "USD"); assert.equal(q.unit, "per_1M_tokens");
  assert.equal(q.region, "Singapore"); assert.equal(q.channel, "pay_as_you_go");
  assert.ok(Math.abs(q.total - 0.00195) < 1e-12);
  const cached = estimate(m, { inputTokens: 1000, outputTokens: 0, cachedInputTokens: 1000 }, at);
  assert.ok(Math.abs(cached.total - 0.000075) < 1e-15);
  const write5m = estimate(m, { inputTokens: 1000, outputTokens: 0, cacheWriteTokens: 1000 }, at);
  assert.ok(Math.abs(write5m.total - 0.001875) < 1e-15);
  const write1h = estimate(m, { inputTokens: 1000, outputTokens: 0, cacheWrite1hTokens: 1000 }, at);
  assert.ok(Math.abs(write1h.total - 0.003) < 1e-15);
  for (const key of ["cacheWrite12hTokens", "storageTokenHours"])
    checkCode(() => estimate(m, { ...usage, [key]: 1 }, at), "PRICE_UNAVAILABLE");
  checkCode(() => estimate(m, { inputTokens: 983617, outputTokens: 1 }), "LIMIT_EXCEEDED");
});

test("Hy4 list prices, inclusive promotional instant and known restoration retain CNY", () => {
  const m = model("hy4-flash");
  for (const [at, expected] of [["2026-11-30T03:59:59.999Z", 0.25], ["2026-11-30T04:00:00Z", 0.25], ["2026-11-30T04:00:00.001Z", 0.5]]) {
    const q = estimate(m, { inputTokens: 1000, outputTokens: 0 }, { at });
    assert.equal(q.unit_prices.input, expected); assert.equal(q.currency, "CNY");
    assert.equal(q.region, "Guangzhou (TokenHub)");
  }
  checkCode(() => estimate(m, usage, { at: "2026-11-17T12:18:10Z" }), "HISTORICAL_PRICE_UNAVAILABLE");
  checkCode(() => estimate(m, usage, { at: "2026-11-30" }), "TIME_REQUIRED");
  checkCode(() => estimate(m, { ...usage, cacheWriteTokens: 1 }), "PRICE_UNAVAILABLE");
  const cached = estimate(m, { inputTokens: 1000, outputTokens: 0, cachedInputTokens: 1000 }, { at: "2026-11-30T04:00:00Z" });
  assert.equal(cached.unit_prices.cached_input, 0.01);
});

test("Preview no borrowed discount; date-only retirement is explicitly uncertain", () => {
  const q = estimate(model("hy4-preview"), usage, { at: "2026-11-17T21:00:00+08:00" });
  assert.equal(q.unit_prices.input, 6); assert.equal(q.availability.status, "pending_confirmation");
  assert.ok(q.warnings.some(x => x.includes("not confirmed")));
});

test("stale pre-T details reject direct current token and media estimates at T; explicit historical token quote works", () => {
  const c = load("tests/fixtures/lifecycle-cases.json")[1];
  const m = model("qwen4-max"); m.lifecycle = c.lifecycle;
  checkCode(() => estimate(m, usage, { at: c.at }), "MODEL_RETIRED");
  assert.ok(estimate(m, usage, { at: "2026-12-01T03:59:59Z" }).total > 0);
  const media = model("grok-imagine-image-2.0"); media.lifecycle = c.lifecycle;
  checkCode(() => estimateMedia(media, { images: 1, size: "1k", quality: "low" }, { at: c.at }), "MODEL_RETIRED");
  media.lifecycle = null; media.currency = "CNY";
  const q = estimateMedia(media, { images: 1, size: "1k", quality: "low" });
  assert.equal(q.currency, "CNY"); assert.equal(q.unit, "see_media_pricing");
});

test("v1 is USD-only; v2 requires a single-currency price sort and never silently converts", async () => {
  const envelope = load("api/v2/models.json");
  const fetch = async () => ({ ok: true, json: async () => envelope });
  const client = createClient("https://example.org/api/v2/", { fetch });
  await assert.rejects(client.listModels({ sort: "input" }), e => e.code === "CURRENCY_MISMATCH");
  const cny = await client.listModels({ sort: "input", currency: "CNY" });
  assert.equal(cny.data.length, 3); assert.ok(cny.data.every(m => m.currency === "CNY"));
  assert.ok(load("api/v1/models.json").data.every(m => m.currency === "USD"));
  assert.equal(load("api/v1/models.json").data.length, 86);
});

test("Sol date-only cutoff is not an inferred instant or future price", () => {
  const m = model("gpt-5.6-sol");
  assert.equal(m.price_schedule[0].effective_until, "2026-11-30");
  checkCode(() => estimate(m, usage, { at: "2026-11-30T12:00:00+08:00" }), "PRICE_BOUNDARY_UNCONFIRMED");
});


test("real v2 HTTP list/vendor/modality/detail and direct quotes share currency/versions", async t => {
  const http = require("node:http");
  const root = path.resolve(__dirname, "..");
  const server = http.createServer((req, res) => {
    const target = path.resolve(root, "." + new URL(req.url, "http://localhost").pathname);
    if (!target.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
    fs.readFile(target, (err, body) => { res.writeHead(err ? 404 : 200, { "Content-Type": "application/json" }).end(err ? "{}" : body); });
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const client = createClient("http://127.0.0.1:" + server.address().port + "/api/v2/");
  const all = await client.listModels();
  assert.equal(all.data.length, 89);
  assert.equal((await client.getIndex()).data.models.length, 89);
  const manifest = all.meta;
  for (const vendor of (await client.listVendors()).data) {
    const subset = await client.getVendor(vendor.slug);
    assert.equal(subset.meta.data_version, manifest.data_version);
    assert.deepEqual(subset.data.map(m => m.id), all.data.filter(m => m.vendor === vendor.slug).map(m => m.id));
  }
  for (const mod of (await client.listModalities()).data) {
    const subset = await client.getModality(mod.name);
    assert.equal(subset.meta.as_of, manifest.as_of);
    assert.deepEqual(subset.data.map(m => m.id), all.data.filter(m => m.modality === mod.name).map(m => m.id));
  }
  for (const m of all.data) {
    const detail = await client.getModel(m.id);
    assert.equal(detail.meta.data_version, manifest.data_version);
    assert.deepEqual(detail.data, m);
  }
  const q = await client.estimate("hy4-flash", usage, { at: "2026-11-17T21:00:00+08:00" });
  assert.equal(q.currency, "CNY");
  const usd = await client.estimate("qwen4-max", usage, { at: "2026-11-17T21:00:00+08:00" });
  assert.equal(usd.currency, "USD");
  const old = createClient("http://127.0.0.1:" + server.address().port + "/api/v1/");
  await assert.rejects(old.getModel("hy4"), e => e.code === "NOT_FOUND");
});
