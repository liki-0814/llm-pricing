"""Original public HTTP bodies exercise the production parser and build entry."""
import copy
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import public_price_facts as p
import build_api

class PublicPriceFactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger=p.load()
        cls.meta=cls.ledger['sources'][0]
        cls.raw=(p.ROOT/cls.meta['body_path']).read_bytes()
        cls.xmeta=cls.ledger['sources'][1]
        cls.xraw=(p.ROOT/cls.xmeta['body_path']).read_bytes()

    def rows(self,mid,region,component):
        return [f for f in self.ledger['facts'] if f['model_id']==mid and f['region']==region and f['component']==component]

    def test_qwen_original_text_region_currency_unit(self):
        rows=self.rows('qwen4-max','华北2（北京）','input')
        self.assertTrue(rows)
        for f in rows:
            self.assertEqual((f['amount'],f['currency'],f['unit'],f['channel']),(10.,'CNY','per_1M_tokens','pay_as_you_go'))
            self.assertIn('0<Token≤1M',f['tier'])
            self.assertRegex(f['quote'],r'10(?:<[^>]+>)*元')
            self.assertEqual(f['quote_sha256'],p.digest(f['quote'].encode()))
            self.assertIsNone(f['effective_from'])
            self.assertFalse(f['scope_complete'])

    def test_qwen_image_and_video_real_regions_not_fx(self):
        image=[f for f in self.ledger['facts'] if f['model_id']=='qwen-image-2.1-pro' and f['component']=='output']
        self.assertTrue(any(f['amount']==.25 and f['region']=='华北2（北京）' for f in image))
        self.assertTrue(any(f['amount']==.283404 and '新加坡' in f['region'] for f in image))
        self.assertTrue(all(f['currency']=='CNY' and f['unit']=='per_image' for f in image))
        video=self.rows('wan2.7-t2v','华北2（北京）','output')
        self.assertTrue(any(f['amount']==.6 and '720P' in f['tier'] for f in video))
        self.assertTrue(any(f['amount']==1. and '1080P' in f['tier'] for f in video))
        self.assertTrue(all(f['unit']=='per_second' for f in video))

    def test_every_verified_field_bound_to_original(self):
        bodies={m['source_url']:(p.ROOT/m['body_path']).read_bytes().decode() for m in self.ledger['sources']}
        for f in self.ledger['facts']:
            body=bodies[f['source_url']]
            self.assertIn(f['quote'],body)
            self.assertTrue(all(q in body for q in f['context_quotes']))
            self.assertEqual(f['source_sha256'],p.digest(body.encode()))
            self.assertTrue(f['region'] and f['tier'] and f['unit'] and f['observed_at'])
            self.assertFalse(f['scope_complete'] or f['history_complete'] or f['eligible_for_estimation'])
            self.assertEqual(f['availability'],'not_assessed')

    def test_no_body_hash_source_channel_or_vendor_substitution(self):
        for key,value in [('source_url','https://example.com/pricing'),('channel','subscription'),('vendor','OpenAI'),('source_sha256','0'*64),('http_status',403),('observed_at','2026-11-19')]:
            meta=dict(self.meta,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):p.parse(meta,self.raw)
        with self.assertRaises(ValueError):p.parse(self.meta,b'')

    def test_missing_dimensions_or_rate_never_verified(self):
        original=self.raw.decode()
        reader=p.Tables(original);reader.feed(original)
        regions={t['headings'][4]['quote'] for t in reader.tables if 4 in t['headings'] and t['headings'][4]['text']=='华北2（北京）'}
        variants={
          'rate':re.sub(r'10(?:<[^>]+>)*元','待公布',original),
          'region':original,
          'currency':original.replace('元','美元'),
          'unit':re.sub(r'每百万(?:<[^>]+>|\s)*Token','Token',original),
          'channel':original.replace('模型调用默认 按量计费 ，涵盖各类模型的计费规则与价格。',''),
        }
        for quote in regions:variants['region']=variants['region'].replace(quote,'<h4></h4>')
        for field,changed in variants.items():
            self.assertNotEqual(original,changed,field)
            meta=dict(self.meta,source_sha256=p.digest(changed.encode()))
            with self.subTest(field=field):
                if field=='channel':
                    with self.assertRaises(ValueError):p.parse(meta,changed.encode())
                else:
                    result=p.parse(meta,changed.encode())
                    if field=='rate':self.assertFalse(any(f['amount']==10 and f['model_id']=='qwen4-max' for f in result['facts']))
                    if field=='region':self.assertFalse(any(f['region']=='华北2（北京）' for f in result['facts']))
                    if field=='currency':self.assertEqual(result['facts'],[])
                    if field=='unit':self.assertFalse(any(f['unit']=='per_1M_tokens' for f in result['facts']))
                    self.assertTrue(result['pending'])

    def test_xai_plan_prose_consumed_without_api_id_or_entitlement(self):
        rows=[f for f in self.ledger['pending'] if f.get('vendor')=='xAI']
        self.assertEqual(len(rows),6)
        for f in rows:
            self.assertEqual(f['channel'],'subscription');self.assertIsNone(f['model_id'])
            self.assertEqual(f['offering_name'],'Grok 4.7 Fast')
            self.assertFalse(f['price_verified']);self.assertIsNone(f['region'])
        offerings=self.ledger['offering_channel_observations']
        self.assertEqual(len(offerings),1)
        self.assertTrue(offerings[0]['channel_verified'])
        self.assertFalse(offerings[0]['scope_complete'])
        self.assertEqual(offerings[0]['account_entitlement'],'not_assessed')
        self.assertIn('not available on the public xAI API',offerings[0]['quote'])
        changed=self.xraw.decode().replace('billed through your plan','billed another way')
        result=p.parse(dict(self.xmeta,source_sha256=p.digest(changed.encode())),changed.encode())
        self.assertEqual(result['facts'],[])
        self.assertTrue(result['pending'])

    def test_inventory_exact_join_no_cross_context_and_no_universe_upgrade(self):
        snapshots=[dict(vendor=v,channel=c,records=[dict(model_id='qwen4-max',output_modalities=['text'],alias_status='unknown',native_vendor_status='unknown')],scope_certificates=[dict(status='unknown')]) for v,c in [('阿里云 Qwen','pay_as_you_go'),('阿里云 Qwen','subscription'),('xAI','pay_as_you_go')]]
        before=copy.deepcopy(snapshots)
        p.attach(snapshots,self.ledger)
        self.assertTrue(snapshots[0]['records'][0]['public_price_observations'])
        for i in (1,2):self.assertEqual(snapshots[i]['records'][0]['public_price_observations'],[])
        for a,b in zip(before,snapshots):
            self.assertEqual(a['scope_certificates'],b['scope_certificates'])
            for k in ('model_id','alias_status','native_vendor_status','output_modalities'):self.assertEqual(a['records'][0][k],b['records'][0][k])
        self.assertTrue(self.ledger['pending'])

    def test_real_build_api_and_website_data_consume_price_facts(self):
        d=build_api.load();before=copy.deepcopy(d)
        for mixed in (False,True):
            api=build_api.build(d,mixed=mixed)
            self.assertIn('price-facts',api['index.json']['data']['endpoints'])
            view=api['price-facts.json']['data']
            self.assertTrue(view['offering_channel_observations']);self.assertFalse(view['scope_complete'])
            self.assertEqual(set(f['currency'] for f in view['facts']),{'CNY'} if mixed else set())
            self.assertIn('/price-facts.json',api['openapi.json']['paths'])
        page=build_api.page_data(d)
        self.assertGreater(page['public_price_evidence']['price_verified_count'],0)
        self.assertEqual(page['public_price_evidence']['url'],'api/v2/price-facts.json')
        self.assertIn('data.public_price_evidence',(p.ROOT/'assets/app.js').read_text())
        self.assertEqual(d,before)

if __name__=='__main__':unittest.main()
