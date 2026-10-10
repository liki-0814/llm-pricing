/* Shared: theme toggle, vendor colors, toast, clipboard. Loaded on every page. */
(function () {
  "use strict";
  var root = document.documentElement;
  function apply(t) {
    root.setAttribute("data-theme", t);
    var b = document.querySelector(".theme-toggle");
    if (b) b.setAttribute("aria-label", t === "dark" ? "切换到浅色模式" : "切换到深色模式");
  }
  apply(root.getAttribute("data-theme") || "light");
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest(".theme-toggle");
    if (!b) return;
    var t = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    apply(t);
    try { localStorage.setItem("theme", t); } catch (_) {}
  });
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var onChange = function (e) {
      var saved = null; try { saved = localStorage.getItem("theme"); } catch (_) {}
      if (!saved) apply(e.matches ? "dark" : "light");
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
  }

  // Vendor display name -> slug (same slugs as scripts/build_api.py VENDOR_SLUGS)
  var SLUGS = {
    "DeepSeek": "deepseek", "OpenAI": "openai", "Anthropic": "anthropic", "智谱 Z.ai": "zhipu",
    "Moonshot Kimi": "moonshot", "阿里云 Qwen": "qwen", "Google Gemini": "google", "MiniMax": "minimax"
  };
  function slug(name) {
    return SLUGS[name] || String(name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "other";
  }
  var toastTimer;
  function toast(msg) {
    var el = document.getElementById("toast");
    if (!el) { el = document.createElement("div"); el.id = "toast"; el.className = "toast"; el.setAttribute("role", "status"); document.body.appendChild(el); }
    el.textContent = msg; el.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { el.classList.remove("show"); }, 1600);
  }
  function copy(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (res, rej) {
      var ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy") ? res() : rej(); } catch (e) { rej(e); } finally { ta.remove(); }
    });
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  window.LP = { slug: slug, toast: toast, copy: copy, esc: esc };
})();
