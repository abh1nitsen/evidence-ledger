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

 def test_demo_examples_never_enter_personal_totals(self):
  from docintel.spending import DEMO_TEXT
  demo=attach_document(validate(DEMO_TEXT,baseline(DEMO_TEXT)),DEMO_TEXT);demo['transcript']=DEMO_TEXT
  self.store.register('b'*64,demo);self.ready('b'*64);self.ready()
  r=self.store.spending_summary()
  self.assertEqual(r['totals'],[{'currency':'USD','total':'110.00'}])
  self.assertEqual(r['included_receipts'],1);self.assertEqual(len(r['receipts']),1)
  self.assertEqual(len(r['demo']['receipts']),1);self.assertEqual(r['demo']['included_receipts'],1)
 def test_non_demo_pasted_text_remains_real(self):
  self.ready();r=self.store.spending_summary()
  self.assertEqual(r['included_receipts'],1);self.assertEqual(r['demo']['receipts'],[])
 def test_receipt_status_and_review_target_follow_missing_step(self):
  r=self.store.spending_summary()['receipts'][0]
  self.assertEqual(r['status'],'needs_review');self.assertEqual(r['field'],'total');self.assertFalse(r['amount_confirmed'])
  self.store.decide('a'*64,'total','accept',None,0)
  self.assertEqual(self.store.spending_summary()['receipts'][0]['field'],'currency')
  self.store.decide('a'*64,'currency','accept',None,1)
  self.assertEqual(self.store.spending_summary()['receipts'][0]['target'],'grouping')
  self.store.group('a'*64,'Shopping',[],2)
  r=self.store.spending_summary()['receipts'][0]
  self.assertEqual(r['status'],'included');self.assertFalse(r['date_confirmed']);self.assertTrue(r['amount_confirmed'])
 def test_unique_receipt_counts_hide_old_extraction_versions(self):
  first=self.store.get('a'*64);second=copy.deepcopy(first);second['review']['document_id']='b'*64
  r=summarize([first,second]);self.assertEqual(len(r['receipts']),1);self.assertEqual(r['needs_review'],1)
 def test_different_photo_duplicate_is_separate_from_main_receipts(self):
  first=self.ready();second=copy.deepcopy(first);second['source_sha256']='other-photo';second['review']['document_id']='b'*64
  r=summarize([first,second]);self.assertEqual(r['included_receipts'],1)
  self.assertEqual([x['status'] for x in r['receipts']],['included','possible_duplicate'])
  self.assertEqual(r['receipts'][1]['duplicate_of'],'a'*64)
 def test_combined_receipt_hides_page_and_other_order_versions(self):
  from test_pages import page
  a,b=page('one'),page('two');self.store.register('b'*64,a);self.store.register('c'*64,b)
  first=self.store.chain(['b'*64,'c'*64]);second=self.store.chain(['c'*64,'b'*64])
  r=summarize([first,second,self.store.get('b'*64),self.store.get('c'*64)])
  self.assertEqual(len(r['receipts']),1);self.assertEqual(r['receipts'][0]['page_count'],2)
  self.assertEqual(r['needs_review'],1);self.assertEqual(r['excluded']['page_in_receipt_chain'],2)
 def test_arithmetic_mismatch_has_clear_status(self):
  self.ready();self.store.decide('a'*64,'tax','edit','12.00',3)
  r=self.store.spending_summary()['receipts'][0]
  self.assertEqual(r['status'],'amount_mismatch');self.assertEqual(self.store.spending_summary()['totals'],[])
