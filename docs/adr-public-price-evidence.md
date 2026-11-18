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

## Model-level normalization batch (2026-11-19 06:37 Asia/Shanghai)

Decision (compatible path approved by coordinator): retain strict `price_verified`
and all old estimator/SDK semantics. A source-bound, normalized model price is a
separate queryable record, NOT an executable offer, native identity passport or
scope/history certificate. `quote_verified` verifies only the literal original.
`selector_completeness` explicitly distinguishes known, missing, unparsed and
not-applicable dimensions. `region=not_stated` never means global; the user's
region is never inferred. All records remain `eligible_for_estimation=false`.

### One complete evidence rule for all vendors

1. Use only the ten approved source-bound HTTP-200 originals (06:31 capture for
   this execution), validated hash, aware observation, vendor/channel and literal
   quote/context. No fetch retry, challenged URL, secret, inferred FX or replay
   freshness. Catalog documents can bridge a display label ONLY through an
   explicit platform Model-ID row, not by slugification or URL-name invention.
2. A queryable model-price record requires a literal official model identifier,
   scalar finite nonnegative amount, explicit currency and billing unit, exact
   charge component, source channel and preserved rate conditions. Identity here
   means the price-table identifier, NOT independently certified invocation/
   provider/alias/lifecycle/output eligibility. Unbindable rows remain candidates.
3. Keep service tier, short/long-context/range, modality/billing basis, resolution,
   price kind and effective conditions separate. A tab's explicit enclosing label
   is binding, not a nearby guessed heading. Multi-amount cells cannot be reduced
   to their first/last number. Deleted list prices and an explicit permanent
   replacement can be separate records; unresolved timed discounts are not a
   payable charge. Date-only schedules retain literal inclusive/exclusive date
   wording and missing timezone precision, never an invented timestamp.
4. Preserve per-million token, image, audio, second and minute units separately;
   an image-input token charge is NOT image-output certification. Currency `$`
   alone is not proof of USD without a source declaration/qualified header.
5. Missing region gives `price_verified=false`, but does not prevent querying a
   correctly normalized price statement. Strict verification is allowed only
   when every applicable selector has source evidence, including explicitly
   stated region/global scope. Native scope/history/entitlement remain unassessed.
6. One parser/validator supplies discovery, v1/v2 API and the existing website API
   query playground. v1 only USD; v2 keeps CNY distinct. Do not alter 89 audited
   calculator rows or SDK. Individual model lookup never silently selects a
   region/date/tier or treats absence of full catalog as an empty model list.

### Positive / negative controls

- Google Carbon: input USD2 through 2026-11-30 and USD4 starting 2026-12-01
  are two conditional records; timezone unknown, never flattened/default-picked.
- MiniMax: M3.1-Flash USD0.15/M input tokens and image-01 USD0.0035/image
  are model prices. M3's deleted/discounted pair cannot become an unqualified
  scalar. PAYG retirement and plan routing remain separate lifecycle evidence.
- OpenAI: gpt-6.2-sol Standard short input USD2/M vs Batch USD1/M remain
  distinct; an Image token input row cannot be charged as output image count.
- xAI: grok-4.7 PAYG threshold rows are separate. Fast offering prose has no
  invocation ID and cannot invent a subscription model or user entitlement.
- Qwen: CNY regional prices remain regional; explicit list price with an undated
  promotion is NOT payable discounted price; ID-less subtable stays unbound.
- Removing literal ID, currency/unit, source body/hash, channel binding or a
  required conditional header prevents normalized/strict approval. Region absent
  stays queryable only with selector incompleteness, never `global`/executable.

### Root-cause blocker matrix (start-of-batch, not completion claims)

| Root class | Existing evidence / internal work | Genuine evidence limit |
|---|---|---|
| Anthropic text | Price table + explicit Claude API Model-ID row bridge; parse/cache/output components | Unbridged historical labels; no inferred historical universe |
| Google text | Literal Model codes + Markdoc price tables; parse service tabs and date schedules | Date-only timezone; region not stated; whole catalog/retirement independent |
| MiniMax text/image/video | LLM/media tables + literal model list; span-aware headers and condition units | Missing region, unsupported mixed cells/expired promos remain unresolved |
| OpenAI text/image/audio | Literal model column + tier headings + per-unit context | USD must be evidenced, not guessed from `$`; generic context threshold may remain literal |
| xAI PAYG/plan | PAYG price-table IDs/units; Fast positive offering-channel prose | Region unstated; no Fast invocation ID or exhaustive native subscription table |
| Qwen four classes | Shared multiheaders, per-ID output components, list-price extraction | 8 ID-less subtables cannot be bound; promotion time absent; unmapped mixed units/cells remain candidates |
| Public prices vs full scopes | Queryable model prices are an internal consumer gap, not login need | Native identity/alias/history/output universe gates unchanged |

All later increments must report normalized model records, actual per-ID HTTP
queries and remaining causes, not merely a larger count of raw paragraphs.

### Implemented batch result and residual matrix (06:57 Asia/Shanghai)

The 06:31 originals now produce **2303 model-price records / 240 literal price
IDs**: Anthropic 25/4, Google 109/14, MiniMax 76/16, xAI PAYG 53/13,
OpenAI 625/54 (currency unresolved), Qwen 1415/139. Counts are conditional records,
not unique invocable models, offers, newly completed scopes or a mutation score.

- **263 USD records / 47 literal IDs** from Anthropic/Google/MiniMax/xAI now enter
  real v1/v2 per-ID lookup. Region/conditions remain explicitly incomplete except
  Anthropic's literal first-party global-default statement (not user region).
- OpenAI's captured Markdown states `$` and units but has no USD declaration.
  Its **625 scalar model records** retain `currency=null`, symbol `$`, distinct
  Standard/Batch/Flex/Priority, short/long, text/image/audio token and minute
  fields; v2 exposes them as currency-unresolved candidates. They are not silently
  changed to USD and are omitted entirely from USD-only v1. Resolving currency is
  a precise additional official declaration need, not a login/export prerequisite.
- Qwen strict price facts are 1319 -> **1337 (+18 media list prices)** when both
  versions use the same 06:31 capture. Another **78 component statements** are
  queryable without certifying native output modality. CNY never replaces USD.
- Qwen residual source causes: 3 free/quota-only or nonscalar price rows; 34
  promotion-term rows (18 newly parsed list-price rows still retain their unknown
  discount dates); 32 partial component rows (20 previously omitted audio/other
  component remainders now explicitly retained); 8 ID-less subtable headers.
  This mixed row/table count is NOT comparable to a directory coverage fraction.
- Google date-only pairs remain two records per priced component/tier; no
  timezone or current/future default is invented. MiniMax permanent deleted/
  replacement prices are separate kinds; timed deleted promotions are not
  accepted as a charge. A quoted 768P/6s video fee stays `per_video`, never divided
  into an invented second rate. Explicit scalar-cell unit overrides table default.
- Existing partial/scalar quote rows remain independently archived. Other
  historical display labels without a literal ID bridge, unparsed mixed/range
  prices, source-only applicability notes and whole-catalog/lifecycle evidence
  are still real residual work/evidence limits. No blanket completion claim.

Production consumers: additive `price-models.json` index and
`price-models/{literal_id}.json`, linked from static index/OpenAPI and the existing
website API playground. Dropdown IDs come from this real price index, not the 89
old estimator models; its response shows selector completeness and missing fields.
Discovery attaches the same normalized statements by exact vendor/channel/ID,
without rewriting native output/alias/history/scope certificates. All 89 audited
estimator records, SDK, M1 and the three universe-contract files remain unchanged.


## Shared source-context correction (B36 review R1–R3)

One pure `public_price_context` component owns Markdoc heading/container scopes,
complete printed billing-unit recognition and literal atomic evidence claims. Both
quote observations and normalized price records consume the same open-tab stack;
`/tab`/`/tabs` terminate ownership. Missing tabs are null, never the preceding tier.
Table source offsets/opening-tab quotes distinguish duplicate printed rows.
Malformed scope is retained as unknown and not normalized. HTML tablepanel scope
uses its existing enclosing-element stack with matching closure controls.

A denominator alone is not a unit. Scalar, price-column header and scoped default
are distinguished: unsupported dimensions/denominators and contradictory specific
cell/header units remain candidates. A weaker source paragraph/table default may
be overridden by a printed scalar unit (e.g. a minute-priced audio session); no
character fee is relabelled as token billing. Strict facts and additional model
records share the recognition gate, including mixed-output Qwen remainders.

Fast availability, subscription-plan billing, public-API exclusion and free-Build
exclusion now each carry a separately evaluated `claim_evidence` predicate and
literal quote/hash. Missing exclusion is null/unknown, not false; other supported
propositions survive. Existing real-original values remain unchanged. This is an
additive nullable-unknown compatibility path, not a weakened `price_verified` or
an inferred API ID/account entitlement. The source remains the ten archived06:31
originals; all generated API/page products are rebuilt, not relabelled fresh.

Controls: actual Google capture/archive five formerly contaminated tables/eleven
observations, live/closed/nested tab controls; Atlas's53 token→character header
variant and unknown/contradictory units through real assemblers/API/page/inventory;
independently deleted Fast propositions and original Markdown positive control.
The latter synthetic inputs are NOT claims of errors in official original rates.
