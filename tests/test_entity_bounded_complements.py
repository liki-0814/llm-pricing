"""Bounded proposition/unknown-tail contract. Pure functions, no fixture I/O."""
import sys,socket,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import public_price_context as c
A='Grok 4.7 Fast is the same Grok 4.7 model served on faster infrastructure.'
F="Grok Build's free tier does not include it"
class BoundedComplements(unittest.TestCase):
 def setUp(self):
  g=patch.object(socket.socket,'connect',side_effect=AssertionError('unit network'));g.start();self.addCleanup(g.stop)
 def parse(self,body):
  text=A+' '+body;return text,c.entity_clauses(text,A)[0]
 def claim(self,body,key='free_build_tier_included',value=False,predicate=None):
  text,clauses=self.parse(body);return c.entity_claim(text,clauses,value,predicate or (lambda q:F in q),property_name=key)
 def test_all_subject_entry_points_reject_arbitrary_suffix_not_case_or_verb_list(self):
  entries=('It is ','It was ','It remains ',"It's ",'It’s ','Grok 4.7 Fast is ','Token rates below are ')
  tails=('with other plan demanding more','with another plan requiring more','with Other Plan demanding more','for a separate service','beside an unrelated account','alpha beta gamma','via another account')
  for entry in entries:
   for tail in tails:
    with self.subTest(entry=entry,tail=tail):self.assertEqual(self.claim(entry+'billed through your plan there '+tail+', and '+F+'.')['state'],'unknown')
  self.assertEqual(self.claim('It is available only in Cursor and Grok Build, and is billed through your plan there alpha beta, and '+F+'.')['state'],'unknown')
 def test_all_complement_lengths_remain_unknown_instead_of_eleven_word_cutoff(self):
  for size in (1,2,5,11,12,25):
   with self.subTest(size=size):self.assertEqual(self.claim('It is billed through your plan there '+' '.join(['anonymous']*size)+', and '+F+'.')['state'],'unknown')
 def test_generic_np_modifiers_cannot_supply_semantic_completeness(self):
  for obj in ('the other plan offering the API','your anonymous subscription','the rival API','a plan requiring another tier'):
   with self.subTest(obj=obj):self.assertEqual(self.claim('It is available in '+obj+', and '+F+'.')['state'],'unknown')
 def test_unknown_remainder_and_blocker_have_exact_original_positions(self):
  tail='with another plan requiring more';text,clauses=self.parse('It is billed through your plan there '+tail+', and '+F+'.')
  bad=next(x for x in clauses if x['relation']=='unresolved');lo,hi=bad['unconsumed_span'];self.assertEqual(text[lo:hi],tail);self.assertEqual(bad['unconsumed_quote'],tail);self.assertFalse(bad['complete_consumption'])
  later=next(x for x in clauses if x['relation']=='unique_object_it');self.assertTrue(later['complete_consumption']);self.assertFalse(later['unique_subject']);self.assertEqual(later['unresolved_antecedent']['unconsumed_span'],[lo,hi]);self.assertNotIn('billing_channel',bad['proved_properties'])
 def test_known_source_objects_and_neutral_controls_preserve_independent_claims(self):
  for body in ("It's available only in Cursor and Grok Build, and is billed through your plan there. ",'It is available somewhere in Cursor and Grok Build, and is billed another way there. ','It is available on a separately described API. '):
   with self.subTest(body=body):self.assertEqual(self.claim(body+F+'.')['state'],'verified')
 def test_explicit_named_recovery_only_not_a_later_pronoun(self):
  broken='It is billed through your plan there unknown suffix. '
  self.assertEqual(self.claim(broken+'It is billed through your plan there, and '+F+'.')['state'],'unknown')
  self.assertEqual(self.claim(broken+'Grok 4.7 Fast is billed through your plan there, and '+F+'.')['state'],'verified')
 def test_negated_billing_cannot_pass_positive_substring_property(self):
  for body in ('It is not billed through your plan there.',"It's not billed through your plan there."):
   self.assertEqual(self.claim(body,'billing_channel','subscription',lambda q:'billed through your plan there' in q)['state'],'unknown')
  self.assertEqual(self.claim('It is billed through your plan there.','billing_channel','subscription',lambda q:'billed through your plan there' in q)['state'],'verified')
 def test_extra_object_or_negation_cannot_verify_positive_available_substring(self):
  for body in ('It is not available only in Cursor and Grok Build.','It is available only in Cursor and Grok Build and the public xAI API.'):
   self.assertEqual(self.claim(body,'available_in',['Cursor','Grok Build'],lambda q:'available only in Cursor and Grok Build' in q)['state'],'unknown')
 def test_cost_and_legal_object_coordination_still_keep_subject(self):
  body="It's available only in Cursor and Grok Build. It costs 2x the standard token rates, or 4x for long-context requests, and "+F+'.'
  self.assertEqual(self.claim(body)['state'],'verified')
if __name__=='__main__':unittest.main()
