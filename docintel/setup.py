"""Offline setup diagnostics and guarded creation of a new shared household ledger."""
import importlib.util
import json
from pathlib import Path
import re
from .pipeline import atomic_json,exclusive
from .cloud import create_sheet

def inspect_setup(config):
    checks={}
    for key in ('telegram_token_file','groq_key_file','google_token_file'):
        path=config.get(key)
        state='missing'
        if isinstance(path,str) and Path(path).is_file():
            try:
                value=Path(path).read_text(encoding='utf-8').strip()
                if key=='telegram_token_file':valid=bool(re.fullmatch(r'\d+:[A-Za-z0-9_-]+',value))
                elif key=='google_token_file':
                    token=json.loads(value);valid=isinstance(token,dict) and all(token.get(k) for k in ('refresh_token','client_id','client_secret','token_uri'))
                else:valid=bool(value)
                state='present' if valid else 'invalid'
            except (OSError,ValueError):state='invalid'
        checks[key]=state
    checks['spreadsheet']='configured' if re.fullmatch(r'[A-Za-z0-9_-]+',str(config.get('spreadsheet_id',''))) else 'not_created'
    checks['members']='registered' if config.get('members') else 'awaiting_start'
    checks['google_runtime']='installed' if importlib.util.find_spec('google_auth_oauthlib') else 'missing'
    uncertain=config.get('sheet_creation_state') in ('pending','uncertain')
    if uncertain:checks['spreadsheet']='creation_uncertain_check_drive'
    return {'checks':checks,'ready_for_receipts':all(checks[k]=='present' for k in ('telegram_token_file','groq_key_file','google_token_file')) and checks['spreadsheet']=='configured' and checks['members']=='registered' and checks['google_runtime']=='installed',
            'ready_to_create_sheet':checks['google_token_file']=='present' and checks['google_runtime']=='installed' and not uncertain and checks['spreadsheet']=='not_created',
            'account_access_verified':False}

def create_household(config_file):
    config_file=Path(config_file)
    with exclusive(config_file):
        config=json.loads(config_file.read_text(encoding='utf-8'))
        identity=config.get('spreadsheet_id')
        if identity:
            if not re.fullmatch(r'[A-Za-z0-9_-]+',identity):raise ValueError('invalid_sheet_id')
            return {'created':False,'url':'https://docs.google.com/spreadsheets/d/'+identity}
        if config.get('sheet_creation_state') in ('pending','uncertain'):
            raise RuntimeError('creation_uncertain_check_drive_before_retrying')
        if not inspect_setup(config)['ready_to_create_sheet']:raise RuntimeError('google_authorization_required')
        # A lost API reply may still have created the sheet. Never blindly create another.
        config['sheet_creation_state']='pending';atomic_json(config_file,config)
        try:
            identity=create_sheet(config['google_token_file'])
        except Exception:
            config['sheet_creation_state']='uncertain';atomic_json(config_file,config)
            raise RuntimeError('creation_uncertain_check_drive_before_retrying') from None
        config['spreadsheet_id']=identity;config['sheet_creation_state']='created';atomic_json(config_file,config)
    return {'created':True,'url':'https://docs.google.com/spreadsheets/d/'+identity}
