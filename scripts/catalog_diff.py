#!/usr/bin/env python3
"""Conservative catalog-ID diff. No scraping, importing, or automatic retirements.

Each inventory is a provenance-bearing vendor/channel snapshot; complete=false
or any errors means discovery remains incomplete, never "no new models".
IDs are case-normalized only. Punctuation/snapshots/aliases are NOT guessed.
"""
import argparse
import json
import re

ID = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")


def canonical_id(value):
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
        # The label may itself contain `model`; identifiers require a separator.
        for token in re.findall(r"`([^`\s]+)`", line):
            mid = canonical_id(token)
            if mid and ("-" in mid or "." in mid):
                rows.append({"model_id": mid, "api_id_explicit": True, "line": number})
    return rows


def compare_catalogs(database, inventories, previous=None, aliases=()):
    # Aliases require an explicit official map, scoped to vendor and channel.
    mapping = {}
    for item in aliases:
        if not item.get("source_url"):
            raise ValueError("Alias mapping requires an official source")
        key = (item["vendor"], item["channel"], canonical_id(item["alias"]))
        mapping[key] = canonical_id(item["canonical"])
    known = {(m["vendor"], m["billing"]["channel"], canonical_id(m["model_id"])) for m in database["models"]}
    observations, coverage, invalid = {}, [], []
    for snap in inventories:
        complete = snap.get("complete") is True and not snap.get("errors")
        coverage.append({"vendor": snap["vendor"], "channel": snap["channel"], "complete": complete,
                         "errors": snap.get("errors", []), "source_url": snap["source_url"], "observed_at": snap["observed_at"]})
        for row in snap["records"]:
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
    return {"status": "complete" if coverage and all(c["complete"] for c in coverage) else "incomplete",
            "coverage": coverage, "observations": list(observations.values()), "unresolved_rows": invalid,
            "not_in_database": [r for r in observations.values() if r["database_status"] != "present"],
            "not_observed_this_run_not_retired": [list(k) for k in sorted(prior - observations.keys())],
            "historical_comparison": "no_previous_successful_snapshot" if previous is None else "observation_diff_only",
            "note": "Not-in-database is not newly released; absence is never proof of retirement. No automatic writes."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", required=True)
    p.add_argument("--inventory", required=True)
    p.add_argument("--previous")
    args = p.parse_args()
    def load(path):
        with open(path) as f:
            return json.load(f)
    result = compare_catalogs(load(args.database), load(args.inventory), load(args.previous) if args.previous else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
