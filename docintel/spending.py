"""Conservative receipt-level grouping; suggestions are never confirmed automatically."""
from collections import Counter
from decimal import Decimal
import re

CATEGORIES=("Unclassified","Groceries","Dining","Transport","Shopping","Health & personal care","Travel & accommodation","Utilities","Office & business","Other")
RULES=(("Groceries",r"\b(grocery|groceries|supermarket)\b"),("Dining",r"\b(cafe|coffee|restaurant|dining|pizza)\b"),("Transport",r"\b(taxi|transit|parking|fuel|petrol)\b"),("Health & personal care",r"\b(pharmacy|drugstore|clinic|cosmetics)\b"),("Travel & accommodation",r"\b(hotel|resort|airline)\b"),("Utilities",r"\b(electricity|water bill|broadband)\b"),("Office & business",r"\b(office supplies|stationery)\b"),("Shopping",r"\b(clothing|apparel|electronics)\b"))

def suggest_category(result):
    text=result.get("transcript","")
    vendor=result.get("fields",{}).get("vendor",{}).get("value") or ""
    matches=[category for category,pattern in RULES if re.search(pattern,vendor+"\n"+text,re.I)]
    return {"category":matches[0] if len(matches)==1 else "Unclassified","method":"keyword heuristic","needs_confirmation":True,"reason":"One category keyword matched; check mixed purchases." if len(matches)==1 else "No clear single category; choose a group."}

def summarize(documents):
    groups={};excluded=Counter();seen_sources=set();seen_bills=set();included=0
    # Prefer the most reviewed extraction of identical source bytes.
    documents=sorted(documents,key=lambda d:d.get("review",{}).get("revision",0),reverse=True)
    for d in documents:
        source=d["source_sha256"]
        if source in seen_sources:
            excluded["same_source_duplicate"]+=1;continue
        seen_sources.add(source)
        fields=d["fields"];values=d["effective_fields"];spend=d.get("spending",{})
        if any(not fields.get(k,{}).get("human_review") or values.get(k) is None for k in ("total","currency")):
            excluded["total_or_currency_not_reviewed"]+=1;continue
        item_mode=bool(d.get('items'))
        if not item_mode and not spend.get("category"):
            excluded["category_not_saved"]+=1;continue
        if item_mode and d.get('item_reconciliation',{}).get('status')!='matched':
            excluded['items_not_reviewed_or_reconciled']+=1;continue
        if any(i["code"]=="reviewed_arithmetic_mismatch" for i in d.get("effective_issues",[])):
            excluded["amounts_do_not_add_up"]+=1;continue
        amount=Decimal(values["total"])
        if amount<0:
            excluded["negative_total_needs_separate_refund_handling"]+=1;continue
        # Different photographs of the same bill can otherwise inflate spend.
        identity=tuple(values.get(k) for k in ("vendor","invoice_id","invoice_date","currency","total"))
        if all(identity):
            if identity in seen_bills:
                excluded["possible_duplicate_bill"]+=1;continue
            seen_bills.add(identity)
        date_review=fields.get("invoice_date",{}).get("human_review")
        month=values["invoice_date"][:7] if date_review and values.get("invoice_date") else "Date not reviewed"
        allocations=d['item_reconciliation']['allocations'] if item_mode else [{'category':spend['category'],'amount':str(amount)}]
        for allocation in allocations:
            key=(allocation['category'],values['currency'],month)
            group=groups.setdefault(key,{'category':key[0],'currency':key[1],'month':key[2],'total':Decimal(0),'receipts':0})
            group['total']+=Decimal(allocation['amount']);group['receipts']+=1
        included+=1
    return {"groups":[{**v,"total":format(v["total"],".2f")} for _,v in sorted(groups.items())],"included_receipts":included,"excluded":dict(excluded),"scope":"reviewed receipt or reconciled item spend; no exchange-rate conversion"}
