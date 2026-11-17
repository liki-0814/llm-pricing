#!/usr/bin/env python3
"""Conservative catalog-ID diff. No scraping, importing, or automatic retirements.

Each inventory is a provenance-bearing vendor/channel snapshot; complete=false
or any errors means discovery remains incomplete, never "no new models".
IDs are case-normalized only. Punctuation/snapshots/aliases are NOT guessed.
"""
import argparse
import json
import hashlib
import os
import pathlib
import tempfile
import datetime as dt
import re

ID = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")


def canonical_id(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if ID.fullmatch(value) else None


def extract_explicit_ids(text):
    """Only machine-call identifiers in explicit invocation labels, not display names.

    Supplements catalog table adapters when merged pricing headers corrupt IDs.
    Deliberately does not infer an ID from a marketing/model display name.
    """
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not re.search(r"(?:model invocation ID|model(?:[（(].*?调用参数| calling ID)|API model ID)", line, re.I):
            continue
        # Skip the label's `model` parameter token; alphanumeric IDs are valid too.
        tail = line.split(":", 1)[1] if ":" in line else line
        for token in re.findall(r"`([^`\s]+)`", tail):
            mid = canonical_id(token)
            if mid and mid != "model":
                rows.append({"model_id": mid, "api_id_explicit": True, "line": number})
    return rows



def extract_horizontal_identities(text, api_row_label):
    """Parse a vendor's chosen first-party API-ID row, never partner ID rows.

    The display header is evidence for ID/display matching; punctuation in API
    IDs remains untouched. The caller selects the source's documented row label,
    not a list of model IDs. Returned line numbers support human review.
    """
    rows, header = [], None
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip().startswith("|"): continue
        cells = [x.strip() for x in line.strip().strip("|").split("|")]
        if cells[0].lower() in ("feature", "model name"):
            header = cells
        if cells[0].lower() != api_row_label.lower() or header is None: continue
        if len(cells) != len(header): raise ValueError("API-ID table/header column mismatch")
        for name, cell in zip(header[1:], cells[1:]):
            tokens = re.findall(r"`([^`\s]+)`", cell)
            if len(tokens) != 1 or not canonical_id(tokens[0]):
                raise ValueError("Missing or ambiguous first-party API ID")
            rows.append({"model_id": canonical_id(tokens[0]), "display_name": name,
                         "api_id_explicit": True, "line": number})
    return rows


def compare_catalogs(database, inventories, previous=None, aliases=()):
    # Aliases require an explicit official map, scoped to vendor and channel.
    mapping = {}
    for item in aliases:
        if not item.get("source_url"):
            raise ValueError("Alias mapping requires an official source")
        key = (item["vendor"], item["channel"], canonical_id(item["alias"]))
        target = canonical_id(item["canonical"])
        if not key[2] or not target or (key in mapping and mapping[key] != target):
            raise ValueError("Invalid or conflicting official alias map")
        mapping[key] = target
    # Maps are direct source-backed bridges, never guessed transitive aliases.
    if any((v, c, target) in mapping and mapping[(v, c, target)] != target
           for (v, c, mid), target in mapping.items()):
        raise ValueError("Alias chains/cycles require explicit direct canonical resolution")
    known = {(m["vendor"], m["billing"]["channel"], canonical_id(m["model_id"])) for m in database["models"]}
    observations, coverage, invalid = {}, [], []
    for snap in inventories:
        errors = list(snap.get("errors", []))
        rows = snap.get("records", [])
        if not isinstance(rows, list):
            rows = []
            errors.append("records_not_a_list")
        invalid_rows = sum(not isinstance(row, dict) or row.get("api_id_explicit") is not True
                           or not canonical_id(row.get("model_id")) for row in rows)
        evidence = snap.get("coverage_evidence", {})
        # A complete=true flag is not evidence of exhaustive enumeration/extraction.
        if snap.get("fetch_status") != "ok": errors.append("fetch_not_verified")
        if snap.get("extraction_status") != "ok": errors.append("extraction_not_verified")
        if evidence.get("enumeration_verified") is not True: errors.append("enumeration_not_verified")
        if evidence.get("pagination_complete") is not True: errors.append("pagination_not_verified")
        if not evidence.get("source_url"): errors.append("enumeration_source_missing")
        if not rows: errors.append("empty_extraction_not_proof_of_empty_catalog")
        if invalid_rows: errors.append("invalid_or_nonexplicit_rows:%d" % invalid_rows)
        expected = evidence.get("expected_record_count")
        if type(expected) is not int or expected != len(rows): errors.append("source_record_count_unverified")
        complete = snap.get("complete") is True and not errors
        coverage.append({"vendor": snap["vendor"], "channel": snap["channel"], "complete": complete,
                         "errors": errors, "source_url": snap["source_url"], "observed_at": snap["observed_at"]})
        for row in rows:
            if not isinstance(row, dict):
                invalid.append({"raw": row, "source_url": snap["source_url"]})
                continue
            mid = canonical_id(row.get("model_id", "")) if row.get("api_id_explicit") is True else None
            if not mid:
                invalid.append(row)
                continue
            key = (snap["vendor"], snap["channel"], mid)
            canonical = mapping.get(key, mid)
            target = (key[0], key[1], canonical)
            if target not in observations:
                observations[target] = {"vendor": key[0], "channel": key[1], "model_id": canonical,
                    "observed_ids": [], "sources": [], "price_public": False,
                    "database_status": "present" if target in known else "not_in_price_database_needs_review"}
            rec = observations[target]
            if mid not in rec["observed_ids"]:
                rec["observed_ids"].append(mid)
            rec["price_public"] |= row.get("price_public") is True
            rec["sources"].append({"source_url": snap["source_url"], "observed_at": snap["observed_at"], "line": row.get("line")})
    prior = {(x["vendor"], x["channel"], x["model_id"]) for x in (previous or {}).get("observations", [])}
    # All tracked scopes must be represented; a successful subset is not a full run.
    required = {(m["vendor"], m["billing"]["channel"]) for m in database["models"]}
    scopes = {(c["vendor"], c["channel"]) for c in coverage}
    missing = sorted(required - scopes)
    vendors = sorted({v for v, c in required | scopes})
    vendor_coverage = [{"vendor": v, "complete": bool([c for c in coverage if c["vendor"] == v])
        and all(c["complete"] for c in coverage if c["vendor"] == v)
        and not any(scope[0] == v for scope in missing)} for v in vendors]
    complete = bool(coverage) and not missing and all(c["complete"] for c in coverage)
    differences = [r for r in observations.values() if r["database_status"] != "present"]
    return {"status": "complete" if complete else "incomplete",
            "vendor_coverage": vendor_coverage, "missing_scopes": missing,
            "discovery_verdict": "differences_need_review" if differences else
                ("no_untracked_ids_in_verified_scope" if complete else "inconclusive_incomplete_coverage"),
            "coverage": coverage, "observations": list(observations.values()), "unresolved_rows": invalid,
            "not_in_database": [r for r in observations.values() if r["database_status"] != "present"],
            "not_observed_this_run_not_retired": [list(k) for k in sorted(prior - observations.keys())],
            "historical_comparison": "no_previous_successful_snapshot" if previous is None else "observation_diff_only",
            "note": "Not-in-database is not newly released; absence is never proof of retirement. No automatic writes."}


def save_attempt(state_dir, result):
    """Immutable attempts + visible latest failure; never replace a good baseline on failure.

    No scheduler is changed. A wrapper must surface nonzero CLI exit and latest-attempt.
    First complete current run creates the baseline; missing history does not block it.
    """
    root = pathlib.Path(state_dir)
    root.mkdir(parents=True, exist_ok=True)
    payload = dict(result, recorded_at=dt.datetime.now(dt.timezone.utc).isoformat())
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    run_id = hashlib.sha256(text.encode()).hexdigest()
    target = root / (run_id + ".json")
    with target.open("x") as f:
        f.write(text)
    def pointer(name):
        fd, temporary = tempfile.mkstemp(prefix=".pointer-", dir=root)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"file": target.name, "status": result["status"]}, f)
            os.replace(temporary, root / name)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)
    pointer("latest-attempt.json")
    if result["status"] == "complete": pointer("last-successful.json")
    return target


def previous_success(state_dir):
    pointer = pathlib.Path(state_dir) / "last-successful.json"
    if not pointer.exists(): return None
    name = json.loads(pointer.read_text())["file"]
    if pathlib.Path(name).name != name: raise ValueError("Invalid snapshot pointer")
    result = json.loads((pointer.parent / name).read_text())
    if result.get("status") != "complete": raise ValueError("Previous baseline was not successful")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", required=True)
    p.add_argument("--inventory", required=True)
    p.add_argument("--previous")
    p.add_argument("--state-dir", help="Record immutable attempts, latest result, and last successful baseline")
    p.add_argument("--aliases", help="Explicit source-backed scoped alias map")
    args = p.parse_args()
    def load(path):
        with open(path) as f:
            return json.load(f)
    prior = load(args.previous) if args.previous else (previous_success(args.state_dir) if args.state_dir else None)
    result = compare_catalogs(load(args.database), load(args.inventory), prior, load(args.aliases) if args.aliases else ())
    result["database_sha256"] = hashlib.sha256(pathlib.Path(args.database).read_bytes()).hexdigest()
    result["inventory_sha256"] = hashlib.sha256(pathlib.Path(args.inventory).read_bytes()).hexdigest()
    if args.state_dir: save_attempt(args.state_dir, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
