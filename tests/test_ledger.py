import copy
from pathlib import Path
import tempfile
import unittest
from docintel.ledger import LocalLedger,projection
from docintel.reviews import ReviewStore,ReviewConflict
from docintel.spending import DEMO_TEXT
from docintel.core import baseline,validate
from docintel.documents import attach_document
from test_items import document


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=ReviewStore(Path(self.temp.name)/'reviews.sqlite')
        self.store.register('a'*64,document());self.calls=[]
        def renderer(data,path):self.calls.append(data);path.write_bytes(b'test-workbook')
        self.ledger=LocalLedger(self.store,renderer)
    def tearDown(self):self.temp.cleanup()
    def ready(self):
        self.store.decide('a'*64,'total','accept',None,0)
        self.store.decide('a'*64,'currency','accept',None,1)
        for n in range(5):self.store.decide_item('a'*64,str(n),'accept',None,n+2)
    def test_pending_values_visible_without_confirmed_spend(self):
        data=projection(self.store)
        self.assertEqual(data['receipts'][0][5],10.9);self.assertIsNone(data['receipts'][0][6])
        self.assertEqual(len(data['items']),5);self.assertTrue(all(i[8] is None for i in data['items']))
    def test_reviewed_discounts_payments_and_quantity(self):
        self.ready();data=projection(self.store)
        self.assertEqual(data['receipts'][0][6],10.9)
        self.assertEqual([i[8] for i in data['items']],[4.0,8.0,-2.0,.9,None])
        self.assertEqual(data['items'][2][4],'Food / cakes & pastries')
        self.assertEqual(data['totals'],[{'currency':'SGD','total':'10.90'}])
    def test_member_persists_and_source_reprocessing_inherits_name(self):
        saved=self.store.member('a'*64,'Alice',0)
        self.assertEqual(saved['member'],'Alice')
        self.store.register('b'*64,document())
        self.assertEqual(self.store.get('b'*64)['member'],'Alice')
        self.assertEqual(len(projection(self.store)['receipts']),1)
        self.assertEqual(ReviewStore(self.store.path).get('a'*64)['member_history'][0]['name'],'Alice')
        with self.assertRaises(ReviewConflict):self.store.member('a'*64,'Bob',0)
    def test_invalid_member_does_not_commit(self):
        for name in ('',' '*2,'x'*81,'bad\x00name',None):
            with self.assertRaises(ValueError):self.store.member('a'*64,name,0)
        self.assertEqual(self.store.get('a'*64)['review']['revision'],0)
    def test_retries_do_not_append_and_review_updates_rebuild(self):
        self.ledger.flush();self.ledger.flush();self.assertEqual(len(self.calls),1)
        self.store.member('a'*64,'Bob',0);self.ledger.flush()
        self.assertEqual(len(self.calls),2);self.assertEqual(self.calls[-1]['receipts'][0][0],'Bob')
        self.assertEqual(len(self.calls[-1]['receipts']),1);self.assertEqual(self.ledger.status()['state'],'ready')
    def test_restart_replays_dirty_generation(self):
        self.ledger.flush();self.store.member('a'*64,'Carol',0)
        restarted=LocalLedger(ReviewStore(self.store.path),self.ledger.renderer)
        self.assertEqual(restarted.status()['state'],'updating');restarted.flush()
        self.assertEqual(restarted.status()['state'],'ready')
    def test_locked_destination_retains_prior_workbook_and_retry(self):
        self.ledger.flush();self.store.member('a'*64,'Alice',0)
        real=self.ledger.renderer
        def fail(*args):raise PermissionError('private path not exposed')
        self.ledger.renderer=fail;self.ledger.flush()
        self.assertEqual(self.ledger.path.read_bytes(),b'test-workbook')
        self.assertEqual(self.ledger.status()['error'],'close_excel_and_retry')
        self.assertIsNone(self.ledger.status()['download_url'])
        self.ledger.retry();self.ledger.renderer=real;self.ledger.flush()
        self.assertEqual(self.ledger.status()['state'],'ready')
    def test_changes_during_render_discard_stale_output(self):
        def render(data,path):
            path.write_bytes(b'stale');self.store.member('a'*64,'Alice',0)
        self.ledger.renderer=render;self.ledger.flush()
        self.assertFalse(self.ledger.path.exists());self.assertEqual(self.ledger.status()['state'],'updating')
    def test_missing_workbook_rebuilds_without_new_upload(self):
        self.ledger.flush();self.ledger.path.unlink();self.ledger.flush()
        self.assertEqual(len(self.calls),2)
    def test_corrupted_workbook_is_not_served_and_rebuilds(self):
        self.ledger.flush();self.ledger.path.write_bytes(b'damaged')
        self.assertEqual(self.ledger.status()['state'],'updating')
        self.assertIsNone(self.ledger.status()['download_url'])
        self.ledger.flush();self.assertEqual(self.ledger.path.read_bytes(),b'test-workbook')
    def test_demo_excluded_and_possible_duplicate_not_counted_twice(self):
        self.ready();demo=attach_document(validate(DEMO_TEXT,baseline(DEMO_TEXT)),DEMO_TEXT);demo['transcript']=DEMO_TEXT
        self.store.register('c'*64,demo)
        copied=document();copied['source_sha256']='second-photo'
        self.store.register('b'*64,copied)
        self.store.decide('b'*64,'total','accept',None,0);self.store.decide('b'*64,'currency','accept',None,1)
        for n in range(5):self.store.decide_item('b'*64,str(n),'accept',None,n+2)
        # Duplicate bill checks require the complete vendor/id/date identity.
        for identity in ('a'*64,'b'*64):self.store.decide(identity,'invoice_date','accept',None,7)
        data=projection(self.store)
        self.assertEqual(len(data['receipts']),2)
        self.assertEqual(sum(r[6] or 0 for r in data['receipts']),10.9)
    def test_corrected_line_amount_retained_while_receipt_pending(self):
        item=document()['items'][0];values={k:item[k] for k in ('label','category','kind','code','quantity','unit_price','amount','discount_for')};values['amount']='3.00'
        self.store.decide_item('a'*64,'0','edit',values,0)
        row=projection(self.store)['items'][0]
        self.assertEqual(row[7],3.0);self.assertIsNone(row[8])
    def test_chain_keeps_one_receipt_and_inherits_matching_members(self):
        from test_pages import page
        self.store.register('b'*64,page('page-one'));self.store.register('c'*64,page('page-two'))
        self.store.member('b'*64,'Alice',0);self.store.member('c'*64,'Alice',0)
        chain=self.store.chain(['b'*64,'c'*64]);self.assertEqual(chain['member'],'Alice')
        data=projection(self.store)
        self.assertEqual(len(data['receipts']),2) # independent original plus combined receipt
        self.assertEqual(len(data['items']),15)
        combined=[r for r in data['receipts'] if r[10]==2][0]
        self.assertEqual(combined[0],'Alice')
        self.store.chain(['c'*64,'b'*64])
        self.assertEqual(len(projection(self.store)['receipts']),2)
    def test_excel_writer_lock_excludes_competing_export(self):
        from docintel.pipeline import exclusive
        with exclusive(self.ledger.path):
            with self.assertRaises(RuntimeError):self.ledger.flush()
        self.ledger.flush();self.assertEqual(self.ledger.status()['state'],'ready')

