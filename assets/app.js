(function () {
  "use strict";
  var DATA_URL = "data/prices.json";
  var PRICE_KEYS = ["input", "output", "cached_input", "cache_write"];
  var esc = LP.esc;
  var state = { models: [], vendors: [], vendor: "", q: "", sortKey: "_i", sortDir: 1, open: {}, modality: "text" };
  var MODS = ["text", "image", "video"];
  var MODLABEL = { text: "文本", image: "图像", video: "视频" };
  var TOKLABEL = { text_input: "文本输入", text_cached_input: "文本缓存输入", text_output: "文本输出", image_input: "图像输入", image_cached_input: "图像缓存输入",
    image_output: "图像输出", video_input: "视频输入", video_output: "视频输出", audio_input: "音频输入" };
  var AUDIO = { with_audio: "含音频", without_audio: "无音频", any: "" };
  var BASIS = { token_equivalent: "按 token 折算", approximate: "官方近似值" };
  var $ = function (id) { return document.getElementById(id); };

  function fmtNum(n) {
    // up to 4 decimals, trim trailing zeros, keep at least 2
    var s = Number(n).toFixed(4).replace(/0+$/, "");
    if (/\.$/.test(s)) s += "00"; else if (/\.\d$/.test(s)) s += "0";
    return s;
  }
  function money(v) { return '<span class="cur">$</span>' + fmtNum(v); }
  function isNum(v) { return typeof v === "number" && isFinite(v); }
  function priceCell(v, best) {
    if (v === null || v === undefined) return '<span class="tbd" title="未能从官方来源核实">待核实</span>';
    if (v === "n/a") return '<span class="na" title="官方定价页没有该项">未列出</span>';
    return '<span class="price">' + money(v) + "</span>" + (best ? '<span class="best-tag">最低</span>' : "");
  }
  function peakCell(m) {
    var parts = [];
    if (m.peak_note) {
      parts.push('<div class="pn" title="' + esc(m.peak_note) + '">' + esc(m.peak_note) + "</div>" +
        (m.peak_note.length > 54 ? '<button type="button" class="more">展开</button>' : ""));
    }
    if (m.offpeak) {
      var o = m.offpeak, b = [];
      if (o.input != null) b.push('<span class="op">输入 <span>' + money(o.input) + "</span></span>");
      if (o.output != null) b.push('<span class="op">输出 <span>' + money(o.output) + "</span></span>");
      if (o.cached_input != null) b.push('<span class="op">缓存 <span>' + money(o.cached_input) + "</span></span>");
      parts.push('<div class="offpeak"><span class="op" style="background:none;padding-left:0;font-weight:600">闲时价</span>' + b.join("") + "</div>");
    }
    return parts.length ? '<div class="peak">' + parts.join("") + "</div>" : '<span class="na">—</span>';
  }
  function effortCell(m) {
    var r = m.reasoning_effort;
    if (!r || r.supported === null || r.supported === undefined)
      return '<span class="tbd" title="官方文档未明确，未做推测">待核实</span>';
    var out = "";
    if (r.supported === false) {
      out = '<span class="lv lv-off" title="官方文档：无可调推理强度">不可调</span>';
    } else if (!r.levels) {
      out = '<span class="tbd" title="档位待核实">档位待核实</span>';
    } else {
      out = '<div class="lvs">' + r.levels.map(function (l) {
        var d = l === r.default;
        return '<span class="lv' + (d ? " lv-def" : "") + (l === "none" ? " lv-none" : "") + '"' + (d ? ' title="默认档"' : "") + ">" + esc(l) + "</span>";
      }).join("") + "</div>";
    }
    var meta = [];
    if (r.default) meta.push("默认 <b>" + esc(r.default) + "</b>");
    else if (r.supported && r.levels) meta.push('默认 <span class="tbd">待核实</span>');
    if (r.can_disable === true) meta.push("可关闭");
    else if (r.can_disable === false) meta.push("不可关闭");
    else if (r.supported !== false) meta.push("关闭方式未说明");
    if (r.supported === false && r.can_disable === false) meta = ["思考恒开，不可关闭"];
    var note = r.note ? '<details class="note"><summary>说明</summary><p>' + esc(r.note) + "</p>" +
      (r.sources || []).map(function (u) { return '<a class="rsrc" href="' + esc(u) + '" target="_blank" rel="noopener noreferrer">' + esc(u.replace(/^https?:\/\//, "")) + "</a>"; }).join("") + "</details>" : "";
    return '<div class="re">' + out + (meta.length ? '<div class="re-meta">' + meta.join(" · ") + "</div>" : "") + note + "</div>";
  }

  // ---- structured specs: tiers / service tiers / cache / sources (same data as api/v1/models/<id>.json) ----
  var SVCLABEL = { batch: "Batch", flex: "Flex", fast: "Fast", priority: "Priority", ultrafast: "Ultrafast", data_residency: "数据驻留加价" };
  function fmtTok(n) {
    if (!isNum(n)) return null;
    var v;
    if (n >= 1e6) { v = (n / 1e6).toFixed(3).replace(/\.?0+$/, ""); return v + "M"; }
    if (n >= 1e3) { v = (n / 1e3).toFixed(1).replace(/\.0$/, ""); return v + "K"; }
    return String(n);
  }
  function tokSpan(n, miss) {
    if (!isNum(n)) return miss === false ? "" : '<span class="tbd" title="官方未明确，未做推测">待核实</span>';
    return '<span class="tokv" title="' + n.toLocaleString("en-US") + ' tokens">' + fmtTok(n) + "</span>";
  }
  function outCell(m) {
    var L = m.limits || {};
    if (L.max_output_tokens === "n/a") return '<span class="tokv" title="' + esc(L.note || "") + '">无独立上限</span>';
    return tokSpan(L.max_output_tokens);
  }
  function ctxCell(m) {
    var L = m.limits || {}, n = isNum(L.context_length) ? L.context_length : m.context_tokens;
    return tokSpan(n);
  }
  function tierCond(t) {
    var a = isNum(t.input_tokens_gt) ? (t.input_tokens_gt + 1).toLocaleString("en-US") : null;
    var b = isNum(t.input_tokens_lte) ? t.input_tokens_lte.toLocaleString("en-US") : null;
    if (a && b) return a + " – " + b + " 输入";
    if (a) return "≥ " + a + " 输入";
    return esc(t.condition);
  }
  function pcell(v) { return isNum(v) ? '<span class="price">' + money(v) + "</span>" : '<span class="na" title="官方未列出该档价格">—</span>'; }
  function kv(k, v) { return '<div class="kv"><span class="k">' + k + '</span><span class="v">' + v + "</span></div>"; }
  function srcLinks(arr) {
    return (arr || []).map(function (u) { return '<a class="rsrc" href="' + esc(u) + '" target="_blank" rel="noopener noreferrer">' + esc(u.replace(/^https?:\/\//, "")) + "</a>"; }).join("");
  }
  function block(title, body, wide) { return '<section class="dblock' + (wide ? " wide" : "") + '"><h4>' + title + "</h4>" + body + "</section>"; }
  function detailHtml(m) {
    var out = [], x, L = m.limits || {};
    // 1 tiers
    var tiers = m.pricing_tiers || [];
    if (tiers.length) {
      x = '<table class="mini"><thead><tr><th>输入长度</th><th>输入</th><th>输出</th><th>缓存读</th><th>缓存写</th></tr></thead><tbody>' + tiers.map(function (t) {
        return "<tr><td>" + tierCond(t) + "</td><td>" + pcell(t.input) + "</td><td>" + pcell(t.output) + "</td><td>" + pcell(t.cached_input) + "</td><td>" + pcell(t.cache_write) + "</td></tr>";
      }).join("") + "</tbody></table>" +
        tiers.filter(function (t) { return t.note; }).map(function (t) { return '<p class="dnote">' + esc(t.note) + "</p>"; }).join("");
    } else x = '<span class="na">无分档价（或官方未列出）</span>';
    out.push(block("长上下文分档价", x, tiers.length > 0));
    // 2 service tiers
    var sv = m.service_tiers || [];
    x = sv.length ? sv.map(function (t) {
      return '<div class="svc" title="' + esc(t.note || "") + '"><span class="lv lv-def">' + esc(SVCLABEL[t.name] || t.name) + '</span><b>×' + t.multiplier + "</b></div>";
    }).join("") + sv.map(function (t) { return t.note ? '<p class="dnote"><b>' + esc(SVCLABEL[t.name] || t.name) + "：</b>" + esc(t.note) + "</p>" : ""; }).join("")
      : '<span class="na">官方未列出服务档倍率</span>';
    if (sv.length) {
      x += '<p class="dnote">上述倍率用于输入与输出；缓存和存储按各费用项规则计费。</p>';
      sv.forEach(function (t) {
        var rules = [];
        ["cached_input", "cache_write"].forEach(function (k) {
          if (m[k] === "n/a" && !Object.prototype.hasOwnProperty.call(t.pricing || {}, k)) return;
          if (t.pricing && Object.prototype.hasOwnProperty.call(t.pricing, k))
            rules.push((k === "cached_input" ? "缓存读单价 " : "缓存写单价 ") + pcell(t.pricing[k]));
          else if (t.multipliers && t.multipliers[k] !== t.multiplier)
            rules.push((k === "cached_input" ? "缓存读 " : "缓存写 ") + (t.multipliers[k] === null ? "倍率待核实" : "×" + t.multipliers[k]));
        });
        if (m.cache_pricing.storage_per_1M_tokens_hour !== null)
          rules.push("存储费 " + (t.multipliers.storage_per_1M_tokens_hour === null ? "倍率待核实" : "×" + t.multipliers.storage_per_1M_tokens_hour));
        if (rules.length) x += '<p class="dnote"><b>' + esc(SVCLABEL[t.name] || t.name) + "：</b>" + rules.join(" · ") + "</p>";
      });
    }
    out.push(block("服务档倍率", x));
    // 3 cache
    var C = m.cache_pricing || {};
    x = "";
    if (isNum(C.implicit_read)) x += kv("隐式缓存命中", money(C.implicit_read));
    if (isNum(C.explicit_read)) x += kv("显式缓存命中", money(C.explicit_read));
    if (isNum(C.explicit_write)) x += kv("缓存写入 / 创建", money(C.explicit_write));
    if (isNum(C.explicit_write_1h)) x += kv("缓存写入（1 小时 TTL）", money(C.explicit_write_1h));
    if (isNum(C.explicit_write_12h)) x += kv("缓存写入（12 小时 TTL）", money(C.explicit_write_12h) +
      (tiers.filter(function (t) { return t.cache_pricing && isNum(t.cache_pricing.explicit_write_12h); }).map(function (t) { return "；" + tierCond(t) + " " + money(t.cache_pricing.explicit_write_12h); }).join("")));
    if (isNum(C.storage_per_1M_tokens_hour)) x += kv("缓存存储 / 百万 token / 小时", C.storage_per_1M_tokens_hour === 0 ? "限时免费" : money(C.storage_per_1M_tokens_hour));
    if (C.note) x += '<p class="dnote">' + esc(C.note) + "</p>";
    out.push(block("缓存价细分", x || '<span class="na">官方未列细分缓存价</span>'));
    // 4 provenance and billing (reference prices remain visible).
    var basis = m.price_basis || {}, billing = m.billing || {};
    x = '<p class="dnote"><b>' + (basis.type === "reference" ? "用户确认参照价" : "官方价格") + '</b>：' + esc(basis.note || "") + '</p>';
    if (basis.reference_model_id) x += '<p class="dnote">参照模型：<a href="api/v1/models/' + encodeURIComponent(basis.reference_model_id) + '.json">' + esc(basis.reference_model_id) + '</a></p>';
    x += '<p class="dnote">计费渠道：' + (billing.channel === "subscription" ? "订阅" : "按量付费") + (billing.region ? " · 地区：" + esc(billing.region) : "") +
      ' · 主价格口径：' + esc(billing.price_type || "current") + ' · 缓存类型：' + esc(billing.cached_input_type || "unspecified") + '</p>';
    out.push(block("价格依据与计费口径", x, true));
    // 5 sources
    var urls = [];
    var structuredSources = [];
    sv.concat(m.price_schedule || [], m.off_peak_schedule ? [m.off_peak_schedule] : []).forEach(function (rule) {
      structuredSources = structuredSources.concat(rule.sources || []);
    });
    [m.source_url].concat(m.extra_sources || [], L.sources || [], basis.sources || [], structuredSources).forEach(function (u) { if (u && urls.indexOf(u) === -1) urls.push(u); });
    x = srcLinks(urls);
    if (L.note) x += '<p class="dnote"><b>上限口径：</b>' + esc(L.note) + "</p>";
    (m.price_schedule || []).forEach(function (e) {
      var when = e.effective_from ? "自 " + esc(e.effective_from) : (e.effective_until ? "至 " + esc(e.effective_until) : "时间未明确");
      x += '<p class="dnote"><b>' + (e.kind === "promotion" ? "促销" : "价格调整") + "（" + when + "）：</b>" + esc(e.note || "") + "</p>";
    });
    x += '<p class="dnote">更新于 ' + esc(m.last_updated || "") + ' · <a href="api/v1/models/' + encodeURIComponent(m.model_id) + '.json">JSON</a></p>';
    out.push(block("来源", x, true));
    return '<div class="detail">' + out.join("") + "</div>";
  }
  function detailRow(m, slug) {
    return '<tr class="detail-row v-' + slug + '" data-for="' + esc(m.model_id) + '"><td colspan="9">' + detailHtml(m) + "</td></tr>";
  }
  function row(m, best) {
    var slug = LP.slug(m.vendor);
    var notes = (m.price_basis && m.price_basis.type === "reference" ? '<span class="tbd" title="' + esc(m.price_basis.note) + '">参照价 · ' + esc(m.price_basis.reference_model_id) + '</span>' : "") +
      (m.notes ? '<details class="note"><summary>备注</summary><p>' + esc(m.notes) + "</p></details>" : "");
    var idBtn = m.model_id ? '<button type="button" class="model-id" data-copy="' + esc(m.model_id) + '" title="点击复制模型 ID">' + esc(m.model_id) + "</button>" : "";
    var det = '<button type="button" class="detail-btn" data-id="' + esc(m.model_id) + '" aria-expanded="' + (state.open[m.model_id] ? "true" : "false") + '">详情<span class="chev" aria-hidden="true"></span></button>';
    var cells = [
      ["c-model", "厂商 / 模型", '<span class="badge">' + esc(m.vendor) + '</span><div class="model-name">' + esc(m.model) + "</div>" + idBtn + notes + '<div class="model-act">' + det + "</div>"],
      ["num c-in", "输入", priceCell(m.input, best.input === m.input)],
      ["num c-out", "输出", priceCell(m.output, best.output === m.output)],
      ["num c-cr", "缓存输入", priceCell(m.cached_input, best.cached_input === m.cached_input)],
      ["num c-cw", "缓存写入", priceCell(m.cache_write, best.cache_write === m.cache_write)],
      ["c-peak" + (m.peak_note || m.offpeak ? "" : " empty-peak"), "高峰 / 闲时", peakCell(m)],
      ["num c-ctx", "最大上下文", ctxCell(m)],
      ["num c-lim", "最大输出", outCell(m)],
      ["c-re", "推理强度", effortCell(m)]
    ];
    var open = m.model_id && state.open[m.model_id];
    return '<tr class="v-' + slug + (open ? " has-detail" : "") + '">' + cells.map(function (c) {
      return '<td class="' + c[0] + '" data-label="' + c[1] + '">' + c[2] + "</td>";
    }).join("") + "</tr>" + (open ? detailRow(m, slug) : "");
  }
  // ---- image / video models: structured media_pricing (same data as api/v1/models/<id>.json) ----
  function imgLabel(e) { return e.size === "any" ? "任意尺寸" : e.size; }
  function priceRows(m, tier) {
    var mp = m.media_pricing, out = [];
    mp.image_prices.filter(function (e) { return e.tier === tier; }).forEach(function (e) {
      out.push({ label: imgLabel(e) + (e.quality ? " · " + e.quality : ""), price: e.price, unit: "/张", basis: e.basis, note: e.note });
    });
    mp.video_prices.filter(function (e) { return e.tier === tier; }).forEach(function (e) {
      out.push({ label: e.resolution + (AUDIO[e.audio] ? " · " + AUDIO[e.audio] : ""), price: e.price_per_second, unit: "/秒", basis: e.basis, note: e.note, inVideo: e.input_video_price_per_second });
    });
    return out;
  }
  function chipPrice(r) {
    var v = isNum(r.price) ? money(r.price) + '<span class="u">' + r.unit + "</span>" : '<span class="tbd" title="官方未列出，未做推测">待核实</span>';
    return '<span class="op" title="' + esc((BASIS[r.basis] ? BASIS[r.basis] + "：" : "") + (r.note || "")) + '">' + esc(r.label) + " <span>" + v + "</span>" +
      (BASIS[r.basis] && isNum(r.price) ? '<i class="bsz">≈</i>' : "") + "</span>";
  }
  function matrixCell(m) {
    var rows = priceRows(m, "standard"), mp = m.media_pricing, x = "";
    if (rows.length) x += '<div class="offpeak">' + rows.map(chipPrice).join("") + "</div>";
    else x += '<span class="tbd" title="官方未公布按张 / 按秒单价，未做推测">按张单价待核实</span>';
    if (mp.promotion) x += '<div class="promo" title="' + esc(mp.promotion.note || "") + '">限时促销' + (isNum(mp.promotion.discount_percent) ? " −" + mp.promotion.discount_percent + "%" : "") + "（表内为原价）</div>";
    return x;
  }
  function batchCell(m) {
    var mp = m.media_pricing, rows = priceRows(m, "batch");
    if (rows.length) return '<div class="offpeak">' + rows.map(chipPrice).join("") + "</div>";
    if (mp.batch_supported === true) return '<span class="na" title="Batch 价格见详情">支持</span>';
    if (mp.batch_supported === false) return '<span class="na">不支持</span>';
    return '<span class="na">—</span>';
  }
  function inputCell(m) {
    var mp = m.media_pricing, b = [];
    if (isNum(mp.input_image_price)) b.push('<span class="op">输入图片 <span>' + money(mp.input_image_price) + '<span class="u">/张</span></span></span>');
    mp.video_prices.filter(function (e) { return e.tier === "standard" && isNum(e.input_video_price_per_second); }).forEach(function (e) {
      b.push('<span class="op">输入视频 ' + esc(e.resolution) + " <span>" + money(e.input_video_price_per_second) + '<span class="u">/秒</span></span></span>');
    });
    return b.length ? '<div class="offpeak">' + b.join("") + "</div>" : '<span class="na">—</span>';
  }
  function tokenCell(m) {
    var tp = m.media_pricing.token_pricing;
    if (!tp || !tp.standard) return '<span class="na">—</span>';
    var b = Object.keys(TOKLABEL).filter(function (k) { return isNum(tp.standard[k]); }).map(function (k) {
      return '<span class="op">' + TOKLABEL[k] + " <span>" + money(tp.standard[k]) + "</span></span>";
    });
    return '<div class="offpeak">' + b.join("") + '</div><div class="dnote">USD / 百万 token</div>';
  }
  function mediaDetail(m) {
    var mp = m.media_pricing, out = [], x;
    var std = priceRows(m, "standard"), bat = priceRows(m, "batch"), labels = [];
    std.concat(bat).forEach(function (r) { if (labels.indexOf(r.label + r.unit) < 0) labels.push(r.label + r.unit); });
    if (labels.length) {
      var find = function (arr, l) { return arr.filter(function (r) { return r.label + r.unit === l; })[0]; };
      var cell = function (r) { return r ? (isNum(r.price) ? '<span class="price">' + money(r.price) + "</span>" + (BASIS[r.basis] ? " ≈" : "") : '<span class="tbd">待核实</span>') : '<span class="na">—</span>'; };
      var hasIn = std.some(function (r) { return isNum(r.inVideo); });
      x = '<table class="mini"><thead><tr><th>' + (m.modality === "image" ? "尺寸 · 质量" : "分辨率 · 音频") + "</th><th>单价（标准）</th><th>单价（Batch）</th>" + (hasIn ? "<th>输入视频 / 秒</th>" : "") + "</tr></thead><tbody>" +
        labels.map(function (l) {
          var a = find(std, l), b = find(bat, l), u = (a || b).unit;
          return "<tr><td>" + esc((a || b).label) + " <small>" + u + "</small></td><td>" + cell(a) + "</td><td>" + cell(b) + "</td>" + (hasIn ? "<td>" + (a && isNum(a.inVideo) ? pcell(a.inVideo) : '<span class="na">—</span>') + "</td>" : "") + "</tr>";
        }).join("") + "</tbody></table>" +
        std.concat(bat).filter(function (r) { return r.note; }).map(function (r) { return '<p class="dnote"><b>' + esc(r.label) + "：</b>" + esc(r.note) + "</p>"; }).join("");
    } else x = '<span class="tbd">官方未公布按张 / 按秒单价（待核实）</span>';
    out.push(block(m.modality === "image" ? "按张价格（USD）" : "按秒价格（USD）", x, true));
    var tp = mp.token_pricing;
    if (tp) {
      var tiers = ["standard", "batch", "priority"].filter(function (t) { return tp[t]; });
      x = '<table class="mini"><thead><tr><th>USD / 百万 token</th>' + tiers.map(function (t) { return "<th>" + t + "</th>"; }).join("") + "</tr></thead><tbody>" +
        Object.keys(TOKLABEL).filter(function (k) { return tiers.some(function (t) { return isNum(tp[t][k]); }); }).map(function (k) {
          return "<tr><td>" + TOKLABEL[k] + "</td>" + tiers.map(function (t) { return "<td>" + pcell(tp[t][k]) + "</td>"; }).join("") + "</tr>";
        }).join("") + "</tbody></table>";
      out.push(block("Token 计价", x, true));
    }
    var basis = m.price_basis || {}, billing = m.billing || {};
    x = "";
    if (isNum(mp.input_image_price)) x += kv("输入图片 / 张", money(mp.input_image_price));
    if (isNum(mp.input_image_price_batch)) x += kv("输入图片 / 张（Batch）", money(mp.input_image_price_batch));
    x += kv("计费方式", mp.billing_methods.map(function (k) { return { token: "按 token", per_image: "按张", per_second: "按秒" }[k] || k; }).join(" + "));
    x += kv("Batch", mp.batch_supported === true ? "支持" : mp.batch_supported === false ? "不支持" : "待核实");
    if (mp.promotion) x += '<p class="dnote"><b>促销：</b>' + esc(mp.promotion.note || "") + (mp.promotion.effective_until ? "（至 " + esc(mp.promotion.effective_until) + "）" : "（官方未给截止日期）") + "</p>";
    if (mp.billing_note) x += '<p class="dnote">' + esc(mp.billing_note) + "</p>";
    out.push(block("计费口径", x, false));
    x = '<p class="dnote"><b>官方价格</b>：' + esc(basis.note || "") + "</p>" + (m.notes ? '<p class="dnote">' + esc(m.notes) + "</p>" : "");
    var urls = [];
    [m.source_url].concat(m.extra_sources || [], mp.sources || []).forEach(function (u) { if (u && urls.indexOf(u) < 0) urls.push(u); });
    x += srcLinks(urls) + '<p class="dnote">更新于 ' + esc(m.last_updated || "") + (billing.region ? " · 地区：" + esc(billing.region) : "") +
      ' · <a href="api/v1/models/' + encodeURIComponent(m.model_id) + '.json">JSON</a></p>';
    if ((m.unverified_fields || []).length) x += '<p class="dnote"><span class="tbd">待核实</span> ' + m.unverified_fields.map(function (f) { return "<code>" + esc(f) + "</code>"; }).join(" ") + "</p>";
    out.push(block("来源", x, false));
    return '<div class="detail">' + out.join("") + "</div>";
  }
  function mediaRow(m) {
    var slug = LP.slug(m.vendor), open = state.open[m.model_id];
    var idBtn = '<button type="button" class="model-id" data-copy="' + esc(m.model_id) + '" title="点击复制模型 ID">' + esc(m.model_id) + "</button>";
    var det = '<button type="button" class="detail-btn" data-id="' + esc(m.model_id) + '" aria-expanded="' + (open ? "true" : "false") + '">详情<span class="chev" aria-hidden="true"></span></button>';
    var cells = [
      ["c-model", "厂商 / 模型", '<span class="badge">' + esc(m.vendor) + '</span><div class="model-name">' + esc(m.model) + "</div>" + idBtn + '<div class="model-act">' + det + "</div>"],
      ["c-matrix", m.modality === "image" ? "单价（按张，标准）" : "单价（按秒，标准）", matrixCell(m)],
      ["c-batch", "Batch", batchCell(m)],
      ["c-minput", "输入素材", inputCell(m)],
      ["c-tok", "Token 计价", tokenCell(m)],
      ["c-mnote", "备注", m.notes ? '<details class="note"><summary>备注</summary><p>' + esc(m.notes) + "</p></details>" : '<span class="na">—</span>']
    ];
    return '<tr class="v-' + slug + (open ? " has-detail" : "") + '">' + cells.map(function (c) {
      return '<td class="' + c[0] + '" data-label="' + c[1] + '">' + c[2] + "</td>";
    }).join("") + "</tr>" + (open ? '<tr class="detail-row v-' + slug + '" data-for="' + esc(m.model_id) + '"><td colspan="6">' + mediaDetail(m) + "</td></tr>" : "");
  }
  function haystack(m) {
    return [m.modality, MODLABEL[m.modality], m.vendor, m.model, m.model_id, m.notes, m.peak_note, m.context_length,
      m.reasoning_effort ? [(m.reasoning_effort.levels || []).join(" "), m.reasoning_effort.default, m.reasoning_effort.note].join(" ") : "推理强度 待核实"].join(" ").toLowerCase();
  }
  function cmp(a, b) {
    var k = state.sortKey, x = a[k], y = b[k];
    var xn = (x === null || x === undefined || x === "n/a"), yn = (y === null || y === undefined || y === "n/a");
    if (xn && yn) return 0;
    if (xn) return 1;           // missing values always last, either direction
    if (yn) return -1;
    if (typeof x === "number" && typeof y === "number") return (x - y) * state.sortDir;
    return String(x).localeCompare(String(y), "zh-Hans-CN", { numeric: true }) * state.sortDir;
  }
  function filtered() {
    var q = state.q.trim().toLowerCase();
    var terms = q ? q.split(/\s+/) : [];
    return state.models.filter(function (m) {
      if (m.modality !== state.modality) return false;
      if (state.vendor && m.vendor !== state.vendor) return false;
      var h = m._h;
      for (var i = 0; i < terms.length; i++) if (h.indexOf(terms[i]) === -1) return false;
      return true;
    });
  }
  function syncUrl() {
    var p = new URLSearchParams(location.search);
    ["vendor", "q", "sort", "modality"].forEach(function (k) { p.delete(k); });
    if (state.modality !== "text") p.set("modality", state.modality);
    if (state.vendor) p.set("vendor", LP.slug(state.vendor));
    if (state.q.trim()) p.set("q", state.q.trim());
    if (state.sortKey !== "_i") p.set("sort", (state.sortDir < 0 ? "-" : "") + state.sortKey);
    var s = p.toString();
    history.replaceState(null, "", location.pathname + (s ? "?" + s : "") + location.hash);
  }
  function fitDetail() {
    var sc = document.querySelector(".table-scroll") || $("tbody").closest("table").parentElement;
    document.documentElement.style.setProperty("--tw", sc.clientWidth + "px");
  }
  window.addEventListener("resize", fitDetail);

  function render() {
    var list = filtered();
    list.sort(function (a, b) { return cmp(a, b) || a._i - b._i; });
    var best = {}, media = state.modality !== "text";
    $("priceTable").hidden = media; $("mediaTable").hidden = !media;
    PRICE_KEYS.forEach(function (k) {
      var vals = list.map(function (m) { return m[k]; }).filter(isNum);
      // only mark a "lowest" when there is something to compare against
      best[k] = vals.length > 1 ? Math.min.apply(null, vals) : undefined;
    });
    if (media) $("mediaBody").innerHTML = list.map(mediaRow).join("");
    else $("tbody").innerHTML = list.map(function (m) { return row(m, best); }).join("");
    document.querySelector(".table-card").classList.toggle("media", media);
    fitDetail();
    $("empty").hidden = list.length > 0;
    var inMod = state.models.filter(function (m) { return m.modality === state.modality; }).length;
    $("count").innerHTML = "显示 <b>" + list.length + "</b> / " + inMod + " 个" + MODLABEL[state.modality] + "模型（共 " + state.models.length + "）";
    $("textLegend").hidden = media; $("mediaLegend").hidden = !media;
    Array.prototype.forEach.call(document.querySelectorAll("#modalityTabs .tab"), function (t) {
      t.setAttribute("aria-selected", String(t.dataset.modality === state.modality));
    });
    $("sortText").hidden = media; $("sortMedia").hidden = !media;
    // vendor chips: only vendors that have models in this modality
    var cnt = {}; state.models.forEach(function (m) { if (m.modality === state.modality) cnt[m.vendor] = (cnt[m.vendor] || 0) + 1; });
    Array.prototype.forEach.call(document.querySelectorAll("#vendorChips .chip"), function (c) {
      var v = c.dataset.vendor, n = v ? (cnt[v] || 0) : inMod;
      c.querySelector(".n").textContent = n; c.hidden = !!v && !n;
    });
    Array.prototype.forEach.call(document.querySelectorAll("th[data-key]"), function (th) {
      if (th.dataset.key === state.sortKey) th.setAttribute("aria-sort", state.sortDir === 1 ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
    });
    Array.prototype.forEach.call(document.querySelectorAll("#vendorChips .chip"), function (c) {
      c.setAttribute("aria-pressed", String(c.dataset.vendor === state.vendor));
    });
    var ss = $("sortSelect"), want = state.sortKey + ":" + state.sortDir;
    ss.value = Array.prototype.some.call(ss.options, function (o) { return o.value === want; }) ? want : "_i:1";
    var sm = $("sortSelectMedia");
    sm.value = Array.prototype.some.call(sm.options, function (o) { return o.value === want; }) ? want : "_i:1";
    syncUrl();
  }
  function chip(label, value, n, slug) {
    return '<button type="button" class="chip' + (slug ? " v-" + slug : "") + '" data-vendor="' + esc(value) + '" aria-pressed="false">' +
      (slug ? '<span class="vdot" aria-hidden="true"></span>' : "") + esc(label) + ' <span class="n">' + n + "</span></button>";
  }
  function setSort(k, dir) { state.sortKey = k; state.sortDir = dir; render(); }
  function reset() { state.vendor = ""; state.q = ""; $("searchBox").value = ""; setSort("_i", 1); }
  function setModality(mod) {
    if (MODS.indexOf(mod) < 0) mod = "text";
    state.modality = mod; state.vendor = "";
    var valid = mod === "text" ? ["_i", "input", "output", "cached_input", "cache_write", "peak_note", "context_tokens", "lim_out", "re_sort", "model"] : ["_i", "model", "media_price"];
    if (valid.indexOf(state.sortKey) < 0) { state.sortKey = "_i"; state.sortDir = 1; }
    render();
  }

  function init(data) {
    var models = data.models;
    state.models = models.map(function (m, i) {
      m._i = i; m._h = haystack(m);
      m.lim_out = m.limits ? m.limits.max_output_tokens : null;
      m.media_price = null;
      if (m.media_pricing) {
        var mpv = priceRows(m, "standard").map(function (r) { return r.price; }).filter(isNum);
        m.media_price = mpv.length ? Math.min.apply(null, mpv) : null;
      }
      var r = m.reasoning_effort;   // sortable: number of levels (0 = not adjustable); 待核实 sorts last
      m.re_sort = (r && r.supported === false) ? 0 : (r && r.levels ? r.levels.length : null);
      return m;
    });
    state.vendors = data.vendors;
    (new URLSearchParams(location.search).get("open") || "").split(",").forEach(function (id) { if (id) state.open[id] = true; });
    $("statUpdated").textContent = data.meta.last_updated;
    $("footUpdated").textContent = data.meta.last_updated;
    var mc = { text: 0, image: 0, video: 0 };
    models.forEach(function (m) { mc[m.modality]++; });
    $("statModels").innerHTML = models.length + "<small>个</small>";
    $("statModels").title = "文本 " + mc.text + " · 图像 " + mc.image + " · 视频 " + mc.video;
    $("modalityTabs").innerHTML = MODS.map(function (k) {
      return '<button type="button" class="tab" role="tab" data-modality="' + k + '" aria-selected="false">' + MODLABEL[k] + ' <span class="n">' + mc[k] + "</span></button>";
    }).join("");
    $("modalityTabs").addEventListener("click", function (e) {
      var t = e.target.closest(".tab"); if (t) setModality(t.dataset.modality);
    });
    $("statVendors").innerHTML = data.vendors.length + "<small>家</small>";
    var cheap = models.filter(function (m) { return m.modality === "text" && isNum(m.input); }).sort(function (a, b) { return a.input - b.input; })[0];
    if (cheap) $("statCheapest").innerHTML = "$" + fmtNum(cheap.input) + "<small>" + esc(cheap.model) + "</small>";
    $("statCheapest").title = cheap ? cheap.model : "";

    var counts = {};
    models.forEach(function (m) { counts[m.vendor] = (counts[m.vendor] || 0) + 1; });
    state.modality = MODS.indexOf(new URLSearchParams(location.search).get("modality")) >= 0 ? new URLSearchParams(location.search).get("modality") : "text";
    $("vendorChips").innerHTML = chip("全部", "", models.length, "") + data.vendors.map(function (v) {
      return chip(v, v, counts[v] || 0, LP.slug(v));
    }).join("");

    // footer: official sources per vendor
    $("sources").innerHTML = data.vendors.map(function (v) {
      var urls = [];
      models.forEach(function (m) { if (m.vendor === v && urls.indexOf(m.source_url) === -1) urls.push(m.source_url); });
      return urls.map(function (u) {
        return '<li class="v-' + LP.slug(v) + '"><span class="badge">' + esc(v) + '</span><a href="' + esc(u) +
          '" target="_blank" rel="noopener noreferrer" title="' + esc(u) + '">' + esc(u.replace(/^https?:\/\//, "")) + "</a></li>";
      }).join("");
    }).join("");

    // restore state from URL (?vendor=slug&q=..&sort=-input)
    var p = new URLSearchParams(location.search);
    var vs = p.get("vendor");
    if (vs) data.vendors.forEach(function (v) { if (LP.slug(v) === vs || v === vs) state.vendor = v; });
    if (p.get("q")) { state.q = p.get("q"); $("searchBox").value = state.q; }
    var so = p.get("sort");
    var validSort = state.modality === "text" ? "#priceTable" : "#mediaTable";
    if (so && document.querySelector(validSort + ' th[data-key="' + so.replace(/^-/, "") + '"]')) {
      state.sortDir = so.charAt(0) === "-" ? -1 : 1; state.sortKey = so.replace(/^-/, "");
    }

    $("vendorChips").addEventListener("click", function (e) {
      var c = e.target.closest(".chip"); if (!c) return;
      state.vendor = (c.dataset.vendor === state.vendor && c.dataset.vendor) ? "" : c.dataset.vendor; render();
    });
    $("searchBox").addEventListener("input", function (e) { state.q = e.target.value; render(); });
    $("resetBtn").addEventListener("click", reset);
    $("emptyReset").addEventListener("click", function (e) { e.preventDefault(); reset(); });
    $("sortSelect").addEventListener("change", function (e) {
      var v = e.target.value.split(":"); setSort(v[0], Number(v[1]));
    });
    $("sortSelectMedia").addEventListener("change", function (e) {
      var v = e.target.value.split(":"); setSort(v[0], Number(v[1]));
    });
    Array.prototype.forEach.call(document.querySelectorAll("th[data-key] .th"), function (btn) {
      btn.addEventListener("click", function () {
        var k = btn.parentNode.dataset.key;
        if (state.sortKey === k) {
          if (state.sortDir === 1) setSort(k, -1); else setSort("_i", 1); // asc -> desc -> default
        } else setSort(k, 1);
      });
    });
    function bodyClick(e) {
      var db = e.target.closest(".detail-btn");
      if (db) { var id = db.dataset.id; if (state.open[id]) delete state.open[id]; else state.open[id] = true; render(); var b2 = document.querySelector('.detail-btn[data-id="' + id.replace(/"/g, "") + '"]'); if (b2) b2.focus(); return; }
      var more = e.target.closest(".more");
      if (more) {
        var pk = more.closest(".peak"), open = pk.classList.toggle("expanded");
        more.textContent = open ? "收起" : "展开"; return;
      }
      var b = e.target.closest(".model-id"); if (!b) return;
      LP.copy(b.dataset.copy).then(function () { LP.toast("已复制模型 ID：" + b.dataset.copy); }, function () { LP.toast("复制失败"); });
    }
    $("tbody").addEventListener("click", bodyClick);
    $("mediaBody").addEventListener("click", bodyClick);
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); $("searchBox").focus(); }
      else if (e.key === "Escape" && document.activeElement === $("searchBox")) { $("searchBox").value = ""; state.q = ""; render(); }
    });
    render();
  }
  fetch(DATA_URL, { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(init)
    .catch(function (e) {
      $("tbody").innerHTML = "";
      var el = $("error"); el.hidden = false;
      el.innerHTML = "<b>数据加载失败（" + esc(e.message) + "）</b>请通过 HTTP 服务器预览（如 <code>python3 -m http.server</code>），不要直接双击打开 file://。";
      $("statUpdated").textContent = "未知";
    });
})();
