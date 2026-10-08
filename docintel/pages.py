"""Ordered receipt pages; explicit grouping with reversible overlap decisions."""
import copy
from .core import VERSION,digest


def combine(readings,identities):
    if not 2<=len(readings)<=10:raise ValueError('receipt needs 2 to 10 pages')
    if len(set(identities))!=len(identities):raise ValueError('same page cannot be added twice')
    if any(r.get('source_type')!='image' or r.get('pages') for r in readings):raise ValueError('only single image readings can be grouped')
    if len({r['source_sha256'] for r in readings})!=len(readings):raise ValueError('identical image bytes are a repeated page')
    result=copy.deepcopy(readings[0])
    for key in ('review','spending','item_review_history','item_reconciliation','effective_fields','effective_issues','download_url','checkpoint','ocr','image'):result.pop(key,None)
    result['source_sha256']=digest('ordered-pages:'+':'.join(r['source_sha256'] for r in readings))
    result['pages']=[{'number':n+1,'document_id':identities[n],'source_sha256':r['source_sha256'],'image':r['image'],'ocr':r.get('ocr'),'transcript':r['transcript']} for n,r in enumerate(readings)]
    result['transcript']='\n\n'.join('PAGE '+str(n+1)+'\n'+r['transcript'] for n,r in enumerate(readings))
    offsets=[];position=0
    for n,r in enumerate(readings):
        offsets.append(position+len('PAGE '+str(n+1)+'\n'));position+=len('PAGE '+str(n+1)+'\n'+r['transcript'])+2
    result['issues']=[{'field':'document','code':'page_chain_needs_review'}]
    result['items']=[]
    for key in result['fields']:
        candidates=[(n,r['fields'][key]) for n,r in enumerate(readings) if r['fields'][key].get('proposal_value') is not None]
        # Tail amounts and first header are proposals, never automatic approval.
        n,f=candidates[-1 if key in {'total','subtotal','tax','base_amount','tip'} else 0] if candidates else (0,readings[0]['fields'][key])
        result['fields'][key]=copy.deepcopy(f);result['fields'][key].pop('human_review',None);result['fields'][key]['page_index']=n
        field=result['fields'][key]
        shifted=set()
        for span in field.get('spans',[])+([field['span']] if field.get('span') else []):
            if id(span) not in shifted:span['start']+=offsets[n];span['end']+=offsets[n];shifted.add(id(span))
        if len({f.get('proposal_value') for _,f in candidates})>1:
            result['fields'][key]['value']=None;result['fields'][key]['state']='needs_review';result['fields'][key]['review_score']['forced_review']=True;result['fields'][key]['review_score']['value']=min(.49,result['fields'][key]['review_score']['value'])
            result['issues'].append({'field':key,'code':'conflicting_page_values'})
    seen={}
    for n,r in enumerate(readings):
        offset=len(result['items'])
        for p in r.get('items',[]):
            item=copy.deepcopy(p);item.pop('human_review',None);item['id']=str(len(result['items']));item['page_index']=n
            if item['discount_for'] is not None:item['discount_for']+=offset
            fingerprint=(item['description'],item['code'],item['amount'],item['kind'])
            if fingerprint in seen and seen[fingerprint][0]!=n:
                item['issues'].append('possible_page_overlap');item['possible_duplicate_of']=seen[fingerprint][1]
            seen[fingerprint]=(n,item['id']);result['items'].append(item)
    if len(result['items'])>300:raise ValueError('too many receipt items')
    result['decision']='review';result['source_type']='image';result['evidence_basis']='ordered_page_evidence'
    result['page_policy']={'overlap_removed_automatically':False,'order_confirmed_by_user':True,'continuity_verified':False,'message':'Check page order, merchant/receipt identifiers and overlapping rows. Only explicitly rejected rows are excluded.'}
    identity=digest(VERSION+':page-chain:'+':'.join(identities))
    return identity,result
