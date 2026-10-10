# 大模型 API 价格速查

纯静态站点（HTML/CSS/JS，无构建步骤、无外部依赖），可直接部署到 GitHub Pages。中文界面（zh-Hans）：

- 深色 / 浅色主题切换（默认跟随系统，选择会记住；也可用 `?theme=dark` 强制）
- 吸顶导航与吸顶表头，厂商彩色标签，每列最低价自动标记“最低”（随筛选结果变化）
- 厂商筛选、搜索（支持空格分隔多关键词，`/` 聚焦、`Esc` 清空）、点击表头排序（升序 → 降序 → 默认），缺失值始终排最后
- 筛选/搜索/排序状态同步到 URL，可直接分享（如 `?vendor=anthropic&sort=-output`）
- 手机端为卡片布局，提供“排序方式”下拉框
- “待核实”（未能从官方核实）与“未列出”（官方页没有该项）区分显示
- 公开查询接口：静态 JSON（`api/v1/`），文档见 `api.html`

所有价格统一为 **美元（USD）/ 每 100 万 token**。

```
index.html               价格表页面
api.html                 接口文档（含 curl / JS / Python 示例与在线试用）
assets/style.css         样式（浅色 + 深色，响应式）
assets/theme-init.js     <head> 中预先设置主题，避免闪烁
assets/common.js         主题切换、厂商 slug、复制、提示
assets/app.js            价格表：渲染 / 排序 / 筛选 / 最低价标记
assets/api.js            接口文档页：示例与在线试用
data/prices.json         全部价格数据（唯一数据源）
api/v1/                  由 scripts/build_api.py 生成的静态 JSON 接口（勿手改）
scripts/build_api.py     生成 api/v1/
scripts/validate.py      数据校验 + 检查 api/v1/ 是否与数据同步
scripts/README.md        如何更新数据
.nojekyll
```

## 本地预览

```bash
cd llm-pricing
python3 -m http.server 8000
# 浏览器打开 http://localhost:8000 ，接口文档 http://localhost:8000/api.html
```
（必须用 HTTP 服务器，直接打开 file:// 会因 fetch 限制无法加载 JSON。）

## 公开查询接口（静态 JSON）

GitHub Pages 无法运行服务端，所以接口是预生成的静态文件，直接 `GET` 即可：

| 路径（相对 `https://<用户名>.github.io/<仓库名>/`） | 内容 |
| --- | --- |
| `api/v1/models.json` | 全部模型，`meta` 含 `updated_at`、`currency`（USD）、`unit`（per_1M_tokens）、`count` |
| `api/v1/models/<model_id>.json` | 单个模型，如 `api/v1/models/deepseek-flash.json` |
| `api/v1/vendors.json` | 全部厂商（slug、名称、模型数、模型 ID、官方来源） |
| `api/v1/vendors/<vendor>.json` | 单个厂商及其模型；vendor 为 `deepseek` `openai` `anthropic` `zhipu` `moonshot` `qwen` `google` |
| `api/v1/openapi.json` | OpenAPI 3.1 描述 |

每个模型的字段固定：`id`、`name`、`vendor`、`vendor_name`、`currency`、`unit`、`pricing{input, output, cached_input, cache_write}`、`pricing_status{…: verified | unverified | not_listed}`、`has_off_peak`、`off_peak_pricing{input, output, cached_input} | null`、`peak_note`、`context_length`（token 数）、`context_length_label`、`source_url`、`extra_sources`、`last_updated`、`notes`、`reasoning_effort{supported, levels, default, can_disable, status, note, sources}`、`unverified_fields`、`links`。`reasoning_effort` 为各厂商官方文档中的推理强度 / 思考档位（如 OpenAI `reasoning.effort`、Claude `output_config.effort`、Gemini `thinking_level`、Kimi/GLM/DeepSeek `reasoning_effort`、Qwen `reasoning_effort` / `enable_thinking`），其中 `null` 表示待核实，不做推测。价格为 `null` 时用 `pricing_status` 区分“待核实”和“官方未列出”。

```bash
curl -s https://<用户名>.github.io/llm-pricing/api/v1/models.json | jq '.data[] | {id, input: .pricing.input}'
```

- **跨域**：GitHub Pages 默认对所有文件返回 `Access-Control-Allow-Origin: *`，任意网页都能直接 `fetch`，无需 `_headers` 文件（GitHub Pages 也不支持自定义响应头）。
- **缓存**：GitHub Pages CDN 约缓存 10 分钟。
- **不支持查询参数**（`?vendor=` 会被忽略），请取回 `models.json` 后在客户端筛选。

### 修改数据后必须重新生成接口

```bash
python3 scripts/build_api.py   # 根据 data/prices.json 重新生成 api/v1/（会删除多余的旧文件）
python3 scripts/validate.py    # 校验数据，并逐文件检查 api/v1/ 是否同步；不同步则退出码为 1
```
`build_api.py --check` 也可单独检查同步状态。生成结果是确定性的（不含时间戳），只有数据变化才会改动文件。新增厂商时需在 `scripts/build_api.py` 的 `VENDOR_SLUGS` 中添加 slug（`assets/common.js` 中有同样的映射，用于页面配色和链接）。

## 部署到 GitHub Pages

1. 在 GitHub 新建仓库（如 `llm-pricing`，Public）。
2. 把本目录**内容**上传到仓库根目录（`index.html` 须在根目录，`api/` 目录要一起提交）：
   - 命令行：`git init && git add . && git commit -m "init" && git branch -M main && git remote add origin git@github.com:<你的用户名>/llm-pricing.git && git push -u origin main`
   - 或在网页端 “Add file → Upload files” 拖入全部文件。
3. 仓库 **Settings → Pages**：Source 选 “Deploy from a branch”，Branch 选 `main` / `/ (root)`，保存。
4. 等待 1–2 分钟，访问 `https://<你的用户名>.github.io/llm-pricing/`，接口在 `…/llm-pricing/api/v1/models.json`。

## 数据说明

- 数据核实日期：2026-10-10；每条记录带官方来源 URL 与核实日期。
- 只收录最新模型，范围见 `data/prices.json` 的 `meta.scope`。
- 价格可能随时调整，请以官方页面为准。更新方法见 `scripts/README.md`。
