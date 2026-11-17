"""Regression cases independently observed in the read-only preflight."""
import copy,json,pathlib,subprocess,sys,tempfile,unittest,multiprocessing
from unittest import mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import catalog_diff as c
import run_discovery as runner
ROOT=pathlib.Path(__file__).resolve().parents[1]
def snapshot(vendor='Vendor',at='2026-11-17T12:00:00Z'):
 return dict(vendor=vendor,channel='native',complete=True,errors=[],source_url='https://official.invalid/catalog',observed_at=at,fetch_status='ok',extraction_status='ok',coverage_evidence=dict(enumeration_verified=True,pagination_complete=True,native_identity_verified=True,source_url='https://official.invalid/catalog',expected_record_count=1,modalities=['text']),records=[dict(model_id='nebula-v1.2',api_id_explicit=True)])
def result(at,mid):
 s=snapshot(at=at)
 return dict(status='complete',scope_manifest_sha256='fixture-v1',coverage=[dict(vendor='Vendor',channel='native',source_url=s['source_url'],observed_at=at,role='catalog',modalities=['text'])],observations=[dict(vendor='Vendor',channel='native',model_id=mid)])
def competing_writer(directory,barrier):
 token=c.begin_attempt(directory);barrier.wait(timeout=10)
 c.save_attempt(directory,result('2026-11-17T12:00:00Z',str(token['run_sequence'])),token)

class DiscoveryRegressions(unittest.TestCase):
 def test_omitted_zero_database_tencent_never_complete(self):
  db=json.loads((ROOT/'data/prices.json').read_text());db['models']=[m for m in db['models'] if m['vendor']!='腾讯混元']
  scopes=sorted({(m['vendor'],m['billing']['channel']) for m in db['models']});snaps=[]
  for v,ch in scopes:
   s=snapshot(v);s['channel']=ch;snaps.append(s)
  r=c.compare_catalogs(db,snaps);self.assertEqual(r['status'],'incomplete')
  self.assertIn(('腾讯混元','pay_as_you_go','text'),r['missing_scopes'])
 def test_bad_json_records_failed_attempt_and_preserves_success(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);state=root/'state';good=c.save_attempt(state,result('2026-11-17T12:00:00Z','new'))
   bad=root/'bad.json';bad.write_text('{broken')
   run=subprocess.run([sys.executable,str(ROOT/'scripts/catalog_diff.py'),'--database',str(ROOT/'data/prices.json'),'--inventory',str(bad),'--state-dir',str(state)],capture_output=True,text=True)
   self.assertNotEqual(run.returncode,0)
   latest=json.loads((state/'latest-attempt.json').read_text());self.assertEqual(latest['status'],'error')
   self.assertEqual(c.previous_success(state)['observations'][0]['model_id'],'new')
 def test_upstream_normalization_preserves_literal_ids_and_unresolved(self):
  rows=[dict(vendor='Vendor',channel='native',observed_name_or_id=x,api_id_explicit=True) for x in ['model-v1.2','model-v12','Model-V12']]
  normalized=c.normalize_rows(rows)
  self.assertEqual([r['model_id'] for r in normalized],['model-v1.2','model-v12','Model-V12'])
 def test_late_old_success_never_replaces_fresh_source_baseline(self):
  with tempfile.TemporaryDirectory() as d:
   c.save_attempt(d,result('2026-11-17T12:00:00Z','new'))
   c.save_attempt(d,result('2026-11-16T12:00:00Z','old'))
   self.assertEqual(c.previous_success(d)['observations'][0]['model_id'],'new')
 def test_official_model_code_and_unknown_family(self):
  rows=c.extract_explicit_ids('* **Model Code**：`glm-5.3-flash`/`glm-5.3-flashx`/`glm-5.3-flashx-legal`\nModel Code: `nebula-99.1-unpriced`')
  self.assertEqual([r['model_id'] for r in rows],['glm-5.3-flash','glm-5.3-flashx','glm-5.3-flashx-legal','nebula-99.1-unpriced'])

 def test_explicit_scope_without_any_database_rows_and_missing_modality(self):
  manifest={'version':1,'scopes':[dict(vendor='Vendor',channel='native',modalities=['text','video'],official_hosts=['official.invalid'])]}
  r=c.compare_catalogs({'models':[]},[snapshot()],scopes=manifest)
  self.assertEqual(r['status'],'incomplete');self.assertEqual(r['missing_scopes'],[('Vendor','native','video')])
 def test_pair_complete_first_run_unknown_id_and_partial_price_separate(self):
  manifest={'version':1,'scopes':[dict(vendor='Vendor',channel='native',modalities=['text'],official_hosts=['official.invalid'])]}
  price=snapshot();price.update(role='price',complete=False,extraction_status='failed')
  r=c.compare_catalogs({'models':[]},[snapshot(),price],scopes=manifest)
  self.assertEqual(r['status'],'complete');self.assertEqual(r['historical_comparison'],'no_previous_successful_snapshot')
  self.assertEqual(r['not_in_database'][0]['model_id'],'nebula-v1.2')
 def test_cross_source_conflicting_origin_stays_unresolved(self):
  manifest={'version':1,'scopes':[dict(vendor='Vendor',channel='native',modalities=['text'],official_hosts=['official.invalid'])]}
  a=snapshot();b=snapshot();a['records'][0]['origin_vendor']='native-A';b['records'][0]['origin_vendor']='native-B'
  r=c.compare_catalogs({'models':[]},[a,b],scopes=manifest)
  self.assertEqual(r['status'],'incomplete');self.assertEqual(len(r['unresolved_rows']),2)
 def test_alias_requires_official_quote_and_does_not_guess_case(self):
  manifest={'version':1,'scopes':[dict(vendor='Vendor',channel='native',modalities=['text'],official_hosts=['official.invalid'])]}
  base=dict(vendor='Vendor',channel='native',alias='nebula-v1.2',canonical='nebula-v12',source_url='https://unofficial.invalid/map',evidence_quote='nebula-v1.2 -> nebula-v12')
  with self.assertRaises(ValueError):c.compare_catalogs({'models':[]},[snapshot()],aliases=[base],scopes=manifest)
  base['source_url']='https://official.invalid/map';base['evidence_quote']='name only'
  with self.assertRaises(ValueError):c.compare_catalogs({'models':[]},[snapshot()],aliases=[base],scopes=manifest)
  base['evidence_quote']='nebula-v1.2 -> nebula-v12'
  self.assertEqual(c.compare_catalogs({'models':[]},[snapshot()],aliases=[base],scopes=manifest)['observations'][0]['model_id'],'nebula-v12')
 def test_started_old_success_and_failure_never_overwrite_new_attempt(self):
  with tempfile.TemporaryDirectory() as d:
   old=c.begin_attempt(d);new=c.begin_attempt(d)
   c.save_attempt(d,result('2026-11-17T12:00:00Z','new'),new)
   target=c.save_attempt(d,result('2026-11-17T13:00:00Z','old-but-future-source'),old)
   self.assertEqual(json.loads(target.read_text())['baseline_update'],'rejected_stale_run')
   self.assertEqual(c.previous_success(d)['observations'][0]['model_id'],'new')
   pointer=json.loads((pathlib.Path(d)/'latest-attempt.json').read_text());self.assertEqual(pointer['run_sequence'],new['run_sequence'])
 def test_real_processes_cannot_regress_sequence(self):
  with tempfile.TemporaryDirectory() as d:
   ctx=multiprocessing.get_context('fork');barrier=ctx.Barrier(4)
   workers=[ctx.Process(target=competing_writer,args=(d,barrier)) for _ in range(4)]
   for p in workers:p.start()
   for p in workers:
    p.join(12)
    if p.is_alive():p.kill();p.join();self.fail('ledger worker hung')
    self.assertEqual(p.exitcode,0)
   self.assertEqual(c.previous_success(d)['run_sequence'],4)
   self.assertEqual(json.loads((pathlib.Path(d)/'latest-attempt.json').read_text())['run_sequence'],4)
 def test_bad_previous_json_also_records_failure(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);c.save_attempt(root,result('2026-11-17T12:00:00Z','new'))
   (root/'last-successful.json').write_text('{bad')
   run=subprocess.run([sys.executable,str(ROOT/'scripts/catalog_diff.py'),'--database',str(ROOT/'data/prices.json'),'--inventory',str(root/'absent.json'),'--state-dir',str(root)],capture_output=True,text=True)
   self.assertEqual(run.returncode,1)
   self.assertEqual(json.loads((root/'latest-attempt.json').read_text())['status'],'error')
   self.assertEqual((root/'last-successful.json').read_text(),'{bad')
 def test_runner_fresh_fetch_parse_diff_failure_and_capture_contract(self):
  manifest={'version':1,'scopes':[dict(vendor='Vendor',channel='native',modalities=['text'],official_hosts=['official.invalid'])]}
  source=dict(id='unfamiliar',vendor='Vendor',channel='native',url='https://official.invalid/catalog',modalities=['text'],role='catalog',adapter='explicit_id_labels_partial')
  config=dict(version=1,adapter_version=runner.ADAPTER_VERSION,scope_manifest_sha256=runner.digest(json.dumps(manifest,sort_keys=True).encode()),sources=[source])
  with tempfile.TemporaryDirectory() as d:
   with mock.patch.object(runner,'fetch_source',return_value=(b'Model Code: `unheard-family-83.2`','2026-11-17T12:00:00Z',{})) as fetch:
    captures=pathlib.Path(d)/'captures';snaps=runner.execute(config,manifest,{'models':[]},captures)
   self.assertEqual(fetch.call_count,1);self.assertTrue((captures/'unfamiliar.body').exists())
   r=c.compare_catalogs({'models':[]},snaps,scopes=manifest)
   self.assertEqual(r['not_in_database'][0]['model_id'],'unheard-family-83.2');self.assertEqual(r['status'],'incomplete')
   with mock.patch.object(runner,'fetch_source',side_effect=TimeoutError('fixture timeout')):
    failed=runner.execute(config,manifest,{'models':[]},pathlib.Path(d)/'failed')
   self.assertEqual(failed[0]['fetch_status'],'failed');self.assertIn('fixture timeout',failed[0]['errors'][0])
 def test_public_cards_keep_history_and_do_not_guess_api_id_from_slug(self):
  parser=runner.OpenAICards();parser.feed('<nav><a href="/api/docs/models/ignore">nav</a></nav><main><a href="/api/docs/models/new-family-99"><img src="/images/api/models/icons/new.webp"><div>Future Family</div></a><details><a href="/api/docs/models/old"><img src="/images/api/models/icons/old.png"><div>Old Display</div></a></details></main>')
  self.assertEqual(len(parser.rows),2);self.assertEqual(parser.rows[1]['catalog_section'],'historical')
  self.assertEqual(parser.rows[0]['display_name'],'Future Family');self.assertIsNone(parser.rows[0]['model_id']);self.assertFalse(parser.rows[0]['api_id_explicit'])
 def test_runner_wrong_scope_version_fails_before_fetch(self):
  with self.assertRaises(ValueError):runner.validate_sources({'version':1,'adapter_version':runner.ADAPTER_VERSION,'scope_manifest_sha256':'wrong'},json.loads(c.DEFAULT_SCOPES.read_text()))

if __name__=='__main__':unittest.main()
