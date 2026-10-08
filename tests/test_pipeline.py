import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from docintel.pipeline import run, atomic_json, exclusive
from docintel.providers import Baseline, ProviderError
from test_core import TEXT


class Counting(Baseline):
    calls = 0

    def extract(self, text):
        self.calls += 1
        return super().extract(text)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        (self.inputs / "a.txt").write_text(TEXT, encoding="utf-8")
        self.db, self.out = self.root / "state.sqlite", self.root / "report.json"
        self.provider = Counting()

    def run_job(self, **kwargs):
        return run(self.inputs, self.db, self.out, self.provider, **kwargs)

    def test_rerun_reuses_result_and_rebuilds_export(self):
        self.run_job()
        self.out.unlink()
        report = self.run_job()
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(report["skipped"], 1)
        self.assertTrue(self.out.exists())

    def test_interruption_then_resume(self):
        (self.inputs / "b.txt").write_text(TEXT.replace("A-1", "B-2"), encoding="utf-8")
        first = self.run_job(stop_after=1)
        self.assertEqual(first["remaining"], 1)
        second = self.run_job()
        self.assertEqual((second["processed"], second["skipped"], second["remaining"]), (1, 1, 0))

    def test_crash_after_extraction_reclaims_pending(self):
        def crash():
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_job(after_extract=crash)
        report = self.run_job()
        self.assertEqual(report["documents"][0]["attempts"], 2)
        self.assertEqual(report["documents"][0]["status"], "completed")

    def test_export_failure_keeps_committed_result(self):
        with patch("docintel.pipeline.atomic_json", side_effect=OSError("disk unavailable")):
            with self.assertRaises(OSError):
                self.run_job()
        self.run_job()
        self.assertEqual(self.provider.calls, 1)

    def test_changed_content_or_provider_creates_new_job(self):
        self.run_job()
        (self.inputs / "a.txt").write_text(TEXT.replace("A-1", "B-2"), encoding="utf-8")
        self.run_job()
        self.provider.identity = "new-configuration"
        self.run_job()
        self.assertEqual(self.provider.calls, 3)

    def test_duplicate_content_computes_once(self):
        (self.inputs / "duplicate.txt").write_text(TEXT, encoding="utf-8")
        report = self.run_job()
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(len(report["documents"]), 2)

    def test_failed_requires_explicit_retry(self):
        with patch.object(self.provider, "extract", side_effect=ProviderError("sensitive body")):
            self.run_job()
        self.run_job()
        self.assertEqual(self.provider.calls, 0)
        report = self.run_job(retry_failed=True)
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(report["documents"][0]["attempts"], 2)
        self.assertNotIn("sensitive", self.out.read_text())

    def test_bad_encoding_and_size_do_not_stop_batch(self):
        (self.inputs / "bad.txt").write_bytes(b"\xff")
        (self.inputs / "big.txt").write_text("x"*100001)
        report = self.run_job()
        self.assertEqual(sum(x["status"] == "failed" for x in report["documents"]), 2)
        self.assertEqual(report["documents"][0]["status"], "completed")

    def test_malformed_provider_output_checkpointed_failed(self):
        with patch.object(self.provider, "extract", return_value={"total": "10"}):
            report = self.run_job()
        self.assertEqual(report["documents"][0]["error"], "invalid_provider_schema")

    def test_lock_rejects_second_writer(self):
        with exclusive(self.db):
            with self.assertRaises(RuntimeError):
                self.run_job()

    def test_atomic_export_preserves_old_file_on_failure(self):
        atomic_json(self.out, {"old": True})
        with patch("docintel.pipeline.os.replace", side_effect=OSError()):
            with self.assertRaises(OSError):
                atomic_json(self.out, {"new": True})
        self.assertEqual(json.loads(self.out.read_text()), {"old": True})
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_empty_directory_errors(self):
        (self.inputs / "a.txt").unlink()
        with self.assertRaises(ValueError):
            self.run_job()
