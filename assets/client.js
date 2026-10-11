/* Static JSON client and token/cache estimator. Browser: LLMPrice; Node: require(). */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.LLMPrice = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  var PRICE = ["input", "output", "cached_input", "cache_write"];
  var CACHE = ["implicit_read", "explicit_read", "explicit_write", "explicit_write_1h", "storage_per_1M_tokens_hour"];
  function error(code, message) { var e = new Error(message); e.code = code; return e; }
  function number(value, label, integer) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || (integer && !Number.isSafeInteger(value)))
      throw error("INVALID_ARGUMENT", label + " must be a nonnegative " + (integer ? "safe integer" : "number"));
    return value;
  }
  function date(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}(?:T.*(?:Z|[+-]\d\d:\d\d))?$/.test(value))
      throw error("INVALID_ARGUMENT", "at must be YYYY-MM-DD or an ISO timestamp with timezone");
    var d = new Date(value);
    if (!Number.isFinite(d.getTime()) || new Date(value.slice(0, 10)).toISOString().slice(0, 10) !== value.slice(0, 10))
      throw error("INVALID_ARGUMENT", "at is not a valid calendar date");
    return d;
  }
  function estimate(model, usage, options) {
    usage = usage || {}; options = options || {};
    var allowedUsage = ["inputTokens", "outputTokens", "cachedInputTokens", "cacheWriteTokens", "cacheWrite1hTokens", "storageTokenHours"];
    Object.keys(usage).forEach(function (k) { if (allowedUsage.indexOf(k) < 0) throw error("INVALID_ARGUMENT", "Unknown usage field: " + k); });
    var allowedOptions = ["at", "serviceTier", "dataResidency", "cacheType", "isChineseHoliday"];
    Object.keys(options).forEach(function (k) { if (allowedOptions.indexOf(k) < 0) throw error("INVALID_ARGUMENT", "Unknown estimate option: " + k); });
    if (!Object.prototype.hasOwnProperty.call(usage, "inputTokens") || !Object.prototype.hasOwnProperty.call(usage, "outputTokens"))
      throw error("INVALID_ARGUMENT", "inputTokens and outputTokens are required");
    var counts = {};
    allowedUsage.forEach(function (k) { counts[k] = number(usage[k] === undefined ? 0 : usage[k], k, k !== "storageTokenHours"); });
    if (counts.cachedInputTokens + counts.cacheWriteTokens + counts.cacheWrite1hTokens > counts.inputTokens)
      throw error("INVALID_ARGUMENT", "inputTokens includes cache reads and writes; their sum cannot exceed inputTokens");
    if (options.dataResidency !== undefined && typeof options.dataResidency !== "boolean")
      throw error("INVALID_ARGUMENT", "dataResidency must be boolean");
    if (options.isChineseHoliday !== undefined && typeof options.isChineseHoliday !== "boolean")
      throw error("INVALID_ARGUMENT", "isChineseHoliday must be boolean");
    if (options.cacheType !== undefined && ["implicit", "explicit"].indexOf(options.cacheType) < 0)
      throw error("INVALID_ARGUMENT", "cacheType must be implicit or explicit");
    var at = date(options.at === undefined ? new Date().toISOString() : options.at), day = at.toISOString().slice(0, 10), warnings = [];
    if (day < model.last_updated) throw error("HISTORICAL_PRICE_UNAVAILABLE", "This snapshot does not contain prices before " + model.last_updated);
    if (model.limits.max_output_tokens !== null && counts.outputTokens > model.limits.max_output_tokens)
      throw error("LIMIT_EXCEEDED", "outputTokens exceeds the documented maximum");
    if (model.context_length !== null && counts.inputTokens > model.context_length)
      throw error("LIMIT_EXCEEDED", "inputTokens exceeds the recorded context window");
    if (day > model.last_updated) warnings.push("Prices are based on the " + model.last_updated + " snapshot and announced schedules; later unannounced changes are not known.");
    var prices = Object.assign({}, model.pricing), cache = Object.assign({}, model.cache_pricing), tier = null, period = "standard";
    (model.pricing_tiers || []).forEach(function (t) {
      if (counts.inputTokens > t.input_tokens_gt && (t.input_tokens_lte === null || counts.inputTokens <= t.input_tokens_lte)) {
        if (tier) throw error("INVALID_DATA", "Overlapping price tiers");
        tier = t;
      }
    });
    if (tier) { PRICE.forEach(function (k) { prices[k] = tier[k]; }); if (tier.cache_pricing) cache = Object.assign(cache, tier.cache_pricing); }
    var schedule = model.off_peak_schedule;
    if (model.has_off_peak) {
      if (!options.at || options.at.length === 10) throw error("TIME_REQUIRED", "Peak pricing requires an ISO timestamp with timezone");
      if (!schedule) throw error("INVALID_DATA", "Missing peak schedule");
      var weekday = at.getUTCDay() || 7, hhmm = at.toISOString().slice(11, 16);
      var candidate = schedule.weekdays.indexOf(weekday) >= 0 && schedule.peak_windows.some(function (w) { return hhmm >= w.start && hhmm < w.end; });
      if (candidate && typeof options.isChineseHoliday !== "boolean")
        throw error("HOLIDAY_REQUIRED", "Confirm isChineseHoliday for a weekday peak window");
      var peak = candidate && !options.isChineseHoliday;
      period = peak ? "peak" : "off_peak";
      if (!peak) Object.assign(prices, model.off_peak_pricing);
    }
    (model.price_schedule || []).forEach(function (e) {
      if (e.effective_from && day < e.effective_from) return;
      if (e.effective_until && day > e.effective_until) {
        if (e.kind === "promotion") throw error("PRICE_EXPIRED", "Promotion needs re-verification after " + e.effective_until);
        return;
      }
      if (e.kind === "promotion" && !e.effective_until) warnings.push("Promotion end date is unknown: " + e.note);
      if (e.multiplier !== null) {
        PRICE.forEach(function (k) { if (prices[k] !== null) prices[k] *= e.multiplier; });
        CACHE.forEach(function (k) { if (cache[k] !== null && k !== "storage_per_1M_tokens_hour") cache[k] *= e.multiplier; });
        if (!tier) Object.assign(cache, e.cache_pricing || {});
        else if (Object.prototype.hasOwnProperty.call(e.cache_pricing || {}, "storage_per_1M_tokens_hour"))
          cache.storage_per_1M_tokens_hour = e.cache_pricing.storage_per_1M_tokens_hour;
      } else {
        if (tier && PRICE.some(function (k) { return e[k] !== null && e[k] !== model.pricing[k]; }))
          throw error("PRICE_UNAVAILABLE", "Scheduled change has no documented long-context tier prices or multiplier");
        if (!tier) PRICE.forEach(function (k) { if (e[k] !== null) prices[k] = e[k]; });
        Object.assign(cache, e.cache_pricing || {});
      }
    });
    if (options.serviceTier !== undefined && (typeof options.serviceTier !== "string" || !options.serviceTier))
      throw error("INVALID_ARGUMENT", "serviceTier must be a nonempty string");
    var selected = options.serviceTier || "standard";
    if (selected === "data_residency") throw error("INVALID_ARGUMENT", "Use dataResidency: true alongside serviceTier");
    var services = (model.service_tiers || []), svc = selected === "standard" ? null : services.find(function (s) { return s.name === selected; });
    if (selected !== "standard" && !svc) throw error("UNSUPPORTED_SERVICE_TIER", "No documented price for service tier " + selected);
    var unknown = {};
    function applyService(s) {
      PRICE.forEach(function (k) {
        var explicit = Object.prototype.hasOwnProperty.call(s.pricing, k);
        if (explicit) { prices[k] = s.pricing[k]; unknown[k] = prices[k] === null; }
        else if (s.multipliers[k] === null) unknown[k] = true;
        else if (prices[k] !== null) prices[k] *= s.multipliers[k];
      });
      CACHE.forEach(function (k) {
        if (s.multipliers[k] === null) unknown[k] = true;
        else if (cache[k] !== null) cache[k] *= s.multipliers[k];
      });
    }
    if (svc) applyService(svc);
    if (options.dataResidency) {
      var region = services.find(function (s) { return s.name === "data_residency"; });
      if (!region) throw error("UNSUPPORTED_SERVICE_TIER", "No documented data residency surcharge");
      applyService(region);
    }
    var readPrice = prices.cached_input, readKey = "cached_input";
    if (options.cacheType && options.cacheType !== model.billing.cached_input_type) {
      readKey = options.cacheType + "_read"; readPrice = cache[readKey];
    }
    var parts = {}, units = {};
    function cost(key, amount, rate, rateKey) {
      if (amount === 0) { parts[key] = 0; return; }
      if (rate === null || rate === undefined || unknown[rateKey]) throw error("PRICE_UNAVAILABLE", "No documented unit price for " + rateKey);
      number(rate, rateKey, false); units[key] = rate; parts[key] = amount / 1e6 * rate;
      if (!Number.isFinite(parts[key])) throw error("INVALID_ARGUMENT", "Usage is too large to estimate " + key);
    }
    cost("input", counts.inputTokens - counts.cachedInputTokens - counts.cacheWriteTokens - counts.cacheWrite1hTokens, prices.input, "input");
    cost("output", counts.outputTokens, prices.output, "output");
    cost("cached_input", counts.cachedInputTokens, readPrice, readKey);
    cost("cache_write", counts.cacheWriteTokens, prices.cache_write, "cache_write");
    cost("cache_write_1h", counts.cacheWrite1hTokens, cache.explicit_write_1h, "explicit_write_1h");
    cost("storage", counts.storageTokenHours, cache.storage_per_1M_tokens_hour, "storage_per_1M_tokens_hour");
    var reference = model.price_basis.type === "reference";
    if (reference) warnings.push("Reference estimate using " + model.price_basis.reference_model_id + "; this is not the subscription bill.");
    var total = Object.keys(parts).reduce(function (n, k) { return n + parts[k]; }, 0);
    if (!Number.isFinite(total)) throw error("INVALID_ARGUMENT", "Usage is too large to estimate the total");
    return { model_id: model.id, currency: "USD", total: total,
      breakdown: parts, unit_prices: units, input_tokens: counts.inputTokens, at: at.toISOString(),
      pricing_tier: tier ? tier.condition : "base", period: period, service_tier: selected,
      price_basis: model.price_basis, billing: model.billing, warnings: warnings,
      excluded_costs: ["server_tools", "taxes", "subscription_quota_settlement", "unrecorded_multimodal_rates"] };
  }

  function createClient(baseUrl, config) {
    config = config || {};
    var base = new URL(baseUrl, typeof location === "undefined" ? undefined : location.href);
    if (base.search || base.hash) throw error("INVALID_ARGUMENT", "baseUrl cannot contain a query or fragment");
    base.pathname = base.pathname.replace(/\/?$/, "/");
    var fetcher = config.fetch || globalThis.fetch, timeout = config.timeoutMs === undefined ? 15000 : number(config.timeoutMs, "timeoutMs", true);
    if (!timeout) throw error("INVALID_ARGUMENT", "timeoutMs must be positive");
    if (typeof fetcher !== "function") throw error("INVALID_ARGUMENT", "fetch is required (Node 18+ or a browser)");
    async function get(path, isOpenAPI) {
      var controller = new AbortController(), timer = setTimeout(function () { controller.abort(); }, timeout);
      try {
        var r = await fetcher(new URL(path, base).href, { signal: controller.signal });
        if (!r.ok) throw error(r.status === 404 ? "NOT_FOUND" : "HTTP_ERROR", "HTTP " + r.status + " for " + path);
        var data;
        try { data = await r.json(); } catch (_) { throw error("INVALID_RESPONSE", "Expected JSON for " + path); }
        if (isOpenAPI) {
          if (!data || !/^3\.1\.\d+$/.test(data.openapi) || !data.info || !data.paths)
            throw error("INVALID_RESPONSE", "Expected an OpenAPI 3.1 document for " + path);
          return data;
        }
        if (!data || data.api_version !== "v1" || !data.meta || data.data === undefined)
          throw error("INVALID_RESPONSE", "Unexpected response envelope for " + path);
        return data;
      } catch (e) {
        if (controller.signal.aborted) throw error("TIMEOUT", "Request timed out for " + path);
        if (e.code) throw e;
        throw error("NETWORK_ERROR", "Cannot fetch " + path + ": " + e.message);
      } finally { clearTimeout(timer); }
    }
    function safeId(id) { if (typeof id !== "string" || !/^[a-z0-9][a-z0-9.\-]*$/.test(id)) throw error("INVALID_ARGUMENT", "Use a model ID or vendor slug from index.json"); return id; }
    function query(envelope, options) {
      options = options || {};
      var keys = ["vendor", "q", "sort", "limit", "priceBasis"];
      Object.keys(options).forEach(function (k) { if (keys.indexOf(k) < 0) throw error("INVALID_ARGUMENT", "Unknown query option: " + k); });
      if (options.vendor !== undefined) safeId(options.vendor);
      if (options.q !== undefined && typeof options.q !== "string") throw error("INVALID_ARGUMENT", "q must be a string");
      if (options.sort !== undefined && typeof options.sort !== "string") throw error("INVALID_ARGUMENT", "sort must be a string");
      if (options.priceBasis !== undefined && ["official", "reference"].indexOf(options.priceBasis) < 0) throw error("INVALID_ARGUMENT", "priceBasis must be official or reference");
      var models = envelope.data.filter(function (m) {
        var terms = (options.q || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
        var text = [m.id, m.name, m.vendor, m.vendor_name, m.notes || ""].join(" ").toLowerCase();
        return (!options.vendor || m.vendor === options.vendor) && (!options.priceBasis || m.price_basis.type === options.priceBasis) && terms.every(function (t) { return text.indexOf(t) >= 0; });
      });
      if (options.sort) {
        var desc = options.sort[0] === "-", key = desc ? options.sort.slice(1) : options.sort;
        var sorting = { input: function (m) { return m.pricing.input; }, output: function (m) { return m.pricing.output; }, cached_input: function (m) { return m.pricing.cached_input; }, cache_write: function (m) { return m.pricing.cache_write; }, context_length: function (m) { return m.context_length; }, max_output_tokens: function (m) { return m.limits.max_output_tokens; }, name: function (m) { return m.name; } };
        if (!sorting[key]) throw error("INVALID_ARGUMENT", "Unknown sort field: " + key);
        models.sort(function (a, b) { var x = sorting[key](a), y = sorting[key](b); return x === null ? (y === null ? 0 : 1) : y === null ? -1 : (typeof x === "number" ? x - y : x.localeCompare(y)) * (desc ? -1 : 1); });
      }
      var matches = models.length;
      if (options.limit !== undefined) models = models.slice(0, number(options.limit, "limit", true));
      return { api_version: envelope.api_version, meta: Object.assign({}, envelope.meta, { count: models.length, matched_count: matches, total_count: envelope.data.length }), data: models };
    }
    return { baseUrl: base.href, getIndex: function () { return get("index.json"); },
      getOpenAPI: function () { return get("openapi.json", true); },
      listVendors: function () { return get("vendors.json"); },
      getVendor: function (slug) { return get("vendors/" + safeId(slug) + ".json"); },
      getModel: function (id) { return get("models/" + safeId(id) + ".json"); },
      listModels: async function (options) { return query(await get("models.json"), options); },
      estimate: async function (id, usage, options) { return estimate((await get("models/" + safeId(id) + ".json")).data, usage, options); } };
  }
  return { createClient: createClient, estimate: estimate };
});
