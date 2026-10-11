# 如何更新 data/prices.json

所有价格都在 `data/prices.json`，页面不含任何硬编码价格。官方报价只填来源中可核实的数字，看不到就写 `null`。用户确认的参照价单独标注 `price_basis.type=reference`，填写参照模型、来源与说明。

## 字段

| 字段 | 说明 |
| --- | --- |
| `id`, `vendor`, `model`, `model_id` | 标识；`vendor` 必须出现在顶层 `vendors` 数组中；`model_id` 必须唯一且只含小写字母、数字、`.`、`-`（它是接口文件名 `api/v1/models/<model_id>.json`） |
| `currency` | 固定 `USD`（站点统一美元计价，validate 会拒绝其他币种） |
| `input` / `output` | 每 100 万 token 价格（数字） |
| `cached_input` | 缓存命中（读取）价 |
| `cache_write` | 缓存写入 / 缓存输出价 |
| 以上价格字段取值 | 数字的依据由 `price_basis` 区分官方价与参照价；`null` = 待核实；`"n/a"` = 官方页没有该项（显示“未列出”） |
| `peak_note` | 高峰/闲时说明文字 |
| `offpeak` | 可选，`{input, output, cached_input}`，闲时价；此时主价格字段写高峰价 |
| `context_length` / `context_tokens` | 显示文本 / 排序用数字；未知两者均为 `null` |
| `source_url` | **必填**，主要官方来源 URL；完整价格依据见 `price_basis` |
| `extra_sources` | 其他官方来源（如上下文长度来源） |
| `last_updated` | 该模型最后核实日期 `YYYY-MM-DD` |
| `notes` | 阶梯价、促销、长上下文价等备注 |
| `reasoning_effort` | **必填**对象，推理强度（取自官方 API 文档）：`supported`（有可调项 true、无可调项 false、待核实 null）、`levels`（由低到高，不适用/待核实为 null）、`default`（默认档，未明确为 null）、`can_disable`（能否关闭，未说明为 null）、`note`、`sources`（官方 URL）。未核实项以精确字段路径列入 `unverified_fields`，如 `reasoning_effort.default`；不可调模型的 levels/default 不适用。接口派生 `status` 和 `field_status` |
| `unverified_fields` | 记录哪些字段待核实（供 validate 输出清单） |

## 更新流程

1. 打开每个模型的 `source_url`，逐项对照价格；有变动就改数字，并把该条 `last_updated` 改为今天。
2. 新增模型：复制一条已有记录，改 `id`（唯一）和各字段。下架旧模型：直接删除该条（本站只收录最新模型）。
3. 修改 `meta.last_updated`（页面顶部显示的“数据更新日期”）。
4. 重新生成接口：`python3 scripts/build_api.py`（生成 `api/v1/`；新增厂商需先在该脚本 `VENDOR_SLUGS` 中加 slug）。
5. 按根目录 README 创建虚拟环境、安装开发依赖，运行 `.venv/bin/python scripts/validate.py` 和回归测试（会打印待核实字段，并检查接口是否同步）。
6. 本地预览：`python3 -m http.server 8000`，打开 http://localhost:8000 。
7. 提交并推送（包括 `api/` 目录），GitHub Pages 会自动更新。

## 推理强度的官方来源

- OpenAI: 各模型页 `https://developers.openai.com/api/docs/models/<model_id>`（`reasoning.effort`）
- Anthropic: https://platform.claude.com/docs/en/build-with-claude/effort 与 .../thinking-troubleshooting
- Google Gemini: https://ai.google.dev/gemini-api/docs/thinking
- MiniMax: https://platform.minimax.io/docs/api-reference/text-chat-openai 、.../guides/text-generation
- DeepSeek: https://api-docs.deepseek.com/guides/thinking_mode
- 智谱: https://docs.z.ai/guides/capabilities/thinking 、https://docs.z.ai/guides/llm/glm-5.3
- Moonshot Kimi: https://platform.kimi.ai/docs/guide/use-thinking-models 、.../use-reasoning-effort
- 阿里云 Qwen: https://docs.qwencloud.com/api-reference/chat/openai-chat 、https://www.alibabacloud.com/help/en/model-studio/deep-thinking

## 本次数据的官方来源

- DeepSeek: https://api-docs.deepseek.com/quick_start/pricing
- OpenAI: https://developers.openai.com/api/docs/pricing
- Anthropic: https://platform.claude.com/docs/en/about-claude/pricing
- 智谱: https://docs.z.ai/guides/overview/pricing ；上下文：https://docs.bigmodel.cn/cn/guide/start/model-overview
- Moonshot Kimi: https://platform.kimi.ai/docs/pricing/chat （K2.8 Preview 仅 Kimi Code 订阅：https://www.kimi.com/code/docs/en/kimi-code/models ）
- 阿里云 Qwen: https://www.alibabacloud.com/help/en/model-studio/model-pricing
- Google Gemini: https://ai.google.dev/gemini-api/docs/pricing
- MiniMax: https://platform.minimax.io/docs/guides/pricing-paygo

## 价格依据、计算与校验补充

开发校验先安装 `requirements-dev.txt`，建议使用仓库 `.venv/bin/python`；站点运行时仍无依赖。

维护时每个模型都要填写 `price_basis`（official/reference、reference_model_id、sources、note）、`billing`（渠道、主价类型、地区、缓存类型、说明）以及 `off_peak_schedule`（无闲时价为 null）。参照价必须引用现有官方报价模型，基本价格与参照模型一致；不可标成官方已核实价。

服务档保留 `multiplier` 作为输入输出展示倍率，补全 `multipliers` 中各 token 与缓存费用项倍率；不知道的倍率为 null。`pricing` 是例外单价的对象，无例外为空对象；`sources` 必填。存储费不默认乘 token 倍率。

价格生效事件补全 `multiplier`（无整体折扣为 null）、`cache_pricing`（存储与缓存例外，无则空对象）、`sources`。分档条件必须精确对应结构化上下界，各区间不能重叠或断开。日期必须是真实日期，不能用过期促销冒充当前已核实价。

`unverified_fields` 精确列出基础价格、limits 和 reasoning_effort 的未核实字段路径；不能漏标或多标。不可调推理的 levels/default 为不适用，不列为待核实。状态由生成器派生，勿手写 API 状态。

运行生成、校验、Python 回归测试和 Node HTTP/计费测试的完整命令见根目录 README；GitHub Actions 使用同一流程。每次修改后需同时提交源数据和生成 JSON，`meta.data_version` 自动由内容生成，不需手动填写。
