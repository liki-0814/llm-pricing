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
source is fetched once, timeout 25s, cap 8MiB, no retries. A short chain of public
official HTTPS redirects (maximum 3 hops) may be followed when the Location is on
an allowlisted official host for that vendor/channel, with no credentials and no
login or non-public endpoint bypass. Redirect hops and the final URL are recorded
in capture metadata. The configured Anthropic URL is the public canonical
`/docs/en/models/overview`; the previous `/docs/en/about-claude/models/overview`
307 is ordinary public navigation, not a login wall. Gzip or similarly compressed
bodies are decoded at parse time. No browser-session scraping or internal APIs.
A source failure is recorded and other configured sources still produce evidence.
SHA and raw database hash identify the actual main baseline.

## Sources input format

`data/discovery-sources.json` is version1 with:

- `adapter_version`: `discovery-adapters/2-catalog-parsers` (strictly checked).
- `scope_manifest_sha256`: SHA256 of Python `json.dumps(manifest, sort_keys=True).encode()`.
- `sources`: unique safe IDs plus original `vendor`, `channel`, HTTPS `url`,
  explicit `modalities`, `role` (`catalog`/`price`/`detail`/`lifecycle`), and `adapter`.
- Current adapters: `explicit_id_labels_partial`, `openai_cards_partial`,
  `hunyuan_invocation_tables`, `qwen_recommended_lists`, `deepseek_model_row`,
  `kimi_model_tables`, `google_endpoint_tables`, `anthropic_claude_api_id`,
  `minimax_model_list`. Unknown adapter/config versions fail before requests.
- No input `complete=true` flag or supplied pagination assertion can promote these
  adapters. Every current adapter still emits `complete=false` / partial. Do not
  edit partial to true to make the run green. OpenAI directory cards without an
  official API ID are `catalog_entries_pending_api_id`, not unresolved identity
  rows; the snapshot remains incomplete.

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
| Anthropic | First-party Claude API ID rows are parsed from the canonical overview; older/Mythos display names still pending ID; All-models count and legacy coverage are not proved; partner/Bedrock IDs stay excluded. |
| DeepSeek | MODEL-row official IDs are parsed and footnotes stripped; aliases, media, and entity-routing are still not fully classified; whole-table/count proof remains. |
| Google | Endpoint backtick IDs and Model-code labels are parsed; card href slugs are not treated as API IDs. Full section/count/pagination proof remains. |
| MiniMax | Markdown list labels are extracted; invocation IDs and media-row inheritance are not fully confirmed; retirement conflicts are not auto-applied. |
| Kimi | Backticked model tables are parsed, including the deprecated section, without treating eligibility limits as global retirement. Code subscription coverage and currency/region remain unconfirmed. |
| OpenAI | Public /all directory cards are retained as catalog observations (pending official API-ID bridges, not unresolved identity). Slugs and alts are still not API IDs. Homepage restricted cards stay in the union only when absent from /all. Card extraction does not prove every callable ID or variant. |
| xAI | Full model catalog adapter AND actual subscription entitlement catalog; the saved public models HTML is still a shell with almost no explicit catalog table. The Build price page does not enumerate the subscription catalog. |
| Z.ai | Featured+Other Models+image full adapter still missing; Legal exact Model Code is extracted. Unverified billing conditions remain separate. |
| Qwen | The recommended-page adapter now extracts official-looking IDs including `qwen4-max` and splits third-party IDs. This is not the Singapore Model Plaza complete catalog; that body was not in the Sage captures and is not claimed here. Prior browser card counts (86/76/49/10) are not this run's extracted inventory. Skeleton details are not full-variant proof. |
| Hunyuan | Official 调用参数 IDs are parsed after gzip decode, including `hy4`, `hy4-flash`, and `hy4-preview`. TokenHub third-party rows are split out and are not treated as native Hunyuan. Required scope is still text only; pagination and full directory count are not proved. Not marked complete. |

A future full adapter must ship source fixtures, row/DOM-selector coverage,
pagination termination proof, unknown/unpriced/foreign future-ID retention,
source-role/modality/native attribution (`coverage_evidence.native_identity_verified` is required for catalogs), and negative/format-drift fixtures. Generic
labels do not provide that proof. The current production config therefore honestly
returns incomplete. Improved catalog parsers extract more official IDs from saved bodies, but the
production config still honestly returns incomplete. This delivery does **not**
claim full catalog adapters, daily routine integration, merge or release.
