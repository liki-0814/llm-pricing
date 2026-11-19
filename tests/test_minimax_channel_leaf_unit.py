"""Small-input channel predicate units; no data/capture/build fixture."""
import copy,sys,unittest,socket
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import discovery_minimax_contracts as native
from discovery_scope_projection import minimax_native_channel_eligible as eligible, minimax_output_statement as output

class MiniMaxChannelLeafUnits(unittest.TestCase):
    def setUp(self):
        self.guard=ExitStack();self.addCleanup(self.guard.close)
        self.guard.enter_context(patch('builtins.open',side_effect=AssertionError('unit file IO forbidden')))
        self.guard.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('unit network forbidden')))
        self.snapshot=dict(vendor='MiniMax',channel='pay_as_you_go',source_url=native.ROOT,coverage_evidence={'modalities':['image']})
        self.entry=dict(source_url=native.BASE+'image/generation/api/text-to-image.json',server='https://api.minimax.io',route='/v1/image_generation')
        self.spec={'servers':[{'url':'https://api.minimax.io'}],'paths':{'/v1/image_generation':{'post':{'requestBody':{'content':{'application/json':{'schema':{'type':'object','required':['model'],'properties':{'model':{'type':'string','enum':['literal-model']}}}}}}}}}}
    def test_existing_native_request_proves_only_its_literal_id(self):
        self.assertTrue(eligible(self.snapshot,self.entry,self.spec,'literal-model'))
        for mid in ('Literal-model','literal-model-new','other-model'):self.assertFalse(eligible(self.snapshot,self.entry,self.spec,mid))
    def test_channel_vendor_source_and_modality_are_not_borrowed(self):
        for changes in ({'vendor':'Other'},{'channel':'subscription'},{'source_url':native.ROOT+'?other'},{'coverage_evidence':{'modalities':['video']}}):
            self.assertFalse(eligible(dict(self.snapshot,**changes),self.entry,self.spec,'literal-model'))
    def test_server_route_and_document_must_be_the_existing_approved_contract(self):
        for changes in ({'server':'https://proxy.example'},{'route':'/v1/not-generation'},{'source_url':native.BASE+'other.json'}):
            self.assertFalse(eligible(self.snapshot,dict(self.entry,**changes),self.spec,'literal-model'))
        bad=copy.deepcopy(self.spec);bad['servers'][0]['url']='https://proxy.example';self.assertFalse(eligible(self.snapshot,self.entry,bad,'literal-model'))
    def test_optional_selector_or_unsatisfiable_model_is_not_channel_proof(self):
        for change in ('optional','impossible'):
            bad=copy.deepcopy(self.spec);schema=bad['paths']['/v1/image_generation']['post']['requestBody']['content']['application/json']['schema']
            if change=='optional':schema['required']=[]
            else:schema.update(additionalProperties=False,required=['model','missing'])
            self.assertFalse(eligible(self.snapshot,self.entry,bad,'literal-model'))

    def test_output_requires_its_bound_operation_statement_not_input_or_route_name(self):
        self.assertIsNone(output(self.snapshot,self.entry,self.spec,'literal-model'))
        self.spec['paths']['/v1/image_generation']['post']['summary']='Image Generation'
        self.assertEqual(output(self.snapshot,self.entry,self.spec,'literal-model'),'Image Generation')
        for summary in ('Video Generation','Image input upload','Something else'):
            self.spec['paths']['/v1/image_generation']['post']['summary']=summary
            self.assertIsNone(output(self.snapshot,self.entry,self.spec,'literal-model'))

if __name__=='__main__':unittest.main()
