"""Unified 7ac rejection regressions: evidence, formal blocks, exact eligibility and DAG."""
import ast,copy,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import discovery_native_claims as native
import discovery_minimax_contracts as mini
import discovery_claim_contract as contract
import catalog_diff as diff
from test_native_claim_consumption import doc,text
import test_native_claim_consumption as fixture
from test_discovery_request_contracts import spec,node
from discovery_request_contracts import request_models

class ContractBatch(unittest.TestCase):
 def parse(self,d):return request_models(d,'/generate','https://api.minimax.io')
 def union(self,kind,branches):
  d=spec();d['components']['schemas']['Request']={kind:branches};return d
 def test_exact_oneof_not_union_or_deduplication(self):
  a=copy.deepcopy(node(spec()));b=copy.deepcopy(a);b['properties']['model']['enum']=['literal-C']
  self.assertEqual(len(self.parse(self.union('anyOf',[a,a]))),2)
  self.assertEqual(len(self.parse(self.union('oneOf',[a,b]))),3)
  with self.assertRaises(ValueError):self.parse(self.union('oneOf',[a,a]))
  b['properties']['model']['enum']=['literal-A','literal-C']
  with self.assertRaises(ValueError):self.parse(self.union('oneOf',[a,b]))
 def test_required_constraint_intersection_unsatisfiable_not_certified(self):
  for bad in ({'type':'integer','minimum':'invalid'}, {'type':'integer','minimum':3,'maximum':2},{'type':'string','minLength':3,'maxLength':2},{'allOf':[{'type':'string'},{'type':'integer'}]}):
   d=spec();node(d)['required'].append('other');node(d)['properties']['other']=bad
   with self.assertRaises(ValueError):self.parse(d)
 def test_overlapping_ids_with_exclusive_required_fields_validated(self):
  a=copy.deepcopy(node(spec()));b=copy.deepcopy(a)
  for branch,key in ((a,'source_task_id'),(b,'base_video')):
   branch['required'].append(key);branch['properties'][key]={'type':'string'}
  self.assertEqual(len(self.parse(self.union('oneOf',[a,b]))),2)
 def test_ref_duplicate_and_ref_siblings_fail_closed(self):
  d=spec();d['paths']['/generate']['post']['requestBody']['content']['application/json']['schema']={'oneOf':[{'$ref':'#/components/schemas/Request'},{'$ref':'#/components/schemas/Request'}]}
  with self.assertRaises(ValueError):self.parse(d)
  node(d)['properties']['other']={'$ref':'https://external.invalid/request'}
  with self.assertRaises(ValueError):self.parse(d)
 def test_native_context_binds_channel_and_catalog_source(self):
  rows=native.xai_records(doc(fixture.XaiClaims.BODY,native.XAI));row=rows[0]
  for channel,url,expected in (('pay_as_you_go',native.XAI,'verified'),('subscription','https://docs.x.ai/developers/pricing','unknown'),('pay_as_you_go','https://docs.x.ai/developers/pricing','unknown')):
   snap=dict(vendor='xAI',channel=channel,source_url=url,observed_at=doc('')['observed_at'],records=[row],complete=False,coverage_evidence={'modalities':['text']})
   result=diff.compare_catalogs({'models':[]},[snap]);actual=result['observations'][0];self.assertEqual(actual['channel_applicability'],expected)
   if expected=='unknown':self.assertEqual(actual['rejected_native_claims'],row['native_claims'])
  with self.assertRaises(ValueError):native.xai_records(dict(doc(fixture.XaiClaims.BODY,native.XAI),channel='subscription'))
 def test_candidates_preserved_before_validation_and_primary_remains_independent(self):
  for bad in ('bad identity','bad+identity'):
   rows,proof=native.openai_detail(doc(text()+'\n- `'+bad+'`'),{})
   self.assertFalse(proof['id_enumeration_complete']);self.assertEqual(rows[0]['channel_applicability'],'verified')
   pending=next(x for x in rows if x['model_id'] is None);self.assertEqual(pending['raw_token'],bad);self.assertIn(bad,pending['identity_evidence']['quote']);self.assertTrue(pending['identity_evidence']['source_sha256']);self.assertFalse(rows[1]['output_modalities'])
   rows,proof=native.openai_detail(doc(text().replace('future.Native/9`','bad identity`')+'\n- `'+bad+'`'),{});self.assertFalse(proof['id_enumeration_complete']);self.assertTrue(any(x['model_id'] is None for x in rows))
 def test_formal_directory_shared_fences_and_multiple_subjects(self):
  base='# Model List\nthose that have been retired\n## Available Models\n### LLM\n| Live | link |\n## Retired Models\n| Old | LLM | Retired |'
  positive='\n| Live | LLM | Retired |\n| Other | Image | Retired |'
  for opening,closing in (('```','```'),('~~~','~~~'),('````','`````')):
   rows=mini.directory(base+'\n'+opening+'markdown\n| Live | LLM | Retired |\n'+closing+'\n'+positive)
   live=[x for x in rows if x['display_name']=='Live' and x['lifecycle_status']=='retired'];self.assertEqual(len(live),1);self.assertEqual(live[0]['line'],len((base+'\n'+opening+'markdown\n| Live | LLM | Retired |\n'+closing+'\n').splitlines())+2)
   self.assertTrue(any(x['display_name']=='Other' for x in rows))
 def test_claim_dependency_graph_no_import_cycle_even_in_functions(self):
  root=pathlib.Path(__file__).resolve().parents[1]/'scripts';graph={}
  for path in root.glob('*.py'):
   graph[path.stem]=set()
   for item in ast.walk(ast.parse(path.read_text())):
    if isinstance(item,ast.Import):graph[path.stem].update(a.name.split('.')[0] for a in item.names)
    elif isinstance(item,ast.ImportFrom) and item.module:graph[path.stem].add(item.module.split('.')[0])
  visiting=set();done=set()
  def visit(name):
   self.assertNotIn(name,visiting,'import cycle: '+name)
   if name in done:return
   visiting.add(name)
   for dependency in graph.get(name,set()):
    if dependency in graph:visit(dependency)
   visiting.remove(name);done.add(name)
  for name in ('catalog_diff','discovery_native_claims','discovery_claim_contract'):visit(name)
if __name__=='__main__':unittest.main()
