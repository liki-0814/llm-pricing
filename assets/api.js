(function () {
  "use strict";
  var esc = LP.esc, $ = function (id) { return document.getElementById(id); };
  var BASE = new URL("api/v1/", location.href).href;
  $("baseUrl").textContent = BASE;

  // ---------- examples (base URL filled in) ----------
  var EX = {
    curl:
      "# 全部模型\ncurl -s " + BASE + "models.json\n\n" +
      "# 单个模型 / 单个厂商\ncurl -s " + BASE + "models/deepseek-flash.json\ncurl -s " + BASE + "vendors/anthropic.json\n\n" +
      "# 配合 jq：输入价最低的 5 个模型\ncurl -s " + BASE + "models.json \\\n  | jq -r '.data | map(select(.pricing.input != null)) | sort_by(.pricing.input) | .[:5][] | \"\\(.id)\\t$\\(.pricing.input)\"'",
    js:
      'const BASE = "' + BASE + '";\n\n' +
      "const res = await fetch(BASE + \"models.json\");\nconst { meta, data } = await res.json();\n" +
      "console.log(`更新于 ${meta.updated_at}，共 ${meta.count} 个模型（${meta.unit_label}）`);\n\n" +
      "// 客户端筛选：OpenAI 模型按输出价升序\nconst openai = data\n  .filter(m => m.vendor === \"openai\" && m.pricing.output != null)\n  .sort((a, b) => a.pricing.output - b.pricing.output);\nconsole.table(openai.map(m => ({ id: m.id, input: m.pricing.input, output: m.pricing.output })));\n\n" +
      "// 估算一次调用费用（USD）\nconst cost = (m, inTok, outTok) => (inTok * m.pricing.input + outTok * m.pricing.output) / 1e6;",
    py:
      "import json, urllib.request\n\nBASE = \"" + BASE + "\"\n\n" +
      "def get(path):\n    with urllib.request.urlopen(BASE + path) as r:\n        return json.load(r)\n\n" +
      "models = get(\"models.json\")\nprint(models[\"meta\"][\"updated_at\"], models[\"meta\"][\"count\"])\n\n" +
      "# 输入价最低的 5 个模型（跳过 null = 待核实 / 未列出）\npriced = [m for m in models[\"data\"] if m[\"pricing\"][\"input\"] is not None]\n" +
      "for m in sorted(priced, key=lambda m: m[\"pricing\"][\"input\"])[:5]:\n    print(f'{m[\"id\"]:<28} in ${m[\"pricing\"][\"input\"]}  out ${m[\"pricing\"][\"output\"]}')\n\n" +
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
    if (s.length > 120000) s = s.slice(0, 120000) + "\n… (已截断显示)";
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
      code: 'const { data } = await (await fetch(BASE + "models.json")).json();\nreturn data\n  .filter(m => m.pricing.input != null)\n  .sort((a, b) => a.pricing.input - b.pricing.input)\n  .slice(0, 5)\n  .map(m => ({ id: m.id, vendor: m.vendor, input: m.pricing.input, output: m.pricing.output }));',
      run: function (d) {
        return d.data.filter(function (m) { return m.pricing.input != null; })
          .sort(function (a, b) { return a.pricing.input - b.pricing.input; }).slice(0, 5)
          .map(function (m) { return { id: m.id, vendor: m.vendor, input: m.pricing.input, output: m.pricing.output }; });
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
  var vendors = [], modelIds = [];
  function fillParam() {
    var v = $("tryPreset").value, p = $("tryParam");
    var list = v === "vendor" ? vendors : v === "model" ? modelIds : null;
    p.hidden = !list;
    if (list) p.innerHTML = list.map(function (x) { return '<option value="' + esc(x) + '">' + esc(x) + "</option>"; }).join("");
    updateUrl();
  }
  function updateUrl() {
    var v = $("tryPreset").value, path = v;
    if (v === "vendor") path = "vendors/" + ($("tryParam").value || "openai") + ".json";
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

  fetch(BASE + "vendors.json").then(function (r) { return r.json(); }).then(function (d) {
    $("footUpdated").textContent = d.meta.updated_at;
    vendors = d.data.map(function (v) { return v.slug; });
    d.data.forEach(function (v) { modelIds = modelIds.concat(v.model_ids); });
    $("slugList").innerHTML = "可用 <code>vendor</code>：" + d.data.map(function (v) {
      return '<a href="api/v1/vendors/' + esc(v.slug) + '.json"><code>' + esc(v.slug) + "</code></a>（" + esc(v.name) + "，" + v.model_count + "）";
    }).join("、") + "。全部 <code>model_id</code> 见 <a href=\"api/v1/vendors.json\">vendors.json</a> 的 <code>model_ids</code>。";
    fillParam();
  }).catch(function () {});
})();
