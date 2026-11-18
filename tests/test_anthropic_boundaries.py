"""Synthetic reviewer counterexamples; never claims of an official source omission."""
import copy,itertools,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import discovery_anthropic_contracts as n
from test_anthropic_observations import doc,detail,root,status,notes,observe,DETAIL,NOTES
NOTICE="* We’ve retired the Claude Injected 9 model (`example-only`). All requests to these models on the Claude API will now return an error."
def release(text):return n.release_claims(doc(text,NOTES))
class FenceBoundary(unittest.TestCase):
 def test_tilde_example_never_adds_retired_subject(self):self.assertEqual(release('~~~markdown\n'+NOTICE+'\n~~~\n'),[])
 def test_long_backtick_cannot_be_closed_by_shorter_run(self):self.assertEqual(release('````markdown\n```\n'+NOTICE+'\n````\n'),[])
 def test_mixed_characters_do_not_close_each_other(self):
  for op,close in [('```','~~~'),('~~~','```'),('`````','~~~~~')]:
   with self.subTest(op=op):self.assertEqual(release(op+'\n'+close+'\n'+NOTICE+'\n'),[])
 def test_pseudo_closers_and_unclosed_tail_remain_code(self):
  for closing in ['``','``` trailing','````python','    ```','\t```','```\v','~~~']:
   with self.subTest(closing=closing):self.assertEqual(release('```markdown\n'+closing+'\n'+NOTICE+'\n'),[])
 def test_valid_closer_equal_or_longer_and_up_to_three_spaces(self):
  for char in ['`','~']:
   for opened,closed in [(3,3),(3,4),(4,6),(8,9)]:
    for indentation in range(4):
     text=' '*indentation+char*opened+'markdown\n'+NOTICE+'\n'+' '*indentation+char*closed+' \t\n'+NOTICE+'\n'
     with self.subTest(char=char,opened=opened,closed=closed,indentation=indentation):self.assertEqual(len(release(text)),1)
 def test_invalid_backtick_info_is_not_an_opener(self):
  for opening in ['```bad`info','``text','    ```','\t```']:
   with self.subTest(opening=opening):self.assertEqual(len(release(opening+'\n'+NOTICE+'\n')),1)
 def test_tilde_info_may_contain_backticks(self):self.assertEqual(release('~~~lang`info\n'+NOTICE+'\n~~~\n'),[])
 def test_unclosed_tail_keeps_earlier_formal_claim_only(self):self.assertEqual(len(release(NOTICE+'\n~~~\n'+NOTICE)),1)
 def test_repeated_quote_after_fence_retains_true_original_line(self):
  text='~~~markdown\n'+NOTICE+'\n~~~\n\n'+NOTICE+'\n'+NOTICE+'\n';claims=release(text);self.assertEqual([c['line'] for c in claims],[5,6]);self.assertTrue(all(c['source_sha256']==doc(text,NOTES)['source_sha256'] for c in claims));self.assertTrue(all(c['quote']==NOTICE for c in claims))
 def test_code_only_heading_cannot_supply_required_termination(self):
  st=status().replace('## API parameter deprecations','~~~markdown\n## API parameter deprecations\n~~~');self.assertFalse(observe(st=st)[1]['structures_verified'])
 def test_code_only_history_note_cannot_retire_subject(self):
  st=status().replace('<Note>These models were retired June 15, 2026.</Note>','~~~markdown\n<Note>These models were retired June 15, 2026.</Note>\n~~~');rows,p=observe(st=st,nt='');self.assertNotEqual(next(r for r in rows if r.get('model_id')=='old-native')['lifecycle_status'],'retired')
 def test_code_identity_table_does_not_supply_alias(self):
  fake='~~~markdown\n| Platform | Model ID |\n| --- | --- |\n| Claude API | `example-native` |\n~~~\n';rows,p=observe(ds=[doc(detail().replace('### Pricing',fake+'### Pricing'),DETAIL)]);self.assertTrue(p['structures_verified']);self.assertNotIn('example-native',{r.get('model_id') for r in rows})
class PredicateBoundary(unittest.TestCase):
 def test_same_sentence_recommendation_never_inherits_retirement(self):
  for connector in [' and recommend ','; we recommend ', ', recommending ', ' in favor of ', ' as a replacement for ']:
   line="* We’ve retired the Claude Old 1 model (`old-native`)"+connector+"the Claude New 9 model (`recommendation-only`) on the Claude API. Requests to the retired model will now return an error."
   with self.subTest(connector=connector):self.assertNotIn('recommendation-only',{c['model_id'] for c in release(line)})
 def test_multiple_explicit_retirement_subjects_still_retained(self):
  line="* We’ve retired the Claude Old 1 model (`old-native`) and the Claude Other 2 model (`another-old`) on the Claude API. Requests will now return an error.";self.assertEqual({c['model_id'] for c in release(line)},{'old-native','another-old'})
 def test_deprecation_subjects_do_not_retire_recommendations(self):
  line="* We announced the deprecation of the Claude Old 1 model (`old-native`) and recommend the Claude New 9 model (`new-only`) on the Claude API.";claims=release(line);self.assertEqual({c['model_id'] for c in claims},{'old-native'});self.assertFalse(any(c.get('lifecycle_status')=='retired' for c in claims))
class ApplicableClaims(unittest.TestCase):
 def ambiguous(self):return detail().replace('| Input → output | Text and images → text |','| Input → output | text → text |\n| Input → output | text → image |')
 def check_unknown(self,docs):
  rows,p=observe(ds=docs);by={r['model_id']:r for r in rows if r.get('model_id')};self.assertIn('text',by['opaque.Native/9']['unknown_output_modalities']);self.assertNotIn('text',by['opaque.Native/9']['output_modalities']);self.assertFalse(p['structures_verified']);return rows,p
 def test_same_page_conflict_then_known_page_cannot_clear_unknown(self):self.check_unknown([doc(self.ambiguous(),DETAIL),doc(detail(),DETAIL.replace('future','other'))])
 def test_all_raw_output_rows_and_locations_survive(self):
  rows,p=self.check_unknown([doc(self.ambiguous(),DETAIL)]);claims=next(r for r in rows if r.get('model_id')=='opaque.Native/9')['identity_evidence']['claims'];outputs=[c for c in claims if c.get('output_modalities') is not None];self.assertEqual(len(outputs),2);self.assertEqual({tuple(c['output_modalities']) for c in outputs},{('text',),('image',)});self.assertEqual(len({c['output_evidence']['line'] for c in outputs}),2)
 def test_source_positions_page_order_and_three_pages_keep_conflict(self):
  urls=[DETAIL,DETAIL.replace('future','other'),DETAIL.replace('future','third')]
  for position in range(3):
   docs=[doc(self.ambiguous() if i==position else detail(),url) for i,url in enumerate(urls)]
   for ordered in itertools.permutations(docs):self.check_unknown(list(ordered))
 def test_swapped_in_page_declarations_do_not_change_decision(self):
  text=self.ambiguous();reverse=text.replace('text → text |\n| Input → output | text → image','text → image |\n| Input → output | text → text')
  for value in [text,reverse]:self.check_unknown([doc(value,DETAIL),doc(detail(),DETAIL.replace('future','other'))])
 def test_same_declarations_positive_control(self):
  duplicated=detail().replace('| Input → output | Text and images → text |','| Input → output | text → text |\n| Input → output | text → text |');rows,p=observe(ds=[doc(duplicated,DETAIL),doc(detail(),DETAIL.replace('future','other'))]);r=next(r for r in rows if r.get('model_id')=='opaque.Native/9');self.assertEqual(r['output_modalities'],['text']);self.assertEqual(r['unknown_output_modalities'],[]);self.assertTrue(p['structures_verified'])
 def test_identical_output_rows_keep_distinct_original_locations(self):
  line='| Input → output | Text and images → text |'
  text=detail().replace(line,line+'\n'+line);claims=n.detail_claims(doc(text,DETAIL));native=[x for x in claims if x['kind']=='canonical'];expected=[i for i,value in enumerate(text.splitlines(),1) if value==line];self.assertEqual([x['output_evidence']['line'] for x in native],expected)
 def test_missing_arrow_remains_unknown_with_known_page(self):
  malformed=detail().replace('Text and images → text','text');self.check_unknown([doc(malformed,DETAIL),doc(detail(),DETAIL.replace('future','other'))])
 def test_crlf_and_cr_preserve_original_source_lines(self):
  for ending in ['\r\n','\r']:
   text=ending.join(['~~~markdown',NOTICE,'~~~',NOTICE]);claims=release(text);self.assertEqual([x['line'] for x in claims],[4]);self.assertEqual(claims[0]['quote'],NOTICE)
 def test_applicable_unknown_declaration_is_not_ignored_by_known_page(self):
  unknown=detail().replace('Text and images → text','text → new-unknown-output');self.check_unknown([doc(unknown,DETAIL),doc(detail(),DETAIL.replace('future','other'))])
class IdentityRole(unittest.TestCase):
 def test_mixed_or_unknown_foreign_prefix_not_silently_ignored(self):
  for role in ['Amazon Bedrock / Claude API alias','Amazon Bedrock new-role','Microsoft Foundry / Claude API','Claude Models on Google Cloud unknown']:
   text=detail().replace('### Pricing','| '+role+' | `mixed-native` |\n### Pricing');rows,p=observe(ds=[doc(text,DETAIL)]);self.assertFalse(p['structures_verified']);raw=p.get('unclassified_identity_observations',[]);self.assertEqual(len(raw),1);self.assertEqual(raw[0]['raw_identifier'],'`mixed-native`');self.assertIsNotNone(raw[0]['line']);self.assertNotIn('mixed-native',{r.get('model_id') for r in rows});self.assertIn('opaque.Native/9',{r.get('model_id') for r in rows});self.assertTrue(any(r.get('catalog_observation') and r.get('identity_evidence',{}).get('kind')=='unclassified_identity_role' for r in rows))
 def test_known_pure_foreign_and_native_alias_controls(self):
  text=detail().replace('### Pricing','| Amazon Bedrock | `foreign-only` |\n### Pricing');rows,p=observe(ds=[doc(text,DETAIL)]);self.assertTrue(p['structures_verified']);self.assertNotIn('foreign-only',{r.get('model_id') for r in rows});self.assertEqual(next(r for r in rows if r.get('model_id')=='opaque-alias')['alias_of'],'opaque.Native/9')
if __name__=='__main__':unittest.main()
