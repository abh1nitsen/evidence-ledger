"""Versioned, evidence-bound numeric view over immutable saved model output."""
import copy
import re
from .core import AMOUNTS,NUMBER_FORMAT_VERSION,canonical
from .items import money,quantity


def number_view(original):
    result=copy.deepcopy(original)
    result['number_format_version']=NUMBER_FORMAT_VERSION
    text=result.get('transcript','')
    for key in AMOUNTS:
        field=result.get('fields',{}).get(key)
        if not field or field.get('proposal_value') is not None:continue
        raw=field.get('candidate');quote=field.get('candidate_quote')
        if not raw or not quote or quote not in text:continue
        try:
            value=canonical(key,raw)
            if canonical(key,quote)!=value:continue
        except ValueError:continue
        field['proposal_value']=value
        field['normalization']={'version':NUMBER_FORMAT_VERSION,'raw':raw,'source':'saved quoted candidate'}
        # Keep the original validation result and uncalibrated score; review is required.
    for item in result.get('items',[]):
        quote=item.get('quote');issues=item.get('issues',[])
        if not quote or quote not in text:continue
        raw_numbers=item.get('raw_numbers',{})
        recovered={}
        for key,parser in (('amount',money),('unit_price',money),('quantity',quantity)):
            if item.get(key) is not None or key+'_format' not in issues:continue
            raw=raw_numbers.get(key)
            if raw is None and key=='amount':raw=item.get('amount_quote')
            if raw is None and key=='quantity':
                matches=re.findall(r'(?<![\w.,])(\d+(?:\.\d{1,3})?\s*[xX\u00d7])(?!\w)',quote)
                if len(matches)==1:raw=matches[0]
            if not raw or raw not in quote:continue
            if key=='amount' and not (item.get('amount_quote') and item['amount_quote'] in text and raw in item['amount_quote']):continue
            try:value=parser(raw)
            except ValueError:continue
            item[key]=value;issues.remove(key+'_format')
            recovered[key]={'raw':raw,'value':value}
        if recovered:item['normalization']={'version':NUMBER_FORMAT_VERSION,'recovered':recovered}
    return result
