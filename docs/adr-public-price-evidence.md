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
