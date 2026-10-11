# 大模型 API 价格速查

中文静态站点，直接部署到 GitHub Pages；运行时只有 HTML、CSS 和 JavaScript，无后端、数据库或第三方运行依赖。

覆盖 9 个厂商、44 个模型，统一美元 / 每百万 token；缓存存储另按百万 token·小时计价。价格表支持主题、厂商筛选、多关键词搜索、排序、URL 分享、移动端卡片和价格详情。官方报价和用户确认的参照价均保留，参照价会显式标注依据。

## 本地预览

```bash
python3 -m http.server 8000
```

打开 `http://localhost:8000/`；接口文档和费用试算在 `http://localhost:8000/api.html`。请通过 HTTP 访问，不能直接打开 `file://`。

## 直接查询

基础地址：`https://liki-0814.github.io/llm-pricing/api/v1/`。本地可替换成 `http://localhost:8000/api/v1/`。

| GET 路径 | 返回数据 |
| --- | --- |
| `index.json` | 轻量索引：模型 ID、厂商 slug 和接口路径 |
| `models.json` | 全部模型 |
| `models/<model_id>.json` | 单模型，完整价格、来源和规则 |
| `vendors.json` | 全部厂商和模型目录 |
| `vendors/<vendor>.json` | 单厂商及其所有模型 |
| `openapi.json` | OpenAPI 3.1 合约 |

数据接口统一返回 `{api_version, meta, data}`；`data` 在列表接口为数组，单模型为对象，索引为对象。厂商详情另含 `vendor`。`links` 和索引的路径均相对于基础地址 `api/v1/`，用 `new URL(path, BASE)` 拼接，不以单模型文件所在目录为基准。

`meta.updated_at` 是数据核实日期，`meta.data_version` 是源数据内容的 SHA-256，同一数据快照的所有接口一致。不存在的路径返回部署平台的 404（GitHub Pages 通常为 HTML），调用方先检查 HTTP 状态再解析 JSON。静态服务器不会处理 `?vendor=` 等筛选参数。

```bash
BASE='https://liki-0814.github.io/llm-pricing/api/v1'
curl --fail --silent --show-error "$BASE/index.json"
curl --fail --silent --show-error "$BASE/models/gemini-3.1-pro-preview.json"
curl --fail --silent --show-error "$BASE/vendors/openai.json"
curl --fail --silent --show-error "$BASE/models.json" \
  | jq '.data | map(select(.vendor == "openai" and .price_basis.type == "official")) | sort_by(.pricing.input) | .[:5]'
```

GitHub Pages 当前返回 `Access-Control-Allow-Origin: *`，支持跨域 fetch。CDN 缓存可能延迟数据更新，核对版本时应同时查看日期和 `data_version`。

## 自然调用：轻量 JavaScript 客户端

HTML 加载 `assets/client.js`，全局对象为 `LLMPrice`。Node.js 18+ 可通过 `require` 使用同一文件，无 npm 安装步骤。

```js
const { createClient, estimate } = require('./assets/client.js');
const api = createClient('https://liki-0814.github.io/llm-pricing/api/v1/');

async function main() {
  const { data: model } = await api.getModel('gemini-3.1-pro-preview');
  const { data: openai } = await api.getVendor('openai');
  const { data: cheapest } = await api.listModels({
    vendor: 'openai', sort: 'input', limit: 5, priceBasis: 'official'
  });
  const { data: matches } = await api.listModels({ q: 'gemini pro' });
  const result = estimate(model, { inputTokens: 300000, outputTokens: 10000 }, {
    at: '2026-10-11'
  });
  console.log(result.total, result.breakdown, result.warnings); // 1.38 USD
}
main().catch(console.error);
```

`getIndex()` 和 `listVendors()` 返回目录；`getOpenAPI()` 直接返回 OpenAPI 描述对象；`api.estimate(id, usage, options)` 可以一次取模型并计算。筛选和排序在客户端执行，HTTP 请求仍然是普通 GET 静态文件。`sort` 支持 input/output/cached_input/cache_write/context_length/max_output_tokens/name，前缀 `-` 表示降序；未知价格始终排最后。`meta.count` 是返回数，`matched_count` 是筛选匹配数，`total_count` 是全量数。

客户端默认 15 秒超时，可用 `{timeoutMs: 5000}` 调整。错误具有稳定 `code`：`NOT_FOUND`、`HTTP_ERROR`、`TIMEOUT`、`NETWORK_ERROR`、`INVALID_RESPONSE`、`INVALID_ARGUMENT`、`PRICE_UNAVAILABLE`、`PRICE_EXPIRED`、`HISTORICAL_PRICE_UNAVAILABLE`、`UNSUPPORTED_SERVICE_TIER`、`LIMIT_EXCEEDED`、`TIME_REQUIRED`、`HOLIDAY_REQUIRED`。

## 命令行 DNS 超时的处理与线上检查

本机排查发现，VPN 的系统 DNS 将 Pages 域名解析到虚拟地址，curl 和 Node 的 TCP 连接超时；通过 HTTPS DNS 获取公开地址后，两个客户端都能连接。正常网络继续使用上面的普通查询。如果遇到同类 DNS 问题，可以明确启用下面的查询方式：

```bash
curl --fail --silent --show-error --connect-timeout 10 --max-time 20 \
  --doh-url https://dns.google/dns-query \
  https://liki-0814.github.io/llm-pricing/api/v1/models/grok-4.7.json
```

```js
const { createClient } = require('./assets/client.js');
const { createDohFetch } = require('./assets/node-doh.cjs');
const base = 'https://liki-0814.github.io/llm-pricing/api/v1/';
const api = createClient(base, { fetch: createDohFetch(base) });
api.getModel('grok-4.7').then(({data}) => console.log(data.pricing));
```

Node 传输只为所选 HTTPS 源查询 DNS，并按 DNS TTL 缓存地址；HTTP Host、TLS SNI 和证书校验仍使用原域名。它不修改系统 DNS、VPN、全局 fetch 或其他进程，不固定 CDN IP，也不关闭证书校验。HTTPS DNS 服务不可达时会明确报错，客户端超时同时取消 DNS 和数据请求。

```bash
# 正常网络省略 --doh；第二个位置参数可指定检查结果 JSON 文件。
node scripts/check_live.cjs --doh \
  https://liki-0814.github.io/llm-pricing/api/v1/ /tmp/llm-pricing-live.json
```

该命令用 curl 和 Node 客户端逐一查询本地快照对应的全部线上 JSON 路径，核对 HTTP 状态、JSON 类型、实际内容与版本；再验证未知模型/厂商的 404、Grok 筛选和费用计算。内容不一致或请求失败时退出码非零。它属于发布后的人工检查，CI 保留不依赖外部站点的本地检查。

## 费用计算口径

`inputTokens` 为总输入，包含缓存读取、缓存创建和 1 小时 TTL 创建的 token；这些部分会从普通输入中扣除，不能重复计费。`outputTokens` 包含供应商计费的思考 token。可选用量：`cachedInputTokens`、`cacheWriteTokens`、`cacheWrite1hTokens`、`storageTokenHours`（token 数乘存储小时数）。

计算按总输入选择分档 → 高峰/闲时 → 价格生效日期 → 服务档各费用项倍率 → 服务档例外单价 → 数据驻留倍率 → 各项用量费用。`cacheType` 可选 implicit/explicit；默认使用该模型 `pricing.cached_input` 的已标注类型。`serviceTier` 默认 standard；`dataResidency: true` 可叠加已列出的驻留费用。

```js
const r = await api.estimate('gemini-3.5-flash-lite', {
  inputTokens: 1000000, outputTokens: 0, cachedInputTokens: 1000000,
  storageTokenHours: 1000000
}, { at: '2026-10-11', serviceTier: 'batch' });
// 缓存读取 0.02 + 存储 1.00 = 1.02 USD；不能统一乘 0.5。
```

- `at` 为 `YYYY-MM-DD` 或带时区的 ISO 时间；省略时用当前时间。日期规则按 UTC 日匹配，官方仅给日期时没有更精确的切换时刻。
- DeepSeek 需完整时间；工作日高峰窗口还需明确 `isChineseHoliday: true/false`。不内置猜测的节假日日历。
- 已公布的未来价格自动生效；超出已确认的促销期限会要求复核。截止日期未知的促销会附带警告。
- 更早日期的历史价不在该快照中，计算会拒绝；晚于核实日的估算会说明快照可能未涵盖后续未公布调整。
- 缺失且实际使用的价格报错，不当作零；未使用的未知费用项不影响计算。未提供最大输出时不猜上限。
- 参照价返回 `price_basis` 和订阅提示，仅作成本参考，不代表会员额度或实际账单。
- Grok 4.7 的长上下文价从总输入 **200,000** tokens 开始（含缓存），整次请求输入/缓存/输出价为 4/1/12 美元；短上下文为 2/0.5/6。Priority ×2、美国区域 ×1.1；只有响应确认 Priority 才采用其倍率。
- 返回 `total`、`breakdown`、`unit_prices`、分档、时段、依据和 warnings。范围为记录内的 token 与缓存费用，排除工具、税费、未收录的多模态费率和订阅额度结算。

## 数据范围与状态

`data/prices.json` 为唯一数据源；`api/v1/` 由脚本生成，勿手改。

模型字段仍限于价格、推理强度、上下文与最大输出、分档、服务档、缓存、生效日期及来源。未恢复最大输入、思考子上限、模态、功能、知识截止、思考预算、可用性、快照和别名。新增的 `price_basis`、`billing`、`off_peak_schedule` 只表达价格依据和计费口径。

- `pricing_status`：verified 官方价；reference 用户确认参照价；unverified 待核实；not_listed 官方未列。
- `price_basis`：official/reference，参照模型 ID、来源 URL 与说明。原参照数值保留。
- `billing`：按量/订阅渠道、current/list/reference 主价格类型、已记录地区、主缓存读取类型。
- `reasoning_effort.field_status`：verified/unverified/not_applicable；不可调模型的档位与默认值为不适用，未说明的关闭选项为待核实，整体状态据此派生。
- `limits.max_output_tokens`：数值为独立输出上限；`null` 且出现在 `unverified_fields` 为待核实，否则表示官方明确无独立输出上限（见 note）。上下文窗口仍有记录的上限。
- `service_tiers[].multiplier` 仅为输入输出展示倍率；实际计算使用 `multipliers` 各费用项倍率和 `pricing` 例外单价。存储费单独处理。
- `price_schedule` 支持各 token 价格、缓存细分与存储费；`multiplier` 非空时对该输入档的 token/缓存价格应用倍率，存储费按独立字段处理。

完整字段定义见 `api.html` 和 `api/v1/openapi.json`。本站仅收录 `meta.scope` 规定的模型，不是全部在售模型目录。

## 更新、验证和 CI

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python scripts/build_api.py
.venv/bin/python scripts/validate.py
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/*.test.cjs
```

只有开发校验使用 jsonschema；部署站点和客户端无第三方运行依赖。校验检查真实日期、非负有限价格、唯一标识、缺失标记、缓存口径、参照关系、分档范围、时段、价格生效日期及所有响应的 OpenAPI Schema，并逐文件核对生成结果。

GitHub Actions 在 push、pull request 和手动运行时执行同样的校验、回归测试、全部静态数据接口的 HTTP 查询及 JavaScript 语法检查。CI 只验证，不自动部署或改写数据。

## 部署到 GitHub Pages

将网站文件、`data/` 和生成的 `api/` 一起提交到仓库根目录。在仓库 Settings → Pages 中选择 Deploy from a branch，分支为 `main`、目录为 `/ (root)`。发布后使用站点地址访问页面和 `api/v1/`；更新数据时先完成上述校验，再按现有发布流程推送。`.nojekyll` 保留在根目录。

## 数据来源与本次修复

按现有官方来源逐项核对需要修正的规则：

- [Gemini 官方定价](https://ai.google.dev/gemini-api/docs/pricing)：Flash-Lite 的缓存例外单价、Pro 的 Batch/Flex 缓存原价与 Priority 存储倍率、Flash 2027 年存储涨价。
- [DeepSeek 定价](https://api-docs.deepseek.com/quick_start/pricing/)：UTC 高峰时段、中国节假日与闲时价。
- [Claude 定价](https://platform.claude.com/docs/en/about-claude/pricing)：缓存 TTL、Batch 和数据驻留倍率。
- [MiniMax 模型调用](https://platform.minimax.io/docs/guides/text-generation)和[按量定价](https://platform.minimax.io/docs/guides/pricing-paygo)：订阅 Preview 模型及 M3 参照价格。
- [Kimi Code 模型配置](https://www.kimi.com/code/docs/en/kimi-code/models)：订阅模型、推理档位和上下文来源。
- [Grok 4.7 官方指南](https://docs.x.ai/developers/grok-4-7)、[定价](https://docs.x.ai/developers/pricing)和[推理规则](https://docs.x.ai/developers/model-capabilities/text/reasoning)：500,000 上下文、无独立文本输出上限、长上下文阈值、缓存、Priority 和美国区域计费。

本次针对已发现问题核实相关规则，没有声称重新核实所有已收录模型的全部价格。每个模型的 `source_url`、`extra_sources` 和结构化 `sources` 可追溯具体依据。未知数值保留未知，不用其他模型的值冒充官方确认。
