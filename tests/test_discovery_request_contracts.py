import copy,json,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import discovery_request_contracts as generic
import discovery_minimax_contracts as native
import discovery_bridges as bridges

def spec(ids=('literal-A','literal-B')):
 return {'openapi':'3.1.0','servers':[{'url':'https://api.minimax.io'}],'paths':{'/generate':{'post':{'requestBody':{'content':{'application/json':{'schema':{'$ref':'#/components/schemas/Request'}}}}}}},'components':{'schemas':{'Request':{'type':'object','required':['model'],'properties':{'model':{'type':'string','enum':list(ids)}}}}}}

def node(d):return d['components']['schemas']['Request']

class RequestContracts(unittest.TestCase):
 def read(self,d):return generic.request_models(d,'/generate','https://api.minimax.io')
 def test_native_literal_and_not_response_or_examples(self):
  d=spec();d['components']['schemas']['Response']={'properties':{'model':{'enum':['not-a-request']}}};node(d)['example']={'model':'also-not-a-request'}
  self.assertEqual({x['model_id'] for x in self.read(d)},{'literal-A','literal-B'})
 def test_effective_server_override_no_root_fallback(self):
  for override in ([],[{'url':'https://other.invalid'}]):
   d=spec();d['paths']['/generate']['post']['servers']=override
   with self.assertRaises(ValueError):self.read(d)
 def test_every_media_type_checked(self):
  d=spec();d['paths']['/generate']['post']['requestBody']['content']['multipart/form-data']={'schema':{'type':'object','properties':{}}}
  with self.assertRaises(ValueError):self.read(d)
 def test_every_union_branch_checked(self):
  d=spec();d['paths']['/generate']['post']['requestBody']['content']['application/json']['schema']={'oneOf':[{'$ref':'#/components/schemas/Request'},{'type':'object','properties':{}}]}
  with self.assertRaises(ValueError):self.read(d)
 def test_valid_union_all_claims(self):
  d=spec();d['components']['schemas']['Second']=copy.deepcopy(node(d));d['components']['schemas']['Second']['properties']['model']['enum']=['literal-C'];d['paths']['/generate']['post']['requestBody']['content']['application/json']['schema']={'anyOf':[{'$ref':'#/components/schemas/Request'},{'$ref':'#/components/schemas/Second'}]}
  self.assertEqual({x['model_id'] for x in self.read(d)},{'literal-A','literal-B','literal-C'})
 def test_optional_or_malformed_model_selector_fails_closed(self):
  for required in (None,[], 'model', ['model',7]):
   d=spec();node(d)['required']=required
   with self.assertRaises(ValueError):self.read(d)
 def test_model_not_string_closed_enum(self):
  for field in ({'type':'string'},{'type':'number','enum':[1]},{'type':'string','enum':[]},{'type':'string','enum':['x'],'anyOf':[{}]},{'type':'string','enum':[' x']}):
   d=spec();node(d)['properties']['model']=field
   with self.assertRaises(ValueError):self.read(d)
 def test_cyclic_external_and_semantic_ref(self):
  for ref in ({'$ref':'#/components/schemas/Request'},{'$ref':'https://other.invalid/schema'},{'$ref':'#/components/schemas/Request','not':{}}):
   d=spec();d['components']['schemas']['Request']=ref
   with self.assertRaises((ValueError,KeyError)):self.read(d)
 def test_nonobject_and_unsupported_composition(self):
  for kind in ({'type':'string','properties':{'model':{'type':'string','enum':['x']}}},{'allOf':[]}):
   d=spec();d['components']['schemas']['Request']=kind
   with self.assertRaises(ValueError):self.read(d)
 def test_projection_no_identity_cross_product_or_price_inference(self):
  root=dict(source_url=native.ROOT,vendor='MiniMax',channel='pay_as_you_go',role='catalog',observed_at='2026-11-18T08:00:00Z',fetch_status='ok')
  out=generic.scoped_snapshot(root,'image',[{'model_id':'A','source_url':'first'},{'model_id':'A','source_url':'second'},{'model_id':'B','source_url':'third'}],verified=True)
  self.assertEqual(len(out['records']),2);self.assertEqual(len(out['records'][0]['identity_evidence']),2)
  self.assertTrue(out['complete']);self.assertNotIn('alias_of',out['records'][0]);self.assertNotIn('price_public',out['records'][0])
 def test_pending_never_complete(self):
  root=dict(source_url=native.ROOT);out=generic.scoped_snapshot(root,'text',[{'model_id':'A'}],[{'display_name':'unproven'}],verified=True)
  self.assertFalse(out['complete']);self.assertEqual(len(out['records']),2)

class IndexAndDataflow(unittest.TestCase):
 def index(self):return '\n'.join('- [schema]('+native.BASE+p+')' for p in set(native.SPECS)|native.SUPPORT)
 def test_index_all_generation_schema_units(self):self.assertEqual(len(native.indexed_specs(self.index())),10)
 def test_index_new_or_missing_unit_refuses_closure(self):
  for text in (self.index().replace('text-to-image.json','gone.json'),self.index()+'\n[x]('+native.BASE+'image/generation/api/new.json)'):
   with self.assertRaises(ValueError):native.indexed_specs(text)
 def test_assignment_use_in_function_without_executing_example(self):
  text='```python\nMODEL = "MiniMax-H3"\nraise RuntimeError("MUST NOT EXECUTE")\ndef sample():\n return {"model": MODEL}\n```'
  self.assertIn('MiniMax-H3',bridges.minimax_ids(text))
 def test_reassignment_shadow_delete_and_external_values_unknown(self):
  for body in ('MODEL=os.environ["X"]\nreturn_value={"model":MODEL}', 'MODEL="A"\nMODEL=some_call()\np={"model":MODEL}', 'MODEL="A"\ndef f(MODEL):\n return {"model":MODEL}', 'MODEL="A"\ndel MODEL\np={"model":MODEL}', 'MODEL="A"\nimport other as MODEL\np={"model":MODEL}'):
   self.assertEqual(bridges.minimax_ids('```python\n'+body+'\n```'),[])
 def test_directory_requires_full_available_retired_boundary(self):
  with self.assertRaises(ValueError):native.directory('# Model List\n### Image Models\n| display |')

if __name__=='__main__':unittest.main()
