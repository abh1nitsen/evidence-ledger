"""Private-chat Telegram intake, durable inbox/outbox and explicit field review."""
import hashlib
import contextlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import urllib.error
import urllib.request
from .intake import disposition
from .pipeline import run,exclusive
from .vision import MAX_IMAGE_BYTES
from .reviews import ReviewConflict

class TransportError(RuntimeError):
    pass

class Telegram:
    def __init__(self,token):
        if not re.fullmatch(r'\d+:[A-Za-z0-9_-]+',token):raise ValueError('invalid_bot_token')
        self.base='https://api.telegram.org/bot'+token+'/'
        self.files='https://api.telegram.org/file/bot'+token+'/'
    def call(self,method,**data):
        request=urllib.request.Request(self.base+method,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=40) as response:
                value=json.loads(response.read(2_000_000))
            if not value.get('ok'):raise TransportError('telegram_unavailable')
            return value['result']
        except (OSError,ValueError):raise TransportError('telegram_unavailable') from None
    def download(self,file_id):
        file=self.call('getFile',file_id=file_id);path=file.get('file_path','')
        if not re.fullmatch(r'[A-Za-z0-9_./-]+',path) or '..' in path or path.startswith('/'):
            raise ValueError('invalid_file_path')
        if file.get('file_size',0)>MAX_IMAGE_BYTES:raise ValueError('image_too_large')
        try:
            with urllib.request.urlopen(self.files+path,timeout=40) as response:raw=response.read(MAX_IMAGE_BYTES+1)
        except OSError:raise TransportError('telegram_download_unavailable') from None
        if not 0<len(raw)<=MAX_IMAGE_BYTES:raise ValueError('image_too_large')
        return raw

class Worker:
    def __init__(self,root,client,provider,store,members,cloud=None,local=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'telegram.sqlite';self.client=client;self.provider=provider
        self.store=store;self.members=members;self.cloud=cloud;self.local=local
        if not isinstance(members,dict) or any(not str(k).isdigit() or not isinstance(v,str) or not 0<len(v.strip())<=80 or any(ord(ch)<32 for ch in v) for k,v in members.items()):raise ValueError('invalid_household_members')
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS inbox (
              id INTEGER PRIMARY KEY,event TEXT,status TEXT DEFAULT 'pending',attempts INTEGER DEFAULT 0,
              next_try REAL DEFAULT 0,document_id TEXT,response TEXT,sent INTEGER DEFAULT 0);
              CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY,value TEXT);
              INSERT OR IGNORE INTO state VALUES ('offset','0');''')
    @contextlib.contextmanager
    def connect(self):
        with contextlib.closing(sqlite3.connect(self.db,timeout=10)) as c:
            c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA synchronous=FULL')
            with c:yield c
    def ingest(self,updates):
        # Telegram is acknowledged only after the entire received batch is durable locally.
        with self.connect() as c:
            for event in updates:
                if not isinstance(event.get('update_id'),int):raise ValueError('invalid_update')
                c.execute('INSERT OR IGNORE INTO inbox (id,event) VALUES (?,?)',(event['update_id'],json.dumps(event)))
            if updates:
                offset=max(e['update_id'] for e in updates)+1
                old=int(c.execute("SELECT value FROM state WHERE key='offset'").fetchone()[0])
                c.execute("UPDATE state SET value=? WHERE key='offset'",(str(max(old,offset)),))
    def lookup(self,job,user_id):
        with self.connect() as c:row=c.execute('SELECT document_id,event FROM inbox WHERE id=?',(job,)).fetchone()
        if not row or not row[0]:raise ValueError('receipt_not_ready')
        event=json.loads(row[1]);owner=event.get('message',{}).get('from',{}).get('id')
        if owner!=user_id:raise ValueError('receipt_not_owned')
        return self.store.get(row[0])
    def review_text(self,doc,job):
        lines=['Receipt '+str(job)+' · '+doc['member']+' · '+doc['review']['status']]
        for key,f in doc['fields'].items():
            if f.get('required') or f.get('proposal_value') is not None or f.get('candidate') is not None:
                human=f.get('human_review')
                value=human['value'] if human else f.get('proposal_value') or f.get('candidate')
                lines.append(key+': '+str(value or 'Not found')+(' · reviewed' if human else ' · NEEDS REVIEW'))
        for index,item in enumerate(doc.get('items',[])):
            human=item.get('human_review');v=(human.get('value') or {}) if human else item
            lines.append('Item '+str(index+1)+': '+str(v.get('label') or item['description'])+' · '+str(v.get('amount') or 'Amount missing')+(' · reviewed' if human else ' · NEEDS REVIEW'))
        lines+=['Use the buttons to review fields/items. To correct a field: /edit '+str(job)+' total 12.34',
                'For detailed item edits, grouping and multi-page receipts, use the laptop app. Confirmed spending requires reviewed, reconciled amounts.']
        return '\n'.join(lines)[:3900]
    def keyboard(self,doc,job):
        rows=[];rev=doc['review']['revision']
        for index,(key,f) in enumerate(doc['fields'].items()):
            if not f.get('human_review') and (f.get('required') or f.get('proposal_value') is not None or f.get('candidate') is not None):
                rows.append([{'text':'Review '+key,'callback_data':f'v:{job}:{rev}:{index}'}])
        for index,item in enumerate(doc.get('items',[])):
            if not item.get('human_review'):rows.append([{'text':'Review item '+str(index+1),'callback_data':f'i:{job}:{rev}:{index}'}])
        return {'inline_keyboard':rows[:40]}
    def handle(self,event,job):
        callback=event.get('callback_query');message=callback.get('message',{}) if callback else event.get('message',{})
        user=(callback or message).get('from',{}).get('id');chat=message.get('chat',{})
        if chat.get('type')!='private' or not isinstance(user,int):return None,None,None
        chat_id=chat['id'];name=self.members.get(str(user))
        if not name:
            return chat_id,{'text':'Ask the household administrator to register your Telegram user ID: '+str(user)+'. Photos have not been sent to the AI service.'},None
        if callback:
            parts=callback.get('data','').split(':')
            if len(parts)!=4 or parts[0] not in {'v','i','a','r','y','n'}:raise ValueError('invalid_review_button')
            action,source,revision,index=parts[0],*map(int,parts[1:])
            if index<0:raise ValueError('invalid_review_button')
            doc=self.lookup(source,user)
            if doc['review']['revision']!=revision:
                return chat_id,{'text':'This review has changed. Here is the latest reading.\n'+self.review_text(doc,source),'reply_markup':self.keyboard(doc,source)},None
            if action in {'i','y','n'}:
                item=doc['items'][index]
                if action=='i':
                    text='Item '+str(index+1)+': '+str(item.get('label') or item['description'])+'\nAmount: '+str(item.get('amount'))+'\nQuantity: '+str(item.get('quantity'))+'\nCategory: '+str(item.get('category'))+'\nPrinted evidence: '+item['quote']
                    buttons=[[{'text':'Accept item','callback_data':f'y:{source}:{revision}:{index}'},{'text':'Reject item','callback_data':f'n:{source}:{revision}:{index}'}]]
                    return chat_id,{'text':text[:3900],'reply_markup':{'inline_keyboard':buttons}},None
                doc=self.store.decide_item(doc['review']['document_id'],item['id'],'accept' if action=='y' else 'reject',None,revision)
            else:
                key=list(doc['fields'])[index];field=doc['fields'][key]
                if action=='v':
                    buttons=[]
                    if field.get('proposal_value') is not None:buttons.append({'text':'Accept','callback_data':f'a:{source}:{revision}:{index}'})
                    buttons.append({'text':'Reject','callback_data':f'r:{source}:{revision}:{index}'})
                    text=key+': '+str(field.get('proposal_value') or field.get('candidate') or 'Not found')+'\nPrinted evidence: '+str(field.get('quote') or field.get('candidate_quote') or 'None')+'\nTo edit: /edit '+str(source)+' '+key+' VALUE'
                    return chat_id,{'text':text[:3900],'reply_markup':{'inline_keyboard':[buttons]}},None
                doc=self.store.decide(doc['review']['document_id'],key,'accept' if action=='a' else 'reject',None,revision)
            return chat_id,{'text':self.review_text(doc,source),'reply_markup':self.keyboard(doc,source)},None
        text=message.get('text','')
        if text=='/retry_excel':
            if self.local is None:return chat_id,{'text':'Local Excel export is not configured in this worker.'},None
            self.local.retry()
            return chat_id,{'text':'Local Excel retry requested. Close the workbook in Excel if it is open. /status shows when the update is ready.'},None
        if text=='/status':
            local_text=''
            if self.local is not None:
                state=self.local.status()['state']
                local_text='Local Excel: '+({'ready':'up to date (purchase-ledger.xlsx).','updating':'update pending.','retry_needed':'update failed; close the workbook and send /retry_excel. Check the export runtime on the laptop if it still fails.'}[state])+'\n'
            if self.cloud is None:return chat_id,{'text':local_text+'Shared Google Sheet is not configured. Readings are saved locally for review.'},None
            from .cloud import tables
            fingerprint=hashlib.sha256(json.dumps(tables(self.store),sort_keys=True).encode()).hexdigest()
            with self.connect() as c:
                previous=c.execute("SELECT value FROM state WHERE key='cloud_hash'").fetchone()
                status=c.execute("SELECT value FROM state WHERE key='cloud_status'").fetchone()
            state='up to date' if previous and previous[0]==fingerprint else 'waiting to retry' if status and status[0]=='retry_needed' else 'update pending'
            return chat_id,{'text':local_text+'Shared Google Sheet: '+state+'.\nhttps://docs.google.com/spreadsheets/d/'+self.cloud.id},None
        if text.startswith('/review ') or text.startswith('/edit '):
            parts=text.split(maxsplit=3);source=int(parts[1]);doc=self.lookup(source,user)
            if parts[0]=='/edit':
                if len(parts)!=4:raise ValueError('invalid_edit')
                doc=self.store.decide(doc['review']['document_id'],parts[2],'edit',parts[3],doc['review']['revision'])
            return chat_id,{'text':self.review_text(doc,source),'reply_markup':self.keyboard(doc,source)},None
        if message.get('media_group_id'):
            return chat_id,{'text':'Telegram albums are not combined automatically yet. Use Add next page in the laptop app for a long receipt. No album page was added to purchases.'},None
        photos=message.get('photo',[]);file=max(photos,key=lambda f:f.get('width',0)*f.get('height',0)) if photos else message.get('document')
        if not file:
            return chat_id,{'text':'Send one receipt photo or JPEG/PNG/WebP file. I will save its reading as Needs review. /review RECEIPT_ID reopens it. Long receipts currently use Add next page in the laptop app.'},None
        if file.get('file_size',0)>MAX_IMAGE_BYTES or (not photos and file.get('mime_type') not in {'image/jpeg','image/png','image/webp'}):
            return chat_id,{'text':'Send a JPEG, PNG or WebP image under 8 MB. Nothing was added to purchases.'},None
        folder=self.root/'photos'/str(job);folder.mkdir(parents=True,exist_ok=True);path=folder/'receipt.jpg'
        if not path.exists():
            raw=self.client.download(file['file_id']);temp=folder/'photo.tmp';temp.write_bytes(raw);os.replace(temp,path)
        source=hashlib.sha256(path.read_bytes()).hexdigest()
        with self.store.connect() as c:known=c.execute('SELECT id FROM documents WHERE json_extract(original,\'$.source_sha256\')=? LIMIT 1',(source,)).fetchone()
        if known:
            doc=self.store.get(known[0])
            if doc.get('telegram_owner')==user and doc.get('telegram_receipt')==job:
                if doc['member']=='Unassigned':doc=self.store.member(known[0],name,doc['review']['revision'])
                return chat_id,{'text':self.review_text(doc,job),'reply_markup':self.keyboard(doc,job)},known[0]
            # Do not expose another member's receipt through a duplicate upload.
            return chat_id,{'text':'This image is already in the household ledger. No duplicate purchase was added.'},None
        report=run(folder,self.root/'image-jobs.sqlite',folder/'reading.json',self.provider,retry_failed=True)
        record=report['documents'][0]
        if record['status']!='completed':
            if record['error'] in {'invalid_input','invalid_provider_schema'}:
                return chat_id,{'text':'This photo could not be read safely. Send a clear bill photo. Nothing was added to purchases.'},None
            raise TransportError('model_delayed')
        doc=record['extraction'];admission=disposition(doc)
        if admission['status']!='ready':return chat_id,{'text':admission['message']},None
        doc['telegram_owner']=user;doc['telegram_receipt']=job
        doc=self.store.register(record['job_key'],doc)
        if doc['member']=='Unassigned':doc=self.store.member(record['job_key'],name,doc['review']['revision'])
        destination='Local Excel updates automatically; use /status to check it.' if self.local is not None else 'Readings are saved locally.'
        if self.cloud is not None:destination+=' Shared-sheet synchronization runs separately.'
        return chat_id,{'text':'Receipt saved locally as Needs review. '+destination+'\n'+self.review_text(doc,job),'reply_markup':self.keyboard(doc,job)},record['job_key']
    def process(self):
        with self.connect() as c:jobs=c.execute("SELECT id,event,attempts FROM inbox WHERE status='pending' AND next_try<=? ORDER BY id LIMIT 20",(time.time(),)).fetchall()
        for job,raw,attempts in jobs:
            event=json.loads(raw)
            try:
                chat,payload,document=self.handle(event,job)
                result={'chat_id':chat,**payload} if payload else None
                with self.connect() as c:c.execute("UPDATE inbox SET status='done',document_id=?,response=?,sent=0,attempts=? WHERE id=?",(document,json.dumps(result),attempts+1,job))
            except (TransportError,OSError,RuntimeError,sqlite3.Error):
                with self.connect() as c:
                    c.execute('UPDATE inbox SET attempts=?,next_try=? WHERE id=?',(attempts+1,time.time()+min(3600,15*2**min(attempts,8)),job))
                    if attempts==0:
                        msg=event.get('callback_query',{}).get('message') or event.get('message',{})
                        notice={'chat_id':msg.get('chat',{}).get('id'),'text':'Reading delayed. This request is saved locally and will retry automatically. No partial purchase was confirmed.'}
                        c.execute('UPDATE inbox SET response=?,sent=0 WHERE id=?',(json.dumps(notice),job))
            except (ValueError,KeyError,IndexError,TypeError,ReviewConflict):
                msg=event.get('callback_query',{}).get('message') or event.get('message',{})
                result={'chat_id':msg.get('chat',{}).get('id'),'text':'Could not apply that request. Reopen /review RECEIPT_ID and check the value; detailed edits are available in the laptop app.'}
                with self.connect() as c:c.execute("UPDATE inbox SET status='done',response=? WHERE id=?",(json.dumps(result),job))
        with self.connect() as c:outbox=c.execute("SELECT id,response FROM inbox WHERE response IS NOT NULL AND sent=0 ORDER BY id LIMIT 20").fetchall()
        for job,raw in outbox:
            payload=json.loads(raw)
            if payload and payload.get('chat_id'):
                try:self.client.call('sendMessage',**payload)
                except TransportError:continue
            with self.connect() as c:c.execute('UPDATE inbox SET sent=1 WHERE id=?',(job,))
            with self.connect() as c:event=json.loads(c.execute('SELECT event FROM inbox WHERE id=?',(job,)).fetchone()[0])
            if event.get('callback_query'):
                try:self.client.call('answerCallbackQuery',callback_query_id=event['callback_query']['id'])
                except (TransportError,KeyError):pass
    def sync(self):
        if self.cloud is None:return
        from .cloud import tables
        fingerprint=hashlib.sha256(json.dumps(tables(self.store),sort_keys=True).encode()).hexdigest()
        with self.connect() as c:
            previous=c.execute("SELECT value FROM state WHERE key='cloud_hash'").fetchone()
            next_try=c.execute("SELECT value FROM state WHERE key='cloud_next_try'").fetchone()
        if next_try and float(next_try[0])>time.time():return
        if previous and previous[0]==fingerprint:return
        try:self.cloud.sync(self.store)
        except Exception:
            with self.connect() as c:
                c.execute("INSERT OR REPLACE INTO state VALUES ('cloud_status','retry_needed')")
                c.execute("INSERT OR REPLACE INTO state VALUES ('cloud_next_try',?)",(str(time.time()+60),))
            return
        with self.connect() as c:
            c.execute("INSERT OR REPLACE INTO state VALUES ('cloud_hash',?)",(fingerprint,))
            c.execute("INSERT OR REPLACE INTO state VALUES ('cloud_status','ready')")
            c.execute("DELETE FROM state WHERE key='cloud_next_try'")
    def loop(self,once=False):
        # One poller per inbox; crashes never acknowledge an update before persistence.
        with exclusive(self.db):
            if self.local is not None:self.local.start()
            try:
                while True:
                    with self.connect() as c:offset=int(c.execute("SELECT value FROM state WHERE key='offset'").fetchone()[0])
                    try:self.ingest(self.client.call('getUpdates',offset=offset,timeout=20,allowed_updates=['message','callback_query']))
                    except TransportError:
                        if once:return
                        time.sleep(5)
                    self.process();self.sync()
                    if once:
                        if self.local is not None:self.local.flush()
                        return
            finally:
                if self.local is not None:
                    self.local.stop.set()
                    if self.local.thread is not None:self.local.thread.join(timeout=3)
