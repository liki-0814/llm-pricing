"""Adapter regressions: previous extractors miss official IDs that the new parsers recover."""
import gzip, pathlib, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import discovery_adapters as a
import catalog_diff as c

HY4_TABLE = """
<table><tr><th>模型名称</th><th>model（调用参数）</th></tr>
<tr><td>Hy4 flash</td><td>hy4-flash</td></tr>
<tr><td>Hy4</td><td>hy4</td></tr>
<tr><td>Hy4 preview（2026-12-07下线）</td><td>hy4-preview</td></tr>
<tr><td>DeepSeek-V4.1-Flash-1017 原厂直供</td><td>deepseek/deepseek-flash</td></tr>
</table>
"""
QWEN_PAGE = """
<html><body>
<div>qwen4-max</div><div>Complex reasoning and coding</div>
<div>qwen3.7-plus</div>
<div>deepseek-v4-pro-0813</div>
<div>glm-5.3</div>
<div>cost-effective</div>
<div>audio/video</div>
</body></html>
"""
GOOGLE = """
{% table variant="model" %}
  * Model
  * Endpoint
  ---
  * [Gemini 3.8 Live](/docs/models/gemini-3.8-live)
  * `gemini-3.8-live`
{% /table %}
"""
KIMI = """
## Multi-modal Model
| Model Name | Description |
| `kimi-k3.1-pro` | flagship |
## Deprecated Models
| `kimi-k2.6` | No longer available to newly registered users; deprecation expected in late December 2026. |
"""
DEEPSEEK = """
<table><tr><th>MODEL</th><td>deepseek-flash (1)</td><td>deepseek-v4-pro</td></tr>
<tr><th>MODEL VERSION</th><td>DeepSeek-V4.1-Flash-1017</td><td>DeepSeek-V4-Pro-0813</td></tr></table>
"""
ANTHROPIC = """
<table>
<tr><th>Feature</th><th>Claude Sonnet 5.5 The best combination</th></tr>
<tr><td>Claude API ID</td><td>claude-sonnet-5-5</td></tr>
<tr><td>Amazon Bedrock ID</td><td>anthropic.claude-sonnet-5-5</td></tr>
</table>
<table>
<tr><th>Model</th><th>Capabilities</th></tr>
<tr><td>Claude Sonnet 5.5</td><td>1M</td></tr>
<tr><td>Claude Mythos 5.2</td><td>1M</td></tr>
</table>
"""

class AdapterRegressions(unittest.TestCase):
    def ids(self, recs):
        return [r["model_id"] for r in recs if r.get("api_id_explicit")]

    def test_hy4_ids_fail_generic_extractor_then_pass_table_adapter(self):
        body = HY4_TABLE.encode()
        old = a.explicit_id_labels(body)[0]
        self.assertFalse({ "hy4", "hy4-flash", "hy4-preview" } & {r.get("model_id") for r in old})
        recs, reseller, notes = a.parse("hunyuan_invocation_tables", gzip.compress(body))
        self.assertEqual(self.ids(recs), ["hy4-flash", "hy4", "hy4-preview"])
        self.assertEqual(self.ids(reseller), ["deepseek/deepseek-flash"])
        self.assertTrue(any("tokenhub" in n for n in notes))

    def test_qwen4_max_fails_generic_extractor_then_is_extracted_without_english_noise(self):
        body = QWEN_PAGE.encode()
        self.assertFalse(any(r.get("model_id")=="qwen4-max" for r in a.explicit_id_labels(body)[0]))
        recs, reseller, notes = a.parse("qwen_recommended_lists", body)
        self.assertIn("qwen4-max", self.ids(recs))
        self.assertIn("qwen3.7-plus", self.ids(recs))
        self.assertNotIn("cost-effective", self.ids(recs)+self.ids(reseller))
        self.assertNotIn("audio/video", self.ids(recs)+self.ids(reseller))
        self.assertEqual(set(self.ids(reseller)), {"deepseek-v4-pro-0813", "glm-5.3"})

    def test_google_uses_endpoint_codes_not_href_slugs_only(self):
        recs, _, _ = a.parse("google_endpoint_tables", GOOGLE)
        self.assertEqual(self.ids(recs), ["gemini-3.8-live"])

    def test_kimi_tables_keep_deprecated_without_bulk_retirement(self):
        recs, _, _ = a.parse("kimi_model_tables", KIMI)
        self.assertEqual(self.ids(recs), ["kimi-k3.1-pro", "kimi-k2.6"])
        retired = next(r for r in recs if r["model_id"]=="kimi-k2.6")
        self.assertEqual(retired["catalog_section"], "deprecated")
        self.assertEqual(retired["retirement"], "pending_confirmation")

    def test_deepseek_model_row_strips_footnote_not_id_text(self):
        recs, _, _ = a.parse("deepseek_model_row", DEEPSEEK)
        self.assertEqual(self.ids(recs), ["deepseek-flash", "deepseek-v4-pro"])

    def test_anthropic_uses_first_party_row_not_bedrock(self):
        recs, _, _ = a.parse("anthropic_claude_api_id", ANTHROPIC)
        self.assertEqual(self.ids(recs), ["claude-sonnet-5-5"])
        self.assertFalse(any("bedrock" in (r.get("model_id") or "") for r in recs))
        pending = [r for r in recs if not r.get("api_id_explicit")]
        self.assertEqual([r["display_name"] for r in pending], ["Claude Mythos 5.2"])

    def test_openai_cards_are_pending_not_unresolved_and_slug_is_not_an_id(self):
        html = b'<main><a href="/api/docs/models/new-family-99"><img src="/images/api/models/icons/n.webp"><div>Future Family</div></a></main>'
        recs, _, _ = a.parse("openai_cards_partial", html)
        self.assertEqual(len(recs), 1)
        self.assertIsNone(recs[0]["model_id"])
        self.assertTrue(recs[0]["catalog_observation"])
        result = c.compare_catalogs({"models": []}, [{
            "vendor": "OpenAI", "channel": "pay_as_you_go", "complete": False, "role": "catalog",
            "source_url": "https://developers.openai.com/api/docs/models/all", "observed_at": "2026-11-17T12:00:00Z",
            "fetch_status": "ok", "extraction_status": "partial", "errors": ["partial"],
            "coverage_evidence": {"source_url": "https://developers.openai.com/api/docs/models/all", "modalities": ["text"],
                                  "enumeration_verified": False, "pagination_complete": False},
            "records": recs
        }], scopes={"version": 1, "scopes": [{"vendor": "OpenAI", "channel": "pay_as_you_go", "modalities": ["text"], "official_hosts": ["developers.openai.com"]}]})
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(len(result["unresolved_rows"]), 0)
        self.assertEqual(len(result["catalog_entries_pending_api_id"]), 1)
