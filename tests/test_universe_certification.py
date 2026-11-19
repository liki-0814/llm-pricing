import copy,hashlib,json,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import discovery_universe_contracts as u
import discovery_document_catalogs as d
import discovery_native_claims as n
import discovery_claim_contract as contract
from test_native_claim_consumption import doc,text

class UniverseCertificates(unittest.TestCase):
 def atoms(self):
  e=dict(doc('catalog'),vendor='OpenAI',channel='pay_as_you_go',quote='All documented models',line=1)
  return {k:dict(state='verified',evidence=[e]) for k in ('population','pagination','alias_enumeration','lifecycle')}
 def test_complete_requires_all_dimensions_not_complete_flag(self):
  rows,_=n.openai_detail(doc(text()),{})
  for r in rows:r.update(n.project(r['native_claims']+[n.claim(doc(text()),r['model_id'],'alias',status='none',line=1,quote='Explicit no aliases'),n.claim(doc(text()),r['model_id'],'lifecycle',status='active',line=1,quote='Explicit active')]))
  atoms=self.atoms();c=u.scope_certificate('OpenAI','pay_as_you_go','text',rows,**atoms);self.assertTrue(c['complete'])
  for key in atoms:
   broken=copy.deepcopy(atoms);broken[key]={'state':'verified','complete':True}
   self.assertFalse(u.scope_certificate('OpenAI','pay_as_you_go','text',rows,**broken)['complete'])
 def test_unknown_and_empty_are_not_negative_populations(self):
  c=u.scope_certificate('OpenAI','pay_as_you_go','text',[],**self.atoms());self.assertFalse(c['complete']);self.assertEqual(c['empty_state'],'not_an_empty_population_proof')
  rows,_=n.openai_detail(doc(text()),{});rows[0]['native_claims']=[];self.assertFalse(u.scope_certificate('OpenAI','pay_as_you_go','text',rows,**self.atoms())['complete'])
 def test_context_substitution_does_not_certify(self):
  rows,_=n.openai_detail(doc(text()),{});self.assertFalse(u.scope_certificate('OpenAI','subscription','text',rows,**self.atoms())['complete'])
 def test_explicit_alias_no_alias_and_lifecycle_only(self):
  body=text(suffix=' — Alias for `future.Native/9`').replace('## Model details','Aliases: None\nStatus: Active\n## Model details');rows,_=n.openai_detail(doc(body),{});self.assertEqual(rows[0]['alias_status'],'explicit_no_aliases');self.assertEqual(rows[0]['lifecycle_status'],'active');self.assertEqual(rows[1]['alias_of'],'future.Native/9')
  rows,_=n.openai_detail(doc(text(suffix=' — Snapshot')),{});self.assertNotEqual(rows[1]['alias_status'],'explicit_no_aliases')
  self.assertFalse(contract.valid_claim(dict(doc('x'),model_id='A',kind='alias',status='direct')))
 def test_alias_conflicts_stay_unknown(self):
  source=doc('alias');claims=[n.claim(source,'A','alias',status='direct',alias_of='B',line=1,quote='A aliases B'),n.claim(source,'A','alias',status='none',line=2,quote='A has no aliases')]
  p=n.project(claims);self.assertIsNone(p['alias_of']);self.assertIn('conflicting',p['alias_status'])

class QwenExport(unittest.TestCase):
 def page(self,page,models,total,size=2,filters=None):
  filters=filters or {};query='page_no='+str(page)+'&page_size='+str(size)+''.join('&'+k+'='+str(v) for k,v in filters.items());body=json.dumps({'output':{'models':models,'total':total}}).encode()
  return dict(url='https://dashscope-us.aliyuncs.com/api/v1/models?'+query,body=body,sha256=hashlib.sha256(body).hexdigest(),http_status=200,capture_kind='http_body',request={'page_no':page,'page_size':size,'filters':filters})
 def model(self,mid):return dict(model=mid,provider='qwen',inference_metadata={'response_modality':['Text']})
 def test_complete_account_pages_not_global(self):
  p=u.qwen_catalog_pages([self.page(1,[self.model('A'),self.model('B')],3),self.page(2,[self.model('C')],3)]);self.assertTrue(p['pagination_complete']);self.assertFalse(p['global_universe_verified']);self.assertEqual(p['total'],3);self.assertEqual(p['models'][0]['output_modalities'],['text'])
 def test_verified_empty_account_not_empty_global(self):
  p=u.qwen_catalog_pages([self.page(1,[],0)]);self.assertEqual(p['empty_state'],'verified_empty_account_region_filter');self.assertFalse(p['global_universe_verified'])
 def test_gaps_duplicates_total_filter_region_and_hash_fail_closed(self):
  first=self.page(1,[self.model('A'),self.model('B')],3);last=self.page(2,[self.model('C')],3)
  broken=[];broken.append([last]);broken.append([first,first]);b=copy.deepcopy(last);b['request']['filters']={'providers':'qwen'};broken.append([first,b]);b=copy.deepcopy(last);b['url']=b['url'].replace('dashscope-us.aliyuncs.com','evil.invalid');broken.append([first,b]);b=copy.deepcopy(last);b['sha256']='0'*64;broken.append([first,b]);b=copy.deepcopy(last);b['capture_kind']='documentation_example';broken.append([first,b]);broken.append([first,self.page(2,[self.model('A')],3)])
  for docs in broken:
   with self.assertRaises(ValueError):u.qwen_catalog_pages(docs)
 def test_unrecognized_output_is_unknown_not_input_inheritance(self):
  model=self.model('A');model['inference_metadata']={'request_modality':['Text'],'response_modality':['unreviewed']};p=u.qwen_catalog_pages([self.page(1,[model],1)]);self.assertEqual(p['models'][0]['output_status'],'unknown')

class PublishedDocuments(unittest.TestCase):
 def test_qwen_formal_link_index_fences_and_invalid_rows(self):
  url=next(iter(d.QWEN_INDEXES));body='# Text Generation\n\n- [Native](/help/en/model-studio/native)\n```\n- [Example](/help/en/model-studio/example)\n```'
  rows,proof=d.qwen_index(body,url);self.assertEqual(len(rows),1);self.assertEqual(proof['global_exhaustiveness'],'not_asserted_by_category_index')
  with self.assertRaises(ValueError):d.qwen_index(body+'\n- malformed',url)
 def test_qwen_model_parameter_and_output_not_provider_or_input_guess(self):
  body='# Candidate\nModel ID (the value of the `model` parameter): `native.ID`\n<table><tr><td>Input Modality</td><td>Image</td><td>Output Modality</td><td>Text</td></tr></table>'
  source=doc(body,d.QWEN+'native.md');r=d.qwen_detail(source,{'display_name':'Candidate'});self.assertEqual(r['observed_model_id'],'native.ID');self.assertEqual(r['output_modalities'],['text']);self.assertIsNone(r['model_id']);self.assertFalse(r['api_id_explicit']);self.assertEqual(r['channel_applicability'],'unknown')
 def test_service_provider_literal_is_observed_not_native_author_or_request_id(self):
  source=doc('# qwen-source\n\nThe inference service provider for `qwen-source` is Alibaba Cloud Model Studio.\n<table><tr><td>Output Modality</td><td>Text</td></tr></table>\n',url='https://www.alibabacloud.com/help/en/model-studio/qwen-source.md')
  row=d.qwen_detail(source,{'display_name':'qwen-source'});self.assertEqual(row['observed_model_id'],'qwen-source');self.assertEqual(row['output_modalities'],['text']);self.assertIsNone(row['model_id']);self.assertFalse(row['api_id_explicit']);self.assertFalse(row['request_parameter_ID_explicit'])
 def test_subscription_config_examples_never_model_membership(self):
  source=doc('# Reference\n```toml\n[models]\ndefault="grok-build"\n```\n| `model` | for example `grok-4.7` |', 'https://docs.x.ai/build/settings/reference.md');self.assertEqual(d.xai_subscription_catalog(source),[])
 def test_formal_subscription_native_model_positive_not_complete_universe(self):
  source=doc('# Models\n## Subscription model catalog\n| Model ID | Output modalities | Lifecycle |\n| --- | --- | --- |\n| `native.subscription-ID` | text | Available |','https://docs.x.ai/build/catalog.md');rows=d.xai_subscription_catalog(source);self.assertEqual(rows[0]['channel_applicability'],'verified');self.assertTrue(all(c['channel']=='subscription' for c in rows[0]['native_claims']))
  source['source_url']='https://foreign.invalid/build/catalog.md'
  with self.assertRaises(ValueError):d.xai_subscription_catalog(source)
 def test_access_gate_is_not_a_catalog(self):
  with self.assertRaises(ValueError):d.qwen_index('gateway-diagnostic',next(iter(d.QWEN_INDEXES)))
class XaiApiExportTests(unittest.TestCase):
 def export(self,path,data):
  raw=json.dumps(data).encode();return dict(url='https://api.x.ai/v1/'+path,body=raw,sha256=hashlib.sha256(raw).hexdigest(),http_status=200,capture_kind='http_body',channel='pay_as_you_go')
 def row(self,**kw):return dict(id='grok-4.7',object='model',owned_by='xai',aliases=['grok-alias'],**kw)
 def test_actual_model_fields_are_consumed_without_subscription_or_global_inference(self):
  docs=[self.export('models',{'data':[self.row()]}),self.export('language-models',{'models':[self.row(output_modalities=['text'])]})]
  r=u.xai_catalog_exports(docs);self.assertEqual(r['direct_alias_map'],{'grok-alias':'grok-4.7'});self.assertEqual(r['models'][0]['output_modalities'],['text']);self.assertFalse(r['global_universe_verified']);self.assertFalse(r['subscription_verified'])
 def test_wrong_owner_context_hash_and_input_only_fail_closed(self):
  base=self.export('models',{'data':[self.row()]})
  for patch in ({'channel':'subscription'},{'sha256':'0'*64},{'url':'https://docs.x.ai/v1/models'}):
   with self.subTest(patch=patch),self.assertRaises(ValueError):u.xai_catalog_exports([dict(base,**patch)])
  d=self.export('language-models',{'models':[self.row(input_modalities=['text'])]})
  with self.assertRaises(ValueError):u.xai_catalog_exports([base,d])
 def test_literal_alias_conflicts_fail_closed(self):
  other=self.row();other['id']='grok-other'
  with self.assertRaises(ValueError):u.xai_catalog_exports([self.export('models',{'data':[self.row(),other]})])


class AtlasCertificateContracts(unittest.TestCase):
 def test_unparsed_directory_and_unrecognized_declarations_are_retained_and_not_closed(self):
  snap=dict(vendor='OpenAI',channel='pay_as_you_go',source_url=n.OA,records=[],complete=False,coverage_evidence={'modalities':['text','image'],'native_claim_consumption':{'source_proofs':[{'source_url':'https://developers.openai.com/api/docs/models/a.md','id_enumeration_complete':True}],'errors':[]}})
  root=doc('# All models\n## Flagship models\n- [A](/api/docs/models/a.md)\n## Deprecated models\n### Legacy models\n1. [B](/api/docs/models/b.md)\n',n.OA)
  rows,proof=n.openai_detail(doc('Model ID: `A`\nAliases: None\nStatus: Active\n## Model details\n- Output modalities: text\n## Endpoints\n| Endpoint | Route | Support |\n| --- | --- | --- |\n| Responses | `v1/responses` | Supported |\n## Snapshots\n- `A`', 'https://developers.openai.com/api/docs/models/a.md'),{})
  snap['records']=rows
  certs=u.native_observation_certificates(snap,root)
  self.assertTrue(any(r.get('scope_status')=='unclassified_directory_candidate' and r.get('display_name')=='B' and r.get('quote') for r in snap['records']))
  self.assertTrue(all(c['complete'] is False for c in certs))
 def test_text_proof_does_not_complete_image_certificate(self):
  rows,_=n.openai_detail(doc('Model ID: `A`\nAliases: None\nStatus: Active\n## Model details\n- Output modalities: text\n## Endpoints\n| Endpoint | Route | Support |\n| --- | --- | --- |\n| Responses | `v1/responses` | Supported |\n## Snapshots\n- `A`','https://developers.openai.com/api/docs/models/a.md'),{})
  atoms={k:dict(state='verified',evidence=[dict(doc('catalog'),vendor='OpenAI',channel='pay_as_you_go',quote='All documented models',line=1)]) for k in ('population','pagination','alias_enumeration','lifecycle')}
  text=u.scope_certificate('OpenAI','pay_as_you_go','text',rows,**atoms);image=u.scope_certificate('OpenAI','pay_as_you_go','image',rows,**atoms)
  self.assertTrue(text['complete']);self.assertFalse(image['complete']);self.assertIn('output',image['unmet'])
 def test_unrecognized_alias_and_lifecycle_keep_positive_row_and_refuse_closure(self):
  rows,_=n.openai_detail(doc('Model ID: `A`\nAliases: None\nStatus: Active\n## Model details\n- Output modalities: text\n## Endpoints\n| Endpoint | Route | Support |\n| --- | --- | --- |\n| Responses | `v1/responses` | Supported |\n## Snapshots\n- `A`\nAliases: `B`\nStatus: Unavailable','https://developers.openai.com/api/docs/models/a.md'),{})
  self.assertEqual(rows[0]['model_id'],'A');self.assertTrue(rows[0]['unrecognized_alias_declarations']);self.assertTrue(rows[0]['unrecognized_lifecycle_declarations'])
  atoms={k:dict(state='verified',evidence=[dict(doc('catalog'),vendor='OpenAI',channel='pay_as_you_go',quote='All documented models',line=1)]) for k in ('population','pagination','alias_enumeration','lifecycle')}
  self.assertFalse(u.scope_certificate('OpenAI','pay_as_you_go','text',rows,**atoms)['complete'])
 def test_xai_export_direct_aliases_reject_chains_and_cycles(self):
  def export(rows):
   raw=json.dumps({'data':rows}).encode();return dict(url='https://api.x.ai/v1/models',body=raw,sha256=hashlib.sha256(raw).hexdigest(),http_status=200,capture_kind='http_body',channel='pay_as_you_go')
  def model(mid,aliases):return dict(id=mid,object='model',owned_by='xai',aliases=aliases)
  ok=u.xai_catalog_exports([export([model('A',['alias-A'])])]);self.assertEqual(ok['direct_alias_map'],{'alias-A':'A'});self.assertFalse(ok['global_universe_verified'])
  with self.assertRaises(ValueError):u.xai_catalog_exports([export([model('A',['B']),model('B',['C'])])])
  with self.assertRaises(ValueError):u.xai_catalog_exports([export([model('A',['B']),model('B',['A'])])])
 def test_qwen_snapshot_versions_are_separate_and_challenge_is_not_a_model(self):
  body='# qwen-source\nThe inference service provider for `qwen-source` is Alibaba Cloud Model Studio.\n<table><tr><td>Output Modality</td><td>Text</td></tr></table>\n## Snapshot Versions\n### qwen-source-2026-01-01\nThe inference service provider for `qwen-source-2026-01-01` is Alibaba Cloud Model Studio.\n<table><tr><td>Output Modality</td><td>Image</td></tr></table>\n'
  rows=d.qwen_details(doc(body,url='https://www.alibabacloud.com/help/en/model-studio/qwen-source.md'),{'display_name':'qwen-source'})
  self.assertEqual([r['observed_model_id'] for r in rows],['qwen-source','qwen-source-2026-01-01'])
  self.assertEqual(rows[0]['output_modalities'],['text']);self.assertEqual(rows[1]['output_modalities'],['image']);self.assertTrue(all(r['model_id'] is None for r in rows))
  with self.assertRaises(ValueError) as err:d.qwen_details(doc('sessionStorage.x5referer = 1; _____tmd_____/punish x5secdata=abc',url='https://www.alibabacloud.com/help/en/model-studio/qwen-source.md'),{'display_name':'x'})
  self.assertIn('access_blocked',str(err.exception))

 def test_self_closing_snapshot_spans_and_reviewed_provider_sentences(self):
  cap='<table><tr><td>Output Modality</td><td>Text</td></tr></table>'
  img='<table><tr><td>Output Modality</td><td>Image</td></tr></table>'
  vid='<table><tr><td>Output modalities</td><td>Video</td></tr></table>'
  body='\n'.join([
   '# qwen-source <span id="h-title" />',
   'The inference service provider for `qwen-source` is Alibaba Cloud Model Studio.',
   cap,
   '## Snapshot Versions <span id="h-snap" />',
   '### qwen-source-2026-01-01 <span id="h-a" />',
   'The inference service provider for `qwen-source-2026-01-01` is Alibaba Cloud Model Studio.',
   img,
  ])
  rows=d.qwen_details(doc(body,url='https://www.alibabacloud.com/help/en/model-studio/qwen-source.md'),{'display_name':'qwen-source'})
  self.assertEqual([r['observed_model_id'] for r in rows],['qwen-source','qwen-source-2026-01-01'])
  self.assertEqual(rows[0]['output_modalities'],['text']);self.assertEqual(rows[1]['output_modalities'],['image'])
  self.assertTrue(all(r['model_id'] is None and r['native_vendor_status']=='unknown_provider_not_explicit' for r in rows))
  body='\n'.join([
   '# qwen-image-source',
   'The inference service provider for the `qwen-image-source` model is Alibaba Cloud Model Studio.',
   img,
  ])
  rows=d.qwen_details(doc(body,url='https://www.alibabacloud.com/help/en/model-studio/qwen-image-source.md'),{'display_name':'qwen-image-source'})
  self.assertEqual(rows[0]['observed_model_id'],'qwen-image-source');self.assertEqual(rows[0]['output_modalities'],['image']);self.assertIsNone(rows[0]['model_id'])
  body='\n'.join([
   '# ZHIPU/GLM-source',
   'The inference service provider for `ZHIPU/GLM-source` is Z.AI.',
   cap,
  ])
  rows=d.qwen_details(doc(body,url='https://www.alibabacloud.com/help/en/model-studio/glm-source.md'),{'display_name':'ZHIPU/GLM-source'})
  self.assertEqual(rows[0]['observed_model_id'],'ZHIPU/GLM-source')
  self.assertEqual(rows[0]['inference_service_provider_evidence'][0]['provider'],'Z.AI')
  self.assertIsNone(rows[0]['model_id'])
  body='\n'.join([
   '# wan-source',
   'The inference service for the `wan-source` model is provided by Alibaba Cloud Model Studio.',
   vid,
  ])
  rows=d.qwen_details(doc(body,url='https://www.alibabacloud.com/help/en/model-studio/wan-source.md'),{'display_name':'wan-source'})
  self.assertEqual(rows[0]['observed_model_id'],'wan-source');self.assertEqual(rows[0]['output_modalities'],['video']);self.assertIsNone(rows[0]['model_id'])

if __name__=='__main__':unittest.main()
