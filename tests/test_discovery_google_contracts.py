import copy,hashlib,html,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import discovery_google_contracts as g
SRC=dict(id='google-models',vendor='Google Gemini',channel='pay_as_you_go',url='https://aistudio.google.com/docs/models',modalities=['text','image','video'],role='catalog',adapter='google_endpoint_tables')
def table(rows,header=('Model','Description','Endpoint')):
 return '{% table variant="model" %}\n'+''.join('  * '+x+'\n' for x in header)+''.join('\n  ---\n\n'+''.join('  * '+c+'\n' for c in row) for row in rows)+'{% /table %}\n'
def detail(mid,output='Text',versions=None):
 rows=[['Model code','`'+mid+'`'],['Supported data types','**Input** Text, Image, Video\n    **Output** '+output],['Versions','Preview: `'+(versions or mid)+'`']]
 return '# Native model\n'+table(rows,('Property','Description'))
def fixture():
 root='# Models\n## Gemini 9\n## All Gemini 9 models\n'+table([['[Display](/docs/models/not-an-id)','A model','`future.Native/9`']]);docs={'https://aistudio.google.com/docs/models/not-an-id.md':detail('future.Native/9')}
 for section in ['Audio models','Generative media models','Music generation models','Tool and agent models','Specialized task models','Previous models']:
  mid='future-video' if section=='Generative media models' else 'future.Native/9';link='/docs/models/video' if section=='Generative media models' else '/docs/models/not-an-id';root+='## '+section+'\n'+table([['[Display]('+link+')','A native model','`'+mid+'`']])
 docs['https://aistudio.google.com/docs/models/video.md']=detail('future-video','Video')
 root+='## Model version name patterns\nFor example: `example-only`.\n## Model deprecations\nFor information about model deprecations, visit the [Gemini\ndeprecations](/docs/deprecations) page.\n'
 return root,{u:dict(text=t,source_url=u,source_sha256=hashlib.sha256(t.encode()).hexdigest(),observed_at='2026-11-18T06:00:00Z') for u,t in docs.items()}
class GoogleContracts(unittest.TestCase):
 def setUp(self):self.root,self.docs=fixture();self.url=next(iter(self.docs));self.assertTrue(self.proof()[1]['verified'])
 def proof(self,root=None,docs=None,src=None):return g.prove(self.root if root is None else root,SRC if src is None else src,self.docs if docs is None else docs)
 def no(self,**kw):self.assertFalse(self.proof(**kw)[1]['verified'])
 def change(self,a,b):d=copy.deepcopy(self.docs);d[self.url]['text']=d[self.url]['text'].replace(a,b);self.no(docs=d)
 def test_positive_dynamic_counts(self):rows,p=self.proof();self.assertEqual(p['expected_record_count'],len(rows));self.assertEqual(p['modalities'],['text','video']);self.assertFalse(any(x['price_public'] for x in rows))
 def test_plain_markdown_balanced_table_eof_legal(self):self.assertIn('future.Native/9',g.detail_models(detail('future.Native/9')))
 def test_wrapped_html(self):root='<html><body><noscript><pre>'+html.escape(self.root)+'</pre></noscript></body></html>';self.assertTrue(self.proof(root=root)[1]['verified'])
 def test_root_wrong_type(self):self.no(root=[])
 def test_docs_wrong_type(self):self.no(docs=[])
 def test_native_channel_bound(self):s=dict(SRC,channel='subscription');self.no(src=s)
 def test_foreign_source(self):s=dict(SRC,url='https://foreign.test/docs/models');self.no(src=s)
 def test_new_id_no_whitelist(self):root=self.root.replace('future.Native/9','new.Unpriced/2099');d=copy.deepcopy(self.docs);d[self.url]['text']=d[self.url]['text'].replace('future.Native/9','new.Unpriced/2099');rows,p=self.proof(root=root,docs=d);self.assertTrue(p['verified']);self.assertIn('new.Unpriced/2099',{r['model_id'] for r in rows})
 def test_slug_not_identity(self):self.assertNotIn('not-an-id',{r['model_id'] for r in self.proof()[0]})
 def test_endpoint_continuations_all_kept(self):root=self.root.replace('`future-video`','`future-video`\n    `second-video`');d=copy.deepcopy(self.docs);d['https://aistudio.google.com/docs/models/video.md']['text']=detail('future-video','Video','second-video');rows,p=self.proof(root=root,docs=d);self.assertTrue(p['verified']);self.assertIn('second-video',{r['model_id'] for r in rows})
 def test_new_variant_kept_not_merged(self):d=copy.deepcopy(self.docs);d[self.url]['text']=detail('future.Native/9','Text','unpriced-variant');rows,p=self.proof(docs=d);self.assertTrue(p['verified']);self.assertIn('unpriced-variant',{r['model_id'] for r in rows})
 def test_label_inside_code_cannot_make_new_id(self):self.change('Preview: `future.Native/9`','`Preview: invented-id`')
 def test_label_inside_code_confirms_literal_only(self):d=copy.deepcopy(self.docs);d[self.url]['text']=detail('future.Native/9').replace('Preview: `future.Native/9`','`Preview: future.Native/9`');self.assertTrue(self.proof(docs=d)[1]['verified'])
 def test_unknown_model_header(self):self.no(root=self.root.replace('Endpoint','SKU'))
 def test_truncated_table(self):self.no(root=self.root.replace('{% /table %}','',1))
 def test_truncated_terminal(self):self.no(root=self.root.split('For information about model deprecations')[0])
 def test_extra_after_terminal(self):self.no(root=self.root+'`hidden-new-id`')
 def test_unknown_section(self):self.no(root=self.root.replace('## Previous models','## Unclassified future models'))
 def test_unknown_conditional(self):self.no(root='{% if hidden %}'+self.root+'{% /if %}')
 def test_foreign_detail(self):self.no(root=self.root.replace('/docs/models/not-an-id','https://foreign.test/model'))
 def test_query_detail(self):self.no(root=self.root.replace('/docs/models/not-an-id','/docs/models/not-an-id?page=2'))
 def test_missing_detail(self):d=copy.deepcopy(self.docs);d.pop(self.url);self.no(docs=d)
 def test_detail_wrong_type(self):d=copy.deepcopy(self.docs);d[self.url]['text']={};self.no(docs=d)
 def test_detail_source_mismatch(self):d=copy.deepcopy(self.docs);d[self.url]['source_url']='https://foreign.test/model';self.no(docs=d)
 def test_literal_endpoint_not_description(self):self.no(root=self.root.replace('`future.Native/9`','Some Display Name'))
 def test_invalid_endpoint(self):self.no(root=self.root.replace('`future-video`','`not an id`'))
 def test_unknown_output(self):self.change('**Output** Text','**Output** Hologram')
 def test_input_video_not_output(self):rows,p=self.proof();self.assertEqual(p['modality_record_counts']['video'],1)
 def test_missing_output(self):self.change('**Output** Text','No output declaration')
 def test_duplicate_output(self):self.change('**Output** Text','**Output** Text **Output** Video')
 def test_output_array_not_coerced(self):self.change('**Output** Text','**Output** ["Text"]')
 def test_model_id_mismatch(self):self.change('`future.Native/9`','`different-id`')
 def test_unknown_property(self):self.change('Versions','Unreviewed invocation IDs')
 def test_unknown_detail_template(self):d=copy.deepcopy(self.docs);d[self.url]['text']='{% if hidden %}'+d[self.url]['text']+'{% /if %}';self.no(docs=d)
 def test_detail_eof_truncation(self):self.change('{% /table %}','')
 def test_duplicate_endpoint_id_in_cell(self):self.no(root=self.root.replace('`future-video`','`future-video` `future-video`'))
 def test_pagination(self):self.no(root=self.root.replace('## Model deprecations','[Next page](?page=2)\n## Model deprecations'))
 def test_deprecated_not_retired(self):root=self.root.replace('A native model','Deprecated');rows,p=self.proof(root=root);self.assertTrue(p['verified']);self.assertFalse(any(r.get('lifecycle_status')=='retired' for r in rows))
 def test_primary_code_wins_and_ambiguous_retired_family_alias_blocks_only_text(self):
  d=copy.deepcopy(self.docs);u='https://aistudio.google.com/docs/models/video.md'
  versions='Stable: `future-video`\n    Stable: `older-video`\n    Shut down: `legacy-video-alias`'
  one=detail('future-video','Video with native Audio, Text').replace('Preview: `future-video`',versions)
  two=detail('older-video','Video').replace('Preview: `older-video`',versions)
  d[u]['text']=one+'\n'+two;rows,p=self.proof(docs=d);self.assertTrue(p['verified']);self.assertEqual(p['modalities'],['video']);self.assertEqual(p['scope_decisions']['text']['unknown_ids'],['legacy-video-alias'])
  by={r['model_id']:r for r in rows};self.assertNotIn('text',by['older-video']['output_modalities']);self.assertEqual(by['legacy-video-alias']['lifecycle_status'],'retired');self.assertIsNone(by['legacy-video-alias']['retired_at'])
 def test_route_is_not_retirement_or_alias_canonicalization(self):
  d=copy.deepcopy(self.docs);d[self.url]['text']=detail('future.Native/9').replace('Preview: `future.Native/9`','Deprecated: `future.Native/9` (effective December 1, 2026, automatically routed to `target-id`)');rows,p=self.proof(docs=d);self.assertTrue(p['verified']);self.assertNotIn('target-id',{r['model_id'] for r in rows});self.assertFalse(any(r.get('lifecycle_status')=='retired' for r in rows))
 def test_foreign_versions_reference_rejected(self):self.change('Preview: `future.Native/9`','Preview: [`future.Native/9`](https://foreign.test/model)')
 def test_plain_version_link_requires_independent_code_capture(self):self.change('Preview: `future.Native/9`','Shut down: [Display name](/docs/models/legacy-native)')
 def test_bare_versions_literal_with_transport_qualifier(self):
  d=copy.deepcopy(self.docs);d[self.url]['text']=detail('future.Native/9').replace('Preview: `future.Native/9`','* `future.Native/9` (Live API)');self.assertTrue(self.proof(docs=d)[1]['verified'])
 def test_unknown_version_qualifier_rejected(self):self.change('Preview: `future.Native/9`','Preview: `future.Native/9` and also `silently-missed-id`')
 def test_runner_missing_replay_never_fetches(self):
  import run_discovery as r,tempfile
  from unittest.mock import patch
  snapshot=r.parse_source(self.root.encode(),SRC,'2026-11-18T06:00:00Z')
  with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b,patch.object(r,'fetch_source') as fetch:
   out=r.bridge_catalog(snapshot,SRC,pathlib.Path(a),pathlib.Path(b));self.assertFalse(out['complete']);fetch.assert_not_called()
 def test_runner_uses_bounded_native_child_capture_and_proves_requested_scopes(self):
  import run_discovery as r,tempfile
  from unittest.mock import patch
  snapshot=r.parse_source(self.root.encode(),SRC,'2026-11-18T06:00:00Z')
  def response(src,hosts):return self.docs[src['url']]['text'].encode(),'2026-11-18T06:00:01Z',{}
  with tempfile.TemporaryDirectory() as a,patch.object(r,'fetch_source',side_effect=response) as fetch:
   out=r.bridge_catalog(snapshot,SRC,pathlib.Path(a));self.assertTrue(out['complete']);self.assertEqual(fetch.call_count,len(self.docs));self.assertEqual(out['coverage_evidence']['modalities'],['text','video']);self.assertEqual(len(list(pathlib.Path(a).glob('*.body'))),len(self.docs))
 def test_runner_rejects_corrupt_replay_provenance_without_http(self):
  import run_discovery as r,tempfile,json
  from unittest.mock import patch
  snapshot=r.parse_source(self.root.encode(),SRC,'2026-11-18T06:00:00Z')
  with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b,patch.object(r,'fetch_source') as fetch:
   for u,doc in self.docs.items():
    sid='google-models-detail-'+r.digest(u.encode())[:16];base=pathlib.Path(b)/sid;base.with_suffix('.body').write_text(doc['text']);base.with_suffix('.json').write_text(json.dumps(dict(url=u,sha256='0'*64,http_status=200,observed_at='2026-11-18T06:00:00Z')))
   self.assertFalse(r.bridge_catalog(snapshot,SRC,pathlib.Path(a),pathlib.Path(b))['complete']);fetch.assert_not_called()
 def test_plain_unknown_versions_row_is_not_silently_omitted(self):self.change('Preview: `future.Native/9`','Preview: untyped-display-name')
if __name__=='__main__':unittest.main()
