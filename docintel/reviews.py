"""Transactional human decisions, immutable extraction snapshots and revision checks."""
import contextlib
import copy
from decimal import Decimal
import json
import re
from pathlib import Path
import sqlite3
import time
from .core import canonical
from .spending import CATEGORIES, suggest_category, summarize
from .items import reviewed_item, reconcile
from .numbers import number_view

class ReviewConflict(ValueError):
    pass

class ReviewStore:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.execute("CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, original TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0)")
            c.execute("CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL, field TEXT NOT NULL, action TEXT NOT NULL, value TEXT, timestamp REAL NOT NULL, revision INTEGER NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS spending_groups (id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL, category TEXT NOT NULL, tags TEXT NOT NULL, timestamp REAL NOT NULL, revision INTEGER NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS item_decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL, item_id TEXT NOT NULL, action TEXT NOT NULL, value TEXT, timestamp REAL NOT NULL, revision INTEGER NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS household_members (source TEXT PRIMARY KEY, name TEXT NOT NULL)")
            c.execute("CREATE TABLE IF NOT EXISTS member_history (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, name TEXT, timestamp REAL, document_id TEXT, revision INTEGER)")
    @contextlib.contextmanager
    def connect(self):
        with contextlib.closing(sqlite3.connect(self.path,timeout=5)) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=FULL")
            with c:
                yield c
    def register(self,identity,result):
        original=copy.deepcopy(result)
        original.pop("download_url",None)
        original.pop("checkpoint",None)
        with self.connect() as c:
            c.execute("INSERT OR IGNORE INTO documents (id,original) VALUES (?,?)",(identity,json.dumps(original,ensure_ascii=False)))
        return self.get(identity)
    def get(self,identity):
        with self.connect() as c:
            c.execute("BEGIN")
            row=c.execute("SELECT original,revision FROM documents WHERE id=?",(identity,)).fetchone()
            if not row: raise KeyError("unknown document")
            history=c.execute("SELECT field,action,value,timestamp,revision FROM decisions WHERE document_id=? ORDER BY revision",(identity,)).fetchall()
            groups=c.execute("SELECT category,tags,timestamp,revision FROM spending_groups WHERE document_id=? ORDER BY revision",(identity,)).fetchall()
            item_history=c.execute("SELECT item_id,action,value,timestamp,revision FROM item_decisions WHERE document_id=? ORDER BY revision",(identity,)).fetchall()
        result=number_view(json.loads(row[0])); result["review"]={"document_id":identity,"revision":row[1],"history":[]}
        with self.connect() as c:
            member=c.execute('SELECT name FROM household_members WHERE source=?',(self.member_key(result),)).fetchone()
            member_history=c.execute('SELECT name,timestamp,document_id,revision FROM member_history WHERE source=? ORDER BY id',(self.member_key(result),)).fetchall()
        result['member']=member[0] if member else 'Unassigned'
        result['member_history']=[dict(zip(('name','timestamp','document_id','revision'),m)) for m in member_history]
        for field,action,value,stamp,revision in history:
            result["fields"][field]["human_review"]={"action":action,"value":value,"revision":revision}
            result["review"]["history"].append({"field":field,"action":action,"value":value,"timestamp":stamp,"revision":revision})
        result.setdefault("items",[])
        result["item_review_history"]=[]
        for item_id,action,value,stamp,revision in item_history:
            item=next(i for i in result["items"] if i['id']==item_id)
            decoded=json.loads(value) if value is not None else None
            item['human_review']={'action':action,'value':decoded,'revision':revision}
            result['item_review_history'].append({'item_id':item_id,'action':action,'value':decoded,'timestamp':stamp,'revision':revision})
        result["spending"]={"suggestion":suggest_category(result),"category":groups[-1][0] if groups else None,"tags":json.loads(groups[-1][1]) if groups else [],"history":[{"category":g[0],"tags":json.loads(g[1]),"timestamp":g[2],"revision":g[3]} for g in groups]}
        result["effective_fields"]={k:(f["human_review"]["value"] if f.get("human_review") else f["value"]) for k,f in result["fields"].items()}
        result["review"]["status"]="reviewed" if all(f.get("human_review") for f in result["fields"].values() if f.get("required") or f.get("proposal_value") is not None) and all(i.get('human_review') for i in result['items']) else "pending"
        result["effective_issues"]=[]
        for key,f in result["fields"].items():
            if f.get("required") and result["effective_fields"][key] is None:
                result["effective_issues"].append({"field":key,"code":"missing_required_field"})
        amounts=result["effective_fields"]
        for names in (("subtotal","tax","total"),("base_amount","tip","total")):
            if all(amounts.get(k) is not None for k in names):
                if Decimal(amounts[names[0]])+Decimal(amounts[names[1]])!=Decimal(amounts[names[2]]):
                    result["effective_issues"].append({"field":"total","code":"reviewed_arithmetic_mismatch"})
        result["item_reconciliation"]=reconcile(result)
        # Human review is distinct from machine validation and payment approval.
        if history:
            result["decision"]="review"
        return result
    @staticmethod
    def member_key(result):
        return '|'.join(sorted(p['source_sha256'] for p in result['pages'])) if result.get('pages') else result['source_sha256']

    def member(self,identity,name,revision):
        if not isinstance(name,str) or not name.strip() or len(name.strip())>80 or any(ord(ch)<32 for ch in name):
            raise ValueError('invalid member name')
        if not isinstance(revision,int) or isinstance(revision,bool): raise ValueError('invalid revision')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT original,revision FROM documents WHERE id=?',(identity,)).fetchone()
            if not row:raise KeyError('unknown document')
            if row[1]!=revision:raise ReviewConflict('stale review revision')
            c.execute('INSERT OR REPLACE INTO household_members VALUES (?,?)',(self.member_key(json.loads(row[0])),name.strip()))
            c.execute('INSERT INTO member_history (source,name,timestamp,document_id,revision) VALUES (?,?,?,?,?)',(self.member_key(json.loads(row[0])),name.strip(),time.time(),identity,revision+1))
            c.execute('UPDATE documents SET revision=revision+1 WHERE id=?',(identity,))
        return self.get(identity)
    def recent(self):
        with self.connect() as c:
            rows=c.execute("SELECT id,original,revision FROM documents ORDER BY rowid DESC LIMIT 100").fetchall()
        items=[];seen=set()
        for identity,raw,revision in rows:
            result=json.loads(raw);source=result["source_sha256"]
            seen.add(source)
            vendor=result["fields"].get("vendor",{}).get("value") or "Unnamed document"
            items.append({"document_id":identity,"vendor":vendor,"document_type":result.get("document_type","unknown"),"revision":revision,"page_count":len(result.get("pages",[])) or 1,"item_count":len(result.get("items",[]))})
            if len(items)==20: break
        return items

    def decide(self,identity,field,action,value,revision):
        if action not in {"accept","reject","edit"} or not isinstance(revision,int) or isinstance(revision,bool):
            raise ValueError("invalid review action")
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT original,revision FROM documents WHERE id=?",(identity,)).fetchone()
            if not row: raise KeyError("unknown document")
            original=number_view(json.loads(row[0]))
            if field not in original["fields"]: raise ValueError("unknown field")
            if row[1]!=revision: raise ReviewConflict("stale review revision")
            if action=="accept":
                value=original["fields"][field].get("proposal_value")
                if value is None: raise ValueError("no supported candidate to accept")
            elif action=="reject": value=None
            else:
                if not isinstance(value,str) or len(value)>200: raise ValueError("invalid edited value")
                if field=="invoice_date" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):
                    raise ValueError("edited dates require explicit four-digit ISO year")
                value=canonical(field,value)
            next_revision=revision+1
            c.execute("INSERT INTO decisions (document_id,field,action,value,timestamp,revision) VALUES (?,?,?,?,?,?)",(identity,field,action,value,time.time(),next_revision))
            c.execute("UPDATE documents SET revision=? WHERE id=?",(next_revision,identity))
        return self.get(identity)

    def group(self,identity,category,tags,revision):
        if category not in CATEGORIES or not isinstance(revision,int) or isinstance(revision,bool):
            raise ValueError("invalid spending group")
        if not isinstance(tags,list) or len(tags)>8 or any(not isinstance(t,str) or not t.strip() or len(t)>30 or any(ord(ch)<32 for ch in t) for t in tags):
            raise ValueError("invalid tags")
        tags=list(dict.fromkeys(t.strip().lower() for t in tags))
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT revision FROM documents WHERE id=?",(identity,)).fetchone()
            if not row: raise KeyError("unknown document")
            if row[0]!=revision: raise ReviewConflict("stale review revision")
            c.execute("INSERT INTO spending_groups (document_id,category,tags,timestamp,revision) VALUES (?,?,?,?,?)",(identity,category,json.dumps(tags),time.time(),revision+1))
            c.execute("UPDATE documents SET revision=? WHERE id=?",(revision+1,identity))
        return self.get(identity)

    def spending_summary(self):
        with self.connect() as c:
            identities=[x[0] for x in c.execute("SELECT id FROM documents ORDER BY rowid DESC")]
        return summarize([self.get(identity) for identity in identities])

    def decide_item(self,identity,item_id,action,values,revision):
        if not isinstance(item_id,str) or not isinstance(revision,int) or isinstance(revision,bool):raise ValueError('invalid item review')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT original,revision FROM documents WHERE id=?',(identity,)).fetchone()
            if not row:raise KeyError('unknown document')
            if row[1]!=revision:raise ReviewConflict('stale review revision')
            original=number_view(json.loads(row[0]));items=original.get('items',[])
            item=next((i for i in items if i['id']==item_id),None)
            if item is None:raise ValueError('unknown item')
            edited=reviewed_item(item,action,values)
            if edited is not None:
                target=edited['discount_for']
                if target is not None and (not isinstance(target,int) or isinstance(target,bool) or not 0<=target<len(items) or str(target)==item_id or edited['kind']!='discount'):raise ValueError('invalid discount link')
            c.execute('INSERT INTO item_decisions (document_id,item_id,action,value,timestamp,revision) VALUES (?,?,?,?,?,?)',(identity,item_id,action,json.dumps(edited) if edited is not None else None,time.time(),revision+1))
            c.execute('UPDATE documents SET revision=? WHERE id=?',(revision+1,identity))
        return self.get(identity)

    def chain(self,identities):
        from .pages import combine
        if not isinstance(identities,list) or any(not isinstance(i,str) or not re.fullmatch(r'[a-f0-9]{64}',i) for i in identities):raise ValueError('invalid page identities')
        pages=[self.get(i) for i in identities]
        identity,result=combine(pages,identities)
        saved=self.register(identity,result)
        members={p['member'] for p in pages}
        if saved['member']=='Unassigned' and len(members)==1 and 'Unassigned' not in members:
            saved=self.member(identity,members.pop(),saved['review']['revision'])
        return saved
