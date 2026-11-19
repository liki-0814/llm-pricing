"""Finite proof grammar units; no real files, captures, network or build fixture."""
import sys,unittest,socket
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import public_price_context as c
A='Grok 4.7 Fast is the same Grok 4.7 model served on faster infrastructure.'
F="Grok Build's free tier does not include it"
class CompleteSubjectUnits(unittest.TestCase):
 def setUp(self):
  g=ExitStack();self.addCleanup(g.close);g.enter_context(patch('builtins.open',side_effect=AssertionError('unit IO')));g.enter_context(patch.object(socket.socket,'connect',side_effect=AssertionError('unit network')))
 def claim(self,text):
  cs,_,_=c.entity_clauses(text,A);return c.entity_claim(text,cs,False,lambda q:F in q)
 def test_unknown_new_subject_verb_family_and_subordination_break_object_chain(self):
  for word in ('requires','needs','demands','prefers','activates','blocks','permits','offers','includes','uses','enforces'):
   for join in ('and','while','whereas','because','although','if','unless'):
    text=A+' It is not available on the public xAI API '+join+' Other Plan '+word+' a separate subscription, and '+F+'.'
    with self.subTest(word=word,join=join):self.assertEqual(self.claim(text)['state'],'unknown')
 def test_objects_and_legal_implicit_same_subject_are_not_split_as_other_entities(self):
  for available in ("It's available only in Cursor and Grok Build",'It is available somewhere in Cursor and Grok Build'):
   text=A+' '+available+', and is billed through your plan there. It is not available on the public xAI API, and '+F+'.'
   cs,_,_=c.entity_clauses(text,A);self.assertFalse(self.claim(text)['value']);self.assertEqual(self.claim(text)['state'],'verified');self.assertTrue(any('Cursor and Grok Build' in x['quote'] and x['unique_subject'] for x in cs))
 def test_unresolved_segment_cannot_be_repaired_by_pronoun_but_named_entity_can_restore(self):
  broken=A+' It is not available on the public xAI API and Other Plan invents an obligation. '
  self.assertEqual(self.claim(broken+'It is billed through your plan there, and '+F+'.')['state'],'unknown')
  self.assertEqual(self.claim(broken+'Grok 4.7 Fast is billed through your plan there, and '+F+'.')['state'],'verified')
 def test_unconsumed_tail_and_multiple_subject_do_not_supply_proof(self):
  for body in ('It and Other Plan are available only in Cursor and Grok Build','It is available only in Cursor and Grok Build whichever Other Plan chooses','It is billed through your plan there with Other Plan demanding more'):
   self.assertEqual(self.claim(A+' '+body+', and '+F+'.')['state'],'unknown')
 def test_unknown_keeps_original_witness_and_explicit_failure_reason(self):
  result=self.claim(A+' Other Plan requires a subscription, and '+F+'.')
  self.assertIsNone(result['value']);self.assertTrue(result['unresolved_witnesses']);self.assertIn('unique-subject',result['unknown_reason'])
if __name__=='__main__':unittest.main()
