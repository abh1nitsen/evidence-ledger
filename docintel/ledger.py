"""Durable local Excel projection. SQLite remains the authoritative receipt store."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
from decimal import Decimal, InvalidOperation
from .pipeline import exclusive


def number(value):
    try:
        n=Decimal(str(value))
        return float(n) if n.is_finite() else None
    except (InvalidOperation,ValueError):return None


def projection(store):
    with store.connect() as c:
        ids=[r[0] for r in c.execute('SELECT id FROM documents ORDER BY rowid DESC')]
    documents={identity:store.get(identity) for identity in ids}
    summary=store.spending_summary()
    receipts=[];items=[]
    for row in summary['receipts']:
        doc=documents[row['document_id']];fields=doc['fields'];values=doc['effective_fields']
        def candidate(key):
            f=fields.get(key,{})
            return values.get(key) if f.get('human_review') else f.get('proposal_value')
        key=hashlib.sha256(store.member_key(doc).encode()).hexdigest()
        receipts.append([doc['member'],row['date'],row['vendor'],candidate('invoice_id'),row['currency'],number(row['total']),number(row['total']) if row['status']=='included' else None,'Confirmed' if row['date_confirmed'] else 'Needs review',row['status'],row['reason'],row['page_count'],key,row['document_id']])
        for item in doc.get('items',[]):
            human=item.get('human_review');v=human['value'] if human else item
            state='Rejected' if human and v is None else 'Reviewed' if human else 'Needs review'
            v=v or {}
            # Only reviewed, reconciled, non-payment lines are eligible for reporting.
            confirmed=row['status']=='included' and state=='Reviewed' and v.get('kind')!='payment'
            category=v.get('category')
            if confirmed and v.get('kind')=='discount' and v.get('discount_for') is not None:
                target=doc['items'][v['discount_for']].get('human_review',{}).get('value')
                if target:category=target['category']
            items.append([doc['member'],row['date'],row['vendor'],v.get('label') or item.get('description'),category,number(v.get('quantity')),number(v.get('unit_price')),number(v.get('amount')),number(v.get('amount')) if confirmed else None,row['currency'],v.get('kind') or item.get('kind'),state,row['status'],item.get('description'),v.get('code'),item.get('page_index',0)+1,key+':'+item['id'],row['document_id']])
    return {'receipts':receipts,'items':items,'totals':summary['totals'],'needs_review':summary['needs_review']}


def runtime():
    base=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
    node=Path(os.environ.get('LEDGER_NODE',base/'bin/node.exe' if os.name=='nt' else base/'bin/node'))
    modules=Path(os.environ.get('LEDGER_ARTIFACT_MODULES',base/'node_modules'))
    if not node.is_file() or not (modules/'@oai/artifact-tool').is_dir():
        raise RuntimeError('excel_runtime_unavailable')
    return node,modules


def render(data,target):
    node,modules=runtime()
    with tempfile.TemporaryDirectory(prefix='ledger-',dir=target.parent) as directory:
        source=Path(directory)/'snapshot.json';source.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        outcome=subprocess.run([str(node),str(Path(__file__).with_name('ledger_export.mjs')),str(source),str(target),str(modules)],capture_output=True,timeout=120)
        if outcome.returncode:raise RuntimeError('excel_render_failed')


class LocalLedger:
    def __init__(self,store,renderer=render):
        self.store=store;self.renderer=renderer;self.path=store.path.parent/'purchase-ledger.xlsx'
        self.lock=threading.Lock();self.stop=threading.Event();self.thread=None
        with store.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS ledger_state (id INTEGER PRIMARY KEY, generation INTEGER, exported INTEGER, error TEXT)')
            c.execute("INSERT OR IGNORE INTO ledger_state (id,generation,exported,error) VALUES (1,1,0,NULL)")
            if 'checksum' not in {r[1] for r in c.execute('PRAGMA table_info(ledger_state)')}:
                c.execute('ALTER TABLE ledger_state ADD COLUMN checksum TEXT')
            for table in ('documents','decisions','spending_groups','item_decisions','household_members'):
                for operation in ('INSERT','UPDATE','DELETE'):
                    c.execute(f'CREATE TRIGGER IF NOT EXISTS ledger_{table}_{operation} AFTER {operation} ON {table} BEGIN UPDATE ledger_state SET generation=generation+1 WHERE id=1; END')
    def status(self):
        with self.store.connect() as c:
            g,e,error,checksum=c.execute('SELECT generation,exported,error,checksum FROM ledger_state WHERE id=1').fetchone()
        exists=checksum is not None and checksum==self.checksum()
        return {'state':'ready' if exists and g==e else 'retry_needed' if error else 'updating','error':error,'download_url':'/api/ledger/download' if exists and g==e else None,'filename':self.path.name}
    def checksum(self):
        try:return hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError:return None
    def flush(self):
        with self.lock, exclusive(self.path):
            with self.store.connect() as c:
                generation,exported,error,checksum=c.execute('SELECT generation,exported,error,checksum FROM ledger_state WHERE id=1').fetchone()
            if generation==exported and checksum is not None and checksum==self.checksum():return
            # Errors require an explicit retry, rather than repeatedly hammering a locked file.
            if error:return
            # Unique staging prevents a surviving renderer child from overwriting a
            # restarted export after its parent's OS lock has been released.
            target=None
            try:
                with tempfile.NamedTemporaryFile(prefix='purchase-ledger-',suffix='.tmp.xlsx',dir=self.path.parent,delete=False) as stage:
                    target=Path(stage.name)
                data=projection(self.store)
                with self.store.connect() as c:
                    if c.execute('SELECT generation FROM ledger_state WHERE id=1').fetchone()[0]!=generation:return
                self.renderer(data,target)
                if not target.is_file() or target.stat().st_size==0:raise RuntimeError('excel_render_failed')
                with target.open('r+b') as stream:os.fsync(stream.fileno())
                exported_checksum=hashlib.sha256(target.read_bytes()).hexdigest()
                with self.store.connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    if c.execute('SELECT generation FROM ledger_state WHERE id=1').fetchone()[0]!=generation:return
                    os.replace(target,self.path)
                    c.execute('UPDATE ledger_state SET exported=?,checksum=?,error=NULL WHERE id=1',(generation,exported_checksum))
            except PermissionError:
                self.fail('close_excel_and_retry')
            except (OSError,RuntimeError,subprocess.SubprocessError):
                self.fail('excel_update_failed_check_runtime_and_retry')
            finally:
                try:
                    if target is not None:target.unlink(missing_ok=True)
                except OSError:pass
    def fail(self,error):
        with self.store.connect() as c:c.execute('UPDATE ledger_state SET error=? WHERE id=1',(error,))
    def retry(self):
        with self.store.connect() as c:c.execute('UPDATE ledger_state SET error=NULL WHERE id=1')
    def start(self):
        def worker():
            while not self.stop.is_set():
                try:self.flush()
                except (sqlite3.Error,RuntimeError,OSError,KeyError):pass
                self.stop.wait(2)
        self.thread=threading.Thread(target=worker,daemon=True);self.thread.start()

