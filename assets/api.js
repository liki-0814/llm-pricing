(function () {
  "use strict";
  var esc = LP.esc, $ = function (id) { return document.getElementById(id); };
  var BASE = new URL("api/v1/", location.href).href;
  var client = LLMPrice.createClient(BASE);
  $("baseUrl").textContent = BASE;

  // ---------- examples (base URL filled in) ----------
  var EX = {
    curl:
      "# 全部模型\ncurl --fail --silent --show-error " + BASE + "models.json\n\n" +
      "# 单个模型 / 单个厂商\ncurl --fail --silent --show-error " + BASE + "models/deepseek-flash.json\ncurl --fail --silent --show-error " + BASE + "vendors/anthropic.json\n\n" +
      "# 图像 / 视频模型（按张、按秒、分模态 token 价）\ncurl --fail --silent --show-error " + BASE + "modalities/image.json\ncurl --fail --silent --show-error " + BASE + "modalities/video.json\n\n" +
      "# 配合 jq：视频模型按秒价格（标准档）\ncurl --fail --silent --show-error " + BASE + "modalities/video.json \\\n  | jq -r '.data[] | .id as $id | .media_pricing.video_prices[] | select(.tier == \"standard\") | \"\\($id) \\(.resolution) \\(.audio) \\(.price_per_second)\"'\n\n" +
      "# 配合 jq：官方输入价最低的 5 个模型\ncurl --fail --silent --show-error " + BASE + "models.json \\\n  | jq -r '.data | map(select(.pricing.input != null and .price_basis.type == \"official\")) | sort_by(.pricing.input) | .[:5][] | \"\\(.id)\\t$\\(.pricing.input)\"'",
    js:
      '// 在 HTML 中加载站点的 assets/client.js（暴露 LLMPrice）\n' +
      'const api = LLMPrice.createClient("' + BASE + '");\n\n' +
      'const { data: index } = await api.getIndex();\n' +
      'const { data: vendors } = await api.listVendors();\n' +
      'const openapi = await api.getOpenAPI();\n' +
      'const { data: model } = await api.getModel("gemini-3.1-pro-preview");\n' +
      'const { data: vendorModels } = await api.getVendor("openai");\n' +
      'const { data: cheapest } = await api.listModels({ vendor: "openai", sort: "input", limit: 5, priceBasis: "official" });\n\n' +
      '// 图像 / 视频模型：按模态过滤，用 estimateMedia 估算（estimate 仅适用于文本模型）\n' +
      'const { data: videos } = await api.listModels({ modality: "video", sort: "media_price" });\n' +
      'const { data: wan } = await api.getModel("wan3.0-video");\n' +
      'const clip = LLMPrice.estimateMedia(wan, { seconds: 10, resolution: "720p" }); // 1 USD（促销折扣未计入）\n\n' +
      '// inputTokens 为总输入，包含缓存读写；outputTokens 包含计费思考 token\n' +
      'const result = LLMPrice.estimate(model, { inputTokens: 300000, outputTokens: 10000 }, { at: "2026-10-11" });\n' +
      'console.log(result.total, result.breakdown, result.warnings); // 1.38 USD\n',
    py:
      "import json, urllib.request\n\nBASE = \"" + BASE + "\"\n\n" +
      "def get(path):\n    with urllib.request.urlopen(BASE + path) as r:\n        return json.load(r)\n\n" +
      "models = get(\"models.json\")\nprint(models[\"meta\"][\"updated_at\"], models[\"meta\"][\"count\"])\n\n" +
      "# 官方输入价最低的 5 个模型（跳过 null 和参照价）\npriced = [m for m in models[\"data\"] if m[\"pricing\"][\"input\"] is not None and m[\"price_basis\"][\"type\"] == \"official\"]\n" +
      "for m in sorted(priced, key=lambda m: m[\"pricing\"][\"input\"])[:5]:\n    print(f'{m[\"id\"]:<28} in ${m[\"pricing\"][\"input\"]}  out ${m[\"pricing\"][\"output\"]}')\n\n" +
      "images = get(\"modalities/image.json\")\nfor m in images[\"data\"]:\n    for p in m[\"media_pricing\"][\"image_prices\"]:\n        if p[\"tier\"] == \"standard\":\n            print(m[\"id\"], p[\"size\"], p[\"quality\"], p[\"price\"])\n\n" +
      "claude = get(\"models/claude-opus-5.json\")[\"data\"]\nprint(claude[\"pricing\"], claude[\"pricing_status\"])"
  };
  function hlCode(s) {
    // tiny highlighter: comments, strings
    return esc(s).replace(/(^|\n)(\s*(#|\/\/)[^\n]*)/g, '$1<span class="tok-c">$2</span>')
      .replace(/(&quot;[^&\n]*?&quot;)/g, '<span class="tok-s">$1</span>');
  }
  Object.keys(EX).forEach(function (k) { $("ex-" + k).innerHTML = hlCode(EX[k]); });

  document.querySelector(".tabs").addEventListener("click", function (e) {
    var t = e.target.closest(".tab"); if (!t) return;
    Array.prototype.forEach.call(document.querySelectorAll(".tab"), function (b) { b.setAttribute("aria-selected", String(b === t)); });
    Array.prototype.forEach.call(document.querySelectorAll("[data-panel]"), function (p) { p.hidden = p.dataset.panel !== t.dataset.tab; });
  });
  document.addEventListener("click", function (e) {
    var b = e.target.closest(".copy"); if (!b) return;
    var pre = b.dataset.copyTarget ? $(b.dataset.copyTarget) : b.parentNode.querySelector("pre");
    LP.copy(pre.textContent).then(function () { LP.toast("已复制"); }, function () { LP.toast("复制失败"); });
  });

  // ---------- JSON highlighter ----------
  function hlJson(obj) {
    var s = JSON.stringify(obj, null, 2);
    // Preserve the complete response so copied JSON remains valid.
    return esc(s).replace(/(&quot;(?:\\.|[^&\\]|&(?!quot;))*?&quot;)(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g,
      function (m, str, colon, kw) {
        if (str) return colon ? '<span class="tok-k">' + str + "</span>" + colon : '<span class="tok-s">' + str + "</span>";
        if (kw) return '<span class="tok-b">' + m + "</span>";
        return '<span class="tok-n">' + m + "</span>";
      });
  }

  // ---------- try it ----------
  var SNIPPETS = {
    cheapest: {
      path: "models.json",
      code: 'const { data } = await (await fetch(BASE + "models.json")).json();\nreturn data\n  .filter(m => m.pricing.input != null && m.price_basis.type === "official")\n  .sort((a, b) => a.pricing.input - b.pricing.input)\n  .slice(0, 5)\n  .map(m => ({ id: m.id, vendor: m.vendor, input: m.pricing.input, output: m.pricing.output }));',
      run: function (d) {
        return d.data.filter(function (m) { return m.pricing.input != null && m.price_basis.type === "official"; })
          .sort(function (a, b) { return a.pricing.input - b.pricing.input; }).slice(0, 5)
          .map(function (m) { return { id: m.id, vendor: m.vendor, input: m.pricing.input, output: m.pricing.output }; });
      }
    },
    imageprice: {
      path: "modalities/image.json",
      code: 'const { data } = await (await fetch(BASE + "modalities/image.json")).json();\nreturn data.flatMap(m => m.media_pricing.image_prices\n  .filter(p => p.tier === "standard")\n  .map(p => ({ id: m.id, size: p.size, quality: p.quality, usd_per_image: p.price })));',
      run: function (d) {
        return d.data.reduce(function (a, m) {
          return a.concat(m.media_pricing.image_prices.filter(function (p) { return p.tier === "standard"; })
            .map(function (p) { return { id: m.id, size: p.size, quality: p.quality, usd_per_image: p.price }; }));
        }, []);
      }
    },
    videoprice: {
      path: "modalities/video.json",
      code: 'const { data } = await (await fetch(BASE + "modalities/video.json")).json();\nreturn data.flatMap(m => m.media_pricing.video_prices\n  .filter(p => p.tier === "standard")\n  .map(p => ({ id: m.id, resolution: p.resolution, audio: p.audio, usd_per_second: p.price_per_second })));',
      run: function (d) {
        return d.data.reduce(function (a, m) {
          return a.concat(m.media_pricing.video_prices.filter(function (p) { return p.tier === "standard"; })
            .map(function (p) { return { id: m.id, resolution: p.resolution, audio: p.audio, usd_per_second: p.price_per_second }; }));
        }, []);
      }
    },
    offpeak: {
      path: "models.json",
      code: 'const { data } = await (await fetch(BASE + "models.json")).json();\nreturn data\n  .filter(m => m.has_off_peak)\n  .map(m => ({ id: m.id, peak: m.pricing, off_peak: m.off_peak_pricing }));',
      run: function (d) {
        return d.data.filter(function (m) { return m.has_off_peak; })
          .map(function (m) { return { id: m.id, peak: m.pricing, off_peak: m.off_peak_pricing }; });
      }
    }
  };
  var vendors = [], modelIds = [], modalities = [];
  function fillParam() {
    var v = $("tryPreset").value, p = $("tryParam");
    var list = v === "vendor" ? vendors : v === "model" ? modelIds : v === "modality" ? modalities : null;
    p.hidden = !list;
    if (list) p.innerHTML = list.map(function (x) { return '<option value="' + esc(x) + '">' + esc(x) + "</option>"; }).join("");
    updateUrl();
  }
  function updateUrl() {
    var v = $("tryPreset").value, path = v;
    if (v === "vendor") path = "vendors/" + ($("tryParam").value || "openai") + ".json";
    else if (v === "modality") path = "modalities/" + ($("tryParam").value || "image") + ".json";
    else if (v === "model") path = "models/" + ($("tryParam").value || "deepseek-flash") + ".json";
    var sn = v.indexOf("snippet:") === 0 ? SNIPPETS[v.slice(8)] : null;
    if (sn) path = sn.path;
    $("tryUrl").value = BASE + path;
    $("trySnippetBox").hidden = !sn;
    if (sn) $("trySnippet").innerHTML = hlCode(sn.code);
  }
  function send() {
    var url = $("tryUrl").value.trim(), v = $("tryPreset").value;
    var sn = v.indexOf("snippet:") === 0 ? SNIPPETS[v.slice(8)] : null;
    var t0 = performance.now(), st = $("tryStatus");
    st.innerHTML = "请求中…";
    $("trySend").disabled = true;
    fetch(url, { cache: "no-cache" }).then(function (r) {
      return r.text().then(function (txt) {
        var ms = Math.round(performance.now() - t0), size = new Blob([txt]).size;
        var ct = r.headers.get("content-type") || "";
        st.innerHTML = '<span class="' + (r.ok ? "ok" : "err") + '">HTTP ' + r.status + "</span><span>" + ms + " ms</span><span>" +
          (size / 1024).toFixed(1) + " KB</span><span>" + esc(ct) + "</span>";
        var body;
        try { body = JSON.parse(txt); } catch (_) {
          $("tryOut").textContent = txt.slice(0, 3000) || "(空响应)"; return;
        }
        if (sn && r.ok) body = sn.run(body);
        $("tryOut").innerHTML = hlJson(body);
      });
    }).catch(function (e) {
      st.innerHTML = '<span class="err">请求失败</span><span>' + esc(e.message) + "</span>";
      $("tryOut").textContent = "";
    }).then(function () { $("trySend").disabled = false; });
  }
  $("tryPreset").addEventListener("change", fillParam);
  $("tryParam").addEventListener("change", updateUrl);
  $("trySend").addEventListener("click", send);
  $("tryUrl").addEventListener("keydown", function (e) { if (e.key === "Enter") send(); });
  updateUrl();

  var costRevision = 0;
  var costData = null;
  async function updateService() {
    var revision = ++costRevision, id = $("costModel").value;
    costData = null; $("costSend").disabled = true;
    $("costStatus").textContent = "加载模型计费规则…";
    $("costOut").textContent = "填写用量后查看费用明细。";
    try {
      var result = await client.getModel(id);
      if (revision !== costRevision) return;
      costData = result.data;
      $("costResidency").value = "false";
      $("costResidency").disabled = !costData.service_tiers.some(function (s) { return s.name === "data_residency"; });
      $("costService").innerHTML = '<option value="standard">Standard</option>' + costData.service_tiers.filter(function (s) { return s.name !== "data_residency"; }).map(function (s) {
        return '<option value="' + esc(s.name) + '">' + esc(s.name) + '</option>';
      }).join("");
      $("costStatus").textContent = costData.price_basis.type === "reference" ? "参照价：" + costData.price_basis.reference_model_id + "，不代表订阅实际账单。" : "输入总量包含缓存读取与创建；估算范围为 token 与缓存费用。";
      $("costSend").disabled = false;
    } catch (e) {
      if (revision === costRevision) $("costStatus").textContent = "模型加载失败：" + e.message;
    }
  }
  $("costModel").addEventListener("change", updateService);
  $("costForm").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!costData) return;
    try {
      var usage = {};
      ["inputTokens", "outputTokens", "cachedInputTokens", "cacheWriteTokens", "cacheWrite1hTokens", "cacheWrite12hTokens", "storageTokenHours"].forEach(function (key) {
        var value = $(key).value.trim();
        if (!value) throw new Error("请填写 " + key + "，不用时填 0。");
        usage[key] = Number(value);
      });
      var options = { at: $("costAt").value.trim(), serviceTier: $("costService").value };
      if (!$("costResidency").disabled) options.dataResidency = $("costResidency").value === "true";
      if ($("costHoliday").value) options.isChineseHoliday = $("costHoliday").value === "true";
      if ($("costCacheType").value) options.cacheType = $("costCacheType").value;
      var estimate = LLMPrice.estimate(costData, usage, options);
      var tier = costData.pricing_tiers.find(function (t) { return t.condition === estimate.pricing_tier; });
      var tierLabel = tier ? "输入 ≥ " + (tier.input_tokens_gt + 1).toLocaleString("en-US") +
        (tier.input_tokens_lte === null ? "" : " 且 ≤ " + tier.input_tokens_lte.toLocaleString("en-US")) + " tokens" : "基础档";
      var periodLabel = {standard:"标准计费",peak:"高峰时段",off_peak:"闲时时段"}[estimate.period];
      $("costStatus").textContent = (estimate.price_basis.type === "reference" ? "参照估算 " : "估算 ") +
        estimate.total.toFixed(6) + " USD · " + tierLabel + " · " + periodLabel +
        (estimate.price_basis.type === "reference" ? " · 不代表订阅实际扣费" : "");
      $("costOut").textContent = JSON.stringify(estimate, null, 2);
    } catch (e) {
      var messages = {PRICE_UNAVAILABLE:"所用费用项没有可核实的价格",HOLIDAY_REQUIRED:"高峰时段需确认是否为中国法定节假日",TIME_REQUIRED:"请填写带时区的完整时间",PRICE_EXPIRED:"促销已超出已确认期限，需复核",HISTORICAL_PRICE_UNAVAILABLE:"本快照不含更早的历史价格",LIMIT_EXCEEDED:"输入或输出超过已记录的上限",INVALID_ARGUMENT:"输入参数不正确"};
      $("costStatus").textContent = (messages[e.code] || "无法估算") + "：" + e.message;
      $("costOut").textContent = "";
    }
  });

  client.listVendors().then(function (d) {
    $("footUpdated").textContent = d.meta.updated_at;
    $("costAt").value = d.meta.updated_at + "T12:00:00+08:00";
    vendors = d.data.map(function (v) { return v.slug; });
    d.data.forEach(function (v) { modelIds = modelIds.concat(v.model_ids); });
    $("slugList").innerHTML = "可用 <code>vendor</code>：" + d.data.map(function (v) {
      return '<a href="api/v1/vendors/' + esc(v.slug) + '.json"><code>' + esc(v.slug) + "</code></a>（" + esc(v.name) + "，" + v.model_count + "）";
    }).join("、") + "。全部 <code>model_id</code> 见 <a href=\"api/v1/vendors.json\">vendors.json</a> 的 <code>model_ids</code>。";
    fillParam();
    return client.listModalities().then(function (m) {
      modalities = m.data.map(function (x) { return x.name; });
      $("modalityList").innerHTML = "可用 <code>modality</code>：" + m.data.map(function (x) {
        return '<a href="api/v1/modalities/' + esc(x.name) + '.json"><code>' + esc(x.name) + "</code></a>（" + esc(x.label) + "，" + x.model_count + "）";
      }).join("、") + "。";
      fillParam();
      // the token / cache estimator only applies to text models
      var textIds = (m.data.filter(function (x) { return x.name === "text"; })[0] || { model_ids: [] }).model_ids;
      $("costModel").innerHTML = textIds.map(function (id) { return '<option value="' + esc(id) + '">' + esc(id) + '</option>'; }).join("");
      $("costModel").value = "gemini-3.1-pro-preview";
      updateService();
    });
  }).catch(function (e) { $("tryStatus").textContent = "接口列表加载失败：" + e.message; $("costStatus").textContent = "接口列表加载失败，请刷新重试。"; });
})();
