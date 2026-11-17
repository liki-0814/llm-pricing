# Audited update evidence, 2026-11-17 (Asia/Shanghai)

Input baseline: main `73f8579161d2957e6a3f19d8c30557172fc77f6a` (71 models). Source captures were obtained by Sage's real rerun from 20:18:11 through 20:26:37 Beijing time, not a claimed fresh scrape by this implementation. The following local snapshot hashes were independently recomputed and matched the input manifest:

| Snapshot | SHA-256 | Source / checked lines |
|---|---|---|
| qwen4-detail.txt | ab8516ca5865e352ec47da4781dfd6d6ad7760ce6f48a5c38022be4a4159f31d | https://www.alibabacloud.com/help/en/model-studio/qwen4-max — 15 invocation ID; 117–119 mode-dependent limits; 143–145 effort; 149–153 Singapore ordinary 1.5/4.5 USD |
| tencent-pricing.txt | 2609703c5b23646ec860769dce1920cf3c3aafe5d206e6a410dea58af8f1b34d | https://cloud.tencent.com/document/product/1823/130055 — 26/28 precise Beijing offer cutoffs/restoration; 40–46 Guangzhou CNY rates and cache-write '-' |
| tencent-catalog.txt | 89aa96175459af9cbe483c5ccbe96dff3cae124a6942b63958b274859ad23d95 | https://cloud.tencent.com/document/product/1823/130051 — 32–34 call IDs/context/input/output; Preview 2026-12-07 date only |
| openai-pricing.txt | 9fedf073cb8ebedd918f314f36109f7fa16726baafbc3b0c848182102e936f4c | https://developers.openai.com/api/docs/pricing — 159 promotional pricing available until November 30, 2026 |

Imported only ordinary text pricing in the exact recorded channel/region. Hy4-flash directory 0.5/2/0.02 CNY per million input/output/cache hit; Hy4 and Preview directory 6/18/0.3. Flash/Hy4 offers are 50%, not assumed for Preview. No cache write zero. Qwen4 cache table is merged/ambiguous and not imported. Sol original monetary values retained.

Full input path on the shared box: `/workspace/sage/llm-pricing/work/2026-11-17-rerun/`; report `2026-11-17-rerun.md` in the parent directory. Own evidence adapter/comparison outputs: `/workspace/alfred/llm-pricing/work/catalog-inventory-2026-11-17.json` and `catalog-comparison-2026-11-17.json`. They are review artifacts, not a canonical official catalog or auto-import list. Coverage status remains **incomplete**, not 'no new models'.
