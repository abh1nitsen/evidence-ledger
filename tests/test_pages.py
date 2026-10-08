import copy
from pathlib import Path
import tempfile
import unittest
from docintel.pages import combine
from docintel.reviews import ReviewStore
from test_items import document

def page(source):
 d=document();d.update(source_type='image',image={'original_dimensions':[800,1000]},source_sha256=source)
 return d
class PageTests(unittest.TestCase):
 def test_page_chain_keeps_order_evidence_and_overlap(self):
  identity,r=combine([page('one'),page('two')],['a'*64,'b'*64])
  self.assertEqual([p['source_sha256'] for p in r['pages']],['one','two'])
  self.assertEqual(r['items'][5]['page_index'],1)
  self.assertIn('possible_page_overlap',r['items'][5]['issues'])
  self.assertEqual(r['items'][7]['discount_for'],6)
  self.assertEqual(len(r['items']),10)
  swapped,other=combine([page('two'),page('one')],['b'*64,'a'*64])
  self.assertNotEqual(identity,swapped)
  self.assertFalse(r['page_policy']['overlap_removed_automatically'])
  span=r['fields']['vendor']['span'];self.assertEqual(r['transcript'][span['start']:span['end']],r['fields']['vendor']['quote'])
 def test_identical_bytes_repeated_page_and_nested_chain_rejected(self):
  for readings,ids in [([page('one')],['a'*64]),([page('one'),page('one')],['a'*64,'b'*64]),([page('one'),page('two')],['a'*64,'a'*64])]:
   with self.assertRaises(ValueError):combine(readings,ids)
  a=page('one');a['pages']=[{}]
  with self.assertRaises(ValueError):combine([a,page('two')],['a'*64,'b'*64])
 def test_conflicting_headers_are_review_only(self):
  a,b=page('one'),page('two');b['fields']['currency']['proposal_value']='USD'
  _,r=combine([a,b],['a'*64,'b'*64])
  self.assertIsNone(r['fields']['currency']['value']);self.assertTrue(r['fields']['currency']['review_score']['forced_review'])
 def test_chain_resume_and_rejected_overlap_persist(self):
  with tempfile.TemporaryDirectory() as folder:
   store=ReviewStore(Path(folder)/'reviews.sqlite');store.register('a'*64,page('one'));store.register('b'*64,page('two'))
   r=store.chain(['a'*64,'b'*64]);identity=r['review']['document_id']
   store.decide_item(identity,'5','reject',None,0)
   resumed=ReviewStore(store.path).chain(['a'*64,'b'*64])
   self.assertEqual(resumed['review']['revision'],1);self.assertIsNone(resumed['items'][5]['human_review']['value'])
   self.assertNotIn('human_review',resumed['items'][0])
