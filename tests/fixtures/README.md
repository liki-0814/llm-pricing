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
