import pathlib, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import discovery_adapters as a
import run_discovery as r
import catalog_diff as c

CODE = '<main><h1>Model Configuration</h1><h2>Model Overview</h2><p>Kimi Code currently offers six model IDs.</p><table><tr><th>Model ID</th><td>k3.1-pro</td><td>k3.1-pro-highspeed</td><td>k3</td><td>k3-256k</td><td>kimi-for-coding</td><td>kimi-for-coding-highspeed</td></tr><tr><th>Model version</th><td>K3</td></tr></table><h2>How to Switch Models</h2></main>'
SOURCE=dict(id='kimi-code',vendor='Moonshot Kimi',channel='subscription',url='https://www.kimi.com/code/docs/en/kimi-code/models',modalities=['text'],role='catalog',adapter='kimi_code_catalog')
XAI='### Text API Pricing\n| Model | Context | Input / 1M tokens |\n| --- | --- | --- |\n| future.Family/9 (< 200k prompt tokens) | 500k | $2 |\n| future.Family/9 (≥ 200k prompt tokens) | 500k | $4 |\n### Image & Video Pricing\n| Model | Cost |\n| --- | --- |\n| grok-imagine-new | $0.02 / image |\n'

class LiveDiscoveryTests(unittest.TestCase):
 def test_kimi_code_six_literal_ids_and_counted_current_coverage(self):
  snap=r.parse_source(CODE.encode(),SOURCE,'2026-11-18T03:40:00Z')
  self.assertEqual(len(snap['records']),6)
  self.assertTrue(snap['complete'])
  self.assertEqual(snap['coverage_evidence']['expected_record_count'],6)
  self.assertIn('kimi-for-coding',[x['model_id'] for x in snap['records']])
 def test_kimi_count_mismatch_missing_id_truncation_and_unknown_future_id(self):
  for text in [CODE.replace('six model IDs','seven model IDs'),CODE.replace('<td>k3</td>','<td>Unknown Display Name</td>'),CODE.replace('<h2>How to Switch Models</h2>',''),'<html>Loading...</html>']:
   self.assertFalse(r.parse_source(text.encode(),SOURCE,'2026-11-18T03:40:00Z')['complete'])
  snap=r.parse_source(CODE.replace('k3-256k','future.Family/9').encode(),SOURCE,'2026-11-18T03:40:00Z')
  self.assertTrue(snap['complete'])
  self.assertIn('future.Family/9',[x['model_id'] for x in snap['records']])
 def test_xai_official_markdown_reads_model_cells_not_alias_examples(self):
  rows,_,_=a.parse('xai_markdown_models',XAI)
  self.assertEqual([x['model_id'] for x in rows],['future.Family/9','grok-imagine-new'])
  self.assertTrue(all(x['price_public'] for x in rows))
 def test_zai_overview_keeps_display_rows_pending_including_quoted_other_models(self):
  text='| Model | Strength | Resource |\n| :- | :- | :- |\n| GLM-5.3 | text | [Guide](https://docs.z.ai/guides/llm/glm-5.3.md) |\n> | Model | Strength | Resource |\n> | :- | :- | :- |\n> | New Unknown Display | text | [Guide](https://docs.z.ai/guides/llm/new.md) |'
  rows,_,_=a.parse('zai_overview_tables',text)
  self.assertEqual(len(rows),2)
  self.assertTrue(all(not x['api_id_explicit'] and x['catalog_observation'] for x in rows))
 def test_minimax_unlinked_retired_rows_survive_without_invented_invocation_ids(self):
  text='## Available Models\n| Model | Description |\n| :- | :- |\n| [MiniMax-H3](https://platform.minimax.io/docs/guides/video-generation.md) | text |\n## Retired Models\nThe following models have been retired and are no longer available.\n| Model | Type | Status |\n| :- | :- | :- |\n| MiniMax-M2.5 | LLM | Retired |\n| Music-2.5+ | Music | Retired |'
  rows,_,_=a.parse('minimax_model_list',text)
  self.assertEqual(len(rows),3)
  self.assertEqual(sum(x.get('lifecycle_status')=='retired' for x in rows),2)
  self.assertTrue(all(not x['api_id_explicit'] for x in rows))

 def test_retirement_notices_keep_source_and_unknown_instant_separate_from_ids(self):
  manifest={'version':1,'scopes':[{'vendor':'MiniMax','channel':'pay_as_you_go','modalities':['text'],'official_hosts':['platform.minimax.io']}]}
  src=dict(vendor='MiniMax',channel='pay_as_you_go',role='catalog',url='https://platform.minimax.io/docs/faq/models.md',adapter='minimax_model_list',modalities=['text'])
  snap=r.parse_source(b'## Retired Models\n| Model | Type | Status |\n| :- | :- | :- |\n| MiniMax-M2.5 | LLM | Retired |',src,'2026-11-18T03:40:00Z');snap.pop('_extraction_text')
  result=c.compare_catalogs({'models':[]},[snap],scopes=manifest)
  self.assertEqual(result['retirement_notices'][0]['display_name'],'MiniMax-M2.5')
  self.assertIsNone(result['retirement_notices'][0]['retired_at'])
  self.assertEqual(result['retirement_notices'][0]['observed_at'],'2026-11-18T03:40:00Z')
  self.assertEqual(result['status'],'incomplete')

 def test_invalid_record_shape_does_not_break_retirement_notice_export(self):
  manifest={'version':1,'scopes':[{'vendor':'MiniMax','channel':'pay_as_you_go','modalities':['text'],'official_hosts':['platform.minimax.io']}]}
  snap={'vendor':'MiniMax','channel':'pay_as_you_go','source_url':'https://platform.minimax.io/docs/faq/models.md','observed_at':'2026-11-18T03:40:00Z','records':None}
  result=c.compare_catalogs({'models':[]},[snap],scopes=manifest)
  self.assertEqual(result['status'],'incomplete')
  self.assertEqual(result['retirement_notices'],[])
