#!/usr/bin/env python3
"""Generate the static JSON query API under api/v1/ from data/prices.json.

Usage:
    python3 scripts/build_api.py          # (re)generate api/v1/
    python3 scripts/build_api.py --check  # exit 1 if api/v1/ is out of sync

Output is deterministic (no generation timestamps), so validate.py can verify
that the committed API files match data/prices.json exactly.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "prices.json"
API_DIR = ROOT / "api" / "v1"
API_VERSION = "v1"
UNIT = "per_1M_tokens"
UNIT_LABEL = "USD per 1M tokens"
PRICE_FIELDS = ("input", "output", "cached_input", "cache_write")
OFFPEAK_FIELDS = ("input", "output", "cached_input")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]*$")

# Stable, URL-safe slugs for each vendor in data/prices.json -> vendors.
# Adding a vendor to prices.json requires adding its slug here.
VENDOR_SLUGS = {
    "DeepSeek": "deepseek",
    "OpenAI": "openai",
    "Anthropic": "anthropic",
    "智谱 Z.ai": "zhipu",
    "Moonshot Kimi": "moonshot",
    "阿里云 Qwen": "qwen",
    "Google Gemini": "google",
}


def load():
    return json.load(open(DATA, encoding="utf-8"))


def price_value(v):
    """data value -> (number|null, status)."""
    if v is None:
        return None, "unverified"
    if v == "n/a":
        return None, "not_listed"
    return v, "verified"


def model_obj(m):
    pricing, status = {}, {}
    for k in PRICE_FIELDS:
        pricing[k], status[k] = price_value(m.get(k))
    off = m.get("offpeak")
    off_pricing = None
    if off:
        off_pricing = {k: off.get(k) for k in OFFPEAK_FIELDS}
    return {
        "id": m["model_id"],
        "name": m["model"],
        "vendor": VENDOR_SLUGS[m["vendor"]],
        "vendor_name": m["vendor"],
        "currency": m["currency"],
        "unit": UNIT,
        "pricing": pricing,
        "pricing_status": status,
        "has_off_peak": off_pricing is not None,
        "off_peak_pricing": off_pricing,
        "peak_note": m.get("peak_note"),
        "context_length": m.get("context_tokens"),
        "context_length_label": m.get("context_length"),
        "source_url": m["source_url"],
        "extra_sources": list(m.get("extra_sources") or []),
        "last_updated": m.get("last_updated"),
        "notes": m.get("notes"),
        "unverified_fields": list(m.get("unverified_fields") or []),
        "links": {"self": "models/%s.json" % m["model_id"],
                  "vendor": "vendors/%s.json" % VENDOR_SLUGS[m["vendor"]]},
    }


def base_meta(d, count=None):
    meta = {
        "updated_at": d["meta"]["last_updated"],
        "currency": "USD",
        "unit": UNIT,
        "unit_label": UNIT_LABEL,
    }
    if count is not None:
        meta["count"] = count
    return meta


def vendor_obj(d, name, models):
    slug = VENDOR_SLUGS[name]
    srcs = []
    for m in models:
        if m["source_url"] not in srcs:
            srcs.append(m["source_url"])
    return {
        "slug": slug,
        "name": name,
        "model_count": len(models),
        "model_ids": [m["model_id"] for m in models],
        "source_urls": srcs,
        "links": {"self": "vendors/%s.json" % slug},
    }


def openapi(d, vendor_slugs, model_ids):
    price = {"type": ["number", "null"], "minimum": 0,
             "description": "USD per 1M tokens; null when not listed or unverified (see pricing_status)"}
    status = {"type": "string", "enum": ["verified", "unverified", "not_listed"],
              "description": "verified = from official page; unverified = 待核实 (could not be verified); not_listed = official page has no such item (未列出)"}
    meta = {
        "type": "object",
        "required": ["updated_at", "currency", "unit", "unit_label"],
        "properties": {
            "updated_at": {"type": "string", "format": "date", "description": "Dataset last-verified date"},
            "currency": {"type": "string", "enum": ["USD"]},
            "unit": {"type": "string", "enum": [UNIT]},
            "unit_label": {"type": "string"},
            "count": {"type": "integer", "description": "Number of items in data"},
            "scope": {"type": "string"},
            "description": {"type": "string"},
        },
    }
    model = {
        "type": "object",
        "required": ["id", "name", "vendor", "vendor_name", "currency", "unit", "pricing",
                     "pricing_status", "has_off_peak", "off_peak_pricing", "peak_note",
                     "context_length", "context_length_label", "source_url", "extra_sources",
                     "last_updated", "notes", "unverified_fields", "links"],
        "properties": {
            "id": {"type": "string", "description": "Model id as used in the vendor API; also the file name of /models/{model_id}.json"},
            "name": {"type": "string", "description": "Display name"},
            "vendor": {"type": "string", "description": "Vendor slug", "enum": vendor_slugs},
            "vendor_name": {"type": "string"},
            "currency": {"type": "string", "enum": ["USD"]},
            "unit": {"type": "string", "enum": [UNIT]},
            "pricing": {"type": "object", "description": "Standard price (peak price when off-peak pricing exists)",
                        "required": list(PRICE_FIELDS),
                        "properties": {
                            "input": price, "output": price,
                            "cached_input": dict(price, description="Cache hit / cache read price"),
                            "cache_write": dict(price, description="Cache write (creation) price"),
                        }},
            "pricing_status": {"type": "object", "required": list(PRICE_FIELDS),
                               "properties": {k: status for k in PRICE_FIELDS}},
            "has_off_peak": {"type": "boolean"},
            "off_peak_pricing": {"type": ["object", "null"], "description": "Off-peak (闲时) price, null if none",
                                 "properties": {k: price for k in OFFPEAK_FIELDS}},
            "peak_note": {"type": ["string", "null"], "description": "Peak / off-peak schedule or time-limited price note"},
            "context_length": {"type": ["integer", "null"], "description": "Context window in tokens"},
            "context_length_label": {"type": ["string", "null"]},
            "source_url": {"type": "string", "format": "uri", "description": "Official pricing page"},
            "extra_sources": {"type": "array", "items": {"type": "string", "format": "uri"}},
            "last_updated": {"type": "string", "format": "date"},
            "notes": {"type": ["string", "null"]},
            "unverified_fields": {"type": "array", "items": {"type": "string"}},
            "links": {"type": "object", "properties": {"self": {"type": "string"}, "vendor": {"type": "string"}}},
        },
    }
    vendor = {
        "type": "object",
        "required": ["slug", "name", "model_count", "model_ids", "source_urls", "links"],
        "properties": {
            "slug": {"type": "string", "enum": vendor_slugs},
            "name": {"type": "string"},
            "model_count": {"type": "integer"},
            "model_ids": {"type": "array", "items": {"type": "string"}},
            "source_urls": {"type": "array", "items": {"type": "string", "format": "uri"}},
            "links": {"type": "object", "properties": {"self": {"type": "string"}}},
        },
    }
    def env(data_schema):
        return {"type": "object", "required": ["api_version", "meta", "data"],
                "properties": {"api_version": {"type": "string", "enum": [API_VERSION]},
                               "meta": {"$ref": "#/components/schemas/Meta"}, "data": data_schema}}
    def ok(desc, ref):
        return {"200": {"description": desc, "content": {"application/json": {"schema": {"$ref": ref}}}},
                "404": {"description": "Unknown vendor / model (GitHub Pages 404 page, not JSON)"}}
    vendor_env = env({"type": "array", "items": {"$ref": "#/components/schemas/Model"}})
    vendor_env["required"].append("vendor")
    vendor_env["properties"]["vendor"] = {"$ref": "#/components/schemas/Vendor"}
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "LLM API Pricing (static JSON API)",
            "version": "1.0.0",
            "description": ("Read-only static JSON files generated from data/prices.json by scripts/build_api.py "
                            "and served by GitHub Pages. All prices are USD per 1M tokens. Only GET is supported; "
                            "there is no server-side filtering or query parameters, filter on the client. "
                            "CORS: GitHub Pages sends Access-Control-Allow-Origin: * so files can be fetched from any origin. "
                            "Dataset updated_at: %s." % d["meta"]["last_updated"]),
        },
        "servers": [{"url": ".", "description": "Relative to this openapi.json (…/api/v1/)"},
                    {"url": "https://{user}.github.io/{repo}/api/v1",
                     "variables": {"user": {"default": "your-user"}, "repo": {"default": "llm-pricing"}}}],
        "paths": {
            "/models.json": {"get": {"operationId": "listModels", "summary": "All models",
                                     "responses": ok("All models", "#/components/schemas/ModelList")}},
            "/models/{model_id}.json": {"get": {
                "operationId": "getModel", "summary": "One model by id",
                "parameters": [{"name": "model_id", "in": "path", "required": True,
                                "schema": {"type": "string", "enum": model_ids}}],
                "responses": ok("One model", "#/components/schemas/ModelItem")}},
            "/vendors.json": {"get": {"operationId": "listVendors", "summary": "All vendors",
                                      "responses": ok("All vendors", "#/components/schemas/VendorList")}},
            "/vendors/{vendor}.json": {"get": {
                "operationId": "getVendor", "summary": "One vendor and its models",
                "parameters": [{"name": "vendor", "in": "path", "required": True,
                                "schema": {"type": "string", "enum": vendor_slugs}}],
                "responses": ok("Vendor with its models", "#/components/schemas/VendorModels")}},
        },
        "components": {"schemas": {
            "Meta": meta, "Model": model, "Vendor": vendor,
            "ModelList": env({"type": "array", "items": {"$ref": "#/components/schemas/Model"}}),
            "ModelItem": env({"$ref": "#/components/schemas/Model"}),
            "VendorList": env({"type": "array", "items": {"$ref": "#/components/schemas/Vendor"}}),
            "VendorModels": vendor_env,
        }},
    }


def build(d):
    """Return {relative path under api/v1: python object}."""
    missing = [v for v in d["vendors"] if v not in VENDOR_SLUGS]
    if missing:
        raise SystemExit("build_api: no slug for vendor(s) %s; add to VENDOR_SLUGS in scripts/build_api.py" % missing)
    out = {}
    models = d["models"]
    objs = [model_obj(m) for m in models]
    for o in objs:
        if not SLUG_RE.match(o["id"]):
            raise SystemExit("build_api: model_id %r is not URL-safe" % o["id"])
    meta = base_meta(d, len(objs))
    meta["scope"] = d["meta"].get("scope")
    meta["description"] = d["meta"].get("description")
    out["models.json"] = {"api_version": API_VERSION, "meta": meta, "data": objs}
    vendors = []
    for name in d["vendors"]:
        vm = [m for m in models if m["vendor"] == name]
        v = vendor_obj(d, name, vm)
        vendors.append(v)
        out["vendors/%s.json" % v["slug"]] = {
            "api_version": API_VERSION, "meta": base_meta(d, len(vm)), "vendor": v,
            "data": [o for o in objs if o["vendor"] == v["slug"]]}
    out["vendors.json"] = {"api_version": API_VERSION, "meta": base_meta(d, len(vendors)), "data": vendors}
    for o in objs:
        out["models/%s.json" % o["id"]] = {"api_version": API_VERSION, "meta": base_meta(d), "data": o}
    out["openapi.json"] = openapi(d, [v["slug"] for v in vendors], [o["id"] for o in objs])
    return out


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def existing_files():
    return {str(p.relative_to(API_DIR)).replace("\\", "/") for p in API_DIR.rglob("*.json")} if API_DIR.exists() else set()


def check(d=None):
    """Return list of problems (empty = in sync)."""
    files = build(d or load())
    problems = []
    for rel, obj in files.items():
        p = API_DIR / rel
        if not p.exists():
            problems.append("missing api/v1/" + rel)
        elif p.read_text(encoding="utf-8") != dump(obj):
            problems.append("stale api/v1/" + rel)
    for rel in sorted(existing_files() - set(files)):
        problems.append("orphan api/v1/" + rel)
    return problems


def main():
    if "--check" in sys.argv:
        probs = check()
        for p in probs:
            print(p)
        print("api in sync" if not probs else "%d api problem(s); run python3 scripts/build_api.py" % len(probs))
        sys.exit(1 if probs else 0)
    files = build(load())
    for rel in existing_files() - set(files):
        (API_DIR / rel).unlink()
    for rel, obj in files.items():
        p = API_DIR / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        s = dump(obj)
        if not p.exists() or p.read_text(encoding="utf-8") != s:
            p.write_text(s, encoding="utf-8")
    print("wrote %d files to %s" % (len(files), API_DIR.relative_to(ROOT)))


if __name__ == "__main__":
    main()
