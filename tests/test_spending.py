import copy
from pathlib import Path
import tempfile
import unittest
from docintel.core import baseline, validate
from docintel.documents import attach_document
from docintel.reviews import ReviewStore, ReviewConflict
from docintel.spending import suggest_category, summarize
from test_core import TEXT

class SpendingTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'reviews.sqlite';self.store=ReviewStore(self.path)
  self.doc=attach_document(validate(TEXT,baseline(TEXT)),TEXT);self.doc['transcript']=TEXT
  self.store.register('a'*64,self.doc)
 def tearDown(self):self.temp.cleanup()
 def ready(self,identity='a'*64,revision=0):
  self.store.decide(identity,'total','accept',None,revision)
  self.store.decide(identity,'currency','accept',None,revision+1)
  return self.store.group(identity,'Office & business',['Work','work'],revision+2)
 def test_group_audit_restores_without_changing_machine_fields(self):
  r=self.store.group('a'*64,'Shopping',['Household'],0)
  restored=ReviewStore(self.path).get('a'*64)
  self.assertEqual(restored['spending']['category'],'Shopping')
  self.assertEqual(restored['spending']['tags'],['household'])
  self.assertEqual(restored['fields'],self.doc['fields'])
  self.assertEqual(restored['review']['revision'],1)
  with self.assertRaises(ReviewConflict):self.store.decide('a'*64,'total','accept',None,0)
  with self.assertRaises(ReviewConflict):self.store.group('a'*64,'Dining',[],0)
 def test_invalid_groups_do_not_commit(self):
  for category,tags in [('Fake',[]),('Dining',['x'*31]),('Dining',['x']*9),('Dining',['bad\x00tag'])]:
   with self.assertRaises(ValueError):self.store.group('a'*64,category,tags,0)
  self.assertEqual(self.store.get('a'*64)['review']['revision'],0)
 def test_machine_values_alone_are_excluded(self):
  self.store.group('a'*64,'Shopping',[],0)
  self.assertEqual(self.store.spending_summary()['included_receipts'],0)
 def test_reviewed_amounts_separate_currencies_and_date_review(self):
  r=self.ready();self.assertEqual(r['spending']['tags'],['work'])
  text=TEXT.replace('USD','EUR').replace('A-1','B-1')
  self.store.register('b'*64,attach_document(validate(text,baseline(text)),text));self.ready('b'*64)
  groups=self.store.spending_summary()['groups']
  self.assertEqual({g['currency'] for g in groups},{'USD','EUR'})
  self.assertEqual({g['total'] for g in groups},{'110.00'})
  self.assertEqual({g['month'] for g in groups},{'Date not reviewed'})
  self.store.decide('a'*64,'invoice_date','accept',None,3)
  self.assertNotEqual(self.store.spending_summary()['groups'][-1]['month'],'Date not reviewed')
 def test_rejected_total_and_arithmetic_mismatch_excluded(self):
  self.ready();self.store.decide('a'*64,'tax','edit','12.00',3)
  self.assertEqual(self.store.spending_summary()['excluded']['amounts_do_not_add_up'],1)
  self.store.decide('a'*64,'total','reject',None,4)
  self.assertEqual(self.store.spending_summary()['included_receipts'],0)
 def test_reprocessed_source_and_same_bill_deduplicate(self):
  first=self.ready();second=copy.deepcopy(first);second['review']['document_id']='b'*64
  self.assertEqual(summarize([first,second])['included_receipts'],1)
  second['source_sha256']='different-photo'
  self.assertEqual(summarize([first,second])['excluded']['possible_duplicate_bill'],1)
 def test_keyword_suggestion_requires_confirmation_and_abstains_on_mixed(self):
  self.assertEqual(suggest_category({'transcript':'Cafe lunch'})['category'],'Dining')
  self.assertTrue(suggest_category({'transcript':'Cafe lunch'})['needs_confirmation'])
  self.assertEqual(suggest_category({'transcript':'Cafe and supermarket'})['category'],'Unclassified')
