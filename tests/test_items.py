import copy
from pathlib import Path
import tempfile
import unittest
from docintel.core import baseline,validate
from docintel.documents import attach_document
from docintel.items import validate_items,reconcile,money
from docintel.reviews import ReviewStore,ReviewConflict
from docintel.spending import summarize

TEXT="""Vendor: Bluebird Market
Invoice ID: TEST-81
Invoice Date: 2026-09-21
Currency: SGD
Subtotal: 10.00
Tax: 0.90
Total: 10.90
PENCIL SET 1 4.00
CAKE BAR 2 8.00
PROMO -2.00
GST 0.90
PAYMENT 10.90
"""
def line(description,amount,kind='product',category='Office / stationery',target=None):
 return dict(description=description,label=description,code=None,quantity=None,unit_price=None,amount=amount,quote=description+' '+amount,amount_quote=amount,kind=kind,category=category,discount_for=target)
def document(lines=None,text=TEXT):
 d=attach_document(validate(text,baseline(text)),text);d['transcript']=text
 d['items']=validate_items(lines or [line('PENCIL SET 1','4.00'),line('CAKE BAR 2','8.00',category='Food / cakes & pastries'),line('PROMO','-2.00','discount','Unallocated',1),line('GST','0.90','tax','Taxes'),line('PAYMENT','10.90','payment','Unallocated')],text)
 return d
class ItemTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'review.sqlite';self.store=ReviewStore(self.path);self.store.register('a'*64,document())
 def tearDown(self):self.temp.cleanup()
 def accept_all(self):
  for n in range(5):self.store.decide_item('a'*64,str(n),'accept',None,n)
  return self.store.get('a'*64)
 def test_sign_currency_and_bounds(self):
  self.assertEqual(money('S$ -2.00'),'-2.00')
  self.assertEqual(money('-S$2.00'),'-2.00')
  for v in ['NaN','1e10','2.999','infinity']:
   with self.assertRaises(ValueError):money(v)
 def test_grounding_flags_and_schema_limits(self):
  r=validate_items([line('INVENTED ITEM','7.00')],TEXT)[0]
  self.assertFalse(r['source_grounded']);self.assertIn('amount_not_in_row',r['issues'])
  for lines in [[{}],[line('x','1.00')]*101,[[],line('x','1.00')]]:
   with self.assertRaises(ValueError):validate_items(lines,TEXT)
  bad=line('x','1.00');bad['discount_for']=True
  with self.assertRaises(ValueError):validate_items([bad],TEXT)
 def test_unreviewed_lines_never_allocate(self):
  self.assertEqual(self.store.get('a'*64)['item_reconciliation']['status'],'pending')
 def test_discount_tax_payment_reconcile_without_double_count(self):
  result=self.accept_all();r=result['item_reconciliation']
  self.assertEqual(r['status'],'matched')
  allocations={x['category']:x['amount'] for x in r['allocations']}
  self.assertEqual(allocations,{'Office / stationery':'4.00','Food / cakes & pastries':'6.00','Taxes':'0.90'})
  self.assertNotIn('Unallocated',allocations)
 def test_inclusive_prices_do_not_add_tax_again(self):
  result=self.accept_all();result['effective_fields']['total']='10.00'
  r=reconcile(result);self.assertEqual(r['status'],'matched')
  self.assertNotIn('Taxes',[x['category'] for x in r['allocations']])
 def test_missing_total_not_replaced_by_base(self):
  result=self.accept_all();result['effective_fields']['total']=None;result['effective_fields']['base_amount']='10.90'
  self.assertEqual(reconcile(result)['status'],'missing_total')
 def test_mismatch_and_unallocated_basket_discount(self):
  result=self.accept_all();result['effective_fields']['total']='99.00'
  self.assertEqual(reconcile(result)['status'],'mismatch')
  result['effective_fields']['total']='10.90';result['items'][2]['human_review']['value']['discount_for']=None
  self.assertEqual(reconcile(result)['status'],'unallocated_discount')
 def test_item_edits_restart_stale_and_original_unchanged(self):
  result=self.store.decide_item('a'*64,'0','accept',None,0)
  values={k:result['items'][0]['human_review']['value'][k] for k in ['label','category','kind','code','quantity','unit_price','amount','discount_for']}
  values.update(label='Writing supplies',category='Other')
  self.store.decide_item('a'*64,'0','edit',values,1)
  self.store.decide_item('a'*64,'1','reject',None,2)
  restored=ReviewStore(self.path).get('a'*64)
  self.assertEqual(restored['items'][0]['label'],'PENCIL SET 1')
  self.assertEqual(restored['items'][0]['human_review']['value']['label'],'Writing supplies')
  self.assertIsNone(restored['items'][1]['human_review']['value'])
  self.assertEqual(len(restored['item_review_history']),3)
  with self.assertRaises(ReviewConflict):self.store.group('a'*64,'Shopping',[],2)
 def test_spend_uses_item_groups_only_after_header_review(self):
  self.accept_all();self.store.decide('a'*64,'total','accept',None,5);self.store.decide('a'*64,'currency','accept',None,6)
  r=self.store.spending_summary();self.assertEqual(r['included_receipts'],1);self.assertEqual(len(r['groups']),3)
 def test_codes_preserve_zeros_and_do_not_claim_identity(self):
  text='00001234 PENCIL 4.00';p=line('PENCIL','4.00');p.update(code='00001234',quote=text)
  r=validate_items([p],text)[0];self.assertEqual(r['code'],'00001234');self.assertFalse(r['classification']['verified_product_identity'])
 def test_quantity_does_not_multiply_printed_total(self):
  result=self.accept_all();result['items'][1]['human_review']['value']['quantity']='2'
  self.assertEqual(reconcile(result)['status'],'matched')
 def test_old_reading_restores_without_items(self):
  d=attach_document(validate(TEXT,baseline(TEXT)),TEXT);self.store.register('b'*64,d)
  self.assertEqual(self.store.get('b'*64)['item_reconciliation']['status'],'no_items')

 def test_discount_link_to_rejected_purchase_blocks_allocations(self):
  r=self.accept_all();r['items'][1]['human_review']['value']=None;r['effective_fields']['total']='2.90'
  self.assertEqual(reconcile(r)['status'],'invalid_discount_target')
  self.assertEqual(reconcile(r)['allocations'],[])
