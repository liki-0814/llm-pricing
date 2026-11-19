"""Adversarial table-role and cross-document identity contract regressions."""
import copy,hashlib,itertools,unittest
from test_discovery_google_contracts import g,SRC,fixture,detail,table

def bind(docs):
 for doc in docs.values():doc['source_sha256']=hashlib.sha256(doc['text'].encode()).hexdigest()
 return docs

def alias_block(mid,out):return detail(mid,out,'shared-ambiguous-alias')
def ambiguous(groups):
 root,docs=fixture();urls=list(docs)
 for i,outputs in enumerate(groups):
  if i>=len(urls):
   u='https://aistudio.google.com/docs/models/page-three.md';urls.append(u)
   # A direct Versions link makes the third page an indexed captured document.
   docs[u]=dict(text='',source_url=u,observed_at='2026-11-18T06:00:00Z')
   docs[urls[0]]['text']=docs[urls[0]]['text'].replace('Preview: `future.Native/9`','Preview: `future.Native/9`\n    Stable: [third](/docs/models/page-three)',1)
  docs[urls[i]]['text']+=''.join(alias_block('extra-%s-%s'%(i,j),out) for j,out in enumerate(outputs))
 return root,bind(docs)

def guide():return '## Robotics capabilities {% id="capabilities" %}\n'+table([['Spatial reasoning','Reason about space','[Guide](/docs/robotics-spatial)']],('Capability','Description','Guide'))

class TableBoundary(unittest.TestCase):
 def test_unknown_headers_cannot_hide_extra_identity_or_conflict(self):
  for change in [('Property','Attribute'),('Description','Unreviewed Description'),('Property','Version'),('Property','Capability')]:
   for added in [detail('added-id','Video'),detail('future-video','Text')]:
    root,docs=fixture();u=list(docs)[1];docs[u]['text']+=added.replace(*change)
    with self.subTest(change=change,added=added):self.assertFalse(g.prove(root,SRC,bind(docs))[1]['verified'])
 def test_all_consumers_share_unknown_table_boundary(self):
  for head in [('Attribute','Value'),('Property','Unreviewed Description'),('Version','Description')]:
   value=detail('native')+table([['Model code','`hidden-id`'],['Versions','Stable: `hidden-id`']],head)
   for consumer in [g.version_links,g.primary_models,g.detail_models]:
    with self.subTest(head=head,consumer=consumer.__name__),self.assertRaises(ValueError):consumer(value)
 def test_empty_or_unidentified_property_table_is_not_unrelated(self):
  for rows in [[['Foo','bar']],[['Versions','Stable: `hidden-id`']],[['Model code','`hidden-id`']]]:
   with self.subTest(rows=rows),self.assertRaises(ValueError):g.detail_models(detail('native')+table(rows,('Property','Description')))
 def test_unknown_code_free_table_fails_closed(self):
  with self.assertRaises(ValueError):g.detail_models(detail('native')+table([['Hello','World']],('A','B')))
 def test_auxiliary_navigation_requires_context_schema_and_row_evidence(self):
  valid=detail('native')+guide();self.assertIn('native',g.detail_models(valid))
  for invalid in [valid.replace('## Robotics capabilities {% id="capabilities" %}','## Models'),valid.replace('Spatial reasoning','Model code'),valid.replace('Reason about space','`hidden-id`'),valid.replace('/docs/robotics-spatial','/docs/models/hidden-id'),valid.replace('Capability\n','Unknown\n')]:
   with self.subTest(invalid=invalid),self.assertRaises(ValueError):g.detail_models(invalid)
 def test_auxiliary_evidence_is_retained(self):
  root,docs=fixture();docs[next(iter(docs))]['text']+=guide();rows,p=g.prove(root,SRC,bind(docs));self.assertTrue(p['verified']);self.assertTrue(p['detail_table_classifications']);self.assertTrue(any(t['kind']=='guide_navigation' for ts in p['detail_table_classifications'].values() for t in ts))
 def test_known_header_control_keeps_identity(self):
  root,docs=fixture();docs[next(iter(docs))]['text']+=detail('added-unpriced','Video');rows,p=g.prove(root,SRC,bind(docs));self.assertTrue(p['verified']);self.assertIn('added-unpriced',{r['model_id'] for r in rows})
 def test_known_conflict_control_refuses_both_scopes(self):
  root,docs=fixture()
  for u in docs:docs[u]['text']+=detail('future.Native/9','Video')+detail('future-video','Text')
  self.assertFalse(g.prove(root,SRC,bind(docs))[1]['verified'])

class GlobalIdentity(unittest.TestCase):
 def test_same_statement_universe_swapped_between_source_sort_positions(self):
  universe=[[('audio-one','Audio'),('video-one','Video')],[('audio-two','Audio'),('text-two','Text')]]
  results=[];claim_sets=[]
  for swapped in [False,True]:
   root,docs=fixture();groups=list(reversed(universe)) if swapped else universe
   for u,group in zip(docs,groups):docs[u]['text']+=''.join(alias_block(mid,out) for mid,out in group)
   rows,p=g.prove(root,SRC,bind(docs));self.assertFalse(p['verified'])
   a=next(r for r in rows if r['model_id']=='shared-ambiguous-alias');self.assertEqual(a['unknown_output_modalities'],['audio','text','video']);self.assertEqual(len(a['identity_evidence']['declarations']),4)
   results.append({r['model_id']:(r['output_modalities'],r['unknown_output_modalities']) for r in rows})
   claim_sets.append(sorted((x['identity_quote'],tuple(x['output']),x['versions_quote']) for x in a['identity_evidence']['declarations']))
  self.assertEqual(results[0],results[1]);self.assertEqual(claim_sets[0],claim_sets[1])
 def test_different_unknown_sets_cannot_certify_text(self):
  root,docs=ambiguous([['Audio','Video'],['Audio','Text']]);rows,p=g.prove(root,SRC,docs);self.assertFalse(p['verified']);alias=next(r for r in rows if r['model_id']=='shared-ambiguous-alias');self.assertEqual(alias['unknown_output_modalities'],['audio','text','video'])
 def test_page_order_and_three_page_permutations(self):
  for groups in itertools.permutations([['Audio','Video'],['Audio','Text'],['Image and text','Text']]):
   root,docs=ambiguous(groups)
   for supplied in [docs,dict(reversed(list(docs.items())))]:
    with self.subTest(groups=groups):
     rows,p=g.prove(root,SRC,supplied);self.assertFalse(p['verified']);a=next(r for r in rows if r['model_id']=='shared-ambiguous-alias');self.assertEqual(a['unknown_output_modalities'],['audio','image','text','video']);self.assertEqual(len(a['identity_evidence']['declarations']),6)
 def test_same_unknown_sets_preserved_not_falsely_expanded(self):
  root,docs=ambiguous([['Audio','Video'],['Audio','Video']]);rows,p=g.prove(root,SRC,docs);self.assertTrue(p['verified']);self.assertEqual(p['modalities'],['text']);a=next(r for r in rows if r['model_id']=='shared-ambiguous-alias');self.assertEqual(a['unknown_output_modalities'],['audio','video']);self.assertEqual(len(a['identity_evidence']['declarations']),4)
 def test_cross_page_same_certain_output_positive(self):
  root,docs=ambiguous([['Text'],['Text']]);rows,p=g.prove(root,SRC,docs);self.assertTrue(p['verified']);a=next(r for r in rows if r['model_id']=='shared-ambiguous-alias');self.assertEqual(a['output_modalities'],['text']);self.assertEqual(len(a['identity_evidence']['declarations']),2)
 def test_same_page_table_order_does_not_select_first(self):
  for outputs in [['Audio','Video','Text'],['Text','Video','Audio']]:
   root,docs=ambiguous([outputs,['Audio','Text']]);rows,p=g.prove(root,SRC,docs);self.assertFalse(p['verified']);self.assertEqual(next(r for r in rows if r['model_id']=='shared-ambiguous-alias')['unknown_output_modalities'],['audio','text','video'])
 def test_all_provenance_and_global_primary_precedence(self):
  root,docs=ambiguous([['Audio','Video'],['Audio','Text']]);u=list(docs)[1];docs[u]['text']+=detail('shared-ambiguous-alias','Video');rows,p=g.prove(root,SRC,bind(docs));a=next(r for r in rows if r['model_id']=='shared-ambiguous-alias');self.assertEqual(a['output_modalities'],['video']);self.assertEqual(a['unknown_output_modalities'],[]);claims=a['identity_evidence']['declarations'];self.assertEqual(len(claims),5);self.assertEqual({x['source_url'] for x in claims},set(docs));self.assertTrue(all(x['source_sha256']==docs[x['source_url']]['source_sha256'] for x in claims))
