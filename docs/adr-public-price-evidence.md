# Additive public-price observations, not weakened universe certification

Status: implementation awaiting Jevis/Atlas/Vera review; no release permission.

## Shared boundary and production consumers

`scripts/public_price_facts.py` validates exact approved HTTPS source/vendor/source-channel,
HTTP 200, raw byte hash, timezone-aware observation and literal quotes before parsing.
The Qwen source is the independent, public Chinese `help.aliyun.com` price table,
not a retry of the challenged international root, llms.txt or detail pages.
Native editorial table sections are bounded; third-party tables are not imported.
HTML row/column spans carry their original row, heading chain and explicit Model ID
header. Exact price column, non-price dimensions (mode/context/resolution etc.),
region, CNY, scalar rate and token/image/second unit are retained. Ambiguous scalar
prices and mixed audio/output tables remain candidates. No FX, guessed effective
start or global/historical termination is introduced.

The authoritative originals are under `data/evidence/public-prices/`, with URL,
byte hash, HTTP status and 2026-11-19 +08:00 observation in
`data/public-price-evidence.json`. They are archival evidence, **not a fresh run**.

Discovery uses the same parser, joins only exact vendor/channel/literal ID
(including explicitly pending observed IDs), retains unparsed candidates and
writes a full separate ledger in the attempt capture. Its result carries a
price-evidence facet. This does not overwrite request/native-provider identity,
output, alias, lifecycle or scope certificates. Unmatched known prices are not
lost or interpreted as an empty catalog. Existing universal closure dimensions
remain unknown unless their independent rules are satisfied.

xAI Fast prose explicitly proves the **offering channel**, limited to Cursor and
Grok Build and excluding the public xAI API/free Build tier. It does not name a
literal invocation ID, establish an exhaustive subscription catalog, specify a
region or establish this user's entitlement. Its six quoted token rates remain
unverified price candidates while the positive channel declaration is exposed.
No invented API ID or replacement subscription-native table is emitted.

## Compatibility and actual consumption

- Existing `data/prices.json`, 89 audited model records, estimator quotes, SDK,
  availability/redaction logic, daily/pin and UI layout are unchanged.
- Add `price-facts.json` to each static API index and OpenAPI. **v1 remains
  USD-only**, including candidate payloads; v2 carries explicit CNY observations.
  Fields separate `price_verified`, `scope_complete`, `history_complete`,
  `account_entitlement` and observation/effective times. `evidence_version` hashes
  evidence independently from the unchanged audited-model `data_version`.
- Website build attaches a compact summary to `page-models.json`; the existing
  footer consumes it, explicitly says archival facts are not global directory or
  current availability approval, and links to the actual v2 evidence endpoint.
  This is not a hidden status field or a redesign, and the calculator's existing
  currency filter/price semantics are not replaced.
- These are quoted-source facts at observation, not executable estimator offers,
  historical price intervals, a freshness claim or automatic retirement inference.

## Unchanged release gates / remaining work

No complete directory, historical aliases or retirement population is inferred
from public prices, and no acceptance threshold is waived. The M1 fixture and
three shared unparsed/modality/direct-alias rules remain untouched. Jevis dual
review, full-discovery acceptance, existing UI/operational release checks and
separately authorized merge/deployment remain required. Previously captured
468fc67 fresh evidence cannot be relabeled as this code's fresh run.

## Follow-up: independent HTTP capture and bounded reference consumption

`refresh_public_prices.py` performs only ordinary unauthenticated GETs of the ten
exact reviewed URLs. It has no URL crawling or API/key input. Every attempt gets
new source-bound bytes/time/hash and a manifest. A source is tried once. Failure
records `failed_NOT_fresh`; last-known cache metadata stays separate and old
bodies never enter this attempt's successfully fetched source list. Injected test
transports are explicitly NOT network. `full_discovery_fresh` is always false.
`build_site.py --public-price-capture-dir DIR` and the same runner option consume
the capture through the same validator/parser, not a separate price rule set.

The other eight originals are now consumed as exact quoted price-condition rows
and catalog literal references, including Google Markdoc tables. Time schedules,
service tabs, mixed media units and discounted/old price cells are retained as
conditions, not flattened into a scalar or silently matched to invented API IDs.
A `quote_verified` statement is a verified original statement, **not** approval
of unparsed quote selectors. They appear in the real v2 evidence API. v1 omits
untyped-currency candidate rows. No existing 89-row calculator rate is changed.

Qwen multi-level headers now bind explicit text components to literal Model ID
rows, keeping audio-only charges out of text facts. Explicit `原价X元（限时Y折）`
can evidence the **list price** only (`rate_kind` marks it); payable discount and
effective terms remain candidates. Nested cache/API tables without their own
literal Model ID remain unbound. No nearby-heading or price-name ID inference.

### Region semantics decision — proposal, NOT a relaxed acceptance rule

Known stated region, explicitly global default, and region not stated/unparsed
must be distinct. Unspecified is not global, is not a specific account's region,
and does not disprove that a public source states a price. Proposed shared rule:
verify the quoted price statement independently; require region-specific binding
only for regional applicability/executable quotations. Missing currency, unit,
channel, identity or conditional interpretation remains unresolved separately.
For backward compatibility, until architecture/product approve changing the
meaning of `price_verified`, that field keeps its strict complete-selector gate;
`quote_verified` exposes the already-confirmed public statement without pretending
it has complete regional applicability. A later alternative is to redefine
`price_verified` as statement verification and add `selector_complete` as the
strict executable quote gate. That alternative is NOT enacted in this batch.
