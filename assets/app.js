(function () {
  "use strict";
  var DATA_URL = "data/prices.json";
  var PRICE_KEYS = ["input", "output", "cached_input", "cache_write"];
  var esc = LP.esc;
  var state = { models: [], vendors: [], vendor: "", q: "", sortKey: "_i", sortDir: 1 };
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
  function ctxCell(m) {
    return m.context_length ? '<span class="ctx">' + esc(m.context_length) + "</span>" : '<span class="tbd">待核实</span>';
  }
  function row(m, best) {
    var slug = LP.slug(m.vendor);
    var notes = m.notes ? '<details class="note"><summary>备注</summary><p>' + esc(m.notes) + "</p></details>" : "";
    var idBtn = m.model_id ? '<button type="button" class="model-id" data-copy="' + esc(m.model_id) + '" title="点击复制模型 ID">' + esc(m.model_id) + "</button>" : "";
    var json = m.model_id ? '<a href="api/v1/models/' + encodeURIComponent(m.model_id) + '.json" title="此模型的 JSON">JSON</a>' : "";
    var cells = [
      ["c-vendor", "厂商", '<span class="badge">' + esc(m.vendor) + "</span>"],
      ["c-model", "模型", '<div class="model-name">' + esc(m.model) + "</div>" + idBtn + notes],
      ["num c-in", "输入", priceCell(m.input, best.input === m.input)],
      ["num c-out", "输出", priceCell(m.output, best.output === m.output)],
      ["num c-cr", "缓存读取", priceCell(m.cached_input, best.cached_input === m.cached_input)],
      ["num c-cw", "缓存写入", priceCell(m.cache_write, best.cache_write === m.cache_write)],
      ["num c-ctx", "上下文", ctxCell(m)],
      ["c-peak" + (m.peak_note || m.offpeak ? "" : " empty-peak"), "高峰 / 闲时", peakCell(m)],
      ["c-src", "来源 / 更新", '<div class="src"><span class="links"><a href="' + esc(m.source_url) +
        '" target="_blank" rel="noopener noreferrer">官方页面 ↗</a>' + json + '</span><span class="date">' + esc(m.last_updated || "") + "</span></div>"]
    ];
    return '<tr class="v-' + slug + '">' + cells.map(function (c) {
      return '<td class="' + c[0] + '" data-label="' + c[1] + '">' + c[2] + "</td>";
    }).join("") + "</tr>";
  }
  function haystack(m) {
    return [m.vendor, m.model, m.model_id, m.notes, m.peak_note, m.context_length].join(" ").toLowerCase();
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
    state.models = models.map(function (m, i) { m._i = i; m._h = haystack(m); return m; });
    state.vendors = data.vendors;
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
