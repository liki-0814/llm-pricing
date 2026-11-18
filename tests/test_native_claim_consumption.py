import hashlib,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import discovery_native_claims as n
import discovery_bridges as bridge
import run_discovery as runner
import catalog_diff as diff
FIX=pathlib.Path(__file__).parent/'fixtures/native-claims'
AT='2026-11-18T08:00:00Z'
def doc(text,url='https://developers.openai.com/api/docs/models/future.md'):
 return dict(text=text,source_url=url,source_sha256=hashlib.sha256(text.encode()).hexdigest(),capture_path='/synthetic/raw.body',observed_at=AT)
def text(outputs='text',suffix='',support='Supported'):
 return f'Model ID: `future.Native/9`\n## Model details\n- Input modalities: image\n- Output modalities: {outputs}\n## Endpoints\n| Endpoint | Route | Support |\n| --- | --- | --- |\n| Responses | `v1/responses` | {support} |\n## Snapshots\n- `future.Native/9-2026`{suffix}'
def byid(rows,mid):return next(x for x in rows if x['model_id']==mid)
class DetailClaims(unittest.TestCase):
 def parse(self,body,entity=None):return n.openai_detail(doc(body),entity or {'catalog_section':'Flagship models'})
 def test_actual_moderation_legal_eof_and_both_ids_typed(self):
  for name in ('latest','stable'):
   body=(FIX/('text-moderation-'+name+'.md')).read_text();rows,proof=n.openai_detail(doc(body,'https://developers.openai.com/api/docs/models/text-moderation-'+name+'.md'),{})
   self.assertTrue(proof['id_enumeration_complete']);self.assertEqual(proof['termination'],['EOF'])
   for mid in ('text-moderation-'+name,'text-moderation-007'):
    row=byid(rows,mid);self.assertEqual(row['output_modalities'],['text']);self.assertEqual(row['channel_applicability'],'verified');self.assertEqual(row['lifecycle_status'],'retired');self.assertTrue(all(x['source_sha256'] for x in row['native_claims']))
 def test_eof_and_following_heading_equivalent(self):
  a,pa=self.parse(text());b,pb=self.parse(text()+'\n## Rate limits\naccount specific')
  for x,y in zip(a,b):self.assertEqual((x['model_id'],x['output_modalities'],x['channel_applicability']),(y['model_id'],y['output_modalities'],y['channel_applicability']))
  self.assertTrue(pa['id_enumeration_complete']);self.assertTrue(pb['id_enumeration_complete'])
 def test_snapshot_is_not_automatic_direct_alias_mapping(self):
  rows,_=self.parse(text());self.assertIsNone(rows[1]['alias_of']);self.assertIn('not_a_direct_mapping',rows[1]['alias_status'])
 def test_openweight_endpoint_is_not_proven_native_payg(self):
  rows,_=self.parse(text(),{'catalog_section':'Open-weight models'})
  self.assertTrue(all(x['channel_applicability']=='unknown' for x in rows));self.assertTrue(all(x['output_modalities']==['text'] for x in rows))
 def test_openweight_preface_cannot_borrow_other_section(self):
  rows,_=self.parse('An open-weight model.\n'+text());self.assertTrue(all(x['channel_applicability']=='unknown' for x in rows))
 def test_input_is_not_output_and_negative_endpoint_not_supported(self):
  rows,_=self.parse(text().replace('- Output modalities: text\n',''));self.assertTrue(all(not x['output_modalities'] for x in rows))
  rows,_=self.parse(text(support='Not supported'));self.assertTrue(all(x['channel_applicability']=='unknown' for x in rows))
 def test_fence_character_length_and_example_isolation(self):
  for opening,closing in (('~~~','~~~'),('````','`````')):
   sample=opening+'python\nModel ID: `not.Native/Example`\n```\n## Model IDs\n- `also.Not/Native`\n'+closing+'\n'+text()
   ids=bridge.openai_ids(sample);self.assertEqual(set(ids),{'future.Native/9','future.Native/9-2026'})
 def test_unclosed_fence_is_not_valid_eof_alias_termination(self):
  rows,p=self.parse(text()+'\n```python\n- `not.Native/Example`')
  self.assertFalse(p['id_enumeration_complete']);self.assertEqual(rows[1]['channel_applicability'],'unknown');self.assertNotIn('not.Native/Example',{x['model_id'] for x in rows})
 def test_unparsed_alias_row_preserves_primary_but_does_not_bind_snapshot(self):
  rows,p=self.parse(text()+'\n- arbitrary display only')
  self.assertFalse(p['id_enumeration_complete']);self.assertEqual(rows[0]['output_modalities'],['text']);self.assertFalse(rows[1]['output_modalities'])
 def test_cloud_provider_ids_not_native_invocation_identity(self):
  rows,_=self.parse(text()+'\n## Cloud providers\n| Provider | Model ID |\n| AWS | `foreign.cloud/ID` |')
  self.assertNotIn('foreign.cloud/ID',{x['model_id'] for x in rows})
 def test_conflict_survives_known_other_source_and_order(self):
  bad=text().replace('- Output modalities: text','- Output modalities: text\n- Output modalities: image');a,_=self.parse(bad);b,_=self.parse(text());claims=a[0]['native_claims']+b[0]['native_claims'];x=n.project(claims);y=n.project(list(reversed(claims)))
  self.assertEqual(x,y);self.assertTrue(x['output_conflict']);self.assertEqual(x['output_modalities'],[]);self.assertEqual(x['unknown_output_modalities'],['image','text'])
 def test_duplicate_details_conflict_survives_cross_page_known_output(self):
  bad=text().replace('## Endpoints','## Model details\n- Output modalities: image\n## Endpoints');a,_=self.parse(bad);b,_=self.parse(text());combined=n.project(a[0]['native_claims']+b[0]['native_claims']);self.assertTrue(combined['output_conflict']);self.assertFalse(combined['output_modalities']);self.assertEqual(combined['unknown_output_modalities'],['image','text'])
 def test_source_hash_path_and_source_boundaries_required(self):
  for changes in ({'source_sha256':None},{'capture_path':None},{'source_url':'https://foreign.invalid/api/docs/models/future.md'},{'source_url':'https://developers.openai.com/api/docs/models/../private.md'}):
   d=doc(text());d.update(changes)
   with self.assertRaises(ValueError):n.openai_detail(d,{})
 def test_projection_refuses_cross_model_identity_mix(self):
  with self.assertRaises(ValueError):n.project([{'model_id':'one','kind':'identity'},{'model_id':'two','kind':'identity'}])
class XaiClaims(unittest.TestCase):
 BODY='''# Models
### Text API Pricing
| Model | Context | Input / 1M tokens | Cached input / 1M tokens | Output / 1M tokens |
| --- | --- | --- | --- | --- |
| future.text (< 200k prompt tokens) | 500k | $2 | $0.5 | $6 |
| future.text (≥ 200k prompt tokens) | 500k | $4 | $1 | $12 |
### Image & Video Pricing
| Model | Cost |
| --- | --- |
| Future.Native/Image | $0.02 / image |
| Future.Native/Video | $0.05 / sec |
## Model Aliases
* `<modelname>-latest` is a generic template.
'''
 def test_typed_output_units_channel_and_long_context_merge(self):
  rows=n.xai_records(doc(self.BODY,n.XAI));self.assertEqual(len(rows),3)
  for mid,modality in [('future.text','text'),('Future.Native/Image','image'),('Future.Native/Video','video')]:
   row=byid(rows,mid);self.assertEqual(row['output_modalities'],[modality]);self.assertEqual(row['channel_applicability'],'verified');self.assertIsNone(row['alias_of'])
  self.assertEqual(len(byid(rows,'future.text')['native_claims']),6)
 def test_alias_templates_not_invented_as_ids(self):
  self.assertFalse(any('latest' in r['model_id'] or '<' in r['model_id'] for r in n.xai_records(doc(self.BODY,n.XAI))))
 def test_subscription_source_cannot_borrow_payg_claims(self):
  with self.assertRaises(ValueError):n.xai_records(doc(self.BODY,'https://docs.x.ai/developers/pricing'))
 def test_unrecognized_unit_not_assigned_from_model_name(self):
  rows=n.xai_records(doc(self.BODY.replace('$0.02 / image','$0.02 / unknown'),n.XAI));self.assertNotIn('Future.Native/Image',{r['model_id'] for r in rows})
class ActualConsumption(unittest.TestCase):
 def test_runner_then_diff_consumes_claims_and_preserves_unknown_channel(self):
  src=dict(id='openai-models',vendor='OpenAI',channel='pay_as_you_go',url=n.OA,adapter='openai_markdown_bridged',role='catalog',modalities=['text','image'])
  root='# All models\n## Open-weight models\n- [Future](/api/docs/models/future.md)\n';manifest=diff.scope_manifest()[0]
  with tempfile.TemporaryDirectory() as td,patch.object(runner,'fetch_source',return_value=(text().encode(),AT,{})):
   cap=pathlib.Path(td);body=root.encode();(cap/'root.body').write_bytes(body);snap=runner.parse_source(body,src,AT);snap=runner.bridge_catalog(snap,src,cap);snap.pop('_extraction_text');snap.update(capture_path=str(cap/'root.body'),source_sha256=hashlib.sha256(body).hexdigest());inv=[snap];runner.apply_native_claims(inv,cap)
   result=diff.compare_catalogs({'models':[]},inv,scopes=manifest);row=byid(result['observations'],'future.Native/9');self.assertEqual(row['channel_applicability'],'unknown');self.assertEqual(row['output_modalities'],['text']);self.assertEqual(row['scope_status'],'pending_native_channel_applicability');self.assertTrue(row['native_claims']);self.assertEqual(result['status'],'incomplete')
 def test_explicit_official_alias_projection_keeps_observed_literal(self):
  raw='alias.Native/9';target='future.Native/9';claims=[n.claim(doc(text()),raw,'output',values=['text']),n.claim(doc(text()),raw,'native_channel',status='verified',reason='synthetic native fixture')]
  snap=dict(vendor='OpenAI',channel='pay_as_you_go',source_url=n.OA,observed_at=AT,records=[dict(model_id=raw,api_id_explicit=True,native_claims=claims)],complete=False,coverage_evidence={'modalities':['text']})
  aliases=[dict(vendor='OpenAI',channel='pay_as_you_go',source_url=n.OA,alias=raw,canonical=target,evidence_quote=raw+' maps directly to '+target)]
  result=diff.compare_catalogs({'models':[]},[snap],aliases=aliases);row=result['observations'][0];self.assertEqual(row['model_id'],target);self.assertEqual(row['output_modalities'],['text']);self.assertTrue(all(x['observed_model_id']==raw for x in row['native_claims']))
 def test_malformed_claim_json_is_rejected_not_a_consumer_crash(self):
  for value in ('wrong', {'kind':'output'}, {'model_id':'A','kind':'output','values':'text'}, None):self.assertFalse(n.valid_claim(value))
 def test_diff_rejects_foreign_or_mismatched_claim(self):
  claim=n.claim(doc(text()),'different.ID','output',values=['image']);row={'model_id':'future.Native/9','api_id_explicit':True,'native_claims':[claim]};snap=dict(vendor='xAI',channel='pay_as_you_go',source_url=n.XAI,observed_at=AT,records=[row],complete=False,coverage_evidence={'modalities':['text']})
  result=diff.compare_catalogs({'models':[]},[snap]);rec=result['observations'][0];self.assertFalse(rec['output_modalities']);self.assertEqual(rec['channel_applicability'],'unknown');self.assertTrue(rec['native_claim_errors'])
if __name__=='__main__':unittest.main()
