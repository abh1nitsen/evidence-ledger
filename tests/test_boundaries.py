import contextlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer

from docintel.pipeline import run
from docintel.providers import Baseline
from docintel.server import handler
from test_core import TEXT


class BoundaryTests(unittest.TestCase):
    def test_abrupt_process_death_resumes_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / "input"
            inputs.mkdir()
            (inputs / "invoice.txt").write_text(TEXT, encoding="utf-8")
            db, report = root / "state.sqlite", root / "report.json"
            code = "from docintel.pipeline import run; from docintel.providers import Baseline; import os,sys; run(sys.argv[1],sys.argv[2],sys.argv[3],Baseline(),after_extract=lambda:os._exit(73))"
            child = subprocess.run([sys.executable, "-c", code, str(inputs), str(db), str(report)], capture_output=True, timeout=15)
            self.assertEqual(child.returncode, 73)
            with contextlib.closing(sqlite3.connect(db)) as con:
                self.assertEqual(con.execute("select status from jobs").fetchone()[0], "pending")
            recovered = run(inputs, db, report, Baseline())
            self.assertEqual(recovered["documents"][0]["status"], "completed")
            self.assertEqual(recovered["documents"][0]["attempts"], 2)

    def test_cli_failure_exit_code(self):
        child = subprocess.run([sys.executable, "-m", "docintel", "run", "--input", "missing-folder-for-test"], capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 1)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.report = Path(self.temp.name) / "report.json"
        self.server = HTTPServer(("127.0.0.1", 0), handler(self.report))
        self.server.timeout = 2
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(3)
        self.temp.cleanup()

    def post(self, text=TEXT, origin=None, raw=None):
        request = urllib.request.Request(self.base + "/api/extract",
            data=raw if raw is not None else json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json", "Origin": origin or self.base})
        return urllib.request.urlopen(request, timeout=3)

    def test_extract_returns_grounded_json(self):
        with self.post() as response:
            data = json.load(response)
        self.assertEqual(data["decision"], "validated")
        self.assertEqual(data["fields"]["total"]["quote"], "110.00")

    def test_foreign_origin_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post(origin="https://untrusted.example")
        self.assertEqual(error.exception.code, 403)

    def test_invalid_documents_rejected(self):
        for text in ("", "\x00", "x" * 100001):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.post(text=text)
            self.assertEqual(error.exception.code, 400)

    def test_unknown_paths_do_not_serve_files(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.base + "/../data/gold.json", timeout=3)
        self.assertEqual(error.exception.code, 404)

    def test_report_and_script_served_with_security_headers(self):
        for path in ("/", "/app.js", "/api/report"):
            with urllib.request.urlopen(self.base + path, timeout=3) as response:
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_json_download_is_an_attachment(self):
        with self.post() as response:
            result = json.load(response)
        with urllib.request.urlopen(self.base + result["download_url"], timeout=3) as response:
            self.assertIn("attachment", response.headers["Content-Disposition"])
            exported = json.load(response)
        self.assertEqual(exported["fields"], result["fields"])
        self.assertNotIn("download_url", exported)

    def test_review_endpoint_persists_and_exports_human_decisions(self):
        with self.post() as response: result=json.load(response)
        body={'document_id':result['review']['document_id'],'field':'invoice_id','action':'edit','value':'CORRECTED-2','revision':0}
        request=urllib.request.Request(self.base+'/api/review',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':self.base})
        with urllib.request.urlopen(request,timeout=3) as response: reviewed=json.load(response)
        self.assertEqual(reviewed['effective_fields']['invoice_id'],'CORRECTED-2')
        self.assertEqual(reviewed['fields']['invoice_id']['value'],'A-1')
        with urllib.request.urlopen(self.base+reviewed['download_url'],timeout=3) as response: exported=json.load(response)
        self.assertEqual(exported['review']['revision'],1)
        self.assertEqual(exported['fields']['invoice_id']['human_review']['action'],'edit')
        with self.post() as response: restored=json.load(response)
        self.assertEqual(restored['effective_fields']['invoice_id'],'CORRECTED-2')
        with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(request,timeout=3)
        self.assertEqual(error.exception.code,409)

    def test_review_foreign_origin_and_invalid_candidate_rejected(self):
        with self.post(TEXT.replace('Currency: USD\n','')) as response: result=json.load(response)
        body={'document_id':result['review']['document_id'],'field':'currency','action':'accept','value':None,'revision':0}
        for origin,expected in ((self.base,400),('https://untrusted.example',403)):
            request=urllib.request.Request(self.base+'/api/review',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':origin})
            with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(request,timeout=3)
            self.assertEqual(error.exception.code,expected)

    def test_group_endpoint_restoration_export_and_origin(self):
        with self.post() as response: result=json.load(response)
        body={'document_id':result['review']['document_id'],'category':'Dining','tags':['work'],'revision':0}
        request=urllib.request.Request(self.base+'/api/group',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':self.base})
        with urllib.request.urlopen(request,timeout=3) as response: grouped=json.load(response)
        self.assertEqual(grouped['spending']['category'],'Dining')
        with urllib.request.urlopen(self.base+grouped['download_url'],timeout=3) as response: exported=json.load(response)
        self.assertEqual(exported['spending']['tags'],['work'])
        with urllib.request.urlopen(self.base+'/api/spending',timeout=3) as response: summary=json.load(response)
        self.assertEqual(summary['included_receipts'],0)
        with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(request,timeout=3)
        self.assertEqual(error.exception.code,409)
        request=urllib.request.Request(self.base+'/api/group',data=json.dumps({**body,'revision':1}).encode(),headers={'Content-Type':'application/json','Origin':'https://untrusted.example'})
        with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(request,timeout=3)
        self.assertEqual(error.exception.code,403)
