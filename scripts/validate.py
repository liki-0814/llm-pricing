#!/usr/bin/env python3
"""Sanity-check data/prices.json and verify api/v1/ is in sync.
Usage: python3 scripts/validate.py"""
import json, sys, pathlib, re
sys.dont_write_bytecode = True
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_api  # noqa: E402

p = HERE.parent / "data" / "prices.json"
d = json.load(open(p, encoding="utf-8"))
req = ["id","vendor","model","model_id","currency","input","output","cached_input","cache_write","source_url","last_updated"]
bad = 0
ids, mids = set(), set()
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
def num_ok(v): return v is None or v == "n/a" or (isinstance(v,(int,float)) and not isinstance(v,bool) and v >= 0)
if not DATE.match(str(d["meta"].get("last_updated"))): print("BAD meta.last_updated"); bad += 1
for m in d["models"]:
    for k in req:
        if k not in m: print("MISSING KEY", m.get("model"), k); bad += 1
    if m["id"] in ids: print("DUP ID", m["id"]); bad += 1
    ids.add(m["id"])
    if m.get("model_id") in mids: print("DUP MODEL_ID", m.get("model_id")); bad += 1
    mids.add(m.get("model_id"))
    if not build_api.SLUG_RE.match(str(m.get("model_id"))): print("MODEL_ID NOT URL-SAFE", m.get("model_id")); bad += 1
    if m["currency"] != "USD": print("BAD CURRENCY (USD only)", m["model"]); bad += 1
    if not str(m["source_url"]).startswith("http"): print("BAD SOURCE", m["model"]); bad += 1
    if not DATE.match(str(m.get("last_updated"))): print("BAD DATE", m["model"]); bad += 1
    for k in ("input","output","cached_input","cache_write"):
        if not num_ok(m[k]): print("BAD VALUE", m["model"], k, m[k]); bad += 1
    off = m.get("offpeak")
    if off is not None:
        for k, v in off.items():
            if k not in build_api.OFFPEAK_FIELDS or not num_ok(v): print("BAD OFFPEAK", m["model"], k, v); bad += 1
    re_ = m.get("reasoning_effort")
    if not isinstance(re_, dict): print("MISSING reasoning_effort", m["model"]); bad += 1
    else:
        extra = set(re_) - {"supported","levels","default","can_disable","note","sources"}
        if extra: print("UNKNOWN reasoning_effort keys", m["model"], sorted(extra)); bad += 1
        sup, lv, df = re_.get("supported"), re_.get("levels"), re_.get("default")
        if sup is not None and not isinstance(sup, bool): print("BAD reasoning_effort.supported", m["model"], sup); bad += 1
        if lv is not None and not (isinstance(lv, list) and lv and all(isinstance(x, str) and x for x in lv) and len(set(lv)) == len(lv)):
            print("BAD reasoning_effort.levels", m["model"], lv); bad += 1
        if df is not None and not isinstance(df, str): print("BAD reasoning_effort.default", m["model"], df); bad += 1
        if isinstance(lv, list) and isinstance(df, str) and df not in lv: print("reasoning_effort.default not in levels", m["model"], df); bad += 1
        if sup is None and (lv is not None or df is not None): print("reasoning_effort: supported=null (待核实) but levels/default set", m["model"]); bad += 1
        if sup is False and lv is not None: print("reasoning_effort: supported=false but levels set", m["model"]); bad += 1
        cd = re_.get("can_disable")
        if cd is not None and not isinstance(cd, bool): print("BAD reasoning_effort.can_disable", m["model"], cd); bad += 1
        if not isinstance(re_.get("note"), str) or not re_["note"].strip(): print("reasoning_effort.note required", m["model"]); bad += 1
        srcs = re_.get("sources")
        if not (isinstance(srcs, list) and srcs and all(str(x).startswith("http") for x in srcs)): print("reasoning_effort.sources must be a non-empty list of URLs", m["model"]); bad += 1
        partial = sup is None or (sup is True and lv is None)
        if partial != ("reasoning_effort" in m.get("unverified_fields", [])):
            print("unverified_fields must list reasoning_effort iff it is 待核实/partial", m["model"]); bad += 1
    ct = m.get("context_tokens")
    if ct is not None and not isinstance(ct, int): print("BAD context_tokens", m["model"], ct); bad += 1
    if m["vendor"] not in d["vendors"]: print("UNKNOWN VENDOR", m["vendor"]); bad += 1

    # ---- structured spec fields (limits / tiers / cache / modalities / ...) ----
    def isint(v): return isinstance(v, int) and not isinstance(v, bool) and v >= 0
    def isnum(v): return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0
    def urls_ok(v): return isinstance(v, list) and all(str(x).startswith("http") for x in v)
    def strlist(v): return isinstance(v, list) and all(isinstance(x, str) and x for x in v) and len(set(v)) == len(v)
    for k in ("limits","pricing_tiers","service_tiers","cache_pricing","price_schedule"):
        if k not in m: print("MISSING KEY", m["model"], k); bad += 1
    for k in ("modalities","features","knowledge_cutoff","thinking_budget","availability","snapshot","aliases"):
        if k in m: print("REMOVED FIELD still present", m["model"], k); bad += 1
    L = m.get("limits")
    if not isinstance(L, dict): print("BAD limits", m["model"]); bad += 1
    else:
        extra = set(L) - set(build_api.LIMIT_FIELDS) - {"note", "sources"}
        if extra: print("UNKNOWN limits keys", m["model"], sorted(extra)); bad += 1
        for k in build_api.LIMIT_FIELDS:
            if k not in L or not (L[k] is None or isint(L[k])): print("BAD limits.%s" % k, m["model"], L.get(k)); bad += 1
        if L.get("context_length") != m.get("context_tokens"): print("limits.context_length != context_tokens", m["model"]); bad += 1
        if L.get("max_output_tokens") is not None and L.get("context_length") is not None and L["max_output_tokens"] > L["context_length"]: print("limits.max_output_tokens > context_length", m["model"]); bad += 1
        if not isinstance(L.get("note"), str) or not L["note"].strip(): print("limits.note required (say where the numbers come from / what is 待核实)", m["model"]); bad += 1
        if not (urls_ok(L.get("sources")) and L["sources"]): print("limits.sources must be a non-empty URL list", m["model"]); bad += 1
        for k in ("max_output_tokens", "context_length"):
            if (L.get(k) is None) != (("limits." + k) in m.get("unverified_fields", [])): print("unverified_fields must list limits.%s iff null" % k, m["model"]); bad += 1
    base = {k: m.get(k) for k in ("input", "output", "cached_input", "cache_write")}
    seen_cond = set()
    for t in m.get("pricing_tiers") or []:
        if set(t) != set(build_api.TIER_FIELDS): print("BAD pricing_tiers keys", m["model"], sorted(set(t) ^ set(build_api.TIER_FIELDS))); bad += 1; continue
        if not re.match(r"^input_tokens(>|<=)\d+( and input_tokens(>|<=)\d+)?$", str(t["condition"])): print("BAD tier condition", m["model"], t["condition"]); bad += 1
        if t["condition"] in seen_cond: print("DUP tier condition", m["model"], t["condition"]); bad += 1
        seen_cond.add(t["condition"])
        if not (isint(t["input_tokens_gt"]) and (t["input_tokens_lte"] is None or (isint(t["input_tokens_lte"]) and t["input_tokens_lte"] > t["input_tokens_gt"]))): print("BAD tier bounds", m["model"], t["condition"]); bad += 1
        if ("input_tokens>%s" % t["input_tokens_gt"]) not in t["condition"]: print("tier condition/bounds mismatch", m["model"], t["condition"]); bad += 1
        for k in ("input", "output", "cached_input", "cache_write"):
            if not (t[k] is None or isnum(t[k])): print("BAD tier price", m["model"], t["condition"], k, t[k]); bad += 1
        if t["input"] is None or t["output"] is None: print("tier needs input and output", m["model"], t["condition"]); bad += 1
        if isnum(t["input"]) and isnum(base["input"]) and t["input"] < base["input"]: print("tier input below base price", m["model"], t["condition"]); bad += 1
        if t["cache_pricing"] is not None and set(t["cache_pricing"]) != set(build_api.CACHE_FIELDS): print("BAD tier cache_pricing keys", m["model"]); bad += 1
    names = set()
    for t in m.get("service_tiers") or []:
        if set(t) != {"name", "multiplier", "note"}: print("BAD service_tiers keys", m["model"], sorted(t)); bad += 1; continue
        if t["name"] not in build_api.SERVICE_TIER_NAMES: print("BAD service tier name", m["model"], t["name"]); bad += 1
        if t["name"] in names: print("DUP service tier", m["model"], t["name"]); bad += 1
        names.add(t["name"])
        if not (isnum(t["multiplier"]) and t["multiplier"] > 0): print("BAD service tier multiplier", m["model"], t["name"], t["multiplier"]); bad += 1
    C = m.get("cache_pricing")
    if not isinstance(C, dict) or set(C) != set(build_api.CACHE_FIELDS): print("BAD cache_pricing keys", m["model"]); bad += 1
    else:
        for k in build_api.CACHE_FIELDS[:-1]:
            if not (C[k] is None or isnum(C[k])): print("BAD cache_pricing.%s" % k, m["model"], C[k]); bad += 1
        if isnum(C["explicit_write"]) and isnum(m["cache_write"]) and C["explicit_write"] != m["cache_write"]: print("cache_pricing.explicit_write != cache_write", m["model"]); bad += 1
        if isnum(m["cached_input"]) and (C["implicit_read"] is not None or C["explicit_read"] is not None) and m["cached_input"] not in (C["implicit_read"], C["explicit_read"]):
            print("cached_input must equal cache_pricing.implicit_read or explicit_read", m["model"]); bad += 1
        if C["implicit_read"] is not None and C["explicit_read"] is not None and not str(C.get("note") or "").strip(): print("cache_pricing.note must say which one pricing.cached_input is", m["model"]); bad += 1
    for e in m.get("price_schedule") or []:
        if e.get("kind") not in build_api.SCHEDULE_KINDS or not set(e) >= {"kind", "effective_from", "effective_until", "note"}: print("BAD price_schedule", m["model"]); bad += 1; continue
        for k in ("effective_from", "effective_until"):
            if e[k] is not None and not DATE.match(str(e[k])): print("BAD price_schedule date", m["model"], k, e[k]); bad += 1
        for k in ("input", "output", "cached_input", "cache_write"):
            if e.get(k) is not None and not isnum(e[k]): print("BAD price_schedule price", m["model"], k); bad += 1
    # principle: a fact stated only in notes must also be structured -> long-context price tiers
    if re.search(r"[>＞]\s*\d+\s*[KkMm]\b", m.get("notes") or "") and not m.get("pricing_tiers"):
        print("notes mention a '>NNK' tier but pricing_tiers is empty (promote it to a structured field)", m["model"]); bad += 1
for v in d["vendors"]:
    if v not in build_api.VENDOR_SLUGS: print("NO API SLUG FOR VENDOR (scripts/build_api.py VENDOR_SLUGS)", v); bad += 1
print(f'{len(d["models"])} models, {bad} data problem(s)')
tbd = [(m["model"], f) for m in d["models"] for f in m.get("unverified_fields", [])]
print("unverified (待核实):", len(tbd))
for n,f in tbd: print("  -", n, f)

api_probs = build_api.check(d) if not bad else ["(skipped api check: fix data problems first)"]
for x in api_probs[:20]: print("API", x)
if len(api_probs) > 20: print("API ... and", len(api_probs) - 20, "more")
print("api/v1: in sync" if not api_probs else "api/v1: OUT OF SYNC -> run python3 scripts/build_api.py")
sys.exit(1 if bad or api_probs else 0)
