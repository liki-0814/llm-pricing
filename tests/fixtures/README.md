# Estimator fixtures

`estimator-models.json` freezes the inputs used by the deterministic arithmetic,
service-tier, promotion, and calendar tests in `client.test.cjs`. The records are
selected from `api/v1/models.json` at commit
`afcff1f069d98861002e732f945e96814f09f89a`, with unrelated display/source fields
omitted. Snapshot dates and all tested rates/rules are preserved, including the
Opus verification date of 2026-10-20. These are test inputs, not an independently
maintained historical pricing API or a claim about prices on earlier dates.

Do not regenerate these fixtures during routine catalog updates. Change a fixture
and its expected results deliberately when adding or changing estimator behavior.
The helper returns a fresh clone so mutation cases cannot contaminate other tests.

Published data is still tested separately: every current model must estimate at
its own verification date and reject the preceding day, and the HTTP tests read
all real static endpoints. The client-estimate HTTP assertion compares against the
same current model at its own verification date, rather than a frozen price/date.

`media-models.json` freezes six image / video records (selected fields only: `id`, `name`,
`vendor`, `modality`, `media_pricing`, `price_basis`, `billing`, `last_updated`, `unverified_fields`)
copied from `api/v1/models/*.json` when image and video models were added (2026-10-29,
on top of commit `5ca2d568a131522ce93c75ddbea97fa0d7eb22c2`). They drive the deterministic `estimateMedia` arithmetic tests
(per image, per second, per token, batch tier, null prices, promotion and approximate-price warnings).
Do not regenerate them during routine price updates.
