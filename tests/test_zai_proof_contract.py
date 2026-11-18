"""Synthetic in-memory mutations only: no HTTP and no assertion the public schema is broken."""
import copy,json,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from discovery_bridges import zai_request_models
NATIVE='https://api.z.ai/api'
FOREIGN='https://outside.invalid/api'
CHAT='/paas/v4/chat/completions'
IMAGE='/paas/v4/images/generations'
ASYNC_IMAGE='/paas/v4/async/images/generations'
ROUTES=(CHAT,IMAGE,ASYNC_IMAGE)
def leaf(ids):return {'properties':{'model':{'type':'string','enum':ids}}}
def fixture():
 spec={'servers':[{'url':NATIVE}],'components':{'schemas':{'Text':leaf(['future.Native/9']),'Vision':leaf(['future.Vision/9']),'Image':leaf(['future.Image/9'])}},'paths':{}}
 for route,ref in [(CHAT,None),(IMAGE,'Image'),(ASYNC_IMAGE,'Image')]:
  schema={'oneOf':[{'$ref':'#/components/schemas/Text'},{'$ref':'#/components/schemas/Vision'}]} if ref is None else {'$ref':'#/components/schemas/'+ref}
  spec['paths'][route]={'post':{'requestBody':{'content':{'application/json':{'schema':schema}}}}}
 return spec
def request(spec,route=CHAT):return spec['paths'][route]['post']['requestBody']['content']['application/json']
def proof(spec):return zai_request_models(json.dumps(spec))[1]
class ZaiProofContractTests(unittest.TestCase):
 def test_atlas_operation_and_path_server_mutations_fail_closed(self):
  for level in ('operation','path'):
   with self.subTest(level=level):
    spec=fixture();node=spec['paths'][CHAT]['post'] if level=='operation' else spec['paths'][CHAT];node['servers']=[{'url':FOREIGN}]
    self.assertFalse(proof(spec)['verified'])
 def test_effective_server_precedence_operation_then_path_then_root(self):
  spec=fixture();spec['paths'][CHAT]['servers']=[{'url':FOREIGN}];spec['paths'][CHAT]['post']['servers']=[{'url':NATIVE}]
  self.assertTrue(proof(spec)['verified'])
  spec=fixture();spec['servers']=[{'url':FOREIGN}]
  for route in ROUTES:spec['paths'][route]['servers']=[{'url':NATIVE}]
  self.assertTrue(proof(spec)['verified'])
  spec=fixture();spec.pop('servers')
  for route in ROUTES:spec['paths'][route]['post']['servers']=[{'url':NATIVE}]
  self.assertTrue(proof(spec)['verified'])
 def test_effective_servers_must_be_nonempty_valid_and_all_native(self):
  for value in ([],None,{},['bad'],[{}],[{'url':NATIVE},{'url':FOREIGN}],[{'url':'https://api.z.ai.evil.invalid/api'}],[{'url':NATIVE+'?forward=outside'}]):
   with self.subTest(value=value):
    spec=fixture();spec['paths'][CHAT]['post']['servers']=value;self.assertFalse(proof(spec)['verified'])
  spec=fixture();spec['servers']=[{'url':FOREIGN}];self.assertFalse(proof(spec)['verified'])
 def test_atlas_empty_text_oneof_cannot_be_filled_by_image_routes(self):
  spec=fixture();request(spec)['schema']={'oneOf':[]};self.assertFalse(proof(spec)['verified'])
 def test_every_composition_branch_is_nonempty_and_valid(self):
  invalid=[{'oneOf':[]},{'anyOf':[]},{'oneOf':{}},{'oneOf':'bad'},{'oneOf':[{}]},{'oneOf':[True]},{'oneOf':[{'anyOf':[]},leaf(['future.Native/9'])]},{'oneOf':[leaf(['future.Native/9'])],'anyOf':[]}]
  for node in invalid:
   with self.subTest(node=node):
    spec=fixture();request(spec)['schema']=node;self.assertFalse(proof(spec)['verified'])
 def test_each_required_route_and_modality_has_legal_nonempty_enum(self):
  for route in ROUTES:
   for ids in ([],[''],[None],[7],['Display Name']):
    with self.subTest(route=route,ids=ids):
     spec=fixture();request(spec,route)['schema']=leaf(ids);self.assertFalse(proof(spec)['verified'])
  spec=fixture();request(spec,IMAGE)['schema']=leaf(['future.Image/9']);request(spec,ASYNC_IMAGE)['schema']={'anyOf':[]};self.assertFalse(proof(spec)['verified'])
 def test_valid_local_refs_nonempty_compositions_future_ids_and_modality_counts(self):
  spec=fixture();spec['components']['schemas']['Vision']={'anyOf':[leaf(['future.New.Family/9']),leaf(['future.Second/9'])]}
  rows,result=zai_request_models(json.dumps(spec));self.assertTrue(result['verified']);self.assertEqual(result['modality_record_counts'],{'text':3,'image':1});self.assertIn('future.New.Family/9',[x['model_id'] for x in rows]);self.assertTrue(all(x['effective_servers']==[NATIVE] for x in result['requests']))
 def test_missing_external_cyclic_ref_missing_route_and_wrong_enum_type_reject(self):
  for ref in ('#/components/schemas/Missing','https://outside.invalid/schema.json','#/components/schemas/Loop'):
   spec=fixture();spec['components']['schemas']['Loop']={'$ref':'#/components/schemas/Loop'};request(spec)['schema']={'$ref':ref};self.assertFalse(proof(spec)['verified'])
  spec=fixture();del spec['paths'][CHAT];self.assertFalse(proof(spec)['verified'])
  spec=fixture();request(spec)['schema']=leaf(['future.Native/9']);request(spec)['schema']['properties']['model']['type']='integer';self.assertFalse(proof(spec)['verified'])

 def test_model_field_semantic_composition_is_not_silently_ignored(self):
  for extra in ({'oneOf':[]},{'anyOf':[]},{'not':{}}):
   spec=fixture();request(spec)['schema']=leaf(['future.Native/9']);request(spec)['schema']['properties']['model'].update(extra);self.assertFalse(proof(spec)['verified'])
 def test_model_field_local_enum_ref_can_be_closed_and_valid(self):
  spec=fixture();spec['components']['schemas']['ModelNames']={'type':'string','enum':['future.Ref/9']};request(spec)['schema']={'properties':{'model':{'$ref':'#/components/schemas/ModelNames'}}};self.assertTrue(proof(spec)['verified'])
