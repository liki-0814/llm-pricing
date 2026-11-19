import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import public_price_facts as p
import refresh_public_prices as refresh
import build_api

class PublicPriceRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger=p.load();cls.meta=next(m for m in cls.ledger['sources'] if m['vendor']=='xAI');cls.raw=(p.ROOT/cls.meta['body_path']).read_bytes();cls.url=cls.meta['source_url']

    def test_successful_capture_then_failure_never_relabels_cache_fresh(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);calls=[]
            def good(url):calls.append(url);return self.raw,url
            first=refresh.refresh(root/'first',root/'cache',[self.url],fetcher=good)
            self.assertEqual(calls,[self.url]);self.assertEqual(first['refresh_run']['transport'],'test_injected_NOT_network')
            self.assertFalse(first['refresh_run']['all_sources_http_ok'])
            at=first['sources'][0]['observed_at']
            def fail(url):calls.append(url);raise OSError('simulated HTTP 403: do not retry')
            second=refresh.refresh(root/'second',root/'cache',[self.url],fetcher=fail)
            self.assertEqual(calls,[self.url,self.url]);self.assertEqual(second['sources'],[])
            self.assertEqual(second['facts'],[]);self.assertFalse(second['refresh_run']['all_sources_http_ok'])
            self.assertEqual(second['archival_last_known'][0]['observed_at'],at)
            self.assertTrue(second['archival_last_known'][0]['not_fresh'])
            self.assertEqual(second['refresh_run']['source_results'][0]['retry_count'],0)

    def test_http_gate_is_sticky_and_never_retried_automatically(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);calls=[]
            def blocked(url):calls.append(url);raise urllib.error.HTTPError(url,403,'Forbidden',{},None)
            first=refresh.refresh(root/'one',root/'cache',[self.url],fetcher=blocked)
            self.assertEqual(first['refresh_run']['source_results'][0]['status'],'blocked_NOT_fresh')
            second=refresh.refresh(root/'two',root/'cache',[self.url],fetcher=blocked)
            self.assertEqual(second['refresh_run']['source_results'][0]['status'],'skipped_blocked_NOT_fresh')
            self.assertEqual(calls,[self.url]);self.assertEqual(second['sources'],[])

    def test_capture_body_status_hash_time_and_attempt_binding(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);out=root/'out';refresh.refresh(out,root/'cache',[self.url],fetcher=lambda u:(self.raw,u))
            path=out/'capture-manifest.json';original=json.loads(path.read_text())
            for key,value in [('reused_cache',True),('observed_at','2026-11-19T00:00:00+08:00'),('source_sha256','0'*64),('attempt_id','old-attempt')]:
                bad=copy.deepcopy(original);bad['refresh_run']['source_results'][0][key]=value;path.write_text(json.dumps(bad))
                with self.subTest(key=key),self.assertRaises(ValueError):p.load_capture(out)
            path.write_text(json.dumps(original));(out/original['sources'][0]['body_path']).write_bytes(b'not original')
            with self.assertRaises(ValueError):p.load_capture(out)

    def test_forbidden_challenged_and_authenticated_urls_never_requested(self):
        with tempfile.TemporaryDirectory() as t:
            for i,url in enumerate(['https://www.alibabacloud.com/help/en/model-studio/models','https://www.alibabacloud.com/llms.txt','https://api.x.ai/v1/models','https://example.com/']):
                calls=[]
                with self.subTest(url=url),self.assertRaises(ValueError):refresh.refresh(Path(t)/str(i),Path(t)/'cache',[url],fetcher=lambda u:calls.append(u))
                self.assertEqual(calls,[])

    def test_all_ten_originals_are_consumed_and_unscoped_quotes_not_global(self):
        self.assertEqual(len(self.ledger['sources']),10)
        quotes=[r for r in self.ledger['pending'] if r.get('quote_verified')]
        self.assertEqual({r['vendor'] for r in quotes},{'Anthropic','Google Gemini','MiniMax','OpenAI'})
        self.assertEqual({r['source_role'] for r in quotes},{'pricing','catalog'})
        bodies={s['source_url']:(p.ROOT/s['body_path']).read_bytes().decode() for s in self.ledger['sources']}
        for row in quotes:
            self.assertIn(row['quote'],bodies[row['source_url']]);self.assertEqual(row['quote_sha256'],p.digest(row['quote'].encode()))
            self.assertFalse(row['price_verified'] or row['scope_complete']);self.assertIsNone(row['region'])
            self.assertEqual(row['region_scope'],'unspecified_or_unparsed_NOT_global')
        # A known Google schedule is retained in one original condition-bearing
        # cell, not flattened to an invented scalar or guessed date/time.
        self.assertTrue(any('November 30, 2026' in r['quote'] and 'December 1, 2026' in r['quote'] and '$2.00' in r['quote'] and '$4.00' in r['quote'] for r in quotes))

    def test_capture_is_consumed_by_real_api_and_page_without_audited_rate_changes(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);ledger=refresh.refresh(root/'out',root/'cache',[self.url],fetcher=lambda u:(self.raw,u))
            d=build_api.load();before=copy.deepcopy(d)
            result=build_api.build(d,mixed=True,public_price_ledger=ledger)['price-facts.json']['data']
            self.assertEqual(result['refresh_run']['attempt_id'],ledger['refresh_run']['attempt_id'])
            self.assertEqual(result['price_verified_count'],0)
            page=build_api.page_data(d,public_price_ledger=ledger)
            self.assertEqual(page['public_price_evidence']['observed_at'],[ledger['sources'][0]['observed_at']]);self.assertEqual(d,before)

    def test_multilevel_text_component_and_explicit_list_price_are_not_audio_or_discount_quotes(self):
        facts=self.ledger['facts']
        rows=[f for f in facts if f['model_id']=='qwen3-omni-flash' and f['component']=='output']
        self.assertTrue(rows)
        self.assertTrue(all('文本' in r['tier'] and '仅音频计费' not in json.loads(r['tier'])['price_header'] for r in rows))
        listed=[f for f in facts if f.get('rate_kind')=='explicit_list_price_NOT_discounted_charge']
        self.assertTrue(listed)
        for r in listed:self.assertFalse(r['eligible_for_estimation']);self.assertIn('原价',r['quote'])

if __name__=='__main__':unittest.main()
