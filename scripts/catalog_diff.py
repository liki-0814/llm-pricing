#!/usr/bin/env python3
"""Conservative catalog-ID diff. No scraping, importing, or automatic retirements.

Each inventory is a provenance-bearing vendor/channel snapshot; complete=false
or any errors means discovery remains incomplete, never "no new models".
Literal ID case and punctuation are preserved. Snapshots/aliases are NOT guessed.
"""
import argparse
import json
import hashlib
import os
import pathlib
import tempfile
import datetime as dt
import re
import contextlib
import fcntl
import uuid
from urllib.parse import urlparse

DEFAULT_SCOPES = pathlib.Path(__file__).resolve().parents[1] / "data/discovery-scopes.json"

ID = re.compile(r"^[a-z0-9][a-z0-9._/-]*$", re.I)


def canonical_id(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if ID.fullmatch(value) else None


def extract_explicit_ids(text):
    """Only machine-call identifiers in explicit invocation labels, not display names.

    Supplements catalog table adapters when merged pricing headers corrupt IDs.
    Deliberately does not infer an ID from a marketing/model display name.
    """
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not re.search(r"(?:model invocation ID|model(?:[（(].*?调用参数| calling ID)|API model ID|Model\s+Code)", line, re.I):
            continue
        # Skip the label's `model` parameter token; alphanumeric IDs are valid too.
        tail = re.split(r"[:：]", line, maxsplit=1)[-1]
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


def normalize_rows(rows):
    """Lossless upstream identity gate; never strip punctuation, split or guess names.

    Every input row survives, including display-only, ambiguous and excluded rows.
    No alias application here. Conflicting native/provider identity is unresolved.
    """
    output, groups = [], {}
    for raw in rows:
        row = dict(raw) if isinstance(raw, dict) else {"raw": raw}
        literal = row.get("model_id", row.get("observed_name_or_id", ""))
        mid = canonical_id(literal) if row.get("api_id_explicit") is True else None
        row["literal_id"] = literal
        row["model_id"] = mid
        row["api_id_explicit"] = bool(mid)
        if not mid: row["identity_error"] = "unresolved_literal_identity"
        output.append(row)
        if mid: groups.setdefault((row.get("vendor"), row.get("channel"), mid), []).append(row)
    for group in groups.values():
        for field in ("origin_vendor", "entity_id"):
            if len({row[field] for row in group if row.get(field)}) > 1:
                for row in group:
                    row["identity_error"] = "conflicting_official_identity:" + field
                    row["api_id_explicit"] = False
    return output


def scope_manifest(value=None):
    data = json.loads(DEFAULT_SCOPES.read_text()) if value is None else value
    if not isinstance(data, dict) or data.get("version") != 1 or not data.get("scopes"):
        raise ValueError("Explicit nonempty version-1 monitoring scopes required")
    triples = set()
    for item in data["scopes"]:
        if not item.get("vendor") or not item.get("channel") or not item.get("modalities") or not item.get("official_hosts"):
            raise ValueError("Scope requires vendor/channel/modalities/official_hosts")
        for modality in item["modalities"]:
            key = (item["vendor"], item["channel"], modality)
            if key in triples: raise ValueError("Duplicate monitoring scope")
            triples.add(key)
    return data, triples


def official_url(url, vendor, channel, manifest):
    parsed = urlparse(url or "")
    hosts = {h for s in manifest["scopes"] if (s["vendor"], s["channel"]) == (vendor, channel) for h in s["official_hosts"]}
    return parsed.scheme == "https" and not parsed.username and not parsed.password and parsed.hostname in hosts


def compare_catalogs(database, inventories, previous=None, aliases=(), scopes=None):
    # Aliases require an explicit official map, scoped to vendor and channel.
    manifest, required = scope_manifest(scopes)
    mapping = {}
    for item in aliases:
        if not official_url(item.get("source_url"), item["vendor"], item["channel"], manifest) or not item.get("evidence_quote"):
            raise ValueError("Alias mapping requires an allowlisted official URL and exact mapping quotation")
        key = (item["vendor"], item["channel"], canonical_id(item["alias"]))
        target = canonical_id(item["canonical"])
        if not key[2] or not target or (key in mapping and mapping[key] != target):
            raise ValueError("Invalid or conflicting official alias map")
        if item["alias"] not in item["evidence_quote"] or item["canonical"] not in item["evidence_quote"]:
            raise ValueError("Official quotation must include both literal alias and canonical ID")
        mapping[key] = target
    # Maps are direct source-backed bridges, never guessed transitive aliases.
    if any((v, c, target) in mapping and mapping[(v, c, target)] != target
           for (v, c, mid), target in mapping.items()):
        raise ValueError("Alias chains/cycles require explicit direct canonical resolution")
    known = {(m["vendor"], m["billing"]["channel"], canonical_id(m["model_id"])) for m in database["models"]}
    # Check identity conflicts across ALL source snapshots, not just within one table.
    prepared, flat = [], []
    for index, snap in enumerate(inventories):
        prepared.append(dict(snap))
        if isinstance(snap.get("records", []), list):
            for raw in snap.get("records", []):
                row = dict(raw) if isinstance(raw, dict) else {"raw": raw}
                row.update(vendor=snap["vendor"], channel=snap["channel"], _snapshot_index=index)
                flat.append(row)
            prepared[-1]["records"] = []
    for row in normalize_rows(flat):
        prepared[row.pop("_snapshot_index")]["records"].append(row)
    observations, coverage, invalid = {}, [], []
    for snap in prepared:
        errors = list(snap.get("errors", []))
        rows = normalize_rows(snap.get("records", [])) if isinstance(snap.get("records", []), list) else snap.get("records")
        if not isinstance(rows, list):
            rows = []
            errors.append("records_not_a_list")
        invalid_rows = sum(not isinstance(row, dict) or row.get("api_id_explicit") is not True
                           or not canonical_id(row.get("model_id")) for row in rows)
        evidence = snap.get("coverage_evidence", {})
        role = snap.get("role", "catalog")
        modalities = evidence.get("modalities", [])
        if role == "catalog" and not modalities: errors.append("modalities_not_verified")
        if role == "catalog" and evidence.get("native_identity_verified") is not True: errors.append("native_identity_not_verified")
        if not official_url(snap.get("source_url"), snap["vendor"], snap["channel"], manifest): errors.append("source_origin_not_verified")
        try: parse_time(snap["observed_at"])
        except (ValueError, KeyError, TypeError): errors.append("observed_at_invalid")
        # A complete=true flag is not evidence of exhaustive enumeration/extraction.
        if snap.get("fetch_status") != "ok": errors.append("fetch_not_verified")
        if snap.get("extraction_status") != "ok": errors.append("extraction_not_verified")
        if evidence.get("enumeration_verified") is not True: errors.append("enumeration_not_verified")
        if evidence.get("pagination_complete") is not True: errors.append("pagination_not_verified")
        if not evidence.get("source_url"): errors.append("enumeration_source_missing")
        elif not official_url(evidence["source_url"], snap["vendor"], snap["channel"], manifest): errors.append("enumeration_origin_not_verified")
        if not rows: errors.append("empty_extraction_not_proof_of_empty_catalog")
        if invalid_rows: errors.append("invalid_or_nonexplicit_rows:%d" % invalid_rows)
        expected = evidence.get("expected_record_count")
        if type(expected) is not int or expected != len(rows): errors.append("source_record_count_unverified")
        complete = snap.get("complete") is True and not errors
        coverage.append({"vendor": snap["vendor"], "channel": snap["channel"], "complete": complete,
                         "errors": errors, "source_url": snap["source_url"], "observed_at": snap["observed_at"],
                         "role": role, "modalities": modalities})
        for row in rows:
            if not isinstance(row, dict):
                invalid.append({"raw": row, "source_url": snap["source_url"]})
                continue
            mid = canonical_id(row.get("model_id", "")) if row.get("api_id_explicit") is True else None
            if not mid:
                invalid.append(dict(row, source_url=snap["source_url"], capture_path=snap.get("capture_path"), extraction_path=snap.get("extraction_path")))
                continue
            key = (snap["vendor"], snap["channel"], mid)
            canonical = mapping.get(key, mid)
            target = (key[0], key[1], canonical)
            if target not in observations:
                observations[target] = {"vendor": key[0], "channel": key[1], "model_id": canonical,
                    "observed_ids": [], "sources": [], "price_public": False,
                    "database_status": "present" if target in known else "not_in_price_database_needs_review",
                    "origin_status": "verified_by_source_review" if evidence.get("native_identity_verified") is True else "pending_confirmation"}
            rec = observations[target]
            if mid not in rec["observed_ids"]:
                rec["observed_ids"].append(mid)
            rec["price_public"] |= row.get("price_public") is True
            rec["sources"].append({"source_url": snap["source_url"], "observed_at": snap["observed_at"], "line": row.get("line"), "line_basis": row.get("line_basis"),
                "source_sha256": snap.get("source_sha256"), "capture_path": snap.get("capture_path"), "extraction_path": snap.get("extraction_path")})
    prior = {(x["vendor"], x["channel"], x["model_id"]) for x in (previous or {}).get("observations", [])}
    # All tracked scopes must be represented; a successful subset is not a full run.
    declared = {(c["vendor"], c["channel"], m) for c in coverage if c["role"] == "catalog" for m in c["modalities"]}
    verified = {(c["vendor"], c["channel"], m) for c in coverage if c["role"] == "catalog" and c["complete"] for m in c["modalities"]}
    missing = sorted(required - verified)
    vendors = sorted({v for v, channel, modality in required} | {c["vendor"] for c in coverage})
    catalogs = [c for c in coverage if c["role"] == "catalog"]
    vendor_coverage = [{"vendor": v, "complete": bool([c for c in catalogs if c["vendor"] == v])
        and all(c["complete"] for c in catalogs if c["vendor"] == v)
        and not any(scope[0] == v for scope in missing)} for v in vendors]
    complete = bool(catalogs) and not missing and all(c["complete"] for c in catalogs)
    excluded = {(x["vendor"], x["literal_id"]):x["reason"] for x in manifest.get("exclusions", [])}
    for record in observations.values():
        reason = excluded.get((record["vendor"], record["model_id"]))
        if reason: record.update(scope_status="excluded_by_user", exclusion_reason=reason)
    database_outside = sorted({(m["vendor"], m["billing"]["channel"], m.get("modality", "text"))
                               for m in database["models"]} - required)
    if database_outside: complete = False
    differences = [r for r in observations.values() if r["database_status"] != "present" and r.get("scope_status") != "excluded_by_user"]
    return {"status": "complete" if complete else "incomplete",
            "vendor_coverage": vendor_coverage, "missing_scopes": missing,
            "scope_manifest_sha256": hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
            "undeclared_scopes": sorted(declared - required),
            "database_scopes_outside_manifest": database_outside,
            "discovery_verdict": "differences_need_review" if differences else
                ("no_untracked_ids_in_verified_scope" if complete else "inconclusive_incomplete_coverage"),
            "coverage": coverage, "observations": list(observations.values()), "unresolved_rows": invalid,
            "not_in_database": differences,
            "not_observed_this_run_not_retired": [list(k) for k in sorted(prior - observations.keys())],
            "historical_comparison": "no_previous_successful_snapshot" if previous is None else "observation_diff_only",
            "note": "Not-in-database is not newly released; absence is never proof of retirement. No automatic writes."}


def parse_time(value):
    value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None: raise ValueError("Timezone required")
    return value.astimezone(dt.timezone.utc)


def atomic_json(path, payload):
    fd, name = tempfile.mkstemp(prefix=".ledger-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(name): os.unlink(name)


@contextlib.contextmanager
def ledger_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(lock, fcntl.LOCK_UN)


def begin_attempt(state_dir):
    """Reserve a durable, serialized start order BEFORE fetching/parsing inputs."""
    root = pathlib.Path(state_dir)
    with ledger_lock(root):
        counter = root / "sequence.json"
        sequence = json.loads(counter.read_text())["sequence"] + 1 if counter.exists() else 1
        token = {"run_sequence": sequence, "run_id": uuid.uuid4().hex,
                 "run_started_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        atomic_json(counter, {"sequence": sequence})
        (root / "reservations").mkdir(exist_ok=True)
        atomic_json(root / "reservations" / (token["run_id"] + ".json"), token)
        return token


def source_watermarks(result):
    marks = {}
    for row in result.get("coverage", []):
        if row.get("role", "catalog") != "catalog": continue
        timestamp = parse_time(row["observed_at"])
        for modality in row.get("modalities", []):
            key = (row["vendor"], row["channel"], modality)
            marks[key] = min(marks.get(key, timestamp), timestamp)
    if not marks: raise ValueError("Complete baseline requires source timestamps per scope")
    return marks


def previous_success(state_dir):
    root = pathlib.Path(state_dir); pointer = root / "last-successful.json"
    if not pointer.exists(): return None
    name = json.loads(pointer.read_text())["file"]
    if pathlib.Path(name).name != name: raise ValueError("Invalid snapshot pointer")
    result = json.loads((root / name).read_text())
    if result.get("status") != "complete": raise ValueError("Previous baseline was not successful")
    return result


def save_attempt(state_dir, result, attempt=None):
    """Archive every result; locked monotonic pointers; stale source/run never wins.

    Start sequence handles races; source watermarks reject replayed old sources even
    when the replay starts later. Different scope versions require a new state dir.
    """
    root = pathlib.Path(state_dir)
    attempt = begin_attempt(root) if attempt is None else attempt
    with ledger_lock(root):
        reservation = root / "reservations" / (attempt["run_id"] + ".json")
        if json.loads(reservation.read_text()) != attempt: raise ValueError("Invalid run reservation")
        payload = dict(result, **attempt, recorded_at=dt.datetime.now(dt.timezone.utc).isoformat())
        promote = result.get("status") == "complete"
        old = previous_success(root) if promote else None
        reason = "advanced" if promote else "not_complete"
        if promote:
            try:
                current_marks = source_watermarks(result)
                if old:
                    old_marks = source_watermarks(old)
                    if old.get("scope_manifest_sha256") != result.get("scope_manifest_sha256"):
                        reason = "rejected_scope_version_change"
                    elif attempt["run_sequence"] <= old.get("run_sequence", 0): reason = "rejected_stale_run"
                    elif "comparison_baseline_run_id" in result and result["comparison_baseline_run_id"] != old.get("run_id"):
                        reason = "rejected_comparison_baseline_changed"
                    elif any(k not in current_marks or current_marks[k] < v for k,v in old_marks.items()):
                        reason = "rejected_stale_sources"
                if not result.get("scope_manifest_sha256"): reason = "rejected_missing_scope_version"
            except (ValueError, TypeError, KeyError): reason = "rejected_invalid_source_watermarks"
            promote = reason == "advanced"
        payload["baseline_update"] = reason
        target = root / (attempt["run_id"] + ".json")
        with target.open("x") as f:
            json.dump(payload, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.flush(); os.fsync(f.fileno())
        pointer = {"file": target.name, "status": result["status"], "run_sequence": attempt["run_sequence"]}
        latest = root / "latest-attempt.json"
        if not latest.exists() or attempt["run_sequence"] > json.loads(latest.read_text()).get("run_sequence", 0):
            atomic_json(latest, pointer)
        if promote: atomic_json(root / "last-successful.json", pointer)
        return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", required=True)
    p.add_argument("--inventory", required=True)
    p.add_argument("--previous")
    p.add_argument("--scopes", default=str(DEFAULT_SCOPES))
    p.add_argument("--state-dir", required=True, help="Durable attempt ledger; reserve run before all JSON reads")
    p.add_argument("--aliases")
    args = p.parse_args()
    attempt = None
    try:
        attempt = begin_attempt(args.state_dir)
        def load(path): return json.loads(pathlib.Path(path).read_text())
        prior = load(args.previous) if args.previous else previous_success(args.state_dir)
        result = compare_catalogs(load(args.database), load(args.inventory), prior,
                                  load(args.aliases) if args.aliases else (), load(args.scopes))
        result["comparison_baseline_run_id"] = prior.get("run_id") if prior else None
        for name in ("database", "inventory", "scopes"):
            result[name + "_sha256"] = hashlib.sha256(pathlib.Path(getattr(args,name)).read_bytes()).hexdigest()
    except Exception as error:
        result = {"status": "error", "discovery_verdict": "inconclusive_execution_failure",
                  "errors": [{"type": type(error).__name__, "message": str(error)}]}
    try:
        path = save_attempt(args.state_dir, result, attempt)
        result = json.loads(path.read_text()); result["attempt_path"] = str(path)
    except Exception as error:
        print(json.dumps({"status":"error", "ledger_write_failed":str(error), "result":result}, ensure_ascii=False))
        return 4
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "error": return 1
    if result["status"] != "complete": return 2
    return 0 if result["baseline_update"] == "advanced" else 3


if __name__ == "__main__":
    raise SystemExit(main())
