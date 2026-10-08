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
        result=json.loads(row[0]); result["review"]={"document_id":identity,"revision":row[1],"history":[]}
        for field,action,value,stamp,revision in history:
            result["fields"][field]["human_review"]={"action":action,"value":value,"revision":revision}
            result["review"]["history"].append({"field":field,"action":action,"value":value,"timestamp":stamp,"revision":revision})
        result["spending"]={"suggestion":suggest_category(result),"category":groups[-1][0] if groups else None,"tags":json.loads(groups[-1][1]) if groups else [],"history":[{"category":g[0],"tags":json.loads(g[1]),"timestamp":g[2],"revision":g[3]} for g in groups]}
        result["effective_fields"]={k:(f["human_review"]["value"] if f.get("human_review") else f["value"]) for k,f in result["fields"].items()}
        result["review"]["status"]="reviewed" if all(f.get("human_review") for f in result["fields"].values() if f.get("required") or f.get("proposal_value") is not None) else "pending"
        result["effective_issues"]=[]
        for key,f in result["fields"].items():
            if f.get("required") and result["effective_fields"][key] is None:
                result["effective_issues"].append({"field":key,"code":"missing_required_field"})
        amounts=result["effective_fields"]
        for names in (("subtotal","tax","total"),("base_amount","tip","total")):
            if all(amounts.get(k) is not None for k in names):
                if Decimal(amounts[names[0]])+Decimal(amounts[names[1]])!=Decimal(amounts[names[2]]):
                    result["effective_issues"].append({"field":"total","code":"reviewed_arithmetic_mismatch"})
        # Human review is distinct from machine validation and payment approval.
        if history:
            result["decision"]="review"
        return result
    def recent(self):
        with self.connect() as c:
            rows=c.execute("SELECT id,original,revision FROM documents ORDER BY rowid DESC LIMIT 100").fetchall()
        items=[];seen=set()
        for identity,raw,revision in rows:
            result=json.loads(raw);source=result["source_sha256"]
            if source in seen: continue
            seen.add(source)
            vendor=result["fields"].get("vendor",{}).get("value") or "Unnamed document"
            items.append({"document_id":identity,"vendor":vendor,"document_type":result.get("document_type","unknown"),"revision":revision})
            if len(items)==20: break
        return items

    def decide(self,identity,field,action,value,revision):
        if action not in {"accept","reject","edit"} or not isinstance(revision,int) or isinstance(revision,bool):
            raise ValueError("invalid review action")
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT original,revision FROM documents WHERE id=?",(identity,)).fetchone()
            if not row: raise KeyError("unknown document")
            original=json.loads(row[0])
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
