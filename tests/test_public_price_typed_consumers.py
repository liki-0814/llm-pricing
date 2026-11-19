"""R2/R3 complete materialization-path controls using archived official originals."""
import copy
import dataclasses
import json
import re
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import public_price_facts as p
import public_price_models as models
import build_api
from public_price_context import prove_unit,consume_unit,UnitEvidence

class TypedConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger=p.load();cls.data=build_api.load()
        cls.meta={m['vendor']:m for m in cls.ledger['sources'] if m['source_url'] not in p.CATALOG_URLS}
        cls.bodies={m['source_url']:(p.ROOT/m['body_path']).read_bytes().decode() for m in cls.ledger['sources']}

    def variant(self,vendor,text):
        m=dict(self.meta[vendor],source_sha256=p.digest(text.encode()))
        return p.assemble([m],lambda _:text.encode(),'controlled_R2_R3_NOT_HTTP_NOT_fresh')

    def assert_no_models(self,l):
        self.assertTrue(l['pending']);self.assertEqual(l['model_prices'],[])
        for mixed in (False,True):
            a=build_api.build(self.data,mixed=mixed,public_price_ledger=l)
            self.assertFalse(any(k.startswith('price-models/') for k in a))
            self.assertEqual(a['price-facts.json']['data']['model_prices'],[])
        page=build_api.page_data(self.data,public_price_ledger=l)
        self.assertEqual(page['public_price_evidence']['model_price_record_count'],0)
        snaps=[dict(vendor='Google Gemini',channel='pay_as_you_go',complete=False,records=[dict(model_id='probe-model')])]
        p.attach(snaps,l);self.assertEqual(snaps[0]['records'][0]['public_model_price_statements'],[]);self.assertFalse(snaps[0]['complete'])

    def test_google_scalar_strong_cell_column_and_unknown_keep_candidates(self):
        base='## Probe Model\n\n*[`probe-model`](/docs/models/probe-model)*\n\n{% tab title="Batch" %}\n{% table %}\n* Feature\n* Free Tier\n* Paid Tier, per 1M tokens in USD\n\n---\n\n* Input price\n* Not available\n* $2.00\n{% /table %}\n{% /tab %}\n'
        self.assertEqual(len(self.variant('Google Gemini',base)['model_prices']),1)
        for changed in [base.replace('$2.00\n','$2.00 / image\n'),base.replace('1M tokens in USD','1M tokens / per image in USD')]:
            with self.subTest(changed=changed):self.assert_no_models(self.variant('Google Gemini',changed))

    def test_google_actual_64_date_pair_unit_validation_before_expansion(self):
        text=self.bodies[self.meta['Google Gemini']['source_url']]
        dates=lambda l:[r for r in l['model_prices'] if r['vendor']=='Google Gemini' and r['conditions'].get('date_condition')]
        self.assertEqual(len(dates(self.ledger)),64)
        changed=text.replace('Paid Tier, per 1M tokens in USD','Paid Tier, per 1M tokens / per image in USD')
        self.assertEqual(text.count('Paid Tier, per 1M tokens in USD'),95)
        l=self.variant('Google Gemini',changed);self.assertEqual(dates(l),[]);self.assertEqual(l['model_prices'],[]);self.assertTrue(l['pending'])
        a=build_api.build(self.data,mixed=True,public_price_ledger=l)
        self.assertFalse(any(k.startswith('price-models/') for k in a))
        self.assertEqual(build_api.page_data(self.data,public_price_ledger=l)['public_price_evidence']['model_price_record_count'],0)

    def test_typed_evidence_replayed_at_emit_fact_and_direct_copy(self):
        text='| Model | Input / 1M tokens |\n|---|---|\n| probe-model | $2.00 |\n| other-model | $3.00 |\n'
        row='| probe-model | $2.00 |\n';m=dict(self.meta['xAI'],source_sha256=p.digest(text.encode()))
        evidence=prove_unit(m,text,cell='$2.00',columns=('Input / 1M tokens',),scope=text,row=row)
        self.assertIsInstance(evidence,UnitEvidence)
        self.assertEqual(evidence.to_dict(),json.loads(json.dumps(evidence.to_dict())))
        for bad in ('per_1M_tokens',{'unit':'per_1M_tokens'},dataclasses.replace(evidence,unit='per_image')):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                models.emit([],dict(meta=m,text=text),'probe-model',2,'USD',bad,'input','text',row,['Input / 1M tokens'],{})
        with self.assertRaises(ValueError):consume_unit(evidence,m,text,'| other-model | $3.00 |\n')
        inherited='<table><tr><th>Model</th><th>Input / 1M tokens</th></tr><tr><td>a</td><td rowspan="2">$2.00</td></tr><tr><td>other</td></tr><tr><td>expired</td><td>$3.00</td></tr></table>'
        im=dict(m,source_sha256=p.digest(inherited.encode()))
        self.assertIsNotNone(prove_unit(im,inherited,cell='<td rowspan="2">$2.00</td>',columns=('Input / 1M tokens',),scope=inherited,row='<tr><td>other</td></tr>'))
        with self.assertRaises(ValueError):prove_unit(im,inherited,cell='<td rowspan="2">$2.00</td>',columns=('Input / 1M tokens',),scope=inherited,row='<tr><td>expired</td><td>$3.00</td></tr>')
        other='| other-model | $3.00 |\n';at=text.index(other)
        with self.assertRaises(ValueError):consume_unit(dataclasses.replace(evidence,row_span=(at,at+len(other))),m,text,other)
        for key,val in [('channel','subscription'),('vendor','OpenAI'),('source_sha256','0'*64)]:
            with self.subTest(key=key),self.assertRaises(ValueError):consume_unit(evidence,dict(m,**{key:val}),text,row)
        with self.assertRaises(ValueError):prove_unit(m,text,cell='$2.00',columns=('Input',),scope=text,row=row,default='Input / 1M tokens')
        f=copy.deepcopy(self.ledger['facts'][0]);doc=next(dict(meta=m,text=self.bodies[m['source_url']]) for m in self.ledger['sources'] if m['source_url']==f['source_url'])
        f['unit']='per_minute'
        with self.assertRaises(ValueError):models.normalize([doc],p.Tables,p.expanded,[f],[])
        with self.assertRaises(ValueError):p.fact(m,text,model_id='probe-model',offering_name=None,channel='pay_as_you_go',region='test',modality='text',component='input',amount=2,currency='USD',unit='per_1M_tokens',tier='test',quote=row,context=['Input / 1M tokens'])

    def test_all_original_exits_have_source_row_bound_proof_and_economic_controls(self):
        self.assertEqual((len(self.ledger['facts']),len(self.ledger['model_prices'])),(1337,2303))
        for r in self.ledger['facts']+self.ledger['model_prices']:
            with self.subTest(vendor=r['vendor'],id=r['model_id'],unit=r['unit']):
                e=r['unit_evidence'];self.assertEqual(e['unit'],r['unit']);self.assertEqual(e['source_sha256'],r['source_sha256']);self.assertEqual(e['channel'],r['channel'])
                self.assertEqual(self.bodies[r['source_url']][e['row_span'][0]:e['row_span'][1]],r['quote'])
        self.assertEqual(sum(r['unit']=='per_1M_tokens' for r in self.ledger['facts']),991)
        self.assertEqual(sum(r['vendor']=='OpenAI' and r['currency'] is None for r in self.ledger['model_prices']),625)
        self.assertTrue(any(r['unit']=='per_minute' for r in self.ledger['model_prices']))
        self.assertTrue(any(r['unit']=='per_video' and r['conditions']['dimensions'].get('duration_seconds')==6 for r in self.ledger['model_prices']))
        fast=[r for r in self.ledger['pending'] if r.get('offering_channel_observation')]
        self.assertEqual(len(fast),6);self.assertTrue(all(r['unit']=='per_1M_tokens' and r['unit_evidence'] and not r['price_verified'] for r in fast))

    def test_structural_header_ownership_cannot_be_selected_or_forged(self):
        text='| Model | Input / 1M tokens | Notes |\n|---|---|---|\n| probe-model | $2.00 / image | unrelated |\n'
        row='| probe-model | $2.00 / image | unrelated |\n';m=dict(self.meta['xAI'],source_sha256=p.digest(text.encode()))
        for columns in (None,('Notes',),('Input',),('Input / 1M tokens',)):
            self.assertIsNone(prove_unit(m,text,cell='$2.00 / image',columns=columns,scope=text,row=row))
        with self.assertRaises(ValueError):prove_unit(m,text,cell='$2.00 / image',cell_index=2,scope=text,row=row)
        with self.assertRaises(ValueError):prove_unit(m,text,cell='$2.00',scope=text,row=row)
        good=text.replace('$2.00 / image','$2.00');grow=row.replace('$2.00 / image','$2.00');gm=dict(m,source_sha256=p.digest(good.encode()))
        proof=prove_unit(gm,good,cell='$2.00',cell_index=1,scope=good,row=grow)
        at=good.index('Notes')
        with self.assertRaises(ValueError):consume_unit(dataclasses.replace(proof,column_spans=((at,at+5),)),gm,good,grow)
        # Full multirow/colspan header ownership is derived from the expanded grid.
        html='<table><tr><th rowspan="2">Model</th><th colspan="2">per 1M tokens</th></tr><tr><th>Input</th><th>Output</th></tr><tr><td>probe-model</td><td>$2.00 / image</td><td>$3.00</td></tr></table>'
        hm=dict(m,source_sha256=p.digest(html.encode()));hr='<tr><td>probe-model</td><td>$2.00 / image</td><td>$3.00</td></tr>'
        self.assertIsNone(prove_unit(hm,html,cell='<td>$2.00 / image</td>',cell_index=1,scope=html,row=hr))
        self.assertEqual(prove_unit(hm,html,cell='<td>$3.00</td>',cell_index=2,scope=html,row=hr).unit,'per_1M_tokens')
        td='<table><tr><td>Model</td><td colspan="2">Prices</td></tr><tr><td></td><td>Input per 1M tokens</td><td>Output per 1M tokens</td></tr>'+hr+'</table>'
        tm=dict(m,source_sha256=p.digest(td.encode()))
        self.assertIsNone(prove_unit(tm,td,cell='<td>$2.00 / image</td>',cell_index=1,scope=td,row=hr))

    def test_real_consumer_entrypoints_reject_forged_typed_derivations(self):
        docs=[dict(meta=m,text=self.bodies[m['source_url']]) for m in self.ledger['sources']]
        def poison(*args,**kwargs):
            proof=prove_unit(*args,**kwargs)
            return dataclasses.replace(proof,unit='per_minute' if proof.unit!='per_minute' else 'per_image') if proof else None
        for vendor,consumer in [('Anthropic',lambda out,doc:models.anthropic(out,doc,docs)),('Google Gemini',lambda out,doc:models.google(out,doc,docs)),('OpenAI',models.markdown_prices),('xAI',models.markdown_prices),('MiniMax',lambda out,doc:models.minimax(out,doc,p.Tables,p.expanded))]:
            doc=next(d for d in docs if d['meta']==self.meta[vendor]);out=[]
            with self.subTest(vendor=vendor),patch.object(models,'prove_unit',side_effect=poison),self.assertRaises(ValueError):consumer(out,doc)
            self.assertEqual(out,[])
        for vendor in ('阿里云 Qwen','xAI'):
            m=self.meta[vendor];text=self.bodies[m['source_url']]
            with self.subTest(fact_or_fast=vendor),patch.object(p,'prove_unit',side_effect=poison),self.assertRaises(ValueError):p.parse(m,text.encode())
        candidate=copy.deepcopy(next(c for c in self.ledger['pending'] if c.get('unbound_billing_components')))
        candidate['unbound_billing_components'][0]['unit_evidence']['unit']='per_minute'
        with self.assertRaises(ValueError):models.normalize(docs,p.Tables,p.expanded,[],[candidate])

    def test_fast_subject_punctuation_coordination_and_ambiguous_pronouns(self):
        original=self.bodies[self.meta['xAI']['source_url']]
        missing=re.sub(r", and Grok Build[^<>]{0,40}free tier does not include it\.",'.',original)
        needle='It is not available on the public xAI API.'
        other="Other Plan is a separate offering, and Grok Build's free tier does not include it."
        for separator in ('. ','; ',': ',' — ', ', and ', ' and ', ' while '):
            changed=missing.replace(needle,'It is not available on the public xAI API'+separator+other)
            l=self.variant('xAI',changed);o=l['offering_channel_observations'][0]
            with self.subTest(separator=separator):
                self.assertIsNone(o['free_build_tier_included']);self.assertTrue(o['channel_verified']);self.assertFalse(o['public_xai_API'])
                self.assertEqual(o['claim_evidence']['available_in']['state'],'verified')
                for mixed in (False,True):
                    a=build_api.build(self.data,mixed=mixed,public_price_ledger=l)['price-facts.json']['data']['offering_channel_observations'][0]
                    self.assertIsNone(a['free_build_tier_included'])
                snaps=[dict(vendor='xAI',channel='subscription',records=[])];p.attach(snaps,l);self.assertIsNone(snaps[0]['public_offering_channel_observations'][0]['free_build_tier_included'])
                self.assertIsNotNone(build_api.page_data(self.data,public_price_ledger=l)['public_price_evidence'])
        ambiguous=missing.replace(needle,"It and Other Plan are separate offerings, and Grok Build's free tier does not include it.")
        self.assertIsNone(self.variant('xAI',ambiguous)['offering_channel_observations'][0]['free_build_tier_included'])
        trailing=original.replace('free tier does not include it.', 'free tier does not include it; Other Plan is a separate offering.')
        self.assertFalse(self.variant('xAI',trailing)['offering_channel_observations'][0]['free_build_tier_included'])
        own=original.replace(', and Grok Build', '; Grok Build')
        self.assertFalse(self.variant('xAI',own)['offering_channel_observations'][0]['free_build_tier_included'])

if __name__=='__main__':unittest.main()
