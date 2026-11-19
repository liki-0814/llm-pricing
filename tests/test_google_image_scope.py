"""Image is independently gated by explicit Output and complete image attribution."""
import hashlib,json,pathlib,tempfile,unittest
from unittest.mock import patch
from test_discovery_google_contracts import g,SRC,fixture,detail

def bind(docs):
 for doc in docs.values():doc['source_sha256']=hashlib.sha256(doc['text'].encode()).hexdigest()
 return docs
class GoogleImageScope(unittest.TestCase):
 def setUp(self):self.root,self.docs=fixture();self.urls=list(self.docs)
 def prove(self):return g.prove(self.root,SRC,bind(self.docs))
 def image(self):
  rows,p=self.prove();self.assertIn('image',p['modalities']);self.assertTrue(p['scope_decisions']['image']['verified']);return rows,p
 def test_image_proof_uses_explicit_output_not_video_proof(self):
  self.docs[self.urls[0]]['text']=detail('future.Native/9','Image and Text');rows,p=self.image();self.assertEqual(p['modalities'],['text','image','video']);self.assertEqual(p['modality_record_counts']['image'],1);self.assertEqual(p['expected_record_count'],len(rows));self.assertEqual({r['model_id'] for r in rows},{'future.Native/9','future-video'})
 def test_image_can_be_proven_with_zero_video_output_records(self):
  self.docs[self.urls[0]]['text']=detail('future.Native/9','Image and Text');self.docs[self.urls[1]]['text']=detail('future-video','Text');rows,p=self.image();self.assertEqual(p['modalities'],['text','image']);self.assertEqual(p['modality_record_counts']['video'],0);self.assertFalse(p['scope_decisions']['video']['verified'])
 def test_image_input_does_not_prove_image_output(self):
  rows,p=self.prove();self.assertTrue(p['verified']);self.assertEqual(p['modalities'],['text','video']);self.assertEqual(p['modality_record_counts']['image'],0);self.assertFalse(p['scope_decisions']['image']['verified'])
 def test_image_name_and_catalog_placement_are_not_output(self):
  self.root=self.root.replace('future.Native/9','named-image-but-text');self.docs[self.urls[0]]['text']=detail('named-image-but-text','Text');rows,p=self.prove();self.assertNotIn('image',p['modalities']);self.assertFalse(p['scope_decisions']['image']['verified'])
 def test_unlisted_literal_image_version_is_kept(self):
  self.docs[self.urls[0]]['text']=detail('future.Native/9','Image and Text','unlisted-image-version');rows,p=self.image();self.assertEqual(p['modality_record_counts']['image'],2);self.assertEqual(len(rows),3);self.assertIn('unlisted-image-version',{r['model_id'] for r in rows})
 def test_image_output_agent_outside_media_table_is_included(self):
  self.docs[self.urls[0]]['text']+=detail('research-agent','Text (Cited Reports), Images').replace('Model code','Agent code');rows,p=self.image();self.assertEqual(p['modality_record_counts']['image'],1);self.assertIn('research-agent',{r['model_id'] for r in rows})
 def test_unknown_image_alias_blocks_only_image_when_text_certain(self):
  self.docs[self.urls[0]]['text']+=detail('image-parent','Image and Text','ambiguous-image')+detail('text-parent','Text','ambiguous-image');rows,p=self.prove();self.assertTrue(p['verified']);self.assertEqual(p['modalities'],['text','video']);self.assertEqual(p['scope_decisions']['image']['unknown_ids'],['ambiguous-image']);self.assertEqual(next(r for r in rows if r['model_id']=='ambiguous-image')['unknown_output_modalities'],['image'])
 def test_unknown_image_across_sources_and_source_position_swap(self):
  groups=[[('native-img','Image and Text'),('native-audio-one','Audio')],[('native-text','Text'),('native-audio-two','Audio')]]
  for swapped in [False,True]:
   root,docs=fixture()
   for u,group in zip(docs,reversed(groups) if swapped else groups):docs[u]['text']+=''.join(detail(mid,out,'cross-image-alias') for mid,out in group)
   rows,p=g.prove(root,SRC,bind(docs));self.assertNotIn('image',p['modalities']);self.assertEqual(p['scope_decisions']['image']['unknown_ids'],['cross-image-alias']);r=next(r for r in rows if r['model_id']=='cross-image-alias');self.assertIn('image',r['unknown_output_modalities']);self.assertEqual(len(r['identity_evidence']['declarations']),4)
 def test_all_applicable_image_alias_claims_positive(self):
  self.docs[self.urls[0]]['text']+=detail('img-one','Image and Text','shared-image');self.docs[self.urls[1]]['text']+=detail('img-two','Text (Cited Reports), Images','shared-image');rows,p=self.image();r=next(r for r in rows if r['model_id']=='shared-image');self.assertIn('image',r['output_modalities']);self.assertEqual(r['unknown_output_modalities'],[]);self.assertEqual(len(r['identity_evidence']['declarations']),2)
 def test_retired_image_literal_is_preserved_not_priced_or_canonicalized(self):
  self.docs[self.urls[0]]['text']=detail('future.Native/9','Image and Text','retired-image-literal').replace('Preview:','Shut down:');rows,p=self.image();r=next(r for r in rows if r['model_id']=='retired-image-literal');self.assertEqual(r['lifecycle_status'],'retired');self.assertIsNone(r['retired_at']);self.assertFalse(r['price_public'])
 def test_unknown_header_cannot_hide_image_model(self):
  self.docs[self.urls[0]]['text']+=detail('hidden-image','Image and Text').replace('Description','Unreviewed Description');self.assertFalse(self.prove()[1]['verified'])
 def test_unknown_output_grammar_is_not_an_image_hint(self):
  self.docs[self.urls[0]]['text']+=detail('array-output','["Image", "Text"]');self.assertFalse(self.prove()[1]['verified'])
 def test_text_unknown_does_not_suppress_independently_complete_image(self):
  self.docs[self.urls[0]]['text']=detail('future.Native/9','Image and Text')
  versions='Stable: `future-video`\n    Stable: `older-video`\n    Shut down: `retired-video-alias`'
  self.docs[self.urls[1]]['text']=detail('future-video','Video with native Audio, Text').replace('Preview: `future-video`',versions)+detail('older-video','Video').replace('Preview: `older-video`',versions)
  rows,p=self.image();self.assertEqual(p['modalities'],['image','video']);self.assertEqual(p['scope_decisions']['text']['unknown_ids'],['retired-video-alias']);self.assertEqual(p['scope_decisions']['image']['unknown_ids'],[])
 def test_runner_image_gate_keeps_full_observation_count(self):
  import run_discovery as r
  self.docs[self.urls[0]]['text']=detail('future.Native/9','Image and Text','image-version');bind(self.docs);snapshot=r.parse_source(self.root.encode(),SRC,'2026-11-18T06:00:00Z')
  def response(src,hosts):return self.docs[src['url']]['text'].encode(),'2026-11-18T06:00:00Z',{}
  with tempfile.TemporaryDirectory() as folder,patch.object(r,'fetch_source',side_effect=response) as fetch:
   result=r.bridge_catalog(snapshot,SRC,pathlib.Path(folder));self.assertIn('image',result['coverage_evidence']['modalities']);self.assertEqual(result['coverage_evidence']['expected_record_count'],3);self.assertEqual(len(result['records']),3);self.assertEqual(fetch.call_count,2)
 def test_corrupt_replay_image_body_never_recovers_via_network(self):
  import run_discovery as r
  self.docs[self.urls[0]]['text']=detail('future.Native/9','Image and Text');bind(self.docs);snapshot=r.parse_source(self.root.encode(),SRC,'2026-11-18T06:00:00Z')
  with tempfile.TemporaryDirectory() as target,tempfile.TemporaryDirectory() as replay,patch.object(r,'fetch_source') as fetch:
   for url,doc in self.docs.items():
    sid='google-models-detail-'+r.digest(url.encode())[:16];p=pathlib.Path(replay)/sid;p.with_suffix('.body').write_text(doc['text']);p.with_suffix('.json').write_text(json.dumps(dict(url=url,sha256='0'*64,http_status=200,observed_at='2026-11-18T06:00:00Z')))
   result=r.bridge_catalog(snapshot,SRC,pathlib.Path(target),pathlib.Path(replay));self.assertFalse(result['complete']);fetch.assert_not_called()
