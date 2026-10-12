import contextlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from docintel.cloud import create_sheet,HEADERS,MARKER
from docintel.setup import create_household,inspect_setup

class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.config=self.root/'private.json'
        self.data={'google_token_file':str(self.root/'missing.json'),'spreadsheet_id':'','members':{}}
        self.config.write_text(json.dumps(self.data),encoding='utf-8')
    def test_offline_diagnostic_never_exposes_secret_or_claims_live_access(self):
        secret=self.root/'groq.txt';secret.write_text('do-not-print-this',encoding='utf-8')
        result=inspect_setup({**self.data,'groq_key_file':str(secret)})
        self.assertEqual(result['checks']['groq_key_file'],'present')
        self.assertFalse(result['ready_for_receipts']);self.assertFalse(result['account_access_verified'])
        self.assertNotIn('do-not-print-this',json.dumps(result));self.assertNotIn(str(secret),json.dumps(result))
    def test_local_readiness_does_not_require_google(self):
        bot=self.root/'bot.txt';bot.write_text('123456:'+('x'*30),encoding='utf-8')
        groq=self.root/'groq.txt';groq.write_text('authored-stand-in',encoding='utf-8')
        with patch('docintel.setup.excel_runtime',return_value=(Path('node'),Path('modules'))):
            result=inspect_setup({**self.data,'telegram_token_file':str(bot),'groq_key_file':str(groq),'members':{'101':'Member A'}})
        self.assertTrue(result['ready_for_receipts']);self.assertTrue(result['ready_for_local_receipts'])
        self.assertFalse(result['ready_for_shared_receipts']);self.assertFalse(result['account_access_verified'])
    def test_creation_remembers_id_and_second_call_does_not_create_again(self):
        with patch('docintel.setup.inspect_setup',return_value={'ready_to_create_sheet':True}),patch('docintel.setup.create_sheet',return_value='sample_sheet_id') as create:
            first=create_household(self.config);second=create_household(self.config)
        self.assertTrue(first['created']);self.assertFalse(second['created']);self.assertEqual(create.call_count,1)
        saved=json.loads(self.config.read_text(encoding='utf-8'));self.assertEqual(saved['spreadsheet_id'],'sample_sheet_id')
    def test_uncertain_delivery_prevents_blind_recreation(self):
        with patch('docintel.setup.inspect_setup',return_value={'ready_to_create_sheet':True}),patch('docintel.setup.create_sheet',side_effect=TimeoutError) as create:
            with self.assertRaises(RuntimeError):create_household(self.config)
            with self.assertRaises(RuntimeError):create_household(self.config)
        self.assertEqual(create.call_count,1)
        saved=json.loads(self.config.read_text(encoding='utf-8'));self.assertEqual(saved['sheet_creation_state'],'uncertain')
    def test_pending_crash_state_requires_inspection_and_missing_auth_makes_no_request(self):
        with patch('docintel.setup.create_sheet') as create:
            with self.assertRaises(RuntimeError):create_household(self.config)
            self.config.write_text(json.dumps({**self.data,'sheet_creation_state':'pending'}),encoding='utf-8')
            with self.assertRaises(RuntimeError):create_household(self.config)
            create.assert_not_called()
    def test_create_api_initializes_three_owned_tabs_without_private_receipts(self):
        class Response:
            def raise_for_status(self):pass
            def json(self):return {'spreadsheetId':'sample_sheet_id'}
        class Session:
            def post(self,url,**kwargs):self.url=url;self.body=kwargs['json'];return Response()
        session=Session()
        @contextlib.contextmanager
        def authorized(_):yield session
        with patch('docintel.cloud.authorized',authorized):self.assertEqual(create_sheet('private-token.json'),'sample_sheet_id')
        self.assertEqual(session.body['properties']['title'],'Household Purchases')
        self.assertEqual([s['properties']['title'] for s in session.body['sheets']],list(HEADERS))
        for sheet in session.body['sheets']:
            rows=sheet['data'][0]['rowData'];self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]['values'][0]['userEnteredValue'],{'stringValue':MARKER})
