"""Actual 06:31 original bodies through shared production build/query paths."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import public_price_facts as p
import build_api
import validate

class PublicPriceModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger=p.load();cls.rows=cls.ledger['model_prices'];cls.data=build_api.load()
        cls.bodies={m['source_url']:(p.ROOT/m['body_path']).read_bytes().decode() for m in cls.ledger['sources']}
        cls.sources={m['source_url']:m for m in cls.ledger['sources']}
        cls.v2=build_api.build(cls.data,mixed=True,public_price_ledger=cls.ledger)
        cls.v1=build_api.build(cls.data,mixed=False,public_price_ledger=cls.ledger)

    def test_real_per_ID_API_and_website_playground(self):
        for mid in ('claude-sonnet-5-5','gemini-4-carbon','MiniMax-M3.1-Flash','image-01','MiniMax-H3','gpt-6.2-sol','gpt-image-2.6-sunburst','grok-4.7','grok-imagine-video','qwen4-max','qwen3.8-omni-flash'):
            r=self.v2['price-models/'+mid+'.json']['data'];self.assertTrue(r['prices']);self.assertFalse(r['scope_complete'] or r['eligible_for_estimation'])
        self.assertIn('price-models',self.v2['index.json']['data']['endpoints'])
        self.assertIn('value="price-model"',(p.ROOT/'api.html').read_text())
        self.assertIn('price-models/',(p.ROOT/'assets/api.js').read_text())
        self.assertEqual(validate.validate_api(self.data,self.v1),[])
        self.assertEqual(validate.validate_api(self.data,self.v2),[])

    def test_original_body_quote_hash_bridge_and_incomplete_region(self):
        for r in self.rows:
            body=self.bodies[r['source_url']];self.assertIn(r['quote'],body)
            self.assertEqual(r['source_sha256'],p.digest(body.encode()));self.assertEqual(r['quote_sha256'],p.digest(r['quote'].encode()))
            self.assertTrue(all(q in body for q in r['context_quotes']));self.assertFalse(r['scope_complete'] or r['history_complete'] or r['eligible_for_estimation'])
            if r.get('identity_evidence'):
                i=r['identity_evidence'];self.assertIn(i['quote'],self.bodies[i['source_url']]);self.assertEqual(i['quote_sha256'],p.digest(i['quote'].encode()))
            if r['vendor'] not in ('阿里云 Qwen','Anthropic'):
                self.assertIsNone(r['region']);self.assertFalse(r['price_verified'] or r['selector_complete']);self.assertEqual(r['region_scope'],'not_stated_NOT_global')

    def test_scalar_explicit_units_override_defaults_without_conversion(self):
        from public_price_models import billing_unit,scalar
        for text,unit in [('$0.04 / image','per_image'),('$0.08 / sec','per_second'),('$0.05 / minute','per_minute'),('$2 / MTok','per_1M_tokens')]:
            self.assertEqual(billing_unit(text,'per_1M_tokens'),unit);self.assertIsNotNone(scalar(text))
        self.assertIsNone(scalar('$2 $4'));self.assertIsNone(scalar('Free after quota'))

    def test_google_date_pair_not_flattened(self):
        rows=[r for r in self.rows if r['model_id']=='gemini-4-carbon' and r['component']=='input' and r['conditions']['service_tier']=='Standard']
        self.assertEqual({(r['amount'],r['conditions']['date_condition']['date'],r['conditions']['date_condition']['operator']) for r in rows},{(2.,'2026-11-30','through_inclusive'),(4.,'2026-12-01','starting_inclusive')})
        self.assertTrue(all(r['conditions']['date_condition']['timezone'] is None for r in rows))

    def test_anthropic_literal_ID_bridge_not_slugification(self):
        rows=[r for r in self.rows if r['vendor']=='Anthropic'];self.assertEqual(len({r['model_id'] for r in rows}),4)
        s=[r for r in rows if r['model_id']=='claude-sonnet-5-5'];self.assertTrue(any(r['amount']==2 and r['component']=='input' for r in s));self.assertTrue(any(r['amount']==10 and r['component']=='output' for r in s))
        self.assertTrue(all('Claude API ID' in r['identity_evidence']['quote'] for r in rows))

    def test_minimax_units_tabs_deleted_price_and_channels(self):
        f=[r for r in self.rows if r['model_id']=='MiniMax-M3.1-Flash'];self.assertEqual({(r['component'],r['amount']) for r in f},{('input',.15),('output',.60),('cached_input',.015)})
        image=[r for r in self.rows if r['model_id']=='image-01'];self.assertEqual({(r['amount'],r['unit']) for r in image},{(.0035,'per_image')})
        video=[r for r in self.rows if r['model_id']=='MiniMax-H3'];self.assertTrue(any(r['amount']==.13 and r['unit']=='per_second' and r['component']=='output' for r in video))
        m3=[r for r in self.rows if r['model_id']=='MiniMax-M3'];self.assertEqual({r['conditions']['service_tier'] for r in m3},{'standard','priority'})
        self.assertTrue(all(r['conditions']['rate_kind'] in ('deleted_list_price_NOT_current_charge','explicit_permanent_replacement') for r in m3))
        self.assertTrue(all(r['channel']=='pay_as_you_go' for r in self.rows if r['vendor']=='MiniMax'))
        bundled=[r for r in self.rows if r['model_id']=='MiniMax-Hailuo-2.3-Fast'];self.assertTrue(any(r['amount']==.19 and r['unit']=='per_video' and r['conditions']['dimensions']['duration_seconds']==6 for r in bundled))

    def test_openai_currency_missing_separate_from_model_amount_unit(self):
        rows=[r for r in self.rows if r['model_id']=='gpt-6.2-sol'];self.assertTrue(any(r['amount']==2 and r['component']=='input' and r['conditions']['service_tier']=='Standard' and r['conditions']['price_header']=='Short context input' for r in rows))
        self.assertTrue(any(r['amount']==1 and r['component']=='input' and r['conditions']['service_tier']=='Batch' for r in rows))
        self.assertTrue(all(r['currency'] is None and r['currency_symbol']=='$' and not r['price_verified'] for r in rows))
        image=[r for r in self.rows if r['model_id']=='gpt-image-2.6-sunburst'];self.assertEqual({r['billing_modality'] for r in image},{'image','text'});self.assertTrue(all(r['unit']=='per_1M_tokens' for r in image))
        audio=[r for r in self.rows if r['model_id']=='gpt-live-1'];self.assertTrue(any(r['unit']=='per_minute' for r in audio))

    def test_xai_plan_not_API_and_threshold_prices_not_collapsed(self):
        rows=[r for r in self.rows if r['model_id']=='grok-4.7'];self.assertEqual({(r['component'],r['amount']) for r in rows},{('input',2.),('input',4.),('cached_input',.5),('cached_input',1.),('output',6.),('output',12.)})
        self.assertTrue(all(r['channel']=='pay_as_you_go' for r in rows));self.assertFalse(any('fast' in r['model_id'].lower() and r['vendor']=='xAI' for r in self.rows))
        self.assertEqual(len(self.ledger['offering_channel_observations']),1);self.assertIsNone(self.ledger['offering_channel_observations'][0]['model_id'])

    def test_qwen_media_list_price_NOT_discount_and_omni_NOT_modality_certificate(self):
        rows=[r for r in self.rows if r['model_id']=='wan3.0-video'];self.assertTrue(any(r['amount']==.3 and r['unit']=='per_second' and r['rate_kind']=='explicit_list_price_NOT_discounted_charge' for r in rows))
        self.assertFalse(any(r['amount']==.21 for r in rows))
        omni=[r for r in self.rows if r['model_id']=='qwen3.8-omni-flash'];self.assertTrue(omni);self.assertTrue(all(not r['price_verified'] and r['billing_modality']=='not_stated' for r in omni))
        self.assertTrue(all(r['currency']=='CNY' and r['region'] and r['unit']=='per_1M_tokens' for r in omni))
        self.assertTrue(any(r['reason']=='unreviewed_price_table_header' and not r.get('model_id') for r in self.ledger['pending']))

    def test_v1_no_CNY_or_untyped_currency_candidates_and_audited_89_unchanged(self):
        records=self.v1['price-facts.json']['data']['model_prices'];self.assertTrue(records);self.assertEqual({r['currency'] for r in records},{'USD'})
        self.assertNotIn('price-models/qwen4-max.json',self.v1);self.assertNotIn('price-models/gpt-6.2-sol.json',self.v1)
        self.assertEqual(len(self.v2['models.json']['data']),89)
        self.assertEqual({r['id'] for r in self.v2['models.json']['data']},{r['id'] for r in build_api.build(self.data,mixed=True)['models.json']['data']})

    def test_source_channel_missing_fields_and_ID_negative_controls(self):
        url='https://aistudio.google.com/docs/pricing';original=self.bodies[url]
        for field,changed in [('unit',original.replace('per 1M tokens','per unspecified units')),('currency',original.replace('USD','unknown currency')),('id',__import__('re').sub(r'\[`[^`]+`\]\(/docs/models/[^)]+\)','missing model reference',original))]:
            metas=copy.deepcopy(self.ledger['sources']);meta=next(m for m in metas if m['source_url']==url);meta['source_sha256']=p.digest(changed.encode());bodies=dict(self.bodies,**{url:changed})
            result=p.assemble(metas,lambda m:bodies[m['source_url']].encode());self.assertFalse(any(r['vendor']=='Google Gemini' for r in result['model_prices']),field)
        for field,value in [('channel','subscription'),('vendor','xAI'),('source_sha256','0'*64),('source_url','https://example.com/pricing')]:
            meta=dict(self.sources[url],**{field:value})
            with self.assertRaises(ValueError):p.assemble([meta],lambda m:original.encode())
        with self.assertRaises(ValueError):p.assemble([self.sources[url]],lambda m:b'')

if __name__=='__main__':unittest.main()
