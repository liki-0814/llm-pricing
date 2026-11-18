"""Atlas three-root regressions: original HTTP bodies + controlled no-HTTP variants."""
import copy
import json
import re
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import public_price_facts as p
import public_price_models as models
import build_api
from public_price_context import explicit_unit, markdoc_tables


class SharedPriceContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger=p.load()
        cls.bodies={m['source_url']:(p.ROOT/m['body_path']).read_bytes() for m in cls.ledger['sources']}
        cls.meta={m['vendor']:m for m in cls.ledger['sources'] if m['source_url'] not in p.CATALOG_URLS}
        cls.data=build_api.load()

    def assemble_variant(self,vendor,changed):
        meta=dict(self.meta[vendor],source_sha256=p.digest(changed.encode()))
        return p.assemble([meta],lambda m:changed.encode(),'controlled_counterexample_NOT_HTTP_NOT_fresh')

    def test_original_google_closed_tabs_independent_scope_oracle(self):
        source=self.meta['Google Gemini']['source_url'];text=self.bodies[source].decode();tables=list(markdoc_tables(text))
        self.assertGreater(len(tables),20)
        observations=[r for r in self.ledger['pending'] if r['source_url']==source and isinstance(r.get('heading'),dict) and 'model_section' in r['heading']]
        corrected=[]
        for table in tables:
            active=None
            for event in re.finditer(r'{%\s*(/?)tab\b([^%]*)%}',text[:table['start']]):
                if event[1]=='/':active=None
                else:
                    title=re.search('title="([^"]+)"',event[2]);active=title[1] if title else None
            self.assertEqual(table['tab'],active)
            pieces=re.split(r'^\s*---\s*$',table['body'],flags=re.M)
            found=[r for r in observations if r['heading']['table_start']==table['start']]
            self.assertTrue(all(r['quote'] in pieces[1:] for r in found))
            self.assertTrue(all(r['heading']['tab']==active for r in found))
            previous=re.findall(r'{% tab title="([^"]+)" %}',text[:table['start']])
            if previous and previous[-1]!=active and found:corrected.append((table,len(found)))
        self.assertEqual((len(corrected),sum(n for _,n in corrected)),(5,11))
        lyria=[r for r in observations if 'Lyria 3.5' in str(r['heading']['model_section'])]
        self.assertTrue(lyria);self.assertTrue(all(r['heading']['tab'] is None for r in lyria))
        api=build_api.build(self.data,mixed=True,public_price_ledger=self.ledger)['price-facts.json']['data']
        self.assertTrue(all(r['heading']['tab'] is None for r in api['pending_candidates'] if isinstance(r.get('heading'),dict) and 'Lyria 3.5' in str(r['heading'])))

    def test_structural_stack_close_and_nested_tab_positive_controls(self):
        table='{% table %}\n * Metric\n * Free\n * Paid Tier, per 1M tokens in USD\n---\n * Input price\n * Free of charge\n * $1.00\n{% /table %}\n'
        text='## Example\n[`unit-model`](/docs/models/unit-model)\n{% tabs %}\n{% tab title="Priority" %}\n'+table+'{% tabs %}\n{% tab title="Batch" %}\n'+table+'{% /tab %}\n{% /tabs %}\n'+table+'{% /tab %}\n{% /tabs %}\n'+table
        tables=list(markdoc_tables(text));self.assertEqual([t['tab'] for t in tables],['Priority','Batch','Priority',None]);self.assertTrue(all(not t['scope_errors'] for t in tables))
        meta=dict(self.meta['Google Gemini'],source_sha256=p.digest(text.encode()));out=[]
        models.google(out,dict(meta=meta,text=text),[])
        self.assertEqual(len(out),3);self.assertEqual([r['conditions']['service_tier'] for r in out],['Priority','Batch','Priority'])
        changed=text.replace('{% /table %}','{% /tab %}{% /table %}',1)
        self.assertTrue(any(t['scope_errors'] for t in markdoc_tables(changed)))
        out=[];models.google(out,dict(meta=meta,text=changed),[]);self.assertEqual(out,[])

    def test_explicit_unit_reader_never_defaults_million_to_tokens(self):
        for header in ('输入单价（每百万字符）','Input / 1M characters','Input / million words','Input / M chars','Input / 1K tokens','Input / 10M tokens','Input price'):
            with self.subTest(header=header):self.assertIsNone(explicit_unit('$1.00',header))
        self.assertIsNone(explicit_unit('0.2元/张','输出单价（每百万Token）'))
        self.assertIsNone(explicit_unit('$0.20 / second','Price per minute'))
        for value,header,expected in [('10元','输入单价（每百万Token）','per_1M_tokens'),('$2.00','Input / M tokens','per_1M_tokens'),('$0.20 / image','','per_image'),('$0.05 / sec','','per_second'),('$0.018 / minute','','per_minute')]:
            with self.subTest(value=value):self.assertEqual(explicit_unit(value,header),expected)

    def test_atlas_character_header_negative_assembles_all_real_consumers(self):
        original=self.bodies[self.meta['阿里云 Qwen']['source_url']].decode();reader=p.Tables(original);reader.feed(original);changed=original;changed_headers=set()
        for table in reader.tables:
            for row in table['rows'][:1]:
                old=row['quote'];new=re.sub(r'每百万((?:<[^>]+>|\s)*)Token',r'每百万\1字符',old)
                if new!=old:changed_headers.add(old);changed=changed.replace(old,new)
        self.assertEqual(len(changed_headers),53)
        ledger=self.assemble_variant('阿里云 Qwen',changed)
        self.assertTrue(ledger['pending']);self.assertFalse(any(f['unit']=='per_1M_tokens' for f in ledger['facts']))
        self.assertFalse(any(f['unit']=='per_1M_tokens' for f in ledger['model_prices']))
        self.assertGreater(sum(f['unit']=='per_1M_tokens' for f in self.ledger['facts']),900)
        before=copy.deepcopy(self.data)
        for mixed in (False,True):
            api=build_api.build(self.data,mixed=mixed,public_price_ledger=ledger)
            self.assertFalse(any(f['unit']=='per_1M_tokens' for f in api['price-facts.json']['data']['facts']))
            self.assertFalse(any(f['unit']=='per_1M_tokens' for rel,response in api.items() if rel.startswith('price-models/') for f in response['data']['prices']))
        page=build_api.page_data(self.data,public_price_ledger=ledger)
        self.assertEqual(page['public_price_evidence']['price_verified_count'],len(ledger['facts']))
        snaps=[dict(vendor='阿里云 Qwen',channel='pay_as_you_go',records=[dict(model_id='qwen4-max')])]
        p.attach(snaps,ledger);self.assertEqual(snaps[0]['records'][0]['public_model_price_statements'],[])
        self.assertEqual(before,self.data)

    def test_unknown_denominator_and_contradictory_header_through_api(self):
        original=self.bodies[self.meta['阿里云 Qwen']['source_url']].decode()
        for label in ('每十万Token','每百万Token / 每张'):
            changed=re.sub(r'每百万((?:<[^>]+>|\s)*)Token',lambda m:label,original)
            self.assertNotEqual(original,changed)
            ledger=self.assemble_variant('阿里云 Qwen',changed)
            with self.subTest(label=label):
                self.assertTrue(ledger['pending'])
                self.assertFalse(any(f['unit']=='per_1M_tokens' for f in ledger['facts']))
                api=build_api.build(self.data,mixed=True,public_price_ledger=ledger)['price-facts.json']['data']
                self.assertFalse(any(f['unit']=='per_1M_tokens' for f in api['facts']+api['model_prices']))

    def test_markdown_explicit_character_header_rejects_normalized_token_fallback(self):
        original=self.bodies[self.meta['xAI']['source_url']].decode();changed=original.replace('/ 1M tokens','/ 1M characters')
        ledger=self.assemble_variant('xAI',changed)
        self.assertFalse(any(r['unit']=='per_1M_tokens' for r in ledger['model_prices']))
        self.assertTrue(any(r['unit']=='per_image' for r in ledger['model_prices']))
        self.assertTrue(any(r['unit']=='per_1M_tokens' for r in self.ledger['model_prices'] if r['vendor']=='xAI'))

    def test_each_fast_entitlement_proposition_has_independent_evidence(self):
        original=self.bodies[self.meta['xAI']['source_url']].decode()
        source=self.ledger['offering_channel_observations'][0]
        self.assertTrue(source['channel_verified']);self.assertFalse(source['public_xai_API']);self.assertFalse(source['free_build_tier_included'])
        variants={
            'free_build_tier_included':re.sub(r", and Grok Build[^<>]{0,40}free tier does not include it\.",'.',original),
            'public_xai_API':original.replace('not available on the public xAI API','available on a separately described API'),
            'available_in':original.replace('available only in','available somewhere in'),
            'billing_channel':original.replace('billed through your plan there','billed another way there'),
        }
        for field,changed in variants.items():
            self.assertNotEqual(changed,original)
            ledger=self.assemble_variant('xAI',changed);self.assertEqual(len(ledger['offering_channel_observations']),1)
            observation=ledger['offering_channel_observations'][0]
            with self.subTest(field=field):
                self.assertEqual(observation['claim_evidence'][field]['state'],'unknown')
                self.assertIsNone(observation['claim_evidence'][field]['value'])
                for other in variants.keys()-{field}:self.assertEqual(observation['claim_evidence'][other]['state'],'verified')
                self.assertEqual(observation['channel_verified'],field!='billing_channel')
                if field=='free_build_tier_included':self.assertIsNone(observation[field])
                api=build_api.build(self.data,mixed=True,public_price_ledger=ledger)['price-facts.json']['data']
                self.assertEqual(api['offering_channel_observations'],[observation])
        for claim in source['claim_evidence'].values():
            self.assertEqual(claim['state'],'verified');self.assertIn(claim['quote'],original);self.assertEqual(claim['quote_sha256'],p.digest(claim['quote'].encode()))

    def test_other_plan_or_adjacent_prose_cannot_supply_fast_exclusion(self):
        original=self.bodies[self.meta['xAI']['source_url']].decode()
        missing=re.sub(r", and Grok Build[^<>]{0,40}free tier does not include it\.",'.',original)
        self.assertNotEqual(original,missing)
        unrelated="Other Plan is a separate offering, and Grok Build's free tier does not include it."
        variants=[missing.replace('Long-context rates apply',unrelated+'\n\nLong-context rates apply'),
                  missing.replace('It is not available on the public xAI API.','It is not available on the public xAI API. '+unrelated)]
        for changed in variants:
            self.assertNotEqual(changed,missing)
            ledger=self.assemble_variant('xAI',changed);observation=ledger['offering_channel_observations'][0]
            self.assertTrue(observation['channel_verified']);self.assertFalse(observation['public_xai_API']);self.assertIsNone(observation['free_build_tier_included'])
            projected=build_api.build(self.data,mixed=True,public_price_ledger=ledger)['price-facts.json']['data']['offering_channel_observations'][0]
            self.assertIsNone(projected['free_build_tier_included'])
        adjacent=original.replace('Long-context rates apply','An unrelated plan uses other limits.\n\nLong-context rates apply')
        control=self.assemble_variant('xAI',adjacent)['offering_channel_observations'][0]
        self.assertFalse(control['free_build_tier_included']);self.assertTrue(all(c['state']=='verified' for c in control['claim_evidence'].values()))

    def test_html_tabpanel_closed_panel_not_inherited(self):
        text='<h2>LLM</h2><div role="tabpanel" aria-labelledby="batch"><table><tr><th>Model</th></tr><tr><td>example-model</td></tr></table></div><table><tr><th>Model</th></tr><tr><td>other-model</td></tr></table>'
        reader=p.Tables(text);reader.feed(text);reader.close();self.assertEqual([t['tab_label'] for t in reader.tables],['batch',None])


if __name__=='__main__':unittest.main()
