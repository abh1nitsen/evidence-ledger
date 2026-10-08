import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from docintel.core import FIELDS, EXTRA_FIELDS, baseline, canonical, validate
from docintel.documents import attach_document, classify, optional_fields
from docintel.reviews import ReviewStore, ReviewConflict
from docintel.ocr import check_ocr, Paddle, Hybrid
from docintel.providers import ProviderError
from test_core import TEXT

SLIP="""Merchant: Example Cafe
DATE/TIME:17/08/25 21:13:04
TID:00000017 INV:400731
CARD LABEL:AMEX
BASE : S$ 36.70
TIP : S$
TOTAL : S$
"""

def slip_result():
    proposed={k:{"value":None,"quote":None} for k in FIELDS}
    proposed.update(vendor={"value":"Example Cafe","quote":"Example Cafe"},
        invoice_id={"value":"400731","quote":"INV:400731"},
        invoice_date={"value":"2025-08-17","quote":"17/08/25"},
        currency={"value":"SGD","quote":"S$"})
    ocr={"dimensions":[800,1000],"lines":[{"text":line,"score":.98,"box":[0,n*30,700,n*30+20]} for n,line in enumerate(SLIP.splitlines())]}
    return attach_document(validate(SLIP,proposed),SLIP,ocr=ocr)

class DocumentTests(unittest.TestCase):
    def test_payment_type_and_optional_amount_roles(self):
        result=slip_result()
        self.assertEqual(result["document_type"],"payment_slip")
        self.assertEqual(result["fields"]["base_amount"]["value"],"36.70")
        self.assertIsNone(result["fields"]["total"]["value"])
        self.assertEqual(result["fields"]["tax"]["state"],"not_present")
        self.assertEqual(result["fields"]["transaction_time"]["value"],"21:13:04")
    def test_labelled_id_leading_zeros_and_currency_markers(self):
        text=SLIP.replace('400731','000731')
        proposed={k:{"value":None,"quote":None} for k in FIELDS}
        proposed['invoice_id']={"value":"000731","quote":"INV:000731"}
        self.assertEqual(validate(text,proposed)['fields']['invoice_id']['value'],'000731')
        for raw,iso in [('S$','SGD'),('US$','USD'),('£','GBP'),('€','EUR'),('₹','INR')]:
            self.assertEqual(canonical('currency',raw),iso)
        with self.assertRaises(ValueError):canonical('currency','$')
    def test_two_digit_century_is_review_only(self):
        f=slip_result()['fields']['invoice_date']
        self.assertIsNone(f['value'])
        self.assertEqual(f['proposal_value'],'2025-08-17')
        self.assertTrue(f['review_score']['forced_review'])
        self.assertLessEqual(f['review_score']['value'],.49)
        for raw in ('01/08/25','17/08/925'):
            with self.assertRaises(ValueError):canonical('invoice_date',raw)
    def test_blank_total_does_not_promote_base(self):
        p={k:{"value":None,"quote":None} for k in FIELDS}
        p['total']={"value":"36.70","quote":"36.70"}
        r=attach_document(validate(SLIP,p),SLIP)
        self.assertIsNone(r['fields']['total']['value'])
        self.assertEqual(r['fields']['total']['proposal_value'],'36.70')
        self.assertTrue(r['fields']['total']['review_score']['forced_review'])
    def test_ocr_date_time_split_across_lines_keeps_time(self):
        text=SLIP.replace('17/08/25 21:13:04','17/08/25\n21:13:04')
        extras={k:{"value":None,"quote":None} for k in EXTRA_FIELDS}
        extras['transaction_time']={"value":"21:13:04","quote":"21:13:04"}
        r=attach_document(validate(text,baseline(text)),text,extras)
        self.assertEqual(r['fields']['transaction_time']['value'],'21:13:04')
        self.assertFalse(r['fields']['transaction_time']['review_score']['forced_review'])

    def test_invalid_time_or_extra_schema_rejected(self):
        for raw in ('23:99:12','21:13:04 junk','tomorrow 21:13'):
            with self.assertRaises(ValueError):canonical('transaction_time',raw)
        for extras in ([],{}, {'unexpected':{}}):
            with self.assertRaises(ValueError):attach_document(validate(TEXT,baseline(TEXT)),TEXT,extras)
        with self.assertRaises(ValueError):attach_document(validate(TEXT,baseline(TEXT)),TEXT,document_type='')
    def test_ocr_scores_do_not_override_semantic_conflicts(self):
        r=slip_result()
        score=r['fields']['invoice_date']['review_score']
        self.assertIsNotNone(score['ocr_recognition'])
        self.assertFalse(score['calibrated'])
        self.assertLess(score['value'],.85)
        self.assertTrue(r['fields']['invoice_id']['ocr_evidence'])

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'reviews.sqlite'
        self.store=ReviewStore(self.path);self.original=slip_result();self.identity='a'*64
        self.store.register(self.identity,self.original)
    def tearDown(self):self.temp.cleanup()
    def test_accept_edit_reject_and_restart_preserve_original(self):
        r=self.store.decide(self.identity,'invoice_date','accept',None,0)
        self.assertEqual(r['effective_fields']['invoice_date'],'2025-08-17')
        self.assertIsNone(r['fields']['invoice_date']['value'])
        self.assertEqual(r['fields']['invoice_date']['human_review']['action'],'accept')
        r=self.store.decide(self.identity,'invoice_id','edit','NEW-002',1)
        r=self.store.decide(self.identity,'currency','reject',None,2)
        restarted=ReviewStore(self.path).register(self.identity,self.original)
        self.assertEqual(restarted['effective_fields']['invoice_id'],'NEW-002')
        self.assertIsNone(restarted['effective_fields']['currency'])
        self.assertEqual(restarted['review']['revision'],3)
        self.assertEqual(len(restarted['review']['history']),3)
        self.assertEqual(restarted['fields']['invoice_id']['value'],'400731')
    def test_stale_review_does_not_overwrite(self):
        self.store.decide(self.identity,'currency','accept',None,0)
        with self.assertRaises(ReviewConflict):self.store.decide(self.identity,'currency','reject',None,0)
        self.assertEqual(self.store.get(self.identity)['effective_fields']['currency'],'SGD')
    def test_missing_candidate_cannot_be_accepted(self):
        with self.assertRaises(ValueError):self.store.decide(self.identity,'tax','accept',None,0)
        with self.assertRaises(ValueError):self.store.decide(self.identity,'transaction_time','edit','25:70',0)
        self.assertEqual(self.store.get(self.identity)['review']['revision'],0)
    def test_reviewed_arithmetic_is_checked_without_mutating_original(self):
        original=attach_document(validate(TEXT,baseline(TEXT)),TEXT)
        self.store.register('b'*64,original)
        r=self.store.decide('b'*64,'tax','edit','11.00',0)
        self.assertIn('reviewed_arithmetic_mismatch',[x['code'] for x in r['effective_issues']])
        self.assertEqual(r['fields']['tax']['value'],'10.00')
    def test_edit_requires_an_explicit_century(self):
        with self.assertRaises(ValueError):self.store.decide(self.identity,'invoice_date','edit','17/08/25',0)
        self.assertEqual(self.store.get(self.identity)['review']['revision'],0)
    def test_second_accept_records_a_new_human_decision(self):
        self.store.decide(self.identity,'currency','accept',None,0)
        r=self.store.decide(self.identity,'currency','accept',None,1)
        self.assertEqual(r['review']['revision'],2)

class OCRTests(unittest.TestCase):
    def data(self):return {'dimensions':[800,1000],'lines':[{'text':'Invoice: A-1','score':.95,'box':[0,0,700,25]}]}
    def test_bad_ocr_coordinates_and_scores_rejected(self):
        for field,value in [('box',[-1,0,100,50]),('box',[0,0,900,20]),('score',math.nan),('score',1.1),('text','bad\x00text')]:
            d=self.data();d['lines'][0][field]=value
            with self.assertRaises(ValueError):check_ocr(d,[800,1000])
    def test_missing_dependency_is_actionable(self):
        with patch('importlib.metadata.version',side_effect=__import__('importlib.metadata').metadata.PackageNotFoundError):
            with self.assertRaises(ProviderError) as error:Paddle()
        self.assertEqual(error.exception.code,'ocr_not_installed')
    def test_cached_ocr_avoids_subprocess(self):
        from docintel.core import digest
        with tempfile.TemporaryDirectory() as folder:
            engine=object.__new__(Paddle);engine.cache=Path(folder);engine.identity='test';engine.versions={};engine.timeout=1
            destination=engine.cache/'results'/(digest('hash'+'test')+'.json');destination.parent.mkdir()
            destination.write_text(json.dumps({**self.data(),'model_hashes':{}}))
            with patch('subprocess.run') as call:
                data=engine.read({'metadata':{'normalized_sha256':'hash','normalized_dimensions':[800,1000]}})
                self.assertEqual(data['lines'][0]['text'],'Invoice: A-1');call.assert_not_called()
    def test_ocr_timeout_does_not_silently_fallback(self):
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            engine=object.__new__(Paddle);engine.cache=Path(folder);engine.identity='test';engine.versions={};engine.timeout=1
            with patch('subprocess.run',side_effect=subprocess.TimeoutExpired('ocr',1)):
                with self.assertRaises(ProviderError) as error:
                    engine.read({'metadata':{'normalized_sha256':'hash','normalized_dimensions':[800,1000]},'data_url':'data:image/jpeg;base64,dGVzdA=='})
                self.assertEqual(error.exception.code,'ocr_timeout')
