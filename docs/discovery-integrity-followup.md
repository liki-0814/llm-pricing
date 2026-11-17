# 2026-11-17 bounded discovery follow-up

This is evidence/guard improvement, not full monitoring acceptance and not a new-model import. No routine changed.

## Fixed locally

- A caller's `complete=true` is insufficient. Verified fetch/extraction, whole-catalog/pagination evidence, nonempty explicit-ID rows, matching source record count, all tracked vendor/channel scopes and error-free extraction are required. Partial/empty/invalid/failed input cannot report no untracked IDs, and a successful subset cannot mark the whole vendor complete.
- Explicit invocation labels accept alphanumeric IDs; marketing names never become API IDs merely by punctuation normalization. A horizontal API-ID table adapter selects the first-party row, not partner-platform rows. Source-backed scoped aliases reject conflicts/chains/cycles rather than guessing.
- Immutable per-attempt ledger records current observations; latest attempt exposes incomplete failure, exit code 2 is mandatory for incomplete runs, and failures preserve last successful baseline. First fully verified current run establishes the first successful baseline without requiring nonexistent history. Until then save partial evidence honestly. Historical first-discovery dates cannot be recovered. Caller/scheduler integration and active failure notification remain a separate operational step; none was silently activated.

## Actual replay

Read-only GitHub main check at 2026-11-17 21:05 Beijing confirmed `73f8579161d2957e6a3f19d8c30557172fc77f6a` (71 models). Offline replay read the exact git object's prices and hash-verified the existing original Sage source snapshots, with no ID whitelist. Reproduction and complete results remain in the task work directory as `bounded-catalog-replay.py`, `catalog-comparison-bounded.json`, and `bounded-catalog-summary.json`.

Result: 499 unique scoped observations, **451 untracked-ID review-queue items, not 451 new models**; 215 unresolved rows. None of the vendors is complete. Downgraded 23 normalized IDs without literal source-row evidence. Official Anthropic name/API-ID columns provided three bridges to existing public database IDs (Opus/Sonnet/Haiku 5.5), without global hyphen/dot replacement. Partner API-ID rows no longer leak into the native Anthropic catalog. TokenHub third-party queue is isolated from native Tencent attribution (125 untracked channel observations, not original-vendor IDs). These counts are not directly comparable with earlier raw-occurrence counts.

Known samples Qwen4-Max/Hy4 three IDs still emerge independently. Extra examples include `claude-fable-5-2` (first-party API-ID row), `gemini-3.8-live` (billing conditions still incomplete) and `grok-4.6` (scope review, not a missed latest-model claim). Old generations, snapshots, display aliases, other channels and IDs lacking complete billing conditions remain in review/unresolved categories; no automatic import or retirement. Missing subscription scopes include Kimi/xAI. Other directory coverage and media extraction gaps still require bounded source/adapter work, not an unsupported complete label.

## Bounded source requests: two per vendor, then stop

DeepSeek: `https://api-docs.deepseek.com/quick_start/pricing/` returned numeric pricing in WebFetch; one additional public HTML request saved HTTP200, 29,133 bytes, SHA256 `5efd7e7661de5b86a1a3d5569ea5d9d8633bf1ca1c311ec42baace85ef18d78e`, at 21:04:19 Beijing. Six peak/off-peak token fields each for current Flash/Pro match main (12 values). Exact rows and hashes saved; no price/source data imported. Previous no-trailing-slash captured an introduction; current success is proven, the historical response difference's cause is not. The source explicitly separates retired old entities from accepted route aliases; no automatic entity/ID migration is applied. Full speech/tool/model enumeration is not established by this token table.

Kimi: `https://platform.kimi.ai/docs/pricing/chat.md` again contained narrative without numeric price table; second and final request to canonical `https://platform.kimi.ai/docs/pricing/chat` returned HTTP200, 145,324 bytes, SHA256 `e540c9dc2e3d94865ea2e09b939ae5bb8a210ad76b8001053f5b9e0469e1803c` at 21:04:20 Beijing. Visible HTML contains no table or USD numeric values either. Stop: no inferred zero/unchanged claim. Next concrete step is a separately scoped official rendered table/export or vendor confirmation of the missing numeric component, not cross-domain search. Existing values retain prior verification dates.

## Remaining gates

Re-review the new exact SHA, including standalone SDK and confirmed-retired unknown-time cases. Full discovery completeness is still not accepted. Build failures/latency, actual Pages mode transition and CDN behavior require an authorized release exercise and named incident owner/escalation deadline. These are not erased by unit tests or the first-baseline mechanism.
