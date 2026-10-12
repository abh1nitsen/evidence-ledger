"""Atomic snapshots into dedicated Google Sheets tabs; local reviews stay authoritative."""
import json
from pathlib import Path
from .ledger import projection

SCOPE='https://www.googleapis.com/auth/spreadsheets'
MARKER='Evidence Ledger generated v1 — review in the app; edits here are replaced'
HEADERS={
 'EL Receipts':['Member','Date','Merchant','Receipt number','Currency','Read total','Confirmed total','Date review','Status','Reason','Pages','Source key','Document ID'],
 'EL Purchases':['Member','Date','Merchant','Item','Category','Quantity','Unit price','Read amount','Confirmed amount','Currency','Kind','Item review','Receipt status','Printed description','Code','Page','Source key','Document ID'],
 'EL Overview':['Currency','Confirmed spending']}

def tables(store):
    data=projection(store)
    return {'EL Receipts':data['receipts'],'EL Purchases':data['items'],
            'EL Overview':[[r['currency'],float(r['total'])] for r in data['totals']]}

def requests_for(metadata, data):
    """Only overwrite tabs carrying our explicit ownership marker. RAW string cells prevent formulas."""
    existing={s['properties']['title']:s for s in metadata.get('sheets',[])}
    used={s['properties']['sheetId'] for s in existing.values()}; requests=[]
    for title,values in data.items():
        sheet=existing.get(title)
        matrix=[[MARKER],HEADERS[title],*values]
        rows=max(len(matrix),3);cols=len(HEADERS[title])
        if sheet:
            marker=sheet.get('data',[{}])[0].get('rowData',[{}])[0].get('values',[{}])[0].get('formattedValue')
            if marker!=MARKER:raise ValueError('cloud_tab_not_owned')
            sid=sheet['properties']['sheetId']
            requests.append({'updateSheetProperties':{'properties':{'sheetId':sid,'gridProperties':{'rowCount':max(rows,sheet['properties']['gridProperties']['rowCount']),'columnCount':max(cols,sheet['properties']['gridProperties']['columnCount']),'frozenRowCount':2}},'fields':'gridProperties'}})
        else:
            sid=1
            while sid in used:sid+=1
            used.add(sid)
            requests.append({'addSheet':{'properties':{'sheetId':sid,'title':title,'gridProperties':{'rowCount':rows,'columnCount':cols,'frozenRowCount':2}}}})
        def cell(v):
            if v is None:return {}
            return {'userEnteredValue':{'numberValue':v} if isinstance(v,(int,float)) else {'stringValue':str(v)}}
        # A range covering the whole tab clears stale generated cells in the same atomic batch.
        requests.append({'updateCells':{'range':{'sheetId':sid},'rows':[{'values':[cell(v) for v in row]} for row in matrix],'fields':'userEnteredValue'}})
        requests.append({'repeatCell':{'range':{'sheetId':sid,'startRowIndex':1,'endRowIndex':2},'cell':{'userEnteredFormat':{'backgroundColor':{'red':.06,'green':.46,'blue':.43},'textFormat':{'bold':True,'foregroundColor':{'red':1,'green':1,'blue':1}}}},'fields':'userEnteredFormat'}})
    return requests

class Sheets:
    def __init__(self,token_file,spreadsheet_id):
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]+',spreadsheet_id):raise ValueError('invalid_sheet_id')
        self.token_file=Path(token_file);self.id=spreadsheet_id
    def sync(self,store):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import AuthorizedSession,Request
        creds=Credentials.from_authorized_user_file(str(self.token_file),[SCOPE])
        if not creds.valid:
            creds.refresh(Request())
            self.token_file.write_bytes(creds.to_json().encode())
        session=AuthorizedSession(creds);url='https://sheets.googleapis.com/v4/spreadsheets/'+self.id
        with session:
            response=session.get(url,timeout=30)
            response.raise_for_status();meta=response.json()
            # Read ownership markers individually; missing tabs require no reads.
            for sheet in meta.get('sheets',[]):
                title=sheet['properties']['title']
                if title in HEADERS:
                    r=session.get(url,params={'includeGridData':'true','ranges':"'"+title+"'!A1"},timeout=30)
                    r.raise_for_status()
                    sheet['data']=r.json()['sheets'][0]['data']
            batch=requests_for(meta,tables(store))
            response=session.post(url+':batchUpdate',json={'requests':batch},timeout=60)
            response.raise_for_status()
        return {'state':'ready','url':'https://docs.google.com/spreadsheets/d/'+self.id}

def authorize(client_file,token_file):
    from google_auth_oauthlib.flow import InstalledAppFlow
    token=Path(token_file);token.parent.mkdir(parents=True,exist_ok=True)
    flow=InstalledAppFlow.from_client_secrets_file(str(client_file),[SCOPE])
    creds=flow.run_local_server(port=0)
    token.write_bytes(creds.to_json().encode())
