import copy
import json
from pathlib import Path
import tempfile
import unittest
from docintel.core import canonical,baseline,validate
from docintel.documents import attach_document
from docintel.items import money,quantity,validate_items,reconcile
from docintel.numbers import number_view
from docintel.reviews import ReviewStore

# Authored fixture, independent of privately supplied receipts.
TEXT='Vendor: Cedar Kitchen\nInvoice ID: SAMPLE-23\nInvoice Date: 2026-10-01\nCurrency: EUR\nSubtotal: 17,48 €\nTax: 1,22 €\nTotal: 18,70 €\n11 / 1x Lentil Bowl 12,40\n12 / 2x Flatbread 6,30'

def sample():
    d=attach_document(validate(TEXT,baseline(TEXT)),TEXT);d['transcript']=TEXT
    lines=[]
    for name,code,qty,amount,quote in [('Lentil Bowl','11','1x','12,40','11 / 1x Lentil Bowl 12,40'),('Flatbread','12','2x','6,30','12 / 2x Flatbread 6,30')]:
        lines.append(dict(description=quote.rsplit(' ',1)[0],label=name,code=code,quantity=qty,unit_price=None,amount=amount,quote=quote,amount_quote=amount,kind='product',category='Food / prepared food',discount_for=None))
    d['items']=validate_items(lines,TEXT)
    return d

class NumberTests(unittest.TestCase):
    def test_supported_printed_amounts(self):
        for value,expected in [('14,90','14.90'),('23,79 €','23.79'),('EUR 1.234,56','1234.56'),('1,234.56 USD','1234.56'),('1,234','1234.00'),('1\u202f234,56 €','1234.56'),('1 234.56','1234.56'),('14,9','14.90')]:
            with self.subTest(value=value):self.assertEqual(canonical('total',value),expected)
    def test_malformed_ambiguous_or_conflicting_formats_rejected(self):
        for value in ('1.234','12,34,56','1.23,45','1 23,45','1e3','NaN','-1,20','1,2345','USD 1,20 EUR','1000000001,00'):
            with self.subTest(value=value),self.assertRaises(ValueError):canonical('total',value)
    def test_negative_discount_and_positive_total_are_distinct(self):
        self.assertEqual(money('-2,50 €'),'-2.50');self.assertEqual(money('€ −2,50'),'-2.50')
        self.assertEqual(money('-0,00'),'0.00')
    def test_quantity_multiplier_is_not_a_price_multiplier(self):
        for raw,expected in [('1x','1'),('2 x','2'),('3×','3'),('1.5','1.5')]:self.assertEqual(quantity(raw),expected)
        for raw in ('x2','2x3','1xx','0x','10001x'):
            with self.assertRaises(ValueError):quantity(raw)
    def test_fresh_fields_and_items_preserve_printed_evidence(self):
        d=sample()
        self.assertEqual(d['fields']['total']['proposal_value'],'18.70')
        self.assertEqual(d['fields']['total']['quote'],'18,70 €')
        self.assertEqual(d['items'][0]['amount'],'12.40')
        self.assertEqual(d['items'][1]['quantity'],'2')
        self.assertEqual(d['items'][0]['raw_numbers']['amount'],'12,40')
    def legacy(self):
        d=sample()
        for key in ('subtotal','tax','total'):
            f=d['fields'][key];f.update(candidate=f['quote'],candidate_quote=f['quote'],proposal_value=None,value=None,valid=False,quote=None)
        for item in d['items']:
            item.pop('raw_numbers');item['amount']=None;item['quantity']=None;item['issues']=['amount_format','quantity_format']
        return d
    def test_legacy_recovery_is_non_mutating_and_evidence_bound(self):
        original=self.legacy();snapshot=copy.deepcopy(original);view=number_view(original)
        self.assertEqual(original,snapshot)
        self.assertEqual(view['fields']['total']['proposal_value'],'18.70')
        self.assertIsNone(view['fields']['total']['value'])
        self.assertEqual(view['items'][0]['amount'],'12.40');self.assertEqual(view['items'][1]['quantity'],'2')
        self.assertNotIn('human_review',view['items'][0])
        original['items'][0]['amount_quote']='99,99';original['fields']['total']['candidate_quote']='99,99 €'
        view=number_view(original)
        self.assertIsNone(view['items'][0]['amount']);self.assertIsNone(view['fields']['total']['proposal_value'])
    def test_saved_review_accepts_recovered_proposals_and_preserves_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ReviewStore(Path(folder)/'reviews.sqlite');original=self.legacy();store.register('a'*64,original)
            store.decide('a'*64,'total','edit','18.70',0)
            store.decide('a'*64,'currency','accept',None,1)
            store.decide('a'*64,'tax','accept',None,2)
            store.decide_item('a'*64,'0','accept',None,3)
            store.decide_item('a'*64,'1','accept',None,4)
            d=ReviewStore(store.path).get('a'*64)
            self.assertEqual(d['effective_fields']['total'],'18.70')
            self.assertEqual(d['fields']['total']['human_review']['action'],'edit')
            self.assertEqual(d['item_reconciliation']['status'],'matched')
            self.assertEqual(d['item_reconciliation']['final_total'],'18.70')
            with store.connect() as c:self.assertEqual(json.loads(c.execute('SELECT original FROM documents').fetchone()[0]),original)
    def test_invalid_read_amount_retained_for_correction(self):
        d=sample();d['items'][0]['raw_numbers']['amount']='12,4,0';d['items'][0]['amount']=None;d['items'][0]['issues']=['amount_format']
        view=number_view(d)
        self.assertIsNone(view['items'][0]['amount']);self.assertEqual(view['items'][0]['raw_numbers']['amount'],'12,4,0')
