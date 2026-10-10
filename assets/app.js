(function () {
  "use strict";
  var DATA_URL = "data/prices.json";
  var PRICE_KEYS = ["input", "output", "cached_input", "cache_write"];
  var esc = LP.esc;
  var state = { models: [], vendors: [], vendor: "", q: "", sortKey: "_i", sortDir: 1, open: {} };
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
    return tokSpan(L.max_output_tokens);
  }
  function ctxCell(m) {
    var L = m.limits || {}, n = isNum(L.context_length) ? L.context_length : m.context_tokens;
    return tokSpan(n);
  }
  function tierCond(t) {
    var a = fmtTok(t.input_tokens_gt), b = fmtTok(t.input_tokens_lte);
    if (a && b) return a + " – " + b + " 输入";
    if (a) return "&gt; " + a + " 输入";
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
    out.push(block("服务档倍率", x));
    // 3 cache
    var C = m.cache_pricing || {};
    x = "";
    if (isNum(C.implicit_read)) x += kv("隐式缓存命中", money(C.implicit_read));
    if (isNum(C.explicit_read)) x += kv("显式缓存命中", money(C.explicit_read));
    if (isNum(C.explicit_write)) x += kv("缓存写入 / 创建", money(C.explicit_write));
    if (isNum(C.explicit_write_1h)) x += kv("缓存写入（1 小时 TTL）", money(C.explicit_write_1h));
    if (isNum(C.storage_per_1M_tokens_hour)) x += kv("缓存存储 / 百万 token / 小时", C.storage_per_1M_tokens_hour === 0 ? "限时免费" : money(C.storage_per_1M_tokens_hour));
    if (C.note) x += '<p class="dnote">' + esc(C.note) + "</p>";
    out.push(block("缓存价细分", x || '<span class="na">官方未列细分缓存价</span>'));
    // 4 sources
    var urls = [];
    [m.source_url].concat(m.extra_sources || [], L.sources || []).forEach(function (u) { if (u && urls.indexOf(u) === -1) urls.push(u); });
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
    var notes = m.notes ? '<details class="note"><summary>备注</summary><p>' + esc(m.notes) + "</p></details>" : "";
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
  function haystack(m) {
    return [m.vendor, m.model, m.model_id, m.notes, m.peak_note, m.context_length,
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
      if (state.vendor && m.vendor !== state.vendor) return false;
      var h = m._h;
      for (var i = 0; i < terms.length; i++) if (h.indexOf(terms[i]) === -1) return false;
      return true;
    });
  }
  function syncUrl() {
    var p = new URLSearchParams(location.search);
    ["vendor", "q", "sort"].forEach(function (k) { p.delete(k); });
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
    var best = {};
    PRICE_KEYS.forEach(function (k) {
      var vals = list.map(function (m) { return m[k]; }).filter(isNum);
      // only mark a "lowest" when there is something to compare against
      best[k] = vals.length > 1 ? Math.min.apply(null, vals) : undefined;
    });
    $("tbody").innerHTML = list.map(function (m) { return row(m, best); }).join("");
    fitDetail();
    $("empty").hidden = list.length > 0;
    $("count").innerHTML = "显示 <b>" + list.length + "</b> / " + state.models.length + " 个模型";
    Array.prototype.forEach.call(document.querySelectorAll("th[data-key]"), function (th) {
      if (th.dataset.key === state.sortKey) th.setAttribute("aria-sort", state.sortDir === 1 ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
    });
    Array.prototype.forEach.call(document.querySelectorAll("#vendorChips .chip"), function (c) {
      c.setAttribute("aria-pressed", String(c.dataset.vendor === state.vendor));
    });
    var ss = $("sortSelect"), want = state.sortKey + ":" + state.sortDir;
    ss.value = Array.prototype.some.call(ss.options, function (o) { return o.value === want; }) ? want : "_i:1";
    syncUrl();
  }
  function chip(label, value, n, slug) {
    return '<button type="button" class="chip' + (slug ? " v-" + slug : "") + '" data-vendor="' + esc(value) + '" aria-pressed="false">' +
      (slug ? '<span class="vdot" aria-hidden="true"></span>' : "") + esc(label) + ' <span class="n">' + n + "</span></button>";
  }
  function setSort(k, dir) { state.sortKey = k; state.sortDir = dir; render(); }
  function reset() { state.vendor = ""; state.q = ""; $("searchBox").value = ""; setSort("_i", 1); }

  function init(data) {
    var models = data.models;
    state.models = models.map(function (m, i) {
      m._i = i; m._h = haystack(m);
      m.lim_out = m.limits ? m.limits.max_output_tokens : null;
      var r = m.reasoning_effort;   // sortable: number of levels (0 = not adjustable); 待核实 sorts last
      m.re_sort = (r && r.supported === false) ? 0 : (r && r.levels ? r.levels.length : null);
      return m;
    });
    state.vendors = data.vendors;
    (new URLSearchParams(location.search).get("open") || "").split(",").forEach(function (id) { if (id) state.open[id] = true; });
    $("statUpdated").textContent = data.meta.last_updated;
    $("footUpdated").textContent = data.meta.last_updated;
    $("statModels").innerHTML = models.length + "<small>个</small>";
    $("statVendors").innerHTML = data.vendors.length + "<small>家</small>";
    var cheap = models.filter(function (m) { return isNum(m.input); }).sort(function (a, b) { return a.input - b.input; })[0];
    if (cheap) $("statCheapest").innerHTML = "$" + fmtNum(cheap.input) + "<small>" + esc(cheap.model) + "</small>";
    $("statCheapest").title = cheap ? cheap.model : "";

    var counts = {};
    models.forEach(function (m) { counts[m.vendor] = (counts[m.vendor] || 0) + 1; });
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
    if (so && document.querySelector('th[data-key="' + so.replace(/^-/, "") + '"]')) {
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
    Array.prototype.forEach.call(document.querySelectorAll("th[data-key] .th"), function (btn) {
      btn.addEventListener("click", function () {
        var k = btn.parentNode.dataset.key;
        if (state.sortKey === k) {
          if (state.sortDir === 1) setSort(k, -1); else setSort("_i", 1); // asc -> desc -> default
        } else setSort(k, 1);
      });
    });
    $("tbody").addEventListener("click", function (e) {
      var db = e.target.closest(".detail-btn");
      if (db) { var id = db.dataset.id; if (state.open[id]) delete state.open[id]; else state.open[id] = true; render(); var b2 = document.querySelector('.detail-btn[data-id="' + id.replace(/"/g, "") + '"]'); if (b2) b2.focus(); return; }
      var more = e.target.closest(".more");
      if (more) {
        var pk = more.closest(".peak"), open = pk.classList.toggle("expanded");
        more.textContent = open ? "收起" : "展开"; return;
      }
      var b = e.target.closest(".model-id"); if (!b) return;
      LP.copy(b.dataset.copy).then(function () { LP.toast("已复制模型 ID：" + b.dataset.copy); }, function () { LP.toast("复制失败"); });
    });
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
