# Discovery execution contract (first repair delivery)

## Status / scope

This is an executable fetch → capture → extract → compare → ledger entrypoint,
**not an already connected routine, full-catalog acceptance, price updater, or release**.
The saved `llm` prompt was methods-only; it has not been changed here. Sage must
receive this implementation and run the actual command before claiming integration.
The previous temporary `normalize-discovery.py` is NOT the new entrypoint: do not
feed its punctuation-stripped entities into this pipeline. It remains untouched.

`data/discovery-scopes.json` is the independent monitoring contract: ten original
vendors, twelve vendor/channel scopes and their text/image/video modalities,
including zero-database-row Hunyuan and Kimi/xAI subscription channels. Required
coverage is never inferred from prices.json. A database scope outside the manifest
also blocks acceptance. New model families are candidates, not an ID allowlist.
The explicit 2026-10-31 GLM Prime user exclusion remains auditable, not a candidate.

Identity is **literal, case-sensitive and punctuation-preserving**. Display names,
image alt text and detail URL slugs are NOT API IDs. Unresolved rows survive with
source references; conflicting origin/entity identity across sources blocks coverage.
Aliases require an exact allowlisted original-vendor/channel HTTPS URL and quotation
containing both literal IDs; no guessed punctuation/case equivalence or alias chains.
No aliases are enabled by default.

## Exact live command (to be run by Sage after code/version review)

Use the existing approved checkout at its reviewed new SHA; do not switch or merge
main. Replace EXPECTED_SHA with that exact reviewed commit, not ecc1367:

```bash
cd /workspace/alfred/llm-pricing/repo
python3 scripts/run_discovery.py \
  --expected-code-sha EXPECTED_SHA \
  --sources data/discovery-sources.json \
  --scopes data/discovery-scopes.json \
  --state-dir /workspace/sage/llm-pricing/state/discovery-v1 \
  > /workspace/sage/llm-pricing/work/discovery-attempt.json
rc=$?
# Always inspect stdout + latest-attempt, including nonzero rc. Never read only last-successful.
printf 'discovery exit=%s\n' "$rc"
```

Sage must create its own output parent directories before redirecting; redirection
failure is a shell failure before Python can record an attempt. Capture stderr too
when actually connecting the routine. A missing/nonzero result must be handed off,
not treated as "quiet/no changes". This bot did not create those directories or run
this live command, and did not update the routine.

The command validates clean committed discovery code against EXPECTED_SHA and the
scope/config fingerprint (live inputs must match the reviewed committed files), reserves a durable run BEFORE reading configuration,
reads the current remote main commit and `data/prices.json` at that exact commit
using read-only `gh api`, then fetches only configured approved public URLs. Each
source is fetched once, timeout25s, cap8MiB, no retries or automatic redirects.
Redirects need a reviewed canonical source URL; no credentials, browser-session
scraping or internal APIs. A source failure is recorded and other configured sources
still produce evidence. SHA and raw database hash identify the actual main baseline.

## Sources input format

`data/discovery-sources.json` is version1 with:

- `adapter_version`: `discovery-adapters/1-partial` (strictly checked).
- `scope_manifest_sha256`: SHA256 of Python `json.dumps(manifest, sort_keys=True).encode()`.
- `sources`: unique safe IDs plus original `vendor`, `channel`, HTTPS `url`,
  explicit `modalities`, `role` (`catalog`/`price`/`detail`/`lifecycle`), and `adapter`.
- Current adapters: `explicit_id_labels_partial`, `openai_cards_partial`.
  Unknown adapter/config versions fail before requests.
- No input `complete=true` flag or supplied pagination assertion can promote these
  generic adapters. Both explicitly emit partial. Whole-source reviewed adapters
  are still required; do not edit partial to true to make the run green.

Example source:

```json
{"id":"zai-legal-id","vendor":"智谱 Z.ai","channel":"pay_as_you_go",
 "url":"https://docs.z.ai/guides/vlm/glm-5.3-flash.md","modalities":["text"],
 "role":"detail","adapter":"explicit_id_labels_partial"}
```

`Model Code` (ASCII/fullwidth colon and multiple backticked IDs) is supported,
including arbitrary unfamiliar future IDs. OpenAI cards retain current/history,
display label, detail URL and supplemental restricted cards. Neither detail slug
nor image alt becomes an API ID. Full directory, price and per-model detail are
separate roles; a partial price page does not poison an otherwise proved catalog.
xAI Build pricing is explicitly role=price, so it cannot fake the missing full
subscription catalog.

## Output / state / error codes

Under STATE_DIR:

- `sequence.json`, `.lock`: durable monotonic start sequence and POSIX flock.
- `reservations/RUN_ID.json`: immutable identity of the started run.
- `RUN_ID.json`: immutable result (code/config/main versions, coverage, differences,
  unresolved rows, source evidence, run identity and `baseline_update`).
- `captures/RUN_ID/SOURCE_ID.body`, `.json`, `.txt`: raw body, provenance and exact
  extraction text; `inventory.json` is the actual parser input to the comparator.
- `latest-attempt.json`: highest **started** run result, including errors.
- `last-successful.json`: last accepted complete current-source baseline only.

Bad inventory/database/scopes/aliases/previous JSON becomes status=error and a new
failure attempt; last-successful is not replaced. Even corrupt previous baseline
JSON does not prevent recording an error attempt (the corrupt file is not repaired
or overwritten). If the ledger itself cannot be written, stdout reports
`ledger_write_failed`, exit4; do not claim durable failure recording then.

Start order is serialized under flock. Successful baseline promotion additionally
checks per vendor/channel/modality source observation watermarks, scope version,
and the exact prior baseline used by the comparison. A late old run, an old-source
replay started later, or an outdated concurrent comparison cannot move the pointer
backward. Rejected attempts remain archived; latest-pointer order does not regress.
Different monitoring scope versions require a separate explicit state directory;
never silently overwrite the old complete baseline after a scope change.

| Exit | Meaning / required caller action |
|---|---|
| 0 | Complete fresh result and successful-baseline advancement; inspect differences/unresolved states before deciding whether there is anything to report. |
| 1 | Configuration/input/fetch orchestration error; read failure attempt, hand off actual error. |
| 2 | Incomplete coverage/extraction or offline replay; never "no new models". |
| 3 | Complete comparison rejected for stale run/sources/scope/prior-baseline race; read baseline_update, no automatic blind retry. |
| 4 | Ledger persistence failed; hand off stdout/stderr immediately, preserve existing baseline. |

Price unknown is not directory unknown. A model absent this run is not retired.
First fully verified current directory can create the initial baseline without
history. It may report differences against main, not "newly released today".

## Offline verification (never a fresh monitoring acceptance)

```bash
python3 scripts/run_discovery.py --expected-code-sha EXPECTED_SHA \
  --state-dir /workspace/alfred/llm-pricing/work/discovery-fix-2026-11-17/replay-state \
  --replay-dir /workspace/alfred/llm-pricing/work/discovery-fix-2026-11-17/replay-input \
  --replay-database /workspace/sage/llm-pricing/work/2026-11-17-rerun/baseline.json
```

Each SOURCE_ID.body has SOURCE_ID.json with exact `url`, `observed_at`, `sha256`,
`http_status:200`, `capture_kind:"http_body"`. Existing connector-flattened text may
instead say `http_status:null,capture_kind:"tool_text"`; it stays fetch-unverified,
never laundered into a raw successful HTTP response. Missing cache is an explicit
per-source failure. Offline replay never advances last-successful, even if future
adapters become complete. It uses a separate ledger and does not request the web.

`catalog_diff.py --database DB --inventory INVENTORY --scopes SCOPES --state-dir
ISOLATED_STATE [--aliases FILE]` remains a recorded comparison-only utility. It is
not the fresh-fetch routine entrypoint. Its state must not be passed off as proof
that a network request or scheduler invocation happened.

## Remaining adapter/evidence work (not fixed by a prompt)

| Vendor | Exact remaining artifact |
|---|---|
| Anthropic | Full All-model table adapter, explicit first-party ID/display bridges, all rows/count including legacy; partner IDs separate. |
| DeepSeek | Parse already-saved MODEL/API entity rows and documented aliases without guessing; prove whole current two-column model table and route/entity distinction. Price source already available. |
| Google | Parse saved canonical Markdoc endpoint tables, all current/older/shutdown sections; model ID/display/snapshot separation and all-row count. |
| MiniMax | Full FAQ table adapter and native image01 bridge; media multirow prices separate; retirement conflict cannot be resolved by parser guesses. |
| Kimi | Full models.md adapter plus Code subscription coverage. Parent browser supplied six numeric price rows, but currency code/region and K2 eligibility remain unconfirmed; do not turn partial eligibility into global retirement. |
| OpenAI | Public /all parser now captures105 directory cards (38 current/67 historical) plus a separately retained restricted pricing-linked card. Need source-ID bridges and in-scope classification; keep homepage restricted union. Card extraction does not prove every callable ID or variant. |
| xAI | Full model catalog adapter AND actual subscription entitlement catalog; current Build price page does not enumerate the latter. |
| Z.ai | Featured+Other Models+image full adapter; Legal exact Model Code is now extracted. Unverified billing conditions remain separate. |
| Qwen | Parent Singapore market evidence86 cards: native five authors76/Qwen49, third-party10. Need full card/export/variant/native attribution adapter and explicit call-ID bridges; recommended-page generic adapter remains partial. Skeleton details are not full-variant proof. |
| Hunyuan | Native full directory/table adapter, pagination/count, explicit model IDs and native-vs-TokenHub reseller attribution. |

A future full adapter must ship source fixtures, row/DOM-selector coverage,
pagination termination proof, unknown/unpriced/foreign future-ID retention,
source-role/modality/native attribution (`coverage_evidence.native_identity_verified` is required for catalogs), and negative/format-drift fixtures. Generic
labels do not provide that proof. The current production config therefore honestly
returns incomplete. The first repair delivery fixes four infrastructure holes and
provides real plumbing; it does **not** claim full catalog adapters, daily routine
integration, merge or release.
