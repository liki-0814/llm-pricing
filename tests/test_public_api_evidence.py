"""Literal-input units and separate temporary-capture components; no build fixture."""
import copy,hashlib,json,socket,sys,tempfile,unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import discovery_public_api_evidence as a
from discovery_claim_contract import claim
from discovery_universe_contracts import scope_certificate,unknown

class APIModelColumnLeafUnits(unittest.TestCase):
    def setUp(self):
        self.guard=ExitStack();self.addCleanup(self.guard.close)
        self.guard.enter_context(patch('builtins.open',side_effect=AssertionError('unit file IO forbidden')))
        self.guard.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('unit network forbidden')))
    def meta(self,vendor='OpenAI',url=a.OPENAI):return dict(vendor=vendor,channel='pay_as_you_go',source_url=url)
    def test_literal_id_not_prefix_case_alias_or_unclosed_markup(self):
        for cell,mid in [('probe-ID','probe-ID'),('`probe-ID`','probe-ID'),('probe-ID (short context)','probe-ID'),('`probe-ID` (long context)','probe-ID')]:self.assertEqual(a.model_column_id(cell),mid)
        for cell in ('probe model','probe-ID unknown','`probe-ID','probe-ID`','probe-ID (alias)','[probe-ID](/elsewhere)'):self.assertIsNone(a.model_column_id(cell))
    def test_named_model_column_not_category_or_first_cell(self):
        text='| Category | Model | Input |\n|---|---|---|\n| never-an-ID | probe-ID (short context) | $5 |\n'
        rows=a.model_column_observations(self.meta(),text);self.assertEqual([r['model_id'] for r in rows],['probe-ID']);self.assertEqual(rows[0]['model_column'],1)
        self.assertEqual(a.model_column_observations(self.meta(),text.replace('Model','Product')),[])
        self.assertEqual(a.model_column_observations(self.meta(),text.replace('Category','Model')),[])
    def test_document_examples_are_not_API_listing(self):
        text='```markdown\n| Model | Price |\n|---|---|\n| fake-id | $1 |\n```\n'
        self.assertEqual(a.model_column_observations(self.meta(),text),[])
    def test_qwen_requires_explicit_id_header_and_billing_witness(self):
        table='<table><tr><th>模型 ID（Model ID）</th><th>价格</th></tr><tr><td>qwen-probe</td><td>0.2元</td></tr></table>'
        meta=self.meta('阿里云 Qwen',a.QWEN)
        self.assertEqual(a.model_column_observations(meta,table),[])
        rows=a.model_column_observations(meta,a.BILLING+table);self.assertEqual(rows[0]['model_id'],'qwen-probe');self.assertEqual(rows[0]['billing_quote'],a.BILLING)
        self.assertEqual(a.model_column_observations(meta,a.BILLING+table.replace('模型 ID（Model ID）','Model Name')),[])
    def test_wrong_vendor_channel_or_source_cannot_produce_IDs(self):
        text='| Model | Price |\n|---|---|\n| probe | $1 |\n'
        for changes in ({'vendor':'Other'},{'channel':'subscription'},{'source_url':a.OPENAI+'?copy'}):self.assertEqual(a.model_column_observations(dict(self.meta(),**changes),text),[])

    def test_anthropic_transposed_API_ID_stays_with_its_pricing_table(self):
        text='| Feature | Name |\n|---|---|\n| [Pricing](https://platform.claude.com/docs/en/about-claude/pricing) | $2 |\n| Claude API ID | `claude-probe` |\n'
        meta=self.meta('Anthropic',a.ANTHROPIC)
        self.assertEqual([r['model_id'] for r in a.model_column_observations(meta,text)],['claude-probe'])
        self.assertEqual(a.model_column_observations(meta,text.replace('Claude API ID','Bedrock ID')),[])
        self.assertEqual(a.model_column_observations(meta,text.replace('[Pricing]','[Other]')),[])
    def test_google_literal_API_link_needs_its_billing_statement(self):
        text='# Gemini Developer API pricing\npay-as-you-go pricing for your production-ready applications.\n*[`gemini-probe`](/docs/models/gemini-probe)*\n'
        meta=self.meta('Google Gemini',a.GOOGLE)
        self.assertEqual([r['model_id'] for r in a.model_column_observations(meta,text)],['gemini-probe'])
        self.assertEqual(a.model_column_observations(meta,text.replace('pay-as-you-go','subscription')),[])
        self.assertEqual(a.model_column_observations(meta,text.replace('/docs/models/','https://other.example/')),[])

    def test_unclassified_google_output_artifact_remains_qualified_unknown(self):
        from discovery_scope_projection import qualified_producer_claims
        from discovery_claim_contract import valid_claim,project
        doc=dict(vendor='Google Gemini',channel='pay_as_you_go',source_url='https://aistudio.google.com/docs/models/probe',catalog_source_url='https://aistudio.google.com/docs/models',source_sha256='a'*64,capture_path='/literal-unit-source',observed_at='2026-11-19T06:31:26+08:00')
        snap=dict(vendor='Google Gemini',channel='pay_as_you_go',source_url=doc['catalog_source_url'])
        entry=dict(identity_quote='probe-ID',output_quote='Output Text, Word annotations',output=['text','word_annotations'])
        row=dict(model_id='probe-ID',api_id_explicit=True,identity_evidence={'declarations':[entry]})
        with patch('discovery_scope_projection.source',return_value=doc):claims=qualified_producer_claims(snap,row,{})
        self.assertTrue(all(valid_claim(c) for c in claims));out=next(c for c in claims if c['kind']=='output')
        self.assertIsNone(out['values']);self.assertEqual(out['unclassified_output_values'],entry['output']);self.assertEqual(project(claims)['output_modalities'],[])

class APIModelCaptureComponents(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.network=patch.object(socket.socket,'connect',side_effect=AssertionError('component network forbidden'));self.network.start();self.addCleanup(self.network.stop)
    def evidence(self,vendor='OpenAI',mid='probe-ID'):
        url=a.OPENAI if vendor=='OpenAI' else a.QWEN
        body=('| Category | Model | Input |\n|---|---|---|\n| Life Sciences / Trusted Access | '+mid+' (short context) | $5 |\n') if vendor=='OpenAI' else a.BILLING+'<table><tr><th>模型 ID（Model ID）</th><th>输入单价</th></tr><tr><td>'+mid+'</td><td>1元/百万Token</td></tr></table>'
        raw=body.encode();(self.root/'body').write_bytes(raw)
        meta=dict(vendor=vendor,channel='pay_as_you_go',source_url=url,source_sha256=hashlib.sha256(raw).hexdigest(),http_status=200,observed_at='2026-11-19T06:31:26+08:00',body_path='body')
        return dict(sources=[meta],facts=[],model_prices=[])
    def snapshot(self,vendor='OpenAI',mid='probe-ID',extra_unknown=False):
        cat=next(iter(a.CATALOGS[vendor]));doc=dict(vendor=vendor,channel='pay_as_you_go',source_url=cat,catalog_source_url=cat,source_sha256='a'*64,capture_path=str(self.root/'catalog'),observed_at='2026-11-18T20:00:00+08:00')
        claims=[claim(doc,mid,'identity',role='inline_directory_literal',quote=mid),claim(doc,mid,'native_channel',status='unknown',reason=a.INLINE_ABSENCE),claim(doc,mid,'output',values=None,reason='not declared')] if vendor=='OpenAI' else []
        if extra_unknown:claims.append(claim(doc,mid,'native_channel',status='unknown',reason='separate unresolved applicability declaration'))
        row=dict(model_id=mid if vendor=='OpenAI' else None,observed_model_id=mid,api_id_explicit=vendor=='OpenAI',native_claims=claims,native_vendor_status='unknown',provider='not inferred',output_modalities=['text'],request_parameter_ID_explicit=False,price_status='unchanged')
        snap=dict(vendor=vendor,channel='pay_as_you_go',source_url=cat,role='catalog',records=[row]);snap['scope_certificates']=[scope_certificate(vendor,'pay_as_you_go','text',snap['records'],**{k:unknown('original '+k+' unknown') for k in ('population','pagination','alias_enumeration','lifecycle')})];return snap
    def test_inline_absence_superseded_with_provenance_not_currency_or_output(self):
        ledger=self.evidence();before=copy.deepcopy(ledger);snap=self.snapshot();old=copy.deepcopy(snap['scope_certificates'][0]);self.assertEqual(a.attach_api_evidence([snap],ledger,self.root),1)
        row=snap['records'][0];self.assertEqual(row['channel_applicability'],'verified');self.assertEqual(row['superseded_absence_claims'][0]['reason'],a.INLINE_ABSENCE);self.assertEqual(row['output_modalities'],['text']);self.assertEqual(ledger,before)
        cert=snap['scope_certificates'][0];self.assertFalse(cert['complete']);self.assertEqual(cert['obligations']['output'],old['obligations']['output'])
        for k in ('population','pagination','alias_enumeration','lifecycle'):self.assertEqual(cert['obligations'][k]['state'],'unknown')
        self.assertEqual(a.attach_api_evidence([snap],ledger,self.root),0)
    def test_other_unknown_is_sticky_not_discarded_by_positive_channel(self):
        ledger=self.evidence();snap=self.snapshot(extra_unknown=True);a.attach_api_evidence([snap],ledger,self.root);self.assertEqual(snap['records'][0]['channel_applicability'],'unknown');self.assertIn('separate unresolved',snap['records'][0]['channel_unknown_reasons'][0])
    def test_unknown_with_its_own_statement_is_not_an_absence_placeholder(self):
        ledger=self.evidence();snap=self.snapshot();snap['records'][0]['native_claims'][1]['quote']='unresolved applicability statement'
        a.attach_api_evidence([snap],ledger,self.root)
        self.assertEqual(snap['records'][0]['channel_applicability'],'unknown')
        self.assertNotIn('superseded_absence_claims',snap['records'][0])

    def test_qwen_explicit_API_ID_is_not_authorship_output_or_request_parameter_proof(self):
        ledger=self.evidence('阿里云 Qwen','qwen-probe');snap=self.snapshot('阿里云 Qwen','qwen-probe');a.attach_api_evidence([snap],ledger,self.root);row=snap['records'][0]
        self.assertEqual(row['model_id'],'qwen-probe');self.assertTrue(row['api_id_explicit']);self.assertEqual(row['native_vendor_status'],'unknown');self.assertEqual(row['provider'],'not inferred');self.assertFalse(row['request_parameter_ID_explicit']);self.assertEqual(row['output_modalities'],['text']);self.assertFalse(snap['scope_certificates'][0]['complete'])
    def test_exact_ID_context_and_existing_inline_role_required(self):
        ledger=self.evidence()
        for mutate in (lambda s:s['records'][0].update(model_id='probe-id'),lambda s:s.update(channel='subscription'),lambda s:s.update(source_url='https://example.org/catalog'),lambda s:s['records'][0].update(native_claims=[])):
            snap=self.snapshot();mutate(snap);before=copy.deepcopy(snap);self.assertEqual(a.attach_api_evidence([snap],ledger,self.root),0);self.assertEqual(snap,before)
    def test_raw_source_hash_status_context_and_boundary_are_validated(self):
        for changes in ({'source_sha256':'0'*64},{'http_status':403},{'vendor':'Other'},{'channel':'subscription'},{'body_path':'../escaped'}):
            ledger=self.evidence();ledger['sources'][0].update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):a.attach_api_evidence([self.snapshot()],ledger,self.root)
        ledger=self.evidence();(self.root/'body').write_text('tampered')
        with self.assertRaises(ValueError):a.attach_api_evidence([self.snapshot()],ledger,self.root)

if __name__=='__main__':unittest.main()
