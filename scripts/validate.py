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
    ct = m.get("context_tokens")
    if ct is not None and not isinstance(ct, int): print("BAD context_tokens", m["model"], ct); bad += 1
    if m["vendor"] not in d["vendors"]: print("UNKNOWN VENDOR", m["vendor"]); bad += 1
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
