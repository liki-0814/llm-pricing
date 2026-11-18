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
import copy
import hashlib
import subprocess
import datetime as dt

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "prices.json"
API_DIR = ROOT / "api" / "v1"
API_VERSION = "v1"
UNIT = "per_1M_tokens"
UNIT_LABEL = "per 1M tokens; use each model.currency (no currency conversion)"
MEDIA_UNIT = "see_media_pricing"
MEDIA_UNIT_LABEL = "model.currency; see each model's media_pricing (per image / per second of video / per 1M tokens)"
MODALITIES = ("text", "image", "video")
MODALITY_LABELS = {"text": "文本生成（token 计价）", "image": "图像生成", "video": "视频生成"}
BILLING_METHODS = ("token", "per_image", "per_second")
PRICE_TIERS = ("standard", "batch")
VIDEO_AUDIO = ("with_audio", "without_audio", "any")
TOKEN_PRICE_FIELDS = ("text_input", "text_cached_input", "text_output", "image_input", "image_cached_input",
                      "image_output", "video_input", "video_output", "audio_input")
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
    "MiniMax": "minimax",
    "xAI": "xai",
    "腾讯混元": "tencent",
}


def load():
    return json.loads(DATA.read_text(encoding="utf-8"))


def price_value(v):
    """data value -> (number|null, status)."""
    if v is None:
        return None, "unverified"
    if v == "n/a":
        return None, "not_listed"
    return v, "verified"



LIMIT_FIELDS = ("context_length", "max_output_tokens")
TIER_FIELDS = ("condition", "input_tokens_gt", "input_tokens_lte", "input", "output", "cached_input",
               "cache_write", "cache_pricing", "note")
CACHE_FIELDS = ("implicit_read", "explicit_read", "explicit_write", "explicit_write_1h", "explicit_write_12h",
                "storage_per_1M_tokens_hour", "note")
SERVICE_TIER_NAMES = ("batch", "flex", "fast", "priority", "ultrafast", "data_residency")
SCHEDULE_KINDS = ("promotion", "scheduled_increase", "scheduled_decrease")


def limits_obj(m):
    """Numeric limits, or null; source n/a means a documented absent output cap."""
    L = m.get("limits") or {}
    o = {k: None if L.get(k) == "n/a" else L.get(k) for k in LIMIT_FIELDS}
    vals = [L.get(k) for k in LIMIT_FIELDS]
    o["status"] = ("verified" if all(x is not None for x in vals)
                   else "partial" if any(x is not None for x in vals) else "unverified")
    o["note"] = L.get("note")
    o["sources"] = list(L.get("sources") or [])
    return o


def cache_obj(c):
    c = c or {}
    return {k: c.get(k) for k in CACHE_FIELDS}


def tier_obj(t):
    o = {k: t.get(k) for k in TIER_FIELDS}
    o["cache_pricing"] = cache_obj(t["cache_pricing"]) if t.get("cache_pricing") else None
    return o


def schedule_obj(e):
    return {"kind": e.get("kind"), "effective_from": e.get("effective_from"),
            "effective_until": e.get("effective_until"), "input": e.get("input"), "output": e.get("output"),
            "cached_input": e.get("cached_input"), "cache_write": e.get("cache_write"), "note": e.get("note"),
            "multiplier": e.get("multiplier"), "cache_pricing": e.get("cache_pricing", {}),
            "sources": e.get("sources", []),
            **{k: e[k] for k in ("effective_until_precision", "effective_until_timezone") if k in e}}


def reasoning_obj(m):
    """data reasoning_effort -> API object. null = 待核实 (never guessed)."""
    r = m.get("reasoning_effort")
    if r is None:
        r = {}
    sup, levels = r.get("supported"), r.get("levels")
    field_status = {k: ("not_applicable" if sup is False and k in ("levels", "default")
                        else "unverified" if r.get(k) is None else "verified")
                    for k in ("supported", "levels", "default", "can_disable")}
    status = "unverified" if sup is None else "partial" if "unverified" in field_status.values() else "verified"
    return {
        "supported": sup,
        "levels": list(levels) if levels is not None else None,
        "default": r.get("default"),
        "can_disable": r.get("can_disable"),
        "status": status,
        "field_status": field_status,
        "note": r.get("note"),
        "sources": list(r.get("sources") or []),
    }


def media_obj(mp):
    """Source media_pricing -> API object (explicit keys, stable order)."""
    def tokens(t):
        return None if t is None else {k: t.get(k) for k in TOKEN_PRICE_FIELDS}
    tp = mp.get("token_pricing")
    return {
        "output_kind": mp["output_kind"],
        "billing_methods": list(mp["billing_methods"]),
        "token_pricing": None if tp is None else {"unit": "per_1M_tokens", "standard": tokens(tp["standard"]),
                                                  "batch": tokens(tp.get("batch")), "priority": tokens(tp.get("priority"))},
        "image_prices": [{k: e.get(k) for k in ("tier", "size", "quality", "price", "tokens", "basis", "note")}
                         for e in mp.get("image_prices") or []],
        "video_prices": [{k: e.get(k) for k in ("tier", "resolution", "audio", "price_per_second",
                                                "tokens_per_second",
                                                "input_video_price_per_second", "basis", "note")}
                         for e in mp.get("video_prices") or []],
        "input_image_price": mp.get("input_image_price"),
        "input_image_price_batch": mp.get("input_image_price_batch"),
        **({"input_image_allowance": copy.deepcopy(mp["input_image_allowance"])} if "input_image_allowance" in mp else {}),
        "batch_supported": mp.get("batch_supported"),
        "promotion": copy.deepcopy(mp.get("promotion")),
        "billing_note": mp["billing_note"],
        "sources": list(mp["sources"]),
    }


def media_na_objects(m):
    """Text-only structures are not applicable to image / video models."""
    na = {k: "not_applicable" for k in ("supported", "levels", "default", "can_disable")}
    reasoning = {"supported": False, "levels": None, "default": None, "can_disable": None,
                 "status": "not_applicable", "field_status": na,
                 "note": "Not applicable: %s generation model." % m["modality"], "sources": list(m["media_pricing"]["sources"])}
    limits = {"context_length": None, "max_output_tokens": None, "status": "not_applicable",
              "note": "Not applicable: %s generation model (no token context window)." % m["modality"],
              "sources": list(m["media_pricing"]["sources"])}
    return reasoning, limits


def model_obj(m):
    pricing, status = {}, {}
    modality = m["modality"]
    for k in PRICE_FIELDS:
        if modality != "text":
            pricing[k], status[k] = None, "not_applicable"
            continue
        pricing[k], status[k] = price_value(m.get(k))
        if status[k] == "verified" and m["price_basis"]["type"] == "reference":
            status[k] = "reference"
    off = m.get("offpeak")
    off_pricing = None
    if off:
        off_pricing = {k: off.get(k) for k in OFFPEAK_FIELDS}
    if modality == "text":
        reasoning, limits, media = reasoning_obj(m), limits_obj(m), None
    else:
        reasoning, limits = media_na_objects(m)
        media = media_obj(m["media_pricing"])
    return {
        "id": m["model_id"],
        "name": m["model"],
        "vendor": VENDOR_SLUGS[m["vendor"]],
        "vendor_name": m["vendor"],
        "modality": modality,
        "lifecycle": copy.deepcopy(m.get("lifecycle")),
        "token_offer": copy.deepcopy(m.get("token_offer")),
        "estimation_limits": copy.deepcopy(m.get("estimation_limits")),
        "currency": m["currency"],
        "unit": UNIT if modality == "text" else MEDIA_UNIT,
        "pricing": pricing,
        "pricing_status": status,
        "price_basis": copy.deepcopy(m["price_basis"]),
        "billing": copy.deepcopy(m["billing"]),
        "off_peak_schedule": copy.deepcopy(m.get("off_peak_schedule")),
        "has_off_peak": off_pricing is not None,
        "off_peak_pricing": off_pricing,
        "peak_note": m.get("peak_note"),
        "context_length": m.get("context_tokens"),
        "context_length_label": m.get("context_length"),
        "source_url": m["source_url"],
        "extra_sources": list(m.get("extra_sources") or []),
        "last_updated": m.get("last_updated"),
        "price_observations": copy.deepcopy(m.get("price_observations", [])),
        "notes": m.get("notes"),
        "reasoning_effort": reasoning,
        "limits": limits,
        "media_pricing": media,
        "pricing_tiers": [tier_obj(t) for t in m.get("pricing_tiers") or []],
        "service_tiers": copy.deepcopy(m.get("service_tiers") or []),
        "cache_pricing": cache_obj(m.get("cache_pricing")),
        "price_schedule": [schedule_obj(e) for e in m.get("price_schedule") or []],
        "unverified_fields": list(m.get("unverified_fields") or []),
        "links": {"self": "models/%s.json" % m["model_id"],
                  "vendor": "vendors/%s.json" % VENDOR_SLUGS[m["vendor"]]},
    }


def next_invalidation(d):
    at = dt.datetime.fromisoformat(d["meta"].get("availability_as_of", d["meta"]["last_updated"] + "T00:00:00+08:00").replace("Z", "+00:00"))
    candidates = []
    for m in d["models"]:
        life = m.get("lifecycle") or {}
        if life.get("retired_at") and not life.get("conflict"):
            candidates.append(dt.datetime.fromisoformat(life["retired_at"].replace("Z", "+00:00")))
        for event in m.get("price_schedule", []):
            if event.get("effective_until_precision") == "date" and event.get("effective_until"):
                candidates.append(dt.datetime.fromisoformat(event["effective_until"] + "T00:00:00+00:00") - dt.timedelta(hours=14))
        for service in m.get("service_tiers", []):
            for event in service.get("multiplier_schedule", []):
                candidates.append(dt.datetime.fromisoformat(event["effective_from"].replace("Z", "+00:00")))
        for evidence in m.get("price_observations", []):
            for key in ("valid_until",):
                if evidence.get(key):
                    candidates.append(dt.datetime.fromisoformat(evidence[key].replace("Z", "+00:00")))
        if m.get("token_offer"):
            candidates.append(dt.datetime.fromisoformat(m["token_offer"]["valid_until"].replace("Z", "+00:00")) + dt.timedelta(milliseconds=1))
    future = [t for t in candidates if t > at]
    return min(future).isoformat() if future else None


def base_meta(d, count=None):
    meta = {
        "updated_at": d["meta"]["last_updated"],
        "as_of": d["meta"].get("availability_as_of", d["meta"]["last_updated"] + "T00:00:00+08:00"),
        "source_commit": d["meta"].get("source_commit"),
        "next_invalidation": next_invalidation(d),
        "availability_as_of": d["meta"].get("availability_as_of", d["meta"]["last_updated"] + "T00:00:00+08:00"),
        "currency": "mixed" if len({m["currency"] for m in d["models"]}) > 1 else d["models"][0]["currency"],
        "unit": UNIT,
        "unit_label": UNIT_LABEL,
        "data_version": hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False,
                                                  separators=(",", ":")).encode()).hexdigest(),
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
        "modality_counts": {k: sum(1 for m in models if m["modality"] == k) for k in MODALITIES},
        "source_urls": srcs,
        "links": {"self": "vendors/%s.json" % slug},
    }


def media_pricing_schema():
    """Structured non-token billing for image / video generation models (each model.currency)."""
    def obj(properties, required=None):
        return {"type": "object", "properties": properties,
                "required": list(properties) if required is None else required,
                "additionalProperties": False}
    usd = {"type": ["number", "null"], "minimum": 0}
    tok = dict(usd, description="model.currency per 1M tokens; null = not billed separately / not applicable for this model")
    tier = {"enum": list(PRICE_TIERS), "description": "standard = on-demand list price; batch = Batch API list price"}
    urls = {"type": "array", "minItems": 1, "uniqueItems": True,
            "items": {"type": "string", "format": "uri", "pattern": "^https?://"}}
    token_prices = obj({k: tok for k in TOKEN_PRICE_FIELDS})
    return obj({
        "output_kind": {"enum": ["image", "video"]},
        "billing_methods": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"enum": list(BILLING_METHODS)},
                            "description": "Official billing dimensions: token (token_pricing), per_image (image_prices), per_second (video_prices)"},
        "token_pricing": {"anyOf": [{"type": "null"}, obj({
            "unit": {"enum": ["per_1M_tokens"]},
            "standard": token_prices,
            "batch": {"anyOf": [{"type": "null"}, token_prices]},
            "priority": {"anyOf": [{"type": "null"}, token_prices]}})],
            "description": "Per-modality token prices where the vendor bills tokens (OpenAI GPT Image, Gemini image/video); null otherwise"},
        "image_prices": {"type": "array", "description": "model.currency per generated image by size x quality x tier. Empty + listed in unverified_fields = per-image price 待核实.",
                         "items": obj({
                             "tier": tier,
                             "size": {"type": "string", "minLength": 1, "description": "Resolution tier label (0.5k, 1k, 1.5k, 2k, 4k), lowercase; \"any\" = one flat price regardless of size"},
                             "quality": {"type": ["string", "null"], "description": "Quality setting (low / medium / high ...); null = no quality dimension"},
                             "price": dict(usd, description="model.currency per image; null = 待核实 (listed in unverified_fields)"),
                             "tokens": {"type": ["integer", "null"], "minimum": 1, "description": "Output tokens the vendor documents for this image (token-priced models)"},
                             "basis": {"enum": ["listed", "token_equivalent"], "description": "listed = price printed by the vendor; token_equivalent = per-image figure printed by the vendor as the token cost equivalent"},
                             "note": {"type": ["string", "null"]}})},
        "video_prices": {"type": "array", "description": "model.currency per second of generated video by resolution x audio x tier. Empty + listed in unverified_fields = 待核实.",
                         "items": obj({
                             "tier": tier,
                             "resolution": {"type": "string", "minLength": 1, "description": "Output resolution label, lowercase (480p, 720p, 768p, 1080p, 2k, 4k ...)"},
                             "audio": {"enum": list(VIDEO_AUDIO), "description": "with_audio / without_audio = separate official prices; any = the official price does not distinguish audio"},
                             "price_per_second": dict(usd, description="model.currency per second of output video; null = 待核实"),
                             "tokens_per_second": {"type": ["integer", "null"], "minimum": 1, "description": "Tokens per second where the vendor bills video by tokens"},
                             "input_video_price_per_second": dict(usd, description="model.currency per second of input (source) video at this output resolution when the vendor bills input video; null = not billed"),
                             "basis": {"enum": ["listed", "token_equivalent", "approximate"], "description": "approximate = vendor publishes only an approximate per-second figure"},
                             "note": {"type": ["string", "null"]}})},
        "input_image_price": dict(usd, description="model.currency per input / reference image (editing, image-to-video) when billed per image; null = not billed per image"),
        "input_image_price_batch": dict(usd, description="model.currency per input image under Batch when it differs from input_image_price; null = same / not listed"),
        "input_image_allowance": obj({
            "free_quantity": {"type": "integer", "minimum": 0}, "scope": {"const": "per_task"},
            "sources": urls, "note": {"type": "string", "minLength": 1}}),
        "batch_supported": {"type": ["boolean", "null"], "description": "Whether the Batch API is documented for this model; null = 待核实"},
        "promotion": {"anyOf": [{"type": "null"}, obj({
            "discount_percent": {"type": ["number", "null"], "exclusiveMinimum": 0, "maximum": 100},
            "effective_until": {"type": ["string", "null"], "format": "date"},
            "note": {"type": "string", "minLength": 1}})],
            "description": "Vendor promotion on the recorded prices. Recorded prices are LIST prices before the discount."},
        "billing_note": {"type": "string", "minLength": 1},
        "sources": urls}, required=["output_kind", "billing_methods", "token_pricing", "image_prices", "video_prices", "input_image_price", "input_image_price_batch", "batch_supported", "promotion", "billing_note", "sources"])


def extend_schemas(model, cache_pricing, price):
    """Only pricing metadata; deliberately do not restore removed model capabilities."""
    def obj(properties, required=None):
        return {"type": "object", "properties": properties,
                "required": list(properties) if required is None else required,
                "additionalProperties": False}
    urls = {"type": "array", "minItems": 1, "uniqueItems": True,
            "items": {"type": "string", "format": "uri", "pattern": "^https?://"}}
    note = {"type": "string", "minLength": 1}
    nullable = {"type": ["string", "null"]}
    model["properties"]["price_basis"] = obj({
        "type": {"enum": ["official", "reference"]}, "reference_model_id": nullable,
        "sources": urls, "note": note})
    model["properties"]["price_basis"]["properties"]["reference_multiplier"] = {
        "type": "number", "exclusiveMinimum": 0,
        "description": "Documented multiplier of reference model base prices; omitted means 1. Tier prices are already expanded, not multiplied again."}
    model["properties"]["billing"] = obj({
        "channel": {"enum": ["pay_as_you_go", "subscription"]},
        "price_type": {"enum": ["current", "list", "reference"]}, "region": nullable,
        "cached_input_type": {"enum": ["implicit", "explicit", "unspecified"]}, "note": note})
    model["properties"]["off_peak_schedule"] = {"anyOf": [{"type": "null"}, obj({
        "timezone": {"enum": ["UTC"]},
        "weekdays": {"type": "array", "minItems": 1, "uniqueItems": True,
                     "items": {"type": "integer", "minimum": 1, "maximum": 7}},
        "peak_windows": {"type": "array", "minItems": 1, "items": obj({
            "start": {"type": "string", "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$"},
            "end": {"type": "string", "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$"}})},
        "holiday_region": {"enum": ["CN"]}, "sources": urls, "note": note})]}
    model["required"] += ["price_basis", "billing", "off_peak_schedule"]
    model["properties"]["source_url"]["pattern"] = "^https?://"
    reasoning = model["properties"]["reasoning_effort"]
    reasoning["properties"]["field_status"] = obj({k: {"enum": ["verified", "unverified", "not_applicable"]}
                                                   for k in ("supported", "levels", "default", "can_disable")})
    reasoning["required"].append("field_status")
    reasoning["properties"]["sources"] = urls
    reasoning["properties"]["note"] = note
    model["properties"]["limits"]["sources"] = urls
    model["properties"]["limits"]["note"] = note
    instant = {"type": "string", "format": "date-time"}
    model["properties"]["price_observations"] = {"type": "array", "items": obj({
        "observed_at": instant, "valid_from": {"type": ["string", "null"], "format": "date-time"},
        "valid_until": {"type": ["string", "null"], "format": "date-time"},
        "fields": {"type": "array", "minItems": 1, "uniqueItems": True,
                   "items": {"enum": ["*"] + list(PRICE_FIELDS) + [k for k in CACHE_FIELDS if k not in PRICE_FIELDS and k != "note"]}},
        "input_tokens_gt": {"type": ["integer", "null"], "minimum": 0},
        "sources": urls, "note": note})}
    component_fields = list(PRICE_FIELDS) + [k for k in CACHE_FIELDS if k != "note"]
    svc = model["properties"]["service_tiers"]["items"]
    svc["properties"].update({
        "multipliers": obj({k: {"type": ["number", "null"], "exclusiveMinimum": 0} for k in component_fields}),
        "pricing": obj({k: price for k in PRICE_FIELDS}, []), "sources": urls})
    svc["required"] += ["multipliers", "pricing", "sources"]
    svc["properties"]["multiplier_schedule"] = {"type": "array", "items": obj({
        "effective_from": instant, "timezone": {"type": "string", "minLength": 1},
        "multiplier": {"type": "number", "exclusiveMinimum": 0}, "sources": urls, "note": note})}
    svc["properties"]["status_observation"] = obj({
        "status": {"enum": ["deprecated"]}, "observed_at": instant, "sources": urls, "note": note})
    event = model["properties"]["price_schedule"]["items"]
    event["properties"].update({
        "multiplier": {"type": ["number", "null"], "exclusiveMinimum": 0},
        "cache_pricing": obj({k: price for k in CACHE_FIELDS if k != "note"}, []), "sources": urls})
    event["required"] += ["multiplier", "cache_pricing", "sources"]
    event["properties"]["effective_until_precision"] = {"enum": ["date", "instant"]}
    event["properties"]["effective_until_timezone"] = nullable
    def strict(schema):
        if isinstance(schema, dict):
            if "properties" in schema:
                schema["additionalProperties"] = False
            for value in schema.values():
                strict(value)
        elif isinstance(schema, list):
            for value in schema:
                strict(value)
    model["properties"]["lifecycle"] = {"type": ["object", "null"], "properties": {
        "status": {"enum": ["active", "scheduled", "pending_confirmation", "retired"]},
        "retired_at": {"type": ["string", "null"], "format": "date-time"},
        "observed_at": {"type": ["string", "null"], "format": "date-time"},
        "retirement_date": {"type": ["string", "null"], "format": "date"},
        "timezone": nullable, "precision": {"enum": ["instant", "date", "unknown"]}, "original_text": nullable, "scope": {"enum": ["entity", "endpoint"]},
        "routes_to": nullable, "conflict": {"type": "boolean"}, "note": nullable,
        "sources": {"type": "array", "items": {"type": "string", "format": "uri"}, "minItems": 1}},
        "required": ["status", "retired_at", "retirement_date", "timezone", "precision", "original_text", "scope", "routes_to", "conflict", "note", "sources"]}
    model["properties"]["availability"] = obj({
        "status": {"enum": ["active", "scheduled", "pending_confirmation", "retired", "history_unknown"]},
        "estimable": {"type": "boolean"}, "reason": nullable})
    model["properties"]["token_offer"] = {"type": ["object", "null"], "properties": {
        "observed_at": {"type": "string", "format": "date-time"},
        "valid_until": {"type": "string", "format": "date-time"},
        "multiplier": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
        "fields": {"type": "array", "items": {"enum": list(PRICE_FIELDS)}, "uniqueItems": True, "minItems": 1},
        "sources": {"type": "array", "items": {"type": "string", "format": "uri"}, "minItems": 1},
        "note": {"type": "string", "minLength": 1}},
        "required": ["observed_at", "valid_until", "multiplier", "fields", "sources", "note"]}
    model["properties"]["estimation_limits"] = {"type": ["object", "null"], "properties": {
        "max_input_tokens": {"type": "integer", "minimum": 1},
        "max_output_tokens": {"type": "integer", "minimum": 1},
        "note": note, "sources": urls}, "required": ["max_input_tokens", "max_output_tokens", "note", "sources"]}
    strict(model)
    strict(cache_pricing)


def openapi(d, vendor_slugs, model_ids):
    price = {"type": ["number", "null"], "minimum": 0,
             "description": "model.currency per 1M tokens; null when not listed or unverified (see pricing_status)"}
    status = {"type": "string", "enum": ["verified", "reference", "unverified", "not_listed", "not_applicable", "not_available"],
              "description": "verified = official price; reference = user-approved reference price, see price_basis; unverified = 待核实; not_listed = 未列出"}
    meta = {
        "type": "object",
        "required": ["updated_at", "currency", "unit", "unit_label", "data_version"],
        "properties": {
            "updated_at": {"type": "string", "format": "date", "description": "Dataset last-verified date"},
            "availability_as_of": {"type": "string", "format": "date-time"},
            "as_of": {"type": "string", "format": "date-time"},
            "source_commit": {"type": ["string", "null"]},
            "next_invalidation": {"type": ["string", "null"], "format": "date-time"},
            "currency": {"type": "string", "enum": ["USD", "CNY", "mixed"]},
            "unit": {"type": "string", "enum": [UNIT, MEDIA_UNIT], "description": "per_1M_tokens for top-level token prices; see_media_pricing on modality endpoints that only hold image / video models"},
            "unit_label": {"type": "string"},
            "modality_counts": {"type": "object", "description": "Models per modality in the full dataset (models.json and index.json only)",
                                "required": list(MODALITIES), "properties": {k: {"type": "integer"} for k in MODALITIES}},
            "count": {"type": "integer", "description": "Number of items in data"},
            "data_version": {"type": "string", "pattern": "^[a-f0-9]{64}$", "description": "SHA-256 of canonical source data, shared by all endpoints"},
            "scope": {"type": "string"},
            "description": {"type": "string"},
        },
    }
    model = {
        "type": "object",
        "required": ["id", "name", "vendor", "vendor_name", "modality", "currency", "unit", "pricing",
                     "pricing_status", "has_off_peak", "off_peak_pricing", "peak_note",
                     "context_length", "context_length_label", "source_url", "extra_sources",
                     "last_updated", "notes", "reasoning_effort", "limits", "pricing_tiers", "service_tiers",
                     "cache_pricing", "price_schedule", "media_pricing", "unverified_fields", "links"],
        "properties": {
            "id": {"type": "string", "description": "Query ID for this dataset and /models/{model_id}.json; use vendor docs for the actual vendor API name and case"},
            "name": {"type": "string", "description": "Display name"},
            "vendor": {"type": "string", "description": "Vendor slug", "enum": vendor_slugs},
            "vendor_name": {"type": "string"},
            "modality": {"type": "string", "enum": list(MODALITIES), "description": "Output modality: text (token-priced LLM), image or video generation. Image / video models carry null pricing (pricing_status not_applicable) and use media_pricing."},
            "currency": {"type": "string", "enum": ["USD", "CNY"]},
            "unit": {"type": "string", "enum": [UNIT, MEDIA_UNIT], "description": "per_1M_tokens for text models; see_media_pricing for image / video models"},
            "media_pricing": {"anyOf": [{"type": "null"}, {"$ref": "#/components/schemas/MediaPricing"}],
                              "description": "Non-token billing for image / video models (per image, per second of video, per-modality token prices); null for text models"},
            "pricing": {"type": "object", "description": "Standard price (peak price when off-peak pricing exists); all null with pricing_status not_applicable on image / video models",
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
            "source_url": {"type": "string", "format": "uri", "description": "Primary official source; see price_basis for full pricing and reference provenance"},
            "extra_sources": {"type": "array", "items": {"type": "string", "format": "uri"}},
            "last_updated": {"type": "string", "format": "date"},
            "notes": {"type": ["string", "null"]},
            "reasoning_effort": {
                "type": "object",
                "description": "Reasoning-effort / thinking-intensity support from official vendor docs. null = 待核实 (not verified, never guessed).",
                "required": ["supported", "levels", "default", "can_disable", "status", "note", "sources"],
                "properties": {
                    "supported": {"type": ["boolean", "null"], "description": "true = the API exposes an adjustable reasoning effort / thinking switch or budget; false = no adjustable control (e.g. always-on thinking with no effort parameter); null = 待核实"},
                    "levels": {"type": ["array", "null"], "items": {"type": "string"}, "description": "Accepted effort levels in ascending order (e.g. low, medium, high); null when not applicable or 待核实"},
                    "default": {"type": ["string", "null"], "description": "Default level when the parameter is omitted; null when not stated / 待核实"},
                    "can_disable": {"type": ["boolean", "null"], "description": "Whether reasoning can be turned off via the API; null = not stated in official docs"},
                    "status": {"type": "string", "enum": ["verified", "partial", "unverified", "not_applicable"], "description": "verified = all applicable facts documented; partial = some fields 待核实; unverified = support 待核实; see field_status"},
                    "note": {"type": ["string", "null"], "description": "Parameter names, level mappings and caveats"},
                    "sources": {"type": "array", "items": {"type": "string", "format": "uri"}, "description": "Official documentation pages used"},
                },
            },
            "limits": {
                "type": "object",
                "description": "Official context and output limits. null listed in unverified_fields = unknown; an explicitly absent output cap is also null, documented in note. Official K/M labels use 1K=1,000 / 1M=1,000,000 unless exact numbers are given.",
                "required": list(LIMIT_FIELDS) + ["status", "note", "sources"],
                "properties": {
                    "context_length": {"type": ["integer", "null"], "description": "Maximum context window in tokens (same value as top-level context_length)"},
                    "max_output_tokens": {"type": ["integer", "null"], "description": "Maximum output tokens per request; null = unknown if listed in unverified_fields, otherwise no separate output cap documented (see note)"},
                    "status": {"type": "string", "enum": ["verified", "partial", "unverified", "not_applicable"], "description": "verified = both limits documented, including an explicitly absent output cap; partial = one; unverified = none"},
                    "note": {"type": ["string", "null"]},
                    "sources": {"type": "array", "items": {"type": "string", "format": "uri"}},
                },
            },
            "pricing_tiers": {
                "type": "array",
                "description": "Long-context / prompt-length price tiers where documented, in addition to the base price in pricing (which is the lowest tier). Empty array = single tier (or tiers not documented). A request whose input falls in a tier is billed entirely at that tier's prices. A null price inside a tier = not documented for that tier.",
                "items": {"type": "object", "required": list(TIER_FIELDS),
                          "properties": {
                              "condition": {"type": "string", "description": "Machine-readable condition, e.g. input_tokens>272000"},
                              "input_tokens_gt": {"type": ["integer", "null"], "description": "Tier applies when input tokens > this value"},
                              "input_tokens_lte": {"type": ["integer", "null"], "description": "…and <= this value (null = no upper bound)"},
                              "input": price, "output": price,
                              "cached_input": dict(price, description="Same meaning as pricing.cached_input, at this tier"),
                              "cache_write": dict(price, description="Same meaning as pricing.cache_write, at this tier"),
                              "cache_pricing": {"anyOf": [{"$ref": "#/components/schemas/CachePricing"}, {"type": "null"}]},
                              "note": {"type": ["string", "null"]}}},
            },
            "service_tiers": {
                "type": "array",
                "description": "multiplier is an input/output display hint. Billing uses per-component multipliers, then explicit pricing overrides. Null multiplier means unknown, never zero. Storage has its own multiplier.",
                "items": {"type": "object", "required": ["name", "multiplier", "note"],
                          "properties": {
                              "name": {"type": "string", "enum": list(SERVICE_TIER_NAMES), "description": "batch / flex / fast (OpenAI Fast = formerly Priority; Anthropic fast mode) / priority / ultrafast; data_residency = regional / US-only processing surcharge"},
                              "multiplier": {"type": "number", "minimum": 0, "description": "Price multiplier vs standard, e.g. 0.5 or 2"},
                              "note": {"type": ["string", "null"]}}},
            },
            "cache_pricing": {"$ref": "#/components/schemas/CachePricing"},
            "price_schedule": {
                "type": "array", "description": "Time-limited promotions and scheduled price changes announced on official pages (price fields are the announced prices; null = not announced)",
                "items": {"type": "object", "required": ["kind", "effective_from", "effective_until", "input", "output", "cached_input", "cache_write", "note"],
                          "properties": {"kind": {"type": "string", "enum": list(SCHEDULE_KINDS)},
                                         "effective_from": {"type": ["string", "null"], "format": "date"},
                                         "effective_until": {"type": ["string", "null"], "format": "date"},
                                         "input": price, "output": price, "cached_input": price, "cache_write": price,
                                         "note": {"type": ["string", "null"]}}},
            },
            "unverified_fields": {"type": "array", "items": {"type": "string"}},
            "links": {"type": "object", "properties": {"self": {"type": "string"}, "vendor": {"type": "string"}}},
        },
    }
    cache_pricing = {
        "type": "object", "required": list(CACHE_FIELDS),
        "description": "Cache price breakdown where documented (model.currency per 1M tokens; null = not documented / 待核实). pricing.cached_input and pricing.cache_write keep their meaning; this object adds the finer split. Qwen: implicit_read / explicit_read / explicit_write are the three official cache prices.",
        "properties": {
            "implicit_read": dict(price, description="Implicit (automatic) cache hit price"),
            "explicit_read": dict(price, description="Explicit cache hit (read) price"),
            "explicit_write": dict(price, description="Cache creation / write price at the default TTL (Anthropic 5 minutes, OpenAI 30 minutes)"),
            "explicit_write_1h": dict(price, description="1-hour TTL cache write price (Anthropic, Kimi K3)"),
            "explicit_write_12h": dict(price, description="12-hour minimum-TTL cache write price (OpenAI GPT-5.6+ Responses API prompt_cache_options.ttl=\"12h\", 2.5x uncached input; the default 30-minute write is explicit_write / pricing.cache_write). Total write rate, not a surcharge. Long-context values are in pricing_tiers[].cache_pricing"),
            "storage_per_1M_tokens_hour": dict(price, description="Cache storage fee per 1M tokens per hour (model.currency, not per 1M tokens; 0 = currently free)"),
            "note": {"type": ["string", "null"]}},
    }
    extend_schemas(model, cache_pricing, price)
    vendor = {
        "type": "object",
        "required": ["slug", "name", "model_count", "model_ids", "modality_counts", "source_urls", "links"],
        "properties": {
            "slug": {"type": "string", "enum": vendor_slugs},
            "name": {"type": "string"},
            "model_count": {"type": "integer"},
            "model_ids": {"type": "array", "items": {"type": "string"}},
            "modality_counts": {"type": "object", "required": list(MODALITIES), "additionalProperties": False,
                                "properties": {k: {"type": "integer"} for k in MODALITIES}},
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
    modality_obj = {
        "type": "object",
        "required": ["name", "label", "model_count", "model_ids", "vendors", "links"],
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "enum": list(MODALITIES)},
            "label": {"type": "string"},
            "model_count": {"type": "integer"},
            "model_ids": {"type": "array", "items": {"type": "string"}},
            "vendors": {"type": "array", "items": {"type": "string", "enum": vendor_slugs}, "description": "Vendor slugs with at least one model of this modality"},
            "links": {"type": "object", "properties": {"self": {"type": "string"}}},
        },
    }
    modality_env = env({"type": "array", "items": {"$ref": "#/components/schemas/Model"}})
    modality_env["required"].append("modality")
    modality_env["properties"]["modality"] = {"$ref": "#/components/schemas/Modality"}
    index_schema = {"type": "object", "required": ["endpoints", "models", "vendors", "modalities"], "additionalProperties": False,
                    "properties": {
                        "endpoints": {"type": "object", "required": ["models", "vendors", "modalities", "openapi", "price-facts"], "additionalProperties": False,
                                      "properties": {k: {"const": k + ".json"} for k in ("models", "vendors", "modalities", "openapi", "price-facts")}},
                        "models": {"type": "array", "items": {"type": "object", "required": ["id", "name", "vendor", "modality", "links"],
                            "additionalProperties": False,
                            "properties": {k: model["properties"][k] for k in ("id", "name", "vendor", "modality", "links")}}},
                        "modalities": {"type": "array", "items": {"$ref": "#/components/schemas/Modality"}},
                        "vendors": {"type": "array", "items": {"type": "object", "required": ["slug", "name", "links"],
                            "additionalProperties": False,
                            "properties": {k: vendor["properties"][k] for k in ("slug", "name", "links")}}}}}
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "LLM API Pricing (static JSON API)",
            "version": "1.2.0",
            "description": ("Read-only static JSON files generated from data/prices.json by scripts/build_api.py "
                            "and served by GitHub Pages. Prices use each model.currency (USD or CNY); never compare or sum across currencies. Text models are priced per 1M tokens (top-level pricing); "
                            "image and video generation models (modality image / video) carry pricing_status not_applicable "
                            "and express prices in media_pricing (per image by size and quality, per second of video by "
                            "resolution and audio, and per-modality token prices). Only GET is supported; "
                            "there is no server-side filtering or query parameters, filter on the client. "
                            "CORS: GitHub Pages sends Access-Control-Allow-Origin: * so files can be fetched from any origin. "
                            "Dataset updated_at: %s." % d["meta"]["last_updated"]),
        },
        "servers": [{"url": ".", "description": "Relative to this openapi.json (…/api/v1/)"},
                    {"url": "https://{user}.github.io/{repo}/api/v1",
                     "variables": {"user": {"default": "your-user"}, "repo": {"default": "llm-pricing"}}}],
        "paths": {
            "/price-facts.json": {"get": {"operationId": "getPublicPriceObservations", "summary": "Archival official price facts, NOT universe or availability certification", "responses": ok("Source-bound price observations", "#/components/schemas/PublicPriceEvidence")}},
            "/index.json": {"get": {"operationId": "getIndex", "summary": "Discover endpoint paths and model IDs",
                                     "responses": ok("API index", "#/components/schemas/Index")}},
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
            "/modalities.json": {"get": {"operationId": "listModalities", "summary": "Modalities (text / image / video) and their model ids",
                                         "responses": ok("All modalities", "#/components/schemas/ModalityList")}},
            "/modalities/{modality}.json": {"get": {
                "operationId": "getModality", "summary": "All models of one modality (text, image or video)",
                "parameters": [{"name": "modality", "in": "path", "required": True,
                                "schema": {"type": "string", "enum": list(MODALITIES)}}],
                "responses": ok("Modality with its models", "#/components/schemas/ModalityModels")}},
        },
        "components": {"schemas": {
            "PublicPriceEvidence": env({"type":"object", "required":["facts","price_verified_count","scope_complete","history_complete","evidence_version"], "properties":{
                "scope_complete":{"const":False},"history_complete":{"const":False},"price_verified_count":{"type":"integer","minimum":0},
                "evidence_version":{"type":"string","pattern":"^[a-f0-9]{64}$"},
                "facts":{"type":"array","items":{"type":"object","required":["model_id","offering_name","identity_kind","component","amount","source_url","source_sha256","quote","quote_sha256","context_quotes","channel","region","currency","unit","tier","observed_at","price_verified","scope_complete","history_complete","eligible_for_estimation","availability"],"properties":{
                    "currency":{"enum":["USD","CNY"]},"price_verified":{"const":True},"scope_complete":{"const":False},"history_complete":{"const":False},"eligible_for_estimation":{"const":False},"availability":{"const":"not_assessed"},"region":{"type":"string","minLength":1},"quote":{"type":"string","minLength":1},"source_sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"},"quote_sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"},"amount":{"type":"number","minimum":0}}}}}}),
            "Meta": meta, "Model": model, "Vendor": vendor, "CachePricing": cache_pricing,
            "ModelList": env({"type": "array", "items": {"$ref": "#/components/schemas/Model"}}),
            "ModelItem": env({"$ref": "#/components/schemas/Model"}),
            "VendorList": env({"type": "array", "items": {"$ref": "#/components/schemas/Vendor"}}),
            "VendorModels": vendor_env,
            "MediaPricing": media_pricing_schema(),
            "Modality": modality_obj,
            "ModalityList": env({"type": "array", "items": {"$ref": "#/components/schemas/Modality"}}),
            "ModalityModels": modality_env,
            "Index": env(index_schema),
        }},
    }


def availability_for(models, at):
    result = subprocess.run(["node", str(ROOT / "scripts" / "lifecycle_batch.cjs")],
                            input=json.dumps({"models": models, "at": at}), text=True,
                            capture_output=True, check=True, timeout=30)
    return json.loads(result.stdout)


def build(d, mixed=False):
    """Return {relative path under api/v1: python object}."""
    missing = [v for v in d["vendors"] if v not in VENDOR_SLUGS]
    if missing:
        raise SystemExit("build_api: no slug for vendor(s) %s; add to VENDOR_SLUGS in scripts/build_api.py" % missing)
    out = {}
    all_models = [m for m in d["models"] if mixed or m["currency"] == "USD"]
    at = d["meta"].get("availability_as_of", d["meta"]["last_updated"] + "T00:00:00+08:00")
    decisions = availability_for(all_models, at)
    all_objs = [dict(model_obj(m), availability=a) for m, a in zip(all_models, decisions)]
    for o in all_objs:
        if not o["availability"]["estimable"]:
            # Keep the identity/routing evidence, never a usable current price.
            o["pricing"] = {k: None for k in PRICE_FIELDS}
            o["pricing_status"] = {k: "not_available" for k in PRICE_FIELDS}
            o["cache_pricing"] = {k: None for k in CACHE_FIELDS}
            o["pricing_tiers"], o["service_tiers"], o["price_schedule"] = [], [], []
            o["off_peak_pricing"], o["off_peak_schedule"], o["has_off_peak"] = None, None, False
            o["token_offer"], o["media_pricing"] = None, None
            o["notes"] = "已退役；保留身份及路由证据，不提供当前价格或估算。历史说明：" + (o["notes"] or "")
    models = [m for m, a in zip(all_models, decisions) if a["estimable"]]
    objs = [o for o in all_objs if o["availability"]["estimable"]]
    for o in objs:
        if not SLUG_RE.match(o["id"]):
            raise SystemExit("build_api: model_id %r is not URL-safe" % o["id"])
    modality_counts = {k: sum(1 for o in objs if o["modality"] == k) for k in MODALITIES}
    meta = base_meta(d, len(objs))
    meta["modality_counts"] = modality_counts
    meta["scope"] = d["meta"].get("scope")
    meta["description"] = d["meta"].get("description")
    out["models.json"] = {"api_version": API_VERSION, "meta": meta, "data": objs}
    vendors = []
    for name in d["vendors"]:
        vm = [m for m in models if m["vendor"] == name]
        if not vm:
            continue
        v = vendor_obj(d, name, vm)
        vendors.append(v)
        out["vendors/%s.json" % v["slug"]] = {
            "api_version": API_VERSION, "meta": base_meta(d, len(vm)), "vendor": v,
            "data": [o for o in objs if o["vendor"] == v["slug"]]}
    out["vendors.json"] = {"api_version": API_VERSION, "meta": base_meta(d, len(vendors)), "data": vendors}
    modalities = []
    for k in MODALITIES:
        mo = [o for o in objs if o["modality"] == k]
        mobj = {"name": k, "label": MODALITY_LABELS[k], "model_count": len(mo), "model_ids": [o["id"] for o in mo],
                "vendors": [v["slug"] for v in vendors if any(o["vendor"] == v["slug"] for o in mo)],
                "links": {"self": "modalities/%s.json" % k}}
        modalities.append(mobj)
        mmeta = base_meta(d, len(mo))
        if k != "text":
            mmeta["unit"], mmeta["unit_label"] = MEDIA_UNIT, MEDIA_UNIT_LABEL
        out["modalities/%s.json" % k] = {"api_version": API_VERSION, "meta": mmeta, "modality": mobj, "data": mo}
    out["modalities.json"] = {"api_version": API_VERSION, "meta": base_meta(d, len(modalities)), "data": modalities}
    imeta = base_meta(d, len(objs))
    imeta["modality_counts"] = modality_counts
    out["index.json"] = {"api_version": API_VERSION, "meta": imeta, "data": {
        "endpoints": {"models": "models.json", "vendors": "vendors.json", "modalities": "modalities.json", "openapi": "openapi.json", "price-facts": "price-facts.json"},
        "models": [{k: o[k] for k in ("id", "name", "vendor", "modality", "links")} for o in objs],
        "modalities": modalities,
        "vendors": [{k: v[k] for k in ("slug", "name", "links")} for v in vendors]}}
    for o in all_objs:
        out["models/%s.json" % o["id"]] = {"api_version": API_VERSION, "meta": base_meta(d), "data": o}
    import public_price_facts
    out["price-facts.json"] = {"api_version": API_VERSION, "meta": base_meta(d), "data": public_price_facts.view(public_price_facts.load(), mixed=mixed)}
    out["openapi.json"] = openapi(d, [v["slug"] for v in vendors], [o["id"] for o in all_objs])
    # v1 remains USD-only for existing consumers. v2 is the explicit mixed-currency capability.
    for rel, value in out.items():
        if rel == "openapi.json":
            value["info"]["description"] = ("Explicit mixed-currency v2. " if mixed else "USD-only v1 compatibility endpoint. ") + value["info"]["description"]
            value["components"]["schemas"]["PublicPriceEvidence"]["properties"]["data"]["properties"]["facts"]["items"]["properties"]["currency"]["enum"] = ["USD", "CNY"] if mixed else ["USD"]
            value["components"]["schemas"]["Model"]["properties"]["currency"]["enum"] = ["USD", "CNY"] if mixed else ["USD"]
            value["components"]["schemas"]["Meta"]["properties"]["currency"]["enum"] = ["mixed"] if mixed else ["USD"]
            if mixed:
                out[rel] = json.loads(json.dumps(value).replace("/api/v1", "/api/v2"))
                out[rel]["info"]["version"] = "2.0.0"
                out[rel] = json.loads(json.dumps(out[rel]).replace('"const": "v1"', '"const": "v2"').replace('"enum": ["v1"]', '"enum": ["v2"]'))
        else:
            value["api_version"] = "v2" if mixed else "v1"
            value["meta"]["currency"] = "mixed" if mixed else "USD"
    return out


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def existing_files(directory=None):
    directory = API_DIR if directory is None else directory
    return {str(p.relative_to(directory)).replace("\\", "/") for p in directory.rglob("*.json")} if directory.exists() else set()


def check(d=None, mixed=False):
    """Return list of problems (empty = in sync)."""
    files = build(d or load(), mixed=mixed)
    directory = ROOT / "api" / "v2" if mixed else API_DIR
    prefix = "api/v2/" if mixed else "api/v1/"
    problems = []
    for rel, obj in files.items():
        p = directory / rel
        if not p.exists():
            problems.append("missing " + prefix + rel)
        elif p.read_text(encoding="utf-8") != dump(obj):
            problems.append("stale " + prefix + rel)
    for rel in sorted(existing_files(directory) - set(files)):
        problems.append("orphan " + prefix + rel)
    return problems


def page_data(d):
    at = d["meta"].get("availability_as_of", d["meta"]["last_updated"] + "T00:00:00+08:00")
    decisions = availability_for(d["models"], at)
    result = copy.deepcopy(d)
    result["meta"].update(base_meta(d))
    import public_price_facts
    ledger=public_price_facts.load()
    result["public_price_evidence"]={"price_verified_count":len(ledger["facts"]),"scope_complete":False,"history_complete":False,
        "observed_at":sorted({x["observed_at"] for x in ledger["sources"]}),"url":"api/v2/price-facts.json",
        "offering_channel_observation_count":len(ledger["offering_channel_observations"]),
        "meaning":"archival source observations; audited estimator rates unchanged; not exhaustive directory, current availability or user entitlement"}
    result["models"] = [m for m, a in zip(result["models"], decisions) if a["estimable"]]
    return result


def main():
    if "--page" in sys.argv:
        target = ROOT / "data" / "page-models.json"
        content = dump(page_data(load()))
        if "--check" in sys.argv:
            sys.exit(0 if target.exists() and target.read_text() == content else 1)
        target.write_text(content, encoding="utf-8")
        print("wrote data/page-models.json")
        return
    mixed = "--v2" in sys.argv
    directory = ROOT / "api" / "v2" if mixed else API_DIR
    if "--check" in sys.argv:
        probs = check(mixed=mixed)
        for p in probs:
            print(p)
        print("api in sync" if not probs else "%d api problem(s); run python3 scripts/build_api.py" % len(probs))
        sys.exit(1 if probs else 0)
    files = build(load(), mixed=mixed)
    manifest = directory / ".generated-files"
    managed = set(manifest.read_text().splitlines()) if manifest.exists() else set()
    for rel in managed - set(files):
        target = directory / rel
        if target.is_file() and target.resolve().is_relative_to(directory.resolve()) and rel.endswith(".json"):
            target.unlink()
    for rel, obj in files.items():
        p = directory / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        s = dump(obj)
        if not p.exists() or p.read_text(encoding="utf-8") != s:
            p.write_text(s, encoding="utf-8")
    manifest.write_text("\n".join(sorted(files)) + "\n")
    print("wrote %d files to %s" % (len(files), directory.relative_to(ROOT)))


if __name__ == "__main__":
    main()
