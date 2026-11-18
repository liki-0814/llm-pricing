"""Synthetic error-path observations: not evidence of official missing models."""
import itertools,unittest,json,hashlib,pathlib,tempfile
from unittest.mock import patch
from test_anthropic_observations import doc,detail,observe,DETAIL

def replace_ids(rows):
 tail=detail().split('### Pricing',1)[1]
 return '### Model IDs\n| Platform | Model ID |\n| --- | --- |\n'+''.join('| '+role+' | '+value+' |\n' for role,value in rows)+'### Pricing'+tail
UNKNOWN=('Amazon Bedrock / Claude API alias','`mixed-only`')
class PartialIdentityEvidence(unittest.TestCase):
 def check(self,text,expected,docs=None):
  rows,p=observe(ds=docs if docs is not None else [doc(text,DETAIL)]);self.assertFalse(p['structures_verified']);raw=[r for r in rows if r.get('raw_identifier') in expected];self.assertEqual(sorted(r['raw_identifier'] for r in raw),sorted(expected))
  for row in raw:
   self.assertIsNone(row['model_id']);self.assertFalse(row['api_id_explicit']);self.assertTrue(row['catalog_observation']);claim=row['identity_evidence']['claims'][0];self.assertIn(claim['raw_identifier'],claim['quote']);self.assertIsNotNone(claim['line']);origin=next(d for d in (docs or [doc(text,DETAIL)]) if d['source_url']==claim['source_url']);self.assertEqual(origin['source_sha256'],claim['source_sha256']);self.assertEqual(origin['text'].splitlines()[claim['line']-1],claim['quote'])
  return rows,p
 def test_no_canonical_original_atlas_case(self):self.check(replace_ids([UNKNOWN]),['`mixed-only`'])
 def test_multiple_unknown_rows_and_identical_quotes(self):
  text=replace_ids([UNKNOWN,('Unknown platform','unquoted candidate'),UNKNOWN]);rows,p=self.check(text,['`mixed-only`','unquoted candidate','`mixed-only`']);claims=[r['identity_evidence']['claims'][0] for r in rows if r.get('raw_identifier')=='`mixed-only`'];self.assertEqual(len({x['line'] for x in claims}),2)
 def test_invalid_canonical_and_alias_before_or_after_unknown(self):
  for bad in [('Claude API','not-backticked'),('Claude API','``'),('Claude API alias','not-backticked'),('Claude API alias','`bad space`')]:
   for order in [[bad,UNKNOWN],[UNKNOWN,bad]]:
    with self.subTest(bad=bad,order=order):self.check(replace_ids(order),['`mixed-only`',bad[1]])
 def test_multiple_canonical_candidates_not_promoted(self):
  text=replace_ids([('Claude API','`candidate-a`'),UNKNOWN,('Claude API','`candidate-b`'),('Claude API alias','`alias-x`')]);rows,p=self.check(text,['`candidate-a`','`mixed-only`','`candidate-b`','`alias-x`']);self.assertFalse({'candidate-a','candidate-b','alias-x'}&{r.get('model_id') for r in rows})
 def test_mixed_good_bad_tables_and_row_width(self):
  for extra in ['| Other | Schema |\n| --- | --- |\n| x | y |\n','| broken | too | wide |\n']:
   text=replace_ids([UNKNOWN]).replace('### Pricing',extra+'### Pricing');self.check(text,['`mixed-only`'])
 def test_two_recognized_identity_tables_remain_unverified_and_lossless(self):
  text=replace_ids([UNKNOWN]).replace('### Pricing','\n| Platform | Model ID |\n| --- | --- |\n| Claude API | `second-table-candidate` |\n### Pricing');rows,p=self.check(text,['`mixed-only`','`second-table-candidate`']);self.assertNotIn('second-table-candidate',{r.get('model_id') for r in rows})
 def test_bad_separator_does_not_erase_classifiable_row(self):
  text=replace_ids([UNKNOWN]).replace('| --- | --- |','| not-a-separator | --- |');self.check(text,['`mixed-only`'])
 def test_later_capability_error_keeps_identity_observations(self):
  text=replace_ids([('Claude API','`known-native`'),UNKNOWN]).replace('### Availability','### Unrecognized availability');self.check(text,['`known-native`','`mixed-only`'])
 def test_multiple_pages_source_swaps_and_input_order(self):
  urls=[DETAIL,DETAIL.replace('future','other'),DETAIL.replace('future','third')]
  for position in range(3):
   docs=[doc(replace_ids([UNKNOWN]) if i==position else detail(),url) for i,url in enumerate(urls)]
   for ordered in itertools.permutations(docs):
    rows,p=self.check('', ['`mixed-only`'],list(ordered));self.assertIn('opaque.Native/9',{r.get('model_id') for r in rows})
 def test_actual_runner_keeps_unknown_only_child_capture_and_rows(self):
  import run_discovery as runner
  from test_anthropic_observations import root,status,notes,ROOT,STATUS,NOTES
  base=pathlib.Path(__file__).resolve().parents[1];config=json.loads((base/'data/discovery-sources.json').read_text());config['sources']=[x for x in config['sources'] if x['vendor']=='Anthropic'];manifest=json.loads((base/'data/discovery-scopes.json').read_text())
  with tempfile.TemporaryDirectory() as tmp:
   tmp=pathlib.Path(tmp);inp=tmp/'input';inp.mkdir();text=replace_ids([UNKNOWN]);bodies=[('anthropic-models',ROOT,root()),('anthropic-status',STATUS,status()),('anthropic-release-notes',NOTES,notes()),('anthropic-models-detail-'+hashlib.sha256(DETAIL.encode()).hexdigest()[:16],DETAIL,text)]
   for stem,url,value in bodies:
    body=value.encode();(inp/(stem+'.body')).write_bytes(body);(inp/(stem+'.json')).write_text(json.dumps(dict(url=url,sha256=hashlib.sha256(body).hexdigest(),http_status=200,capture_kind='http_body',observed_at='2026-11-18T07:00:00Z')))
   with patch.object(runner,'fetch_source',side_effect=AssertionError('no HTTP')) as net:snapshots=runner.execute(config,manifest,{},tmp/'capture',inp);net.assert_not_called()
   snap=next(x for x in snapshots if x['role']=='catalog');raw=[r for r in snap['records'] if r.get('raw_identifier')=='`mixed-only`'];self.assertEqual(len(raw),1);self.assertIsNone(raw[0]['model_id']);self.assertFalse(snap['coverage_evidence']['proof']['structures_verified']);self.assertFalse(snap['complete']);claim=raw[0]['identity_evidence']['claims'][0];body=pathlib.Path(claim['capture_path']).read_bytes();self.assertEqual(hashlib.sha256(body).hexdigest(),claim['source_sha256']);self.assertEqual(body.decode().splitlines()[claim['line']-1],claim['quote'])
 def test_fenced_unknown_rows_do_not_become_observations(self):
  text=detail().replace('### Pricing','~~~markdown\n| Unknown platform | `example-only` |\n~~~\n### Pricing');rows,p=observe(ds=[doc(text,DETAIL)]);self.assertTrue(p['structures_verified']);self.assertFalse(any(r.get('raw_identifier')=='`example-only`' for r in rows))
if __name__=='__main__':unittest.main()
