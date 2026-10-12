import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from docintel.intake import disposition
from docintel.cloud import requests_for,MARKER,tables
from docintel.telegram import Worker,TransportError
from docintel.reviews import ReviewStore
from test_numbers import sample

class FakeTelegram:
    def __init__(self):self.sent=[];self.downloads=0;self.fail=False
    def call(self,method,**payload):
        if self.fail:raise TransportError('offline')
        self.sent.append((method,payload));return []
    def download(self,file):self.downloads+=1;return b'authored fake bytes'

def message(job=1,user=101,**extra):
    return {'update_id':job,'message':{'from':{'id':user},'chat':{'id':user,'type':'private'},**extra}}

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=ReviewStore(self.root/'reviews.sqlite');self.client=FakeTelegram()
        self.worker=Worker(self.root/'bot',self.client,None,self.store,{'101':'Member A','102':'Member B'})
    def image(self):
        d=sample();d.update(source_type='image',document_type='retail_receipt',source_sha256='a'*64);return d
    def test_admission_and_old_ledger_exclusion(self):
        d=self.image();self.assertEqual(disposition(d)['status'],'ready')
        for kind,flags,status in [('unknown',[],'rejected'),('invoice',[{'code':'not_invoice'}],'rejected'),('invoice',[{'code':'unreadable'}],'retake')]:
            d.update(document_type=kind,issues=flags);self.assertEqual(disposition(d)['status'],status)
            self.store.register('b'*64,d);self.assertEqual(tables(self.store)['EL Receipts'],[])
    def test_offset_and_inbox_survive_restart_without_duplicate_messages(self):
        self.worker.ingest([message(text='/start')]);self.worker.ingest([message(text='/start')])
        self.worker.process();again=Worker(self.root/'bot',self.client,None,self.store,{'101':'Member A'})
        again.process();self.assertEqual(len(self.client.sent),1)
        with again.connect() as c:self.assertEqual(c.execute("SELECT value FROM state WHERE key='offset'").fetchone()[0],'2')
    def test_unknown_member_and_album_are_not_downloaded(self):
        self.worker.ingest([message(1,user=999,photo=[{'file_id':'x'}]),message(2,photo=[{'file_id':'x'}],media_group_id='album')]);self.worker.process()
        self.assertEqual(self.client.downloads,0);self.assertEqual(self.store.recent(),[])
    def test_irrelevant_image_never_registers_or_enters_sheet(self):
        d=self.image();d['document_type']='unknown'
        with patch('docintel.telegram.run',return_value={'documents':[{'status':'completed','extraction':d,'job_key':'b'*64}]}):
            self.worker.ingest([message(photo=[{'file_id':'x'}])]);self.worker.process()
        self.assertEqual(self.store.recent(),[]);self.assertIn('identified as a receipt',self.client.sent[0][1]['text'])
    def test_retry_durable_and_duplicate_source_does_not_reprocess_or_expose(self):
        d=self.image();d['source_sha256']=__import__('hashlib').sha256(b'authored fake bytes').hexdigest()
        result={'documents':[{'status':'completed','extraction':d,'job_key':'b'*64}]}
        with patch('docintel.telegram.run',side_effect=TransportError('offline')):
            self.worker.ingest([message(photo=[{'file_id':'x'}])]);self.worker.process()
        self.assertIn('retry automatically',self.client.sent[0][1]['text'])
        with self.worker.connect() as c:c.execute('UPDATE inbox SET next_try=0')
        with patch('docintel.telegram.run',return_value=result) as run:
            self.worker.process();self.worker.ingest([message(2,user=102,photo=[{'file_id':'x'}])]);self.worker.process();self.assertEqual(run.call_count,1)
        self.assertEqual(len(self.store.recent()),1)
        with self.assertRaises(ValueError):self.worker.lookup(2,102)
        self.assertEqual(self.worker.lookup(1,101)['member'],'Member A')
    def test_other_member_cannot_review_and_stale_buttons_do_not_apply(self):
        d=self.image();d['telegram_owner']=101;doc=self.store.register('b'*64,d)
        with self.worker.connect() as c:c.execute('INSERT INTO inbox (id,event,status,document_id) VALUES (?,?,?,?)',(1,json.dumps(message()),'done','b'*64))
        with self.assertRaises(ValueError):self.worker.lookup(1,102)
        callback={'callback_query':{'from':{'id':101},'message':{'chat':{'id':101,'type':'private'}},'data':'a:1:0:0'}}
        self.store.decide('b'*64,'vendor','accept',None,0)
        _,payload,_=self.worker.handle(callback,3);self.assertIn('has changed',payload['text'])
        self.assertEqual(self.store.get('b'*64)['review']['revision'],1)
    def test_accept_buttons_persist_fields_and_items_without_bulk_approval(self):
        d=self.image();self.store.register('b'*64,d)
        with self.worker.connect() as c:c.execute('INSERT INTO inbox (id,event,status,document_id) VALUES (?,?,?,?)',(1,json.dumps(message()),'done','b'*64))
        def callback(data):return {'callback_query':{'from':{'id':101},'message':{'chat':{'id':101,'type':'private'}},'data':data}}
        fields=list(d['fields']);index=fields.index('total')
        self.worker.handle(callback(f'a:1:0:{index}'),10)
        current=self.store.get('b'*64);self.assertEqual(current['effective_fields']['total'],'18.70')
        self.assertEqual(current['review']['revision'],1)
        pending=tables(self.store)['EL Receipts'][0][-1].split(', ')
        self.assertIn('vendor',pending);self.assertNotIn('total',pending)
        self.worker.handle(callback('y:1:1:0'),11)
        current=self.store.get('b'*64);self.assertEqual(current['items'][0]['human_review']['value']['amount'],'12.40')
        self.assertFalse(current['items'][1].get('human_review'))
        self.assertEqual(current['review']['status'],'pending')
    def test_registration_crash_recovers_same_job_but_not_other_member(self):
        import hashlib
        d=self.image();d.update(source_sha256=hashlib.sha256(b'authored fake bytes').hexdigest(),telegram_owner=101,telegram_receipt=1)
        self.store.register('b'*64,d)
        folder=self.worker.root/'photos'/'1';folder.mkdir(parents=True);(folder/'receipt.jpg').write_bytes(b'authored fake bytes')
        _,payload,identity=self.worker.handle(message(photo=[{'file_id':'x'}]),1)
        self.assertEqual(identity,'b'*64);self.assertIn('Receipt 1',payload['text'])
        self.assertEqual(self.store.get('b'*64)['member'],'Member A')
        _,payload,identity=self.worker.handle(message(2,user=102,photo=[{'file_id':'x'}]),2)
        self.assertIsNone(identity);self.assertNotIn('Cedar',payload['text'])
    def test_browser_rejection_returns_message_without_creating_saved_receipt(self):
        import threading,urllib.request
        from http.server import HTTPServer
        from docintel.server import handler
        d=self.image();d['issues'].append({'field':'image','code':'not_invoice'})
        server=HTTPServer(('127.0.0.1',0),handler(self.root/'report.json',object(),self.root/'uploads.sqlite'))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            report={'documents':[{'status':'completed','extraction':d,'job_key':'b'*64,'attempts':1}],'skipped':0}
            request=urllib.request.Request(base+'/api/extract-image',data=b'fake',headers={'Content-Type':'application/octet-stream','Origin':base})
            with patch('docintel.server.run',return_value=report):
                with urllib.request.urlopen(request,timeout=3) as response:result=json.load(response)
            self.assertEqual(result['intake']['status'],'rejected');self.assertNotIn('review',result)
            self.assertEqual(ReviewStore(self.root/'uploads-reviews.sqlite').recent(),[])
        finally:server.shutdown();server.server_close();thread.join()
    def test_sheet_snapshot_is_atomic_literal_and_does_not_overwrite_unowned_tab(self):
        data={'EL Receipts':[['=HYPERLINK("bad")']]}
        requests=requests_for({'sheets':[]},data)
        cells=next(r['updateCells'] for r in requests if 'updateCells' in r)
        self.assertEqual(cells['rows'][2]['values'][0]['userEnteredValue'],{'stringValue':'=HYPERLINK("bad")'})
        sheet={'properties':{'title':'EL Receipts','sheetId':8,'gridProperties':{'rowCount':100,'columnCount':13}},'data':[{'rowData':[{'values':[{'formattedValue':'My own data'}]}]}]}
        with self.assertRaises(ValueError):requests_for({'sheets':[sheet]},data)
        sheet['data'][0]['rowData'][0]['values'][0]['formattedValue']=MARKER
        requests=requests_for({'sheets':[sheet]},data);self.assertFalse(any('addSheet' in r for r in requests))
        self.assertEqual(next(r['updateCells']['range'] for r in requests if 'updateCells' in r),{'sheetId':8})
    def test_cloud_failure_retains_dirty_snapshot_until_success(self):
        class Cloud:
            def __init__(self):self.calls=0;self.fail=True
            def sync(self,store):
                self.calls+=1
                if self.fail:raise OSError('offline')
        self.worker.cloud=Cloud();self.worker.sync();self.worker.cloud.fail=False
        with self.worker.connect() as c:c.execute("DELETE FROM state WHERE key='cloud_next_try'")
        self.worker.sync();self.worker.sync()
        self.assertEqual(self.worker.cloud.calls,2)
        with self.worker.connect() as c:self.assertEqual(c.execute("SELECT value FROM state WHERE key='cloud_status'").fetchone()[0],'ready')
    def local_export(self):
        from docintel.ledger import LocalLedger
        self.exports=[]
        def render(data,path):self.exports.append(data);path.write_bytes(b'authored workbook stand-in')
        self.worker.local=LocalLedger(self.store,render)
    def test_worker_exports_pending_receipt_without_browser_or_google(self):
        self.local_export();d=self.image()
        with patch('docintel.telegram.run',return_value={'documents':[{'status':'completed','extraction':d,'job_key':'b'*64}]}):
            self.worker.ingest([message(photo=[{'file_id':'x'}])]);self.worker.loop(once=True)
        self.assertEqual(self.worker.local.status()['state'],'ready')
        self.assertTrue(self.worker.local.path.exists())
        self.assertEqual(self.exports[-1]['receipts'][0][0],'Member A')
        self.assertIsNone(self.exports[-1]['receipts'][0][6])
        self.assertTrue(all(row[11]=='Needs review' for row in self.exports[-1]['items']))
        self.assertTrue(any('Local Excel updates automatically' in p.get('text','') for _,p in self.client.sent))
    def test_local_export_survives_cloud_failure(self):
        self.local_export();self.store.register('b'*64,self.image())
        class Cloud:
            def sync(self,store):raise OSError('cloud offline')
        self.worker.cloud=Cloud();self.worker.loop(once=True)
        self.assertEqual(self.worker.local.status()['state'],'ready')
        with self.worker.connect() as c:self.assertEqual(c.execute("SELECT value FROM state WHERE key='cloud_status'").fetchone()[0],'retry_needed')
    def test_telegram_retry_recovers_locked_excel_and_reports_local_status(self):
        self.local_export();self.store.register('b'*64,self.image())
        def locked(data,path):raise PermissionError('authored locked file')
        renderer=self.worker.local.renderer;self.worker.local.renderer=locked;self.worker.local.flush()
        _,payload,_=self.worker.handle(message(text='/status'),1);self.assertIn('/retry_excel',payload['text'])
        self.worker.local.renderer=renderer
        self.worker.handle(message(text='/retry_excel'),2);self.worker.local.flush()
        _,payload,_=self.worker.handle(message(text='/status'),3);self.assertIn('Local Excel: up to date',payload['text'])
