"""Isolated price leaf units: literal inputs only; no captures, files or build fixture."""
import copy
import dataclasses
import hashlib
import json
import socket
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import price_table_structure as structure
import public_price_context as c
import public_price_models as m
import public_price_facts as p

class PriceLeafUnits(unittest.TestCase):
    def setUp(self):
        self.guard=ExitStack();self.addCleanup(self.guard.close)
        self.guard.enter_context(patch('builtins.open',side_effect=AssertionError('unit file IO forbidden')))
        self.guard.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('unit network forbidden')))
    def meta(self,text,vendor='xAI',url='https://docs.x.ai/developers/pricing'):
        return dict(vendor=vendor,channel='pay_as_you_go',source_url=url,source_sha256=hashlib.sha256(text.encode()).hexdigest(),observed_at='2026-11-19T06:31:26+08:00',http_status=200)
    def simple(self,value='$2.00',header='Input / 1M tokens'):
        text=f'| Model | {header} | Notes |\n|---|---|---|\n| probe-model | {value} | other |\n';row=f'| probe-model | {value} | other |\n'
        meta=self.meta(text);proof=c.prove_unit(meta,text,cell=value,cell_index=1,scope=text,row=row)
        return text,row,meta,proof
    def test_units_supported_dimensions_and_denominators(self):
        for text,unit in [('$2 / MTok','per_1M_tokens'),('每百万Token','per_1M_tokens'),('per million tokens','per_1M_tokens'),('$2 / image','per_image'),('0.2元/张','per_image'),('$2 / sec','per_second'),('每秒','per_second'),('$2 per minute','per_minute'),('$2 per 768P, 6s video','per_video')]:
            with self.subTest(text=text):self.assertEqual(c.explicit_unit(text),unit)
        for text in ('每百万字符','$2 per million characters','$2 per 1000 tokens','per 1M unknown','per image / second'):
            with self.subTest(text=text):self.assertIsNone(c.explicit_unit(text))
    def test_strong_column_conflicts_and_real_weak_defaults(self):
        self.assertIsNone(c.explicit_unit('$2 / image','Input / 1M tokens'))
        self.assertIsNone(c.explicit_unit('$2','per image / per 1M tokens'))
        self.assertEqual(c.explicit_unit('$2 / minute','Input','Prices per 1M tokens.'),'per_minute')
        self.assertEqual(c.explicit_unit('$2 / 1M','Input','the standard token rates'),'per_1M_tokens')
    def test_markdown_column_ownership_and_truncation(self):
        text,row,meta,proof=self.simple('$2.00 / image')
        self.assertIsNone(proof)
        for headers in (('Notes',),('Input',),()):self.assertIsNone(c.prove_unit(meta,text,cell='$2.00 / image',columns=headers,scope=text,row=row))
        with self.assertRaises(ValueError):c.prove_unit(meta,text,cell='$2.00 / image',cell_index=2,scope=text,row=row)
        with self.assertRaises(ValueError):c.prove_unit(meta,text,cell='$2.00',scope=text,row=row)
    def test_identical_cells_require_physical_identity(self):
        t='| Model | Input / 1M tokens | Output per image |\n|---|---|---|\n| probe-model | $2 | $2 |\n';row=t.splitlines(True)[2];meta=self.meta(t)
        self.assertIsNone(c.prove_unit(meta,t,cell='$2',scope=t,row=row))
        a=c.prove_unit(meta,t,cell='$2',cell_index=1,scope=t,row=row);b=c.prove_unit(meta,t,cell='$2',cell_index=2,scope=t,row=row)
        self.assertEqual((a.unit,b.unit),('per_1M_tokens','per_image'));self.assertNotEqual(a.cell_span,b.cell_span)
        self.assertEqual(c.consume_unit(b,meta,t,row),b)
    def test_html_full_header_chain_rowspan_colspan(self):
        t='<table><tr><th rowspan="2">Model</th><th colspan="2">per 1M tokens</th></tr><tr><th>Input</th><th>Output</th></tr><tr><td>probe-model</td><td>$2 / image</td><td>$3</td></tr></table>';row='<tr><td>probe-model</td><td>$2 / image</td><td>$3</td></tr>';meta=self.meta(t)
        self.assertIsNone(c.prove_unit(meta,t,cell='<td>$2 / image</td>',cell_index=1,scope=t,row=row))
        proof=c.prove_unit(meta,t,cell='<td>$3</td>',cell_index=2,scope=t,row=row)
        self.assertEqual(proof.unit,'per_1M_tokens');self.assertEqual(len(proof.column_spans),2)
    def test_html_data_rowspan_lifetime_and_malformed_spans(self):
        t='<table><tr><th>Model</th><th>Input per 1M tokens</th></tr><tr><td>a</td><td rowspan="2">$2</td></tr><tr><td>b</td></tr><tr><td>c</td><td>$3</td></tr></table>';meta=self.meta(t)
        self.assertIsNotNone(c.prove_unit(meta,t,cell='<td rowspan="2">$2</td>',cell_index=1,scope=t,row='<tr><td>b</td></tr>'))
        with self.assertRaises(ValueError):c.prove_unit(meta,t,cell='<td rowspan="2">$2</td>',scope=t,row='<tr><td>c</td><td>$3</td></tr>')
        bad=t.replace('rowspan="2"','rowspan="0"')
        with self.assertRaises(ValueError):c.unit_table_layout(bad)
    def test_proof_json_roundtrip_and_forged_header_rejected(self):
        text,row,meta,proof=self.simple();data=proof.to_dict();self.assertEqual(data,json.loads(json.dumps(data)));self.assertEqual(c.consume_unit(data,meta,text,row),proof)
        at=text.index('Notes')
        for bad in (dataclasses.replace(proof,column_spans=((at,at+5),)),dataclasses.replace(proof,unit='per_image'),{'unit':'per_1M_tokens'},'per_1M_tokens'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):c.consume_unit(bad,meta,text,row)
    def test_proof_wrong_source_row_index_and_default(self):
        text,row,meta,proof=self.simple()
        for key,val in [('vendor','OpenAI'),('channel','subscription'),('observed_at','2026-11-19T07:00:00+08:00'),('source_sha256','0'*64)]:
            with self.subTest(key=key),self.assertRaises(ValueError):c.consume_unit(proof,dict(meta,**{key:val}),text,row)
        with self.assertRaises(ValueError):c.consume_unit(proof,meta,text,'other row')
        with self.assertRaises(ValueError):c.prove_unit(meta,text,cell='$2.00',cell_index=True,scope=text,row=row)
        with self.assertRaises(ValueError):c.prove_unit(meta,text,cell='$2.00',scope=text,row=row,default='Input / 1M tokens')
    def test_google_leaf_dates_and_conflicting_column(self):
        body='## Probe\n[`probe-model`](/docs/models/probe-model)\n{% tab title="Batch" %}\n{% table %}\n* Feature\n* Free Tier\n* Paid Tier, per 1M tokens in USD\n---\n* Input price\n* None\n* $2.00 through November 30, 2026. $4.00 starting December 1, 2026.\n{% /table %}\n{% /tab %}\n'
        for t,count in ((body,2),(body.replace('1M tokens in USD','1M tokens / per image in USD'),0)):
            out=[];m.google(out,dict(meta=self.meta(t,'Google Gemini'),text=t),[]);self.assertEqual(len(out),count)
            for r in out:self.assertEqual(r['unit'],'per_1M_tokens');self.assertIn('date_condition',r['conditions'])
    def test_markdown_media_and_minute_leaf_parsing(self):
        t='All prices are in USD.\n### Image & Video Pricing\n| Model | Cost |\n|---|---|\n| image-probe | $0.02 / image |\n| video-probe | $0.2 / second |\n';out=[];m.markdown_prices(out,dict(meta=self.meta(t),text=t));self.assertEqual([r['unit'] for r in out],['per_image','per_second'])
        t='All prices are in USD.\n| Model | Price per minute |\n|---|---|\n| audio-probe | $0.03 |\n';out=[];m.markdown_prices(out,dict(meta=self.meta(t,'OpenAI'),text=t));self.assertEqual(out[0]['unit'],'per_minute')
    def test_scalar_and_cny_list_price_grammar(self):
        for s,value in [('$2.50',2.5),('$0.2 / MTok',.2),('$0.2 / minute',.2)]:self.assertEqual(m.scalar(s),value)
        for s in ('$2 / character','$2.3 and $4','unknown'):self.assertIsNone(m.scalar(s))
        self.assertEqual(p.cny_rate('原价0.6元/秒（限时5折）'),(.6,True));self.assertEqual(p.cny_rate('0.25元/张'),(.25,False));self.assertIsNone(p.cny_rate('免费'))
    def test_constructors_replay_not_boolean_or_string(self):
        text,row,meta,proof=self.simple();out=[];m.emit(out,dict(meta=meta,text=text),'probe-model',2,'USD',proof,'input','text',row,['Input / 1M tokens'],{});self.assertEqual(out[0]['unit'],'per_1M_tokens')
        with self.assertRaises(ValueError):m.emit([],dict(meta=meta,text=text),'probe-model',2,'USD','per_1M_tokens','input','text',row,[],{})
        args=dict(model_id='probe-model',offering_name=None,channel='pay_as_you_go',region='test',modality='text',component='input',amount=2,currency='USD',unit=proof,tier='test',quote=row,context=['Input / 1M tokens'])
        self.assertTrue(p.fact(meta,text,**args)['price_verified'])
        for updates in ({'unit':'per_1M_tokens'},{'region':None},{'amount':float('nan')}):
            with self.assertRaises(ValueError):p.fact(meta,text,**dict(args,**updates))
    def test_subject_boundary_punctuation_not_sentence_permission(self):
        anchor='Grok 4.7 Fast is the same Grok 4.7 model served on faster infrastructure.'
        for sep in ('. ','; ',': ',' — ', ', and ', ' while '):
            text=anchor+' It is not available on the public xAI API'+sep+"Other Plan is a separate offering, and Grok Build's free tier does not include it."
            clauses,_,_=c.entity_clauses(text,anchor);claim=c.entity_claim(text,clauses,False,lambda q:'free tier does not include it' in q)
            self.assertEqual(claim['state'],'unknown');self.assertIsNone(claim['value'])
    def test_own_subject_exclusion_and_ambiguous_coordination(self):
        anchor='Grok 4.7 Fast is the same Grok 4.7 model served on faster infrastructure.'
        own=anchor+" It is not available on the public xAI API; Grok Build's free tier does not include it."
        cs,_,_=c.entity_clauses(own,anchor);v=c.entity_claim(own,cs,False,lambda q:'free tier does not include it' in q);self.assertEqual((v['state'],v['value']),('verified',False));self.assertIn('subject_quote',v)
        bad=anchor+" It and Other Plan are separate offerings; Grok Build's free tier does not include it."
        cs,_,_=c.entity_clauses(bad,anchor);self.assertEqual(c.entity_claim(bad,cs,False,lambda q:'free tier' in q)['state'],'unknown')
    def test_structural_tab_close_is_not_inherited(self):
        table='{% table %}x{% /table %}'
        parsed=list(c.markdoc_tables('## A\n{% tab title="Batch" %}'+table+'{% /tab %}'+table))
        self.assertEqual([r['tab'] for r in parsed],['Batch',None])

if __name__=='__main__':unittest.main()
