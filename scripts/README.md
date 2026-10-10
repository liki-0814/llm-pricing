# 如何更新 data/prices.json

所有价格都在 `data/prices.json`，页面不含任何硬编码价格。**只填官方页面上能看到的数字，看不到就写 `null`**（页面会显示“待核实”）。

## 字段

| 字段 | 说明 |
| --- | --- |
| `id`, `vendor`, `model`, `model_id` | 标识；`vendor` 必须出现在顶层 `vendors` 数组中；`model_id` 必须唯一且只含小写字母、数字、`.`、`-`（它是接口文件名 `api/v1/models/<model_id>.json`） |
| `currency` | 固定 `USD`（站点统一美元计价，validate 会拒绝其他币种） |
| `input` / `output` | 每 100 万 token 价格（数字） |
| `cached_input` | 缓存命中（读取）价 |
| `cache_write` | 缓存写入 / 缓存输出价 |
| 以上价格字段取值 | 数字 = 已核实；`null` = 待核实；`"n/a"` = 官方页没有该项（显示“未列出”） |
| `peak_note` | 高峰/闲时说明文字 |
| `offpeak` | 可选，`{input, output, cached_input}`，闲时价；此时主价格字段写高峰价 |
| `context_length` / `context_tokens` | 显示文本 / 排序用数字；未知两者均为 `null` |
| `source_url` | **必填**，官方定价页 URL |
| `extra_sources` | 其他官方来源（如上下文长度来源） |
| `last_updated` | 该模型最后核实日期 `YYYY-MM-DD` |
| `notes` | 阶梯价、促销、长上下文价等备注 |
| `unverified_fields` | 记录哪些字段待核实（供 validate 输出清单） |

## 更新流程

1. 打开每个模型的 `source_url`，逐项对照价格；有变动就改数字，并把该条 `last_updated` 改为今天。
2. 新增模型：复制一条已有记录，改 `id`（唯一）和各字段。下架旧模型：直接删除该条（本站只收录最新模型）。
3. 修改 `meta.last_updated`（页面顶部显示的“数据更新日期”）。
4. 重新生成接口：`python3 scripts/build_api.py`（生成 `api/v1/`；新增厂商需先在该脚本 `VENDOR_SLUGS` 中加 slug）。
5. 运行校验：`python3 scripts/validate.py`（同时会打印所有待核实字段，并检查 `api/v1/` 是否与数据同步，不同步会报错）。
6. 本地预览：`python3 -m http.server 8000`，打开 http://localhost:8000 。
7. 提交并推送（包括 `api/` 目录），GitHub Pages 会自动更新。

## 本次数据的官方来源

- DeepSeek: https://api-docs.deepseek.com/quick_start/pricing
- OpenAI: https://developers.openai.com/api/docs/pricing
- Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
- 智谱: https://docs.z.ai/guides/overview/pricing ；上下文：https://docs.bigmodel.cn/cn/guide/start/model-overview
- Moonshot Kimi: https://platform.kimi.ai/docs/pricing/chat
- 阿里云 Qwen: https://www.alibabacloud.com/help/en/model-studio/model-pricing
- Google Gemini: https://ai.google.dev/gemini-api/docs/pricing
