/* Authored SDK factory; generated standalone entry: assets/client.js. */
(function (lifecycle) {
  "use strict";
  var PRICE = ["input", "output", "cached_input", "cache_write"];
  var CACHE = ["implicit_read", "explicit_read", "explicit_write", "explicit_write_1h", "explicit_write_12h", "storage_per_1M_tokens_hour"];
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
  function modelAt(model, at) {
    if (["USD", "CNY"].indexOf(model.currency) < 0) throw error("INVALID_DATA", "Missing or unsupported currency");
    if (!lifecycle) throw error("INVALID_DATA", "Invalid generated SDK lifecycle bundle");
    var decision = lifecycle.availability(model, at.toISOString());
    if (!decision.estimable) throw error(decision.status === "history_unknown" ? "HISTORICAL_PRICE_UNAVAILABLE" : "MODEL_RETIRED", decision.status === "history_unknown" ? "Retirement instant is unknown; observation time is not a historical availability boundary" : "Model retired at this instant; routing aliases do not prove the old entity is available");
    return decision;
  }
  // Observation is evidence, not the vendor's effective date. An explicit valid_from
  // may authorize older history; otherwise only instants from observed_at are known.
  function evidenceAt(e, at, rawAt) {
    var start = Date.parse(e.valid_from || e.observed_at), end = e.valid_until ? Date.parse(e.valid_until) : Infinity;
    if (!Number.isFinite(start) || (e.valid_until && !Number.isFinite(end)) || start >= end)
      throw error("INVALID_DATA", "Invalid price evidence interval");
    if (rawAt && rawAt.length === 10) throw error("TIME_REQUIRED", "Field evidence requires an explicit instant with timezone");
    if (at.getTime() < start) throw error("HISTORICAL_PRICE_UNAVAILABLE", "Requested field has no verified history before " + (e.valid_from || e.observed_at));
    if (at.getTime() >= end) throw error("PRICE_EXPIRED", "Field evidence interval ended at " + e.valid_until);
  }
  function priceEvidence(model, at, rawAt, inputTokens, usedFields, warnings) {
    (model.price_observations || []).forEach(function (e) {
      if (e.input_tokens_gt !== null && inputTokens <= e.input_tokens_gt) return;
      if (e.fields.indexOf("*") < 0 && !e.fields.some(function (k) { return usedFields.indexOf(k) >= 0; })) return;
      evidenceAt(e, at, rawAt);
      warnings.push("Selected fields verified at " + e.observed_at + "; observed_at is not an official effective date.");
    });
  }
  var TOKEN_USAGE = { textInputTokens: "text_input", textCachedInputTokens: "text_cached_input", textOutputTokens: "text_output",
    imageInputTokens: "image_input", imageCachedInputTokens: "image_cached_input", imageOutputTokens: "image_output",
    videoInputTokens: "video_input", videoOutputTokens: "video_output", audioInputTokens: "audio_input" };
  // Image / video models: per-image, per-second and per-modality token prices from model.media_pricing.
  function estimateMedia(model, usage, options) {
    usage = usage || {}; options = options || {};
    if (!model || (model.modality !== "image" && model.modality !== "video") || !model.media_pricing)
      throw error("UNSUPPORTED_MODALITY", "estimateMedia needs an image or video model; use estimate() for text models");
    var allowedUsage = ["images", "size", "quality", "seconds", "resolution", "audio", "inputImages", "inputVideoSeconds"].concat(Object.keys(TOKEN_USAGE));
    Object.keys(usage).forEach(function (k) { if (allowedUsage.indexOf(k) < 0) throw error("INVALID_ARGUMENT", "Unknown usage field: " + k); });
    Object.keys(options).forEach(function (k) { if (["tier", "at"].indexOf(k) < 0) throw error("INVALID_ARGUMENT", "Unknown estimate option: " + k); });
    var quoteAt = date(options.at === undefined ? new Date().toISOString() : options.at);
    if (model.lifecycle && model.lifecycle.retired_at && options.at && options.at.length === 10)
      throw error("TIME_REQUIRED", "Lifecycle boundary needs an explicit instant for historical estimation");
    var available = modelAt(model, quoteAt);
    if (model.last_updated && quoteAt.toISOString().slice(0, 10) < model.last_updated)
      throw error("HISTORICAL_PRICE_UNAVAILABLE", "This snapshot does not contain earlier media prices");
    var mp = model.media_pricing, tier = options.tier === undefined ? "standard" : options.tier;
    if (tier !== "standard" && tier !== "batch") throw error("INVALID_ARGUMENT", "tier must be standard or batch");
    function count(k, integer) { return usage[k] === undefined ? 0 : number(usage[k], k, integer); }
    function unavailable(what) { return error("PRICE_UNAVAILABLE", what + " has no verified price for tier " + tier); }
    var parts = {}, units = {}, warnings = [];
    priceEvidence(model, quoteAt, options.at, 0, ["*"], warnings);
    function add(key, amount, rate, unit, what) {
      if (!amount) return;
      if (rate === null || rate === undefined) throw unavailable(what);
      parts[key] = amount * rate; units[key] = { rate: rate, unit: unit };
    }
    var images = count("images", true), seconds = count("seconds");
    if (images && model.modality !== "image") throw error("INVALID_ARGUMENT", "images applies to image models only");
    if (seconds && model.modality !== "video") throw error("INVALID_ARGUMENT", "seconds applies to video models only");
    var row = null;
    if (images) {
      if (typeof usage.size !== "string") throw error("INVALID_ARGUMENT", "size is required with images");
      var rows = mp.image_prices.filter(function (e) { return e.tier === tier && e.size === usage.size.toLowerCase(); });
      if (usage.quality !== undefined) rows = rows.filter(function (e) { return e.quality === usage.quality; });
      else if (rows.length > 1) throw error("INVALID_ARGUMENT", "quality is required for this size: " + rows.map(function (e) { return e.quality; }).join(", "));
      if (!rows.length) rows = mp.image_prices.filter(function (e) { return e.tier === tier && e.size === "any" && (usage.quality === undefined || e.quality === usage.quality); });
      if (!rows.length) throw unavailable("image size " + usage.size + (usage.quality ? "/" + usage.quality : ""));
      add("images", images, rows[0].price, "per_image", "image size " + usage.size);
      if (rows[0].basis !== "listed") warnings.push("Per-image price is the vendor's token-cost equivalent (" + rows[0].basis + ").");
    }
    if (seconds || count("inputVideoSeconds")) {
      if (typeof usage.resolution !== "string") throw error("INVALID_ARGUMENT", "resolution is required with seconds / inputVideoSeconds");
      var cands = mp.video_prices.filter(function (e) { return e.tier === tier && e.resolution === usage.resolution.toLowerCase(); });
      if (usage.audio !== undefined) {
        if (["with_audio", "without_audio"].indexOf(usage.audio) < 0) throw error("INVALID_ARGUMENT", "audio must be with_audio or without_audio");
        row = cands.find(function (e) { return e.audio === usage.audio; }) || cands.find(function (e) { return e.audio === "any"; });
      } else {
        if (cands.length > 1) throw error("INVALID_ARGUMENT", "audio is required for this resolution (with_audio or without_audio)");
        row = cands[0];
      }
      if (!row) throw unavailable("video resolution " + usage.resolution);
      add("video_seconds", seconds, row.price_per_second, "per_second", "video resolution " + usage.resolution);
      add("input_video_seconds", count("inputVideoSeconds"), row.input_video_price_per_second, "per_second", "input video at " + usage.resolution);
      if (row.basis === "approximate") warnings.push("Per-second price is approximate (vendor publishes only an approximate figure).");
    }
    var inputImages = count("inputImages", true);
    var allowance = mp.input_image_allowance, billableImages = inputImages;
    if (allowance) {
      if (tier !== "standard" && mp.batch_supported !== true) throw unavailable("input-image allowance under undocumented Batch");
      if (allowance.scope !== "per_task" || !Number.isSafeInteger(allowance.free_quantity) || allowance.free_quantity < 0)
        throw error("INVALID_DATA", "Invalid per-task input image allowance");
      billableImages = Math.max(0, inputImages - allowance.free_quantity);
      warnings.push("One estimateMedia call represents one task; split separate tasks. First " + allowance.free_quantity + " input images per task are included.");
    }
    add("input_images", billableImages, tier === "batch" && mp.input_image_price_batch !== null ? mp.input_image_price_batch : mp.input_image_price, "per_image", "input image");
    Object.keys(TOKEN_USAGE).forEach(function (k) {
      var n = count(k, true); if (!n) return;
      var tp = mp.token_pricing && mp.token_pricing[tier];
      add(TOKEN_USAGE[k], n, tp ? (tp[TOKEN_USAGE[k]] === null ? null : tp[TOKEN_USAGE[k]] / 1e6) : null, "per_token", TOKEN_USAGE[k] + " tokens");
    });
    if (mp.promotion) warnings.push("Prices are list prices; vendor promotion not applied: " + mp.promotion.note);
    var total = Object.keys(parts).reduce(function (n, k) { return n + parts[k]; }, 0);
    if (!Number.isFinite(total)) throw error("INVALID_ARGUMENT", "Usage is too large to estimate the total");
    return { model_id: model.id, modality: model.modality, currency: model.currency, unit: model.unit, region: model.billing.region, channel: model.billing.channel, availability: available, total: total, breakdown: parts, unit_prices: units,
      tier: tier, price_basis: model.price_basis, billing: model.billing, warnings: warnings,
      billing_quantities: { input_images: {total: inputImages, included: inputImages - billableImages, billable: billableImages, scope: allowance ? "per_task" : "all_images"} },
      excluded_costs: ["server_tools", "grounding", "taxes", "account_free_quota", "unrecorded_multimodal_rates"] };
  }
  function estimate(model, usage, options) {
    if (model && model.modality && model.modality !== "text")
      throw error("UNSUPPORTED_MODALITY", "estimate() is for text models; use estimateMedia() for " + model.modality + " models");
    usage = usage || {}; options = options || {};
    var allowedUsage = ["inputTokens", "outputTokens", "cachedInputTokens", "cacheWriteTokens", "cacheWrite1hTokens", "cacheWrite12hTokens", "storageTokenHours"];
    Object.keys(usage).forEach(function (k) { if (allowedUsage.indexOf(k) < 0) throw error("INVALID_ARGUMENT", "Unknown usage field: " + k); });
    var allowedOptions = ["at", "serviceTier", "dataResidency", "cacheType", "isChineseHoliday"];
    Object.keys(options).forEach(function (k) { if (allowedOptions.indexOf(k) < 0) throw error("INVALID_ARGUMENT", "Unknown estimate option: " + k); });
    if (!Object.prototype.hasOwnProperty.call(usage, "inputTokens") || !Object.prototype.hasOwnProperty.call(usage, "outputTokens"))
      throw error("INVALID_ARGUMENT", "inputTokens and outputTokens are required");
    var counts = {};
    allowedUsage.forEach(function (k) { counts[k] = number(usage[k] === undefined ? 0 : usage[k], k, k !== "storageTokenHours"); });
    if (counts.cachedInputTokens + counts.cacheWriteTokens + counts.cacheWrite1hTokens + counts.cacheWrite12hTokens > counts.inputTokens)
      throw error("INVALID_ARGUMENT", "inputTokens includes cache reads and writes; their sum cannot exceed inputTokens");
    if (options.dataResidency !== undefined && typeof options.dataResidency !== "boolean")
      throw error("INVALID_ARGUMENT", "dataResidency must be boolean");
    if (options.isChineseHoliday !== undefined && typeof options.isChineseHoliday !== "boolean")
      throw error("INVALID_ARGUMENT", "isChineseHoliday must be boolean");
    if (options.cacheType !== undefined && ["implicit", "explicit"].indexOf(options.cacheType) < 0)
      throw error("INVALID_ARGUMENT", "cacheType must be implicit or explicit");
    var at = date(options.at === undefined ? new Date().toISOString() : options.at), day = at.toISOString().slice(0, 10), warnings = [];
    if (model.lifecycle && model.lifecycle.retired_at && options.at && options.at.length === 10)
      throw error("TIME_REQUIRED", "Lifecycle boundary needs an explicit instant for historical estimation");
    var available = modelAt(model, at);
    if (available.status === "pending_confirmation") warnings.push("Official lifecycle date/time is unresolved; availability is not confirmed: " + available.reason);
    if (day < model.last_updated) throw error("HISTORICAL_PRICE_UNAVAILABLE", "This snapshot does not contain prices before " + model.last_updated);
    if (model.limits.max_output_tokens !== null && counts.outputTokens > model.limits.max_output_tokens)
      throw error("LIMIT_EXCEEDED", "outputTokens exceeds the documented maximum");
    if (model.context_length !== null && counts.inputTokens > model.context_length)
      throw error("LIMIT_EXCEEDED", "inputTokens exceeds the recorded context window");
    if (day > model.last_updated) warnings.push("Base prices snapshot: " + model.last_updated + "; selected fields may have separate observation timestamps. Announced schedules apply; later unannounced changes are not known.");
    var cap = model.estimation_limits;
    if (cap && (counts.inputTokens > cap.max_input_tokens || counts.outputTokens > cap.max_output_tokens))
      throw error("LIMIT_EXCEEDED", "Usage exceeds the verified conservative estimation scope: " + cap.note);
    var prices = Object.assign({}, model.pricing), cache = Object.assign({}, model.cache_pricing), tier = null, period = "standard";
    (model.pricing_tiers || []).forEach(function (t) {
      if (counts.inputTokens > t.input_tokens_gt && (t.input_tokens_lte === null || counts.inputTokens <= t.input_tokens_lte)) {
        if (tier) throw error("INVALID_DATA", "Overlapping price tiers");
        tier = t;
      }
    });
    var used = [];
    if (counts.inputTokens - counts.cachedInputTokens - counts.cacheWriteTokens - counts.cacheWrite1hTokens - counts.cacheWrite12hTokens) used.push("input");
    if (counts.outputTokens) used.push("output");
    if (counts.cachedInputTokens) used.push("cached_input", (options.cacheType || model.billing.cached_input_type) + "_read");
    if (counts.cacheWriteTokens) used.push("cache_write", "explicit_write");
    if (counts.cacheWrite1hTokens) used.push("explicit_write_1h");
    if (counts.cacheWrite12hTokens) used.push("explicit_write_12h");
    if (counts.storageTokenHours) used.push("storage_per_1M_tokens_hour");
    priceEvidence(model, at, options.at, counts.inputTokens, used, warnings);
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
      if (e.effective_until_precision === "date" && e.effective_until && at.getTime() >= Date.parse(e.effective_until + "T00:00:00Z") - 14 * 3600000)
        throw error("PRICE_BOUNDARY_UNCONFIRMED", "Date-only promotional cutoff needs manual confirmation; no exact ending instant or post-promotion price is inferred");
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
      var activeMultiplier = s.multiplier;
      if ((s.multiplier_schedule || []).length && options.at && options.at.length === 10)
        throw error("TIME_REQUIRED", "Scheduled service tier requires an explicit instant with timezone");
      (s.multiplier_schedule || []).forEach(function (e) {
        if (!Number.isFinite(Date.parse(e.effective_from))) throw error("INVALID_DATA", "Invalid service schedule instant");
        if (at.getTime() >= Date.parse(e.effective_from)) activeMultiplier = e.multiplier;
      });
      var ratio = activeMultiplier / s.multiplier;
      if (!Number.isFinite(ratio) || ratio <= 0) throw error("INVALID_DATA", "Invalid service multiplier");
      if (s.status_observation && at.getTime() >= Date.parse(s.status_observation.observed_at))
        warnings.push("Service tier " + s.name + " is " + s.status_observation.status + " (observed " + s.status_observation.observed_at + "); model availability is unchanged.");
      PRICE.forEach(function (k) {
        var explicit = Object.prototype.hasOwnProperty.call(s.pricing, k);
        if (explicit) { prices[k] = s.pricing[k]; unknown[k] = prices[k] === null; }
        else if (s.multipliers[k] === null) unknown[k] = true;
        else if (prices[k] !== null) prices[k] *= s.multipliers[k] * ratio;
      });
      CACHE.forEach(function (k) {
        if (s.multipliers[k] === null) unknown[k] = true;
        else if (cache[k] !== null) cache[k] *= s.multipliers[k] * ratio;
      });
    }
    if (svc) applyService(svc);
    if (options.dataResidency) {
      var region = services.find(function (s) { return s.name === "data_residency"; });
      if (!region) throw error("UNSUPPORTED_SERVICE_TIER", "No documented data residency surcharge");
      applyService(region);
    }
    var offer = model.token_offer;
    if (offer) {
      if (options.at && options.at.length === 10) throw error("TIME_REQUIRED", "Offer needs an exact timestamp with timezone");
      if (at.getTime() < Date.parse(offer.observed_at)) throw error("HISTORICAL_PRICE_UNAVAILABLE", "Offer start is unknown; no historic estimate before observed_at");
      if (at.getTime() <= Date.parse(offer.valid_until)) {
        offer.fields.forEach(function (k) { if (prices[k] !== null) prices[k] *= offer.multiplier; });
        period = "promotion";
      }
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
    cost("input", counts.inputTokens - counts.cachedInputTokens - counts.cacheWriteTokens - counts.cacheWrite1hTokens - counts.cacheWrite12hTokens, prices.input, "input");
    cost("output", counts.outputTokens, prices.output, "output");
    cost("cached_input", counts.cachedInputTokens, readPrice, readKey);
    cost("cache_write", counts.cacheWriteTokens, prices.cache_write, "cache_write");
    cost("cache_write_1h", counts.cacheWrite1hTokens, cache.explicit_write_1h, "explicit_write_1h");
    cost("cache_write_12h", counts.cacheWrite12hTokens, cache.explicit_write_12h, "explicit_write_12h");
    cost("storage", counts.storageTokenHours, cache.storage_per_1M_tokens_hour, "storage_per_1M_tokens_hour");
    var reference = model.price_basis.type === "reference";
    if (reference) warnings.push("Reference estimate using " + model.price_basis.reference_model_id + "; this is not the subscription bill.");
    var total = Object.keys(parts).reduce(function (n, k) { return n + parts[k]; }, 0);
    if (!Number.isFinite(total)) throw error("INVALID_ARGUMENT", "Usage is too large to estimate the total");
    return { model_id: model.id, currency: model.currency, unit: model.unit, region: model.billing.region, channel: model.billing.channel, availability: available, total: total,
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
        if (!data || data.api_version !== (/\/v2\/$/.test(base.pathname) ? "v2" : "v1") || !data.meta || data.data === undefined)
          throw error("INVALID_RESPONSE", "Unexpected response envelope for " + path);
        return data;
      } catch (e) {
        if (controller.signal.aborted) throw error("TIMEOUT", "Request timed out for " + path);
        if (e.code) throw e;
        throw error("NETWORK_ERROR", "Cannot fetch " + path + ": " + e.message);
      } finally { clearTimeout(timer); }
    }
    function safeId(id) { if (typeof id !== "string" || !/^[a-z0-9][a-z0-9.\-]*$/.test(id)) throw error("INVALID_ARGUMENT", "Use a model ID or vendor slug from index.json"); return id; }
    // Lowest listed standard per-image / per-second price (null for text models or when unverified).
    function mediaPrice(m) {
      var mp = m.media_pricing; if (!mp) return null;
      var v = mp.image_prices.concat(mp.video_prices).filter(function (e) { return e.tier === "standard"; })
        .map(function (e) { return e.price === undefined ? e.price_per_second : e.price; }).filter(function (x) { return x !== null; });
      return v.length ? Math.min.apply(null, v) : null;
    }
    function query(envelope, options) {
      options = options || {};
      var keys = ["vendor", "q", "sort", "limit", "priceBasis", "modality", "currency"];
      Object.keys(options).forEach(function (k) { if (keys.indexOf(k) < 0) throw error("INVALID_ARGUMENT", "Unknown query option: " + k); });
      if (options.currency !== undefined && ["USD", "CNY"].indexOf(options.currency) < 0) throw error("INVALID_ARGUMENT", "currency must be USD or CNY");
      if (options.vendor !== undefined) safeId(options.vendor);
      if (options.q !== undefined && typeof options.q !== "string") throw error("INVALID_ARGUMENT", "q must be a string");
      if (options.sort !== undefined && typeof options.sort !== "string") throw error("INVALID_ARGUMENT", "sort must be a string");
      if (options.modality !== undefined && ["text", "image", "video"].indexOf(options.modality) < 0) throw error("INVALID_ARGUMENT", "modality must be text, image or video");
      if (options.priceBasis !== undefined && ["official", "reference"].indexOf(options.priceBasis) < 0) throw error("INVALID_ARGUMENT", "priceBasis must be official or reference");
      var models = envelope.data.filter(function (m) {
        if (!lifecycle.availability(m, new Date().toISOString()).estimable) return false;
        var terms = (options.q || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
        var text = [m.id, m.name, m.vendor, m.vendor_name, m.modality, m.notes || ""].join(" ").toLowerCase();
        return (!options.currency || m.currency === options.currency) && (!options.vendor || m.vendor === options.vendor) && (!options.modality || m.modality === options.modality) && (!options.priceBasis || m.price_basis.type === options.priceBasis) && terms.every(function (t) { return text.indexOf(t) >= 0; });
      });
      if (options.sort) {
        var desc = options.sort[0] === "-", key = desc ? options.sort.slice(1) : options.sort;
        var sorting = { input: function (m) { return m.pricing.input; }, output: function (m) { return m.pricing.output; }, cached_input: function (m) { return m.pricing.cached_input; }, cache_write: function (m) { return m.pricing.cache_write; }, context_length: function (m) { return m.context_length; }, max_output_tokens: function (m) { return m.limits.max_output_tokens; }, name: function (m) { return m.name; }, media_price: mediaPrice };
        if (["input", "output", "cached_input", "cache_write", "media_price"].indexOf(key) >= 0 && new Set(models.map(function (m) { return m.currency; })).size > 1)
          throw error("CURRENCY_MISMATCH", "Price ranking needs a single explicit currency filter; no implicit FX");
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
      listModalities: function () { return get("modalities.json"); },
      getModality: function (name) { return get("modalities/" + safeId(name) + ".json"); },
      getVendor: function (slug) { return get("vendors/" + safeId(slug) + ".json"); },
      getModel: function (id) { return get("models/" + safeId(id) + ".json"); },
      listModels: async function (options) { return query(await get("models.json"), options); },
      estimate: async function (id, usage, options) { return estimate((await get("models/" + safeId(id) + ".json")).data, usage, options); },
      estimateMedia: async function (id, usage, options) { return estimateMedia((await get("models/" + safeId(id) + ".json")).data, usage, options); } };
  }
  return { createClient: createClient, estimate: estimate, estimateMedia: estimateMedia };
})
