import pathlib,sys,unittest,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import discovery_bridges as b
class BridgeTests(unittest.TestCase):
 def test_zai_closed_request_enums_ignore_response_and_keep_unpriced_future_ids(self):
  spec={'paths':{},'components':{'schemas':{}},'servers':[{'url':'https://api.z.ai/api'}]}
  for route,ids in [('/paas/v4/chat/completions',['future.Native/9']),('/paas/v4/images/generations',['new-image']),('/paas/v4/async/images/generations',['new-image'])]:
   spec['paths'][route]={'post':{'requestBody':{'content':{'application/json':{'schema':{'properties':{'model':{'type':'string','enum':ids}}}}}}}}
  spec['components']['schemas']['Response']={'properties':{'model':{'enum':['not-an-input-model']}}}
  rows,proof=b.zai_request_models(json.dumps(spec));self.assertTrue(proof['verified']);self.assertEqual({x['model_id'] for x in rows},{'future.Native/9','new-image'})
  del spec['paths']['/paas/v4/chat/completions']['post']['requestBody']['content']['application/json']['schema']['properties']['model']['enum']
  self.assertFalse(b.zai_request_models(json.dumps(spec))[1]['verified'])
 def test_zai_schema_rejects_unresolved_ref_or_wrong_server(self):
  rows,proof=b.zai_request_models('{}');self.assertFalse(proof['verified'])
  self.assertFalse(b.zai_request_models('{broken')[1]['verified'])
 def test_openai_directory_does_not_promote_slug_to_id(self):
  rows=b.openai_directory('# All models\n## Deprecated models\n- [Some Name](/api/docs/models/future-name.md): Shut down.\n[Deprecated models](/api/docs/deprecations.md)')
  self.assertIsNone(rows[0]['model_id']);self.assertEqual(rows[0]['lifecycle_status'],'retired')
  self.assertEqual(b.openai_ids('Model ID: `future.Native/9`\n## Model IDs\n- `future.Native/9-2026-11-18`\n## Pricing\n- `not-a-model`'),['future.Native/9','future.Native/9-2026-11-18'])
 def test_anthropic_native_ids_do_not_take_bedrock_or_cloud(self):
  text='### Model IDs\n| Platform | Model ID |\n| --- | --- |\n| Claude API | `future.Native/9` |\n| Amazon Bedrock | `global.foreign` |'
  self.assertEqual(b.anthropic_ids(text),['future.Native/9'])
 def test_detail_url_rejects_login_off_origin_and_path_escape(self):
  self.assertTrue(b.allowed_detail('https://developers.openai.com/api/docs/models/future.md','OpenAI'))
  for u in ['https://evil.test/api/docs/models/a.md','https://developers.openai.com/login','https://developers.openai.com/api/docs/models/../private.md','https://user:pass@developers.openai.com/api/docs/models/a.md']:
   self.assertFalse(b.allowed_detail(u,'OpenAI'))

 def test_runner_detail_bridge_captures_and_missing_id_stays_pending(self):
  import run_discovery as r,tempfile
  from unittest.mock import patch
  src=dict(id='openai-models',vendor='OpenAI',channel='pay_as_you_go',url='https://developers.openai.com/api/docs/models/all.md',adapter='openai_markdown_bridged',role='catalog',modalities=['text','image','video'])
  snap=r.parse_source(b'# All models\n- [Future](/api/docs/models/future.md): no public price',src,'2026-11-18T03:45:00Z')
  with tempfile.TemporaryDirectory() as d,patch.object(r,'fetch_source',return_value=(b'Model ID: `future.Native/9`','2026-11-18T03:45:01Z',{})) as fetch:
   out=r.bridge_catalog(snap,src,pathlib.Path(d));self.assertEqual(fetch.call_count,1);self.assertEqual(out['records'][0]['model_id'],'future.Native/9');self.assertTrue(pathlib.Path(out['records'][0]['identity_evidence']['capture_path']).exists());self.assertFalse(out['complete'])
  snap=r.parse_source(b'# All models\n- [Future](/api/docs/models/future.md): no public price',src,'2026-11-18T03:45:00Z')
  with tempfile.TemporaryDirectory() as d,patch.object(r,'fetch_source',return_value=(b'<html>Loading</html>','2026-11-18T03:45:01Z',{})):
   out=r.bridge_catalog(snap,src,pathlib.Path(d));self.assertIsNone(out['records'][0]['model_id']);self.assertFalse(out['complete'])
 def test_status_deprecated_is_not_retired_and_no_midnight_invention(self):
  text='## Model status\n| API model name | Current state | Deprecated | Tentative retirement date |\n| --- | --- | --- | --- |\n| future.Native/9 | Deprecated | Oct 1, 2026 | November 30, 2026 |\n## Deprecation history\n'
  rows=b.anthropic_status(text);self.assertEqual(rows[0]['lifecycle_status'],'deprecated');self.assertIsNone(rows[0]['retired_at']);self.assertIsNone(rows[0]['retirement_timezone'])

 def test_inline_literal_id_retains_pricing_href_for_front_union(self):
  rows=b.openai_directory('- [Future restricted model](/api/docs/pricing#specialized-models): Model ID: `future.Native/9`.')
  self.assertEqual(rows[0]['model_id'],'future.Native/9');self.assertEqual(rows[0]['detail_url'],'https://developers.openai.com/api/docs/pricing#specialized-models');self.assertFalse(b.allowed_detail(rows[0]['detail_url'],'OpenAI'))

 def test_kimi_payg_finite_native_current_and_deprecated_directory(self):
  import run_discovery as r
  src=dict(vendor='Moonshot Kimi',channel='pay_as_you_go',url='https://platform.kimi.ai/docs/models.md',adapter='kimi_model_tables',modalities=['text'],role='catalog')
  body='# Model List\nReview currently available Kimi multimodal and coding models, plus migration guidance for discontinued models.\n## Multi-modal Model\n| Model Name | Description |\n| - | - |\n| `future.Native/9` | current |\n## Deprecated Models\n| Model Name | Description |\n| - | - |\n| `legacy.Native/9` | Deprecated, not retired |\nFor further assistance, please [contact sales](https://platform.kimi.ai/contact-sales).'
  snap=r.parse_source(body.encode(),src,'2026-11-18T03:50:00Z');self.assertTrue(snap['complete']);self.assertEqual(len(snap['records']),2)
  for broken in [body.replace('## Deprecated Models','## Unclassified other models'),body.replace('For further assistance','Missing terminal'),body.replace('`legacy.Native/9`','Unknown Display Name'),'<html>Loading</html>']:
   self.assertFalse(r.parse_source(broken.encode(),src,'2026-11-18T03:50:00Z')['complete'])
