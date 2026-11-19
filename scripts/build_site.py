#!/usr/bin/env python3
"""Build a complete immutable Pages artifact. Never mutate source or published tree.

--as-of freezes QA time; --fail-before-publish exercises failed build preservation.
Use a NEW --output directory for each release. deploy-pages publishes the validated
artifact atomically; GitHub cron timing is best effort, not a retirement clock.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import build_api
import build_sdk
import validate

ROOT = build_api.ROOT


def build_site(output, as_of, source_commit=None, fail_before_publish=False, public_price_capture_dir=None):
    if not build_sdk.check():
        raise ValueError("SDK bundle stale; run python3 scripts/build_sdk.py")
    instant = dt.datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if instant.tzinfo is None or "T" not in as_of:
        raise ValueError("as_of requires an exact timezone-aware instant")
    output = pathlib.Path(output).resolve()
    if output.exists():
        raise ValueError("Refusing to overwrite a release; use a new output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence_args={}
    if public_price_capture_dir is not None:
        import public_price_facts
        evidence_args["public_price_ledger"]=public_price_facts.load_capture(public_price_capture_dir)
    d = build_api.load()
    d["meta"]["availability_as_of"] = instant.isoformat()
    d["meta"]["source_commit"] = source_commit
    problems = validate.validate_data(d)
    if problems:
        raise ValueError("Invalid source: " + "; ".join(problems))
    with tempfile.TemporaryDirectory(prefix=".pricing-stage-", dir=output.parent) as temp:
        stage = pathlib.Path(temp) / "site"
        stage.mkdir()
        for name in ("index.html", "api.html"):
            shutil.copy2(ROOT / name, stage / name)
        shutil.copytree(ROOT / "assets", stage / "assets", ignore=shutil.ignore_patterns("*.cjs"))
        (stage / "data").mkdir()
        page = build_api.page_data(d, **evidence_args)
        (stage / "data" / "page-models.json").write_text(build_api.dump(page))
        for version, mixed in (("v1", False), ("v2", True)):
            files = build_api.build(d, mixed=mixed, **evidence_args)
            problems = validate.validate_api(d, files)
            if problems:
                raise ValueError("Invalid " + version + ": " + "; ".join(problems))
            for rel, value in files.items():
                target = stage / "api" / version / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(build_api.dump(value))
        meta = build_api.base_meta(d)
        meta["build_url"] = os.environ.get("GITHUB_SERVER_URL", "https://github.com") + "/" + os.environ.get("GITHUB_REPOSITORY", "liki-0814/llm-pricing") + "/actions/runs/" + os.environ.get("GITHUB_RUN_ID", "local")
        (stage / "deployment.json").write_text(build_api.dump(meta))
        (stage / ".nojekyll").touch()
        if fail_before_publish:
            raise RuntimeError("Simulated failure after full validation, before artifact publication")
        # Same-filesystem rename: a consumer sees no partial output tree.
        os.replace(stage, output)
    return meta


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--as-of", default=dt.datetime.now(dt.timezone.utc).isoformat())
    p.add_argument("--source-commit", default=os.environ.get("GITHUB_SHA"))
    p.add_argument("--fail-before-publish", action="store_true")
    p.add_argument("--public-price-capture-dir",help="Reviewed public HTTP capture manifest; timestamps remain per-source, never full-discovery fresh")
    args = p.parse_args()
    if args.source_commit is None:
        args.source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    print(json.dumps(build_site(args.output, args.as_of, args.source_commit, args.fail_before_publish, args.public_price_capture_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
