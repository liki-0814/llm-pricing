"""Native literal observations stay partial: no HTTP, credentials or example execution."""
import copy,hashlib,importlib,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import discovery_bridges as b
ROOT='https://platform.claude.com/docs/en/models/overview.md'
STATUS='https://platform.claude.com/docs/en/about-claude/model-deprecations.md'
NOTES='https://platform.claude.com/docs/en/release-notes/overview.md'
DETAIL='https://platform.claude.com/docs/en/models/future/overview.md'
def detail(alias='opaque-alias'):
 return '### Model IDs\n| Platform | Model ID |\n| --- | --- |\n| Claude API | `opaque.Native/9` |\n| Claude API alias | `'+alias+'` |\n| Amazon Bedrock | `foreign-model` |\n### Pricing\n### Capabilities\n| Feature | Value |\n| --- | --- |\n| Input → output | Text and images → text |\n### Availability\n'
def status():
 return '## Model status\n| API model name | Current state | Deprecated | Tentative retirement date |\n| --- | --- | --- | --- |\n| opaque.Native/9 | Active | N/A | To be announced |\n| unknown-preview | Deprecated | June 1, 2026 | To be announced |\n## Deprecation history\nAll deprecations are listed in the following sections.\n### Old models\n<Note>These models were retired June 15, 2026.</Note>\n| Retirement date | Deprecated model | Recommended replacement |\n| --- | --- | --- |\n| June 15, 2026 | `old-native` | `replacement-only` |\n## API parameter deprecations\n'
def root():
 return '## All models\n| Model | Capabilities: Context window | Capabilities: Max output | Base tokens: Input | Base tokens: Output |\n| --- | --- | --- | --- | --- |\n| [Claude Future 9]('+DETAIL.removesuffix('.md')+') | 1M | 1K | $1 | $2 |\n| Claude Old 1 (retired) | 1M | 1K | $1 | $2 |\n## Using the Models API\n'
def notes():
 return '### June 15, 2026\n* We’ve retired the Claude Old 1 model (`old-native`). All requests to these models on the Claude API will now return an error.\n'
def doc(text,url):return dict(text=text,source_url=url,source_sha256=hashlib.sha256(text.encode()).hexdigest(),observed_at='2026-11-18T07:00:00Z',capture_path='/captured/body')
def observe(rt=None,ds=None,st=None,nt=None):
 m=importlib.import_module('discovery_anthropic_contracts')
 return m.observe(doc(root() if rt is None else rt,ROOT),[doc(detail(),DETAIL)] if ds is None else ds,doc(status() if st is None else st,STATUS),doc(notes() if nt is None else nt,NOTES))
class ExistingBoundaries(unittest.TestCase):
 def test_alias_literal_is_not_dropped(self):self.assertEqual(b.anthropic_ids(detail()),['opaque.Native/9','opaque-alias'])
 def test_retired_note_updates_historical_subject(self):
  self.assertEqual(next(r for r in b.anthropic_status(status()) if r['model_id']=='old-native')['lifecycle_status'],'retired')
 def test_replacement_is_not_a_retirement_subject(self):self.assertNotIn('replacement-only',[r['model_id'] for r in b.anthropic_status(status())])
class UnifiedContract(unittest.TestCase):
 def test_union_keeps_unknown_and_provenance_without_complete(self):
  rows,p=observe();by={r['model_id']:r for r in rows if r.get('model_id')}
  self.assertEqual(set(by),{'opaque.Native/9','opaque-alias','old-native','unknown-preview'});self.assertFalse(p['verified']);self.assertTrue(p['structures_verified'])
  self.assertEqual(by['unknown-preview']['unknown_output_modalities'],['text']);self.assertEqual(by['unknown-preview']['lifecycle_status'],'deprecated')
  self.assertEqual(by['opaque-alias']['alias_of'],'opaque.Native/9');self.assertEqual(by['old-native']['lifecycle_status'],'retired');self.assertIsNone(by['old-native']['retired_at'])
  self.assertTrue(all(c['source_sha256'] and c['source_url'] and c['quote'] for r in by.values() for c in r['identity_evidence']['claims']))
 def test_future_alias_added_without_fixed_id_list(self):
  d=detail().replace('| Amazon Bedrock','| Claude API alias | `Future.Unpriced/99` |\n| Amazon Bedrock');rows,p=observe(ds=[doc(d,DETAIL)]);self.assertIn('Future.Unpriced/99',{r.get('model_id') for r in rows});self.assertTrue(p['structures_verified'])
 def test_alias_conflict_is_not_first_wins_and_order_is_invariant(self):
  other=detail().replace('opaque.Native/9','Different.Native/7');docs=[doc(detail(),DETAIL),doc(other,DETAIL.replace('future','other'))]
  a,pa=observe(ds=docs);z,pz=observe(ds=docs[::-1]);self.assertEqual(a,z);self.assertEqual(pa,pz);self.assertFalse(pa['structures_verified']);self.assertTrue(pa['conflicts'])
 def test_joint_sentence_never_guesses_by_id_or_order(self):
  n='Claude Old 1 and Claude Other 2 models retired on the Claude API: `old-native`, `other-native`.'
  rows,p=observe(nt=n);self.assertIn('Claude Old 1',p['pending_display_entities'])
 def test_one_id_for_group_does_not_bind_last_name(self):
  rows,p=observe(nt='the Claude Other 2 and Claude Old 1 model (`old-native`) on the Claude API');self.assertIn('Claude Old 1',p['pending_display_entities'])
 def test_opaque_parenthetical_binding_does_not_use_name_shape(self):
  rows,p=observe();self.assertNotIn('Claude Old 1',p['pending_display_entities'])
 def test_replacement_only_never_becomes_retired(self):
  rows,p=observe();self.assertNotIn('replacement-only',{r.get('model_id') for r in rows})
 def test_missing_history_note_does_not_invent_retired(self):
  rows,p=observe(st=status().replace('<Note>These models were retired June 15, 2026.</Note>',''),nt='');r=next(r for r in rows if r.get('model_id')=='old-native');self.assertNotEqual(r['lifecycle_status'],'retired')
 def test_unknown_identity_table_fails_closed(self):
  for d in [detail().replace('| Platform | Model ID |','| Platform | New ID |'),detail().replace('### Pricing','| Name | Call ID |\n| --- | --- |\n| x | `hidden` |\n### Pricing'),detail().replace('Claude API alias','Claude API nickname')]:
   with self.subTest(d=d):self.assertFalse(observe(ds=[doc(d,DETAIL)])[1]['structures_verified'])
 def test_unknown_status_table_and_missing_termination_fail_closed(self):
  for st in [status().replace('API model name','Display'),status().replace('## API parameter deprecations',''),status().replace('## Deprecation history','| New | ID |\n| --- | --- |\n| x | `hidden` |\n## Deprecation history')]:
   with self.subTest(st=st):self.assertFalse(observe(st=st)[1]['structures_verified'])
 def test_root_unknown_table_and_missing_termination_fail_closed(self):
  for rt in [root().replace('Capabilities: Context window','Unknown'),root().replace('## Using the Models API','')]:self.assertFalse(observe(rt=rt)[1]['structures_verified'])
 def test_missing_detail_termination_fails_closed(self):self.assertFalse(observe(ds=[doc(detail().replace('### Pricing',''),DETAIL)])[1]['structures_verified'])
 def test_cross_page_output_conflict_keeps_unknown(self):
  d=detail().replace('Text and images → text','Text → image');rows,p=observe(ds=[doc(detail(),DETAIL),doc(d,DETAIL.replace('future','other'))]);r=next(r for r in rows if r.get('model_id')=='opaque.Native/9');self.assertEqual(r['unknown_output_modalities'],['text'])
 def test_conflicting_status_never_selects_retired(self):
  rows,p=observe(st=status().replace('| opaque.Native/9 | Active','| old-native | Active'));self.assertFalse(p['structures_verified']);self.assertEqual(next(r for r in rows if r.get('model_id')=='old-native')['lifecycle_status'],'unknown_conflict')
 def test_official_source_identity_required(self):
  m=importlib.import_module('discovery_anthropic_contracts');bad=doc(root(),'https://outside.invalid/models');self.assertFalse(m.observe(bad,[doc(detail(),DETAIL)],doc(status(),STATUS),doc(notes(),NOTES))[1]['structures_verified'])
 def test_retirement_phrase_outside_note_does_not_retire_subject(self):
  st=status().replace('<Note>These models were retired June 15, 2026.</Note>','These models were retired June 15, 2026.');rows,p=observe(st=st,nt='');self.assertNotEqual(next(r for r in rows if r.get('model_id')=='old-native')['lifecycle_status'],'retired')
 def test_release_replacement_is_not_a_retirement_subject(self):
  nt=notes().rstrip()+" We recommend the Claude Replacement 9 model (`replacement-native`).\n";rows,p=observe(nt=nt);self.assertNotIn('replacement-native',{r.get('model_id') for r in rows})
 def test_fenced_release_example_is_not_an_entity_notice(self):
  rows,p=observe(nt='```text\n'+notes()+'```\n');self.assertIn('Claude Old 1',p['pending_display_entities'])
class RunnerCaptureBoundary(unittest.TestCase):
 def execute_fixture(self,missing_release=False,tamper=False):
  import tempfile,json
  from unittest.mock import patch
  import run_discovery as runner
  cfg=json.loads((pathlib.Path(__file__).resolve().parents[1]/'data/discovery-sources.json').read_text());cfg['sources']=[s for s in cfg['sources'] if s['vendor']=='Anthropic']
  manifest=json.loads((pathlib.Path(__file__).resolve().parents[1]/'data/discovery-scopes.json').read_text())
  with tempfile.TemporaryDirectory() as d:
   base=pathlib.Path(d);inp=base/'input';inp.mkdir()
   bodies={'anthropic-models':(ROOT,root()),'anthropic-status':(STATUS,status()),'anthropic-release-notes':(NOTES,notes()),'anthropic-models-detail-'+hashlib.sha256(DETAIL.encode()).hexdigest()[:16]:(DETAIL,detail())}
   for stem,(url,text) in bodies.items():
    if missing_release and stem=='anthropic-release-notes':continue
    (inp/(stem+'.body')).write_text(text)
    (inp/(stem+'.json')).write_text(json.dumps(dict(url=url,sha256='0'*64 if tamper and stem=='anthropic-release-notes' else hashlib.sha256(text.encode()).hexdigest(),http_status=200,capture_kind='http_body',observed_at='2026-11-18T07:00:00Z')))
   with patch.object(runner,'fetch_source',side_effect=AssertionError('replay must never use HTTP')) as fetch:
    inventories=runner.execute(cfg,manifest,{},base/'capture',inp);self.assertEqual(fetch.call_count,0)
   return next(s for s in inventories if s['role']=='catalog')
 def test_same_attempt_replay_wires_literal_alias_and_retired(self):
  snap=self.execute_fixture();self.assertFalse(snap['complete']);self.assertTrue(snap['coverage_evidence']['proof']['structures_verified']);self.assertEqual(len(snap['records']),4)
 def test_missing_release_preserves_pending_without_http_fallback(self):
  snap=self.execute_fixture(missing_release=True);self.assertFalse(snap['complete']);self.assertFalse(snap['coverage_evidence']['proof']['structures_verified']);self.assertTrue(any(r.get('catalog_observation') for r in snap['records']))
 def test_bad_capture_hash_never_becomes_a_binding(self):
  snap=self.execute_fixture(tamper=True);self.assertIn('Claude Old 1',snap['coverage_evidence']['proof']['pending_display_entities'])
 def test_linked_foreign_platform_is_legitimately_excluded(self):
  d=detail().replace('Amazon Bedrock','[Amazon Bedrock](https://platform.claude.com/docs/en/build-with-claude/bedrock)');rows,p=observe(ds=[doc(d,DETAIL)]);self.assertTrue(p['structures_verified']);self.assertNotIn('foreign-model',{r.get('model_id') for r in rows})
 def test_current_status_cannot_be_suppressed_by_missing_detail(self):
  rows,p=observe(ds=[]);self.assertIn('unknown-preview',{r.get('model_id') for r in rows});self.assertIn('Claude Future 9',p['pending_display_entities'])
if __name__=='__main__':unittest.main()
