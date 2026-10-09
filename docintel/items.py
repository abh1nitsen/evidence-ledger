"""Grounded line proposals, explicit human review and Decimal reconciliation."""
import copy
from decimal import Decimal
import re
from .core import canonical,receipt_amount

CATEGORIES=("Unallocated","Food / confectionery","Food / chocolate","Food / snack bars","Food / prepared food","Food / cakes & pastries","Food / groceries","Food / drinks","Personal care / lip care","Beauty / lip cosmetics","Office / stationery","Shopping / accessories","Shopping / other","Travel / accommodation","Transport","Fees / packaging","Fees / service","Taxes","Other")
KINDS=("product","service","discount","tax","payment","fee")
TEXT_KEYS=("description","label","code","quantity","unit_price","amount","quote","amount_quote")
ITEM_PROPERTIES={k:{"type":["string","null"]} for k in TEXT_KEYS}
ITEM_PROPERTIES.update(category={"type":"string","enum":list(CATEGORIES)},kind={"type":"string","enum":list(KINDS)},discount_for={"type":["integer","null"]})
ITEM_SCHEMA={"type":"array","maxItems":100,"items":{"type":"object","additionalProperties":False,"properties":ITEM_PROPERTIES,"required":list(ITEM_PROPERTIES)}}


def money(value):
    if value is None:return None
    if not isinstance(value,str) or len(value)>60:raise ValueError("invalid item amount")
    result=receipt_amount(value,allow_negative=True)
    return '0.00' if Decimal(result)==0 else result


def quantity(value):
    if value is None:return None
    if not isinstance(value,str):raise ValueError('invalid quantity')
    raw=re.sub(r'\s*[xX\u00d7]$','',value.strip()).strip()
    if not re.fullmatch(r"\d+(?:\.\d{1,3})?",raw):raise ValueError("invalid quantity")
    n=Decimal(raw)
    if not 0<n<=10000:raise ValueError("quantity outside limits")
    return format(n,'f')


def validate_items(proposed,text,ocr=None):
    if not isinstance(proposed,list) or len(proposed)>100:raise ValueError("invalid items")
    if any(not isinstance(p,dict) or set(p)!=set(ITEM_PROPERTIES) for p in proposed):raise ValueError('invalid item schema')
    items=[]
    for index,p in enumerate(proposed):
        if not isinstance(p,dict) or set(p)!=set(ITEM_PROPERTIES):raise ValueError("invalid item schema")
        if p['category'] not in CATEGORIES or p['kind'] not in KINDS:raise ValueError("invalid item metadata")
        for key in TEXT_KEYS:
            v=p[key]
            if v is not None and (not isinstance(v,str) or not v.strip() or len(v)>1000 or any(ord(c)<32 and c not in '\n\t' for c in v)):
                raise ValueError("invalid item text")
        target=p['discount_for']
        if target is not None and (not isinstance(target,int) or isinstance(target,bool) or not 0<=target<len(proposed) or target==index):raise ValueError("invalid discount target")
        if p['kind']!='discount' and target is not None:raise ValueError("target only allowed on discounts")
        if target is not None and proposed[target].get('kind') not in {'product','service'}:raise ValueError("discount target is not a purchase")
        item=copy.deepcopy(p);item['id']=str(index);issues=[]
        item['raw_numbers']={key:p[key] for key in ('amount','unit_price','quantity')}
        quote=p['quote'];grounded=bool(quote and quote in text and p['description'] and p['description'] in quote)
        if not grounded:issues.append('description_not_grounded')
        for key,normalize in (('amount',money),('unit_price',money),('quantity',quantity)):
            try:item[key]=normalize(p[key])
            except ValueError:item[key]=None;issues.append(key+'_format')
            if p[key] is not None and not (quote and quote in text and p[key] in quote):issues.append(key+'_not_in_row')
        if p['amount'] is not None and not (p['amount_quote'] and p['amount_quote'] in text and p['amount'] in p['amount_quote']):issues.append('amount_not_grounded')
        if p['code'] and not (quote and quote in text and p['code'] in quote):issues.append('code_not_grounded')
        if item['amount'] is not None and Decimal(item['amount'])<0 and p['kind']!='discount' and p['kind']!='payment':issues.append('negative_purchase_needs_review')
        if item['kind']=='discount' and item['amount'] is not None and Decimal(item['amount'])>=0:issues.append('discount_sign_needs_review')
        regions=[line for line in (ocr or {}).get('lines',[]) if p['description'] and p['description'] in line['text']][:8]
        item['ocr_evidence']=regions
        item['issues']=issues;item['state']='proposed';item['source_grounded']=grounded
        item['evidence_score']={'value':round((.5 if grounded else 0)+(.2 if item['amount'] is not None and 'amount_not_grounded' not in issues and 'amount_not_in_row' not in issues else 0)+(.2*min(x['score'] for x in regions) if regions else 0),3),'calibrated':False}
        item['classification']={'basis':'vision inference','verified_product_identity':False,'needs_confirmation':True}
        items.append(item)
    return items


def reviewed_item(original,action,values):
    if action not in {'accept','reject','edit'}:raise ValueError('invalid item action')
    if action=='reject':return None
    keys={'label','category','kind','code','quantity','unit_price','amount','discount_for'}
    if action=='accept':values={k:original[k] for k in keys}
    if not isinstance(values,dict) or set(values)!=keys:raise ValueError('invalid edited item')
    if values['category'] not in CATEGORIES or values['kind'] not in KINDS:raise ValueError('invalid category or kind')
    if not isinstance(values['label'],str) or not values['label'].strip() or len(values['label'])>200 or any(ord(c)<32 for c in values['label']):raise ValueError('invalid item label')
    if values['code'] is not None and (not isinstance(values['code'],str) or len(values['code'])>100 or any(ord(c)<32 for c in values['code'])):raise ValueError('invalid item code')
    return {**values,'amount':money(values['amount']),'unit_price':money(values['unit_price']),'quantity':quantity(values['quantity'])}


def reconcile(result):
    items=result.get('items',[]);values=result.get('effective_fields') or {k:f['value'] for k,f in result['fields'].items()}
    if not items:return {'status':'no_items','message':'No item detail available. Do not infer purchases from the merchant.','allocations':[]}
    active=[i['human_review']['value'] for i in items if i.get('human_review') and i['human_review']['value'] is not None]
    if any(not i.get('human_review') for i in items):return {'status':'pending','message':'Review every item, including discounts, fees and payments.','allocations':[]}
    if values.get('total') is None:return {'status':'missing_total','message':'A final total is needed for reconciliation; BASE and balance are not substitutes.','allocations':[]}
    purchases=[i for i in active if i['kind'] not in {'payment','tax'}]
    taxes=[i for i in active if i['kind']=='tax']
    if not purchases:return {'status':'no_purchases','message':'No reviewed purchase lines.','allocations':[]}
    if any(i['amount'] is None for i in purchases+taxes):return {'status':'missing_amount','message':'A reviewed item amount is missing.','allocations':[]}
    total=Decimal(values['total']);net=sum((Decimal(i['amount']) for i in purchases),Decimal(0));tax=sum((Decimal(i['amount']) for i in taxes),Decimal(0))
    # Never multiply a printed line amount by quantity again.
    allocations=list(purchases);basis='printed line amounts already include tax'
    if net!=total:
        if taxes and net+tax==total:
            allocations+=taxes;basis='printed tax lines added once'
        elif not taxes and result['fields'].get('tax',{}).get('human_review') and values.get('tax') is not None and net+Decimal(values['tax'])==total:
            allocations.append({'kind':'tax','category':'Taxes','amount':values['tax'],'label':'Reviewed receipt tax','discount_for':None});basis='reviewed receipt tax added once'
        else:return {'status':'mismatch','message':'Reviewed item amounts do not reconcile with the final total.','line_sum':format(net,'.2f'),'final_total':format(total,'.2f'),'allocations':[]}
    grouped={}
    for i in allocations:
        category=i['category']
        if i['kind']=='discount':
            target=i.get('discount_for')
            linked=next((j.get('human_review',{}).get('value') for j in items if j['id']==str(target)),None) if target is not None else None
            if target is not None and (not linked or linked['kind'] not in {'product','service'}):return {'status':'invalid_discount_target','message':'The linked purchase was rejected or changed. Correct the discount target or clear it and confirm a basket category.','allocations':[]}
            if linked:category=linked['category']
            elif category=='Unallocated':return {'status':'unallocated_discount','message':'Assign the discount to a purchase or confirm its spending category.','allocations':[]}
        grouped[category]=grouped.get(category,Decimal(0))+Decimal(i['amount'])
    if any(v<0 for v in grouped.values()):return {'status':'negative_category','message':'A category has a negative allocation; review discount assignment.','allocations':[]}
    return {'status':'matched','message':'Reviewed item amounts reconcile exactly.','basis':basis,'final_total':format(total,'.2f'),'allocations':[{'category':k,'amount':format(v,'.2f')} for k,v in sorted(grouped.items())]}
