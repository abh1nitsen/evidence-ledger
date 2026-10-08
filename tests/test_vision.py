import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from unittest.mock import patch

from docintel.core import baseline
from docintel.documents import optional_fields
from docintel.pipeline import run
from docintel.providers import Groq, ProviderError
from docintel.server import handler
from docintel.vision import MAX_IMAGE_BYTES, prepare_image, validate_image
from test_core import TEXT

HAS_PIL = importlib.util.find_spec("PIL") is not None


class FakeVision:
    name, model, identity, image_identity, supports_images = "groq", "test-model", "text-test", "image-test", True
    calls = 0

    def extract_image(self, prepared):
        self.calls += 1
        return {"transcript": TEXT, "document_type":"invoice", "additional_fields":optional_fields(TEXT), "fields": baseline(TEXT), "quality_issues": []}


def image_bytes(size=(800, 1000), color="white", format="PNG", **kwargs):
    from PIL import Image
    stream = io.BytesIO()
    Image.new("RGB", size, color).save(stream, format=format, **kwargs)
    return stream.getvalue()


@unittest.skipUnless(HAS_PIL, "Install vision extra for image tests")
class VisionTests(unittest.TestCase):
    def test_normalization_strips_metadata_and_corrects_orientation(self):
        from PIL import Image
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "private metadata"
        prepared = prepare_image(image_bytes(size=(800, 1000), format="JPEG", exif=exif))
        raw = base64.b64decode(prepared["data_url"].split(",", 1)[1])
        with Image.open(io.BytesIO(raw)) as normalized:
            self.assertEqual(normalized.size, (1000, 800))
            self.assertFalse(normalized.getexif())

    def test_size_format_and_dimensions_checked(self):
        for raw in (b"not-an-image", b"", b"x"*(MAX_IMAGE_BYTES+1), image_bytes((10,10))):
            with self.assertRaises(ValueError):
                prepare_image(raw)

    def test_pixel_limit_checked_before_decode(self):
        raw = image_bytes((5000, 5000))
        with self.assertRaises(ValueError):
            prepare_image(raw)

    def test_dark_and_low_contrast_warning(self):
        prepared = prepare_image(image_bytes(color="#101010"))
        self.assertIn("dark_image", prepared["metadata"]["local_quality_issues"])
        self.assertIn("low_contrast", prepared["metadata"]["local_quality_issues"])

    def test_all_image_outputs_require_review(self):
        prepared = prepare_image(image_bytes())
        result = validate_image(prepared, FakeVision().extract_image(prepared), FakeVision())
        self.assertEqual(result["decision"], "review")
        self.assertEqual(result["evidence_basis"], "model_transcription")
        self.assertEqual(result["source_sha256"], prepared["metadata"]["original_sha256"])
        self.assertNotEqual(result["transcript_sha256"], result["source_sha256"])

    def test_image_schema_and_quality_are_independently_checked(self):
        prepared = prepare_image(image_bytes())
        for changes in ({"quality_issues": ["unknown"]}, {"transcript": "\x00"}):
            data = {**FakeVision().extract_image(prepared), **changes}
            with self.assertRaises(ValueError):
                validate_image(prepared, data, FakeVision())

    def test_image_rerun_reuses_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / "images"
            inputs.mkdir()
            (inputs / "photo.png").write_bytes(image_bytes())
            provider = FakeVision()
            run(inputs, root / "state.sqlite", root / "report.json", provider)
            report = run(inputs, root / "state.sqlite", root / "report.json", provider)
            self.assertEqual(provider.calls, 1)
            self.assertEqual(report["skipped"], 1)

    def test_upload_is_checkpointed_and_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = FakeVision()
            with HTTPServer(("127.0.0.1", 0), handler(root / "report.json", provider, root / "image.sqlite")) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    base = f"http://127.0.0.1:{server.server_port}"
                    for _ in range(2):
                        request = urllib.request.Request(base+"/api/extract-image", data=image_bytes(),
                            headers={"Origin": base, "Content-Type": "application/octet-stream"})
                        with urllib.request.urlopen(request, timeout=5) as response:
                            result = json.load(response)
                        self.assertEqual(result["decision"], "review")
                    self.assertTrue(result["checkpoint"]["reused"])
                    self.assertEqual(provider.calls, 1)
                finally:
                    server.shutdown()
                    worker.join(3)

    def test_invalid_upload_never_calls_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = FakeVision()
            with HTTPServer(("127.0.0.1", 0), handler(root / "report.json", provider)) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    base = f"http://127.0.0.1:{server.server_port}"
                    request = urllib.request.Request(base+"/api/extract-image", data=b"fake jpg",
                        headers={"Origin": base, "Content-Type": "application/octet-stream"})
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(request, timeout=5)
                    self.assertEqual(error.exception.code, 400)
                    self.assertEqual(provider.calls, 0)
                finally:
                    server.shutdown()
                    worker.join(3)


class GroqTests(unittest.TestCase):
    def provider(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-only"}):
            return Groq(sleep=lambda _: None)

    def response(self, finish="stop", content=None):
        data = {"choices": [{"finish_reason": finish, "message": {"content": json.dumps(content or baseline(TEXT))}}]}
        return io.BytesIO(json.dumps(data).encode())

    def test_text_request_and_user_agent(self):
        with patch("urllib.request.urlopen", return_value=self.response()) as call:
            self.assertEqual(self.provider().extract(TEXT), baseline(TEXT))
            request = call.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.groq.com/openai/v1/chat/completions")
            self.assertEqual(request.get_header("User-agent"), "EvidenceLedger/0.2")
            self.assertEqual(json.loads(request.data)["response_format"], {"type": "json_object"})

    def test_image_request_contains_data_url(self):
        with patch("urllib.request.urlopen", return_value=self.response()) as call:
            self.provider().extract_image({"data_url": "data:image/jpeg;base64,test"})
            body = json.loads(call.call_args.args[0].data)
            self.assertEqual(body["messages"][0]["content"][1]["image_url"]["url"], "data:image/jpeg;base64,test")
            self.assertNotIn("tools", body)

    def test_incomplete_output_fails(self):
        with patch("urllib.request.urlopen", return_value=self.response(finish="length")):
            with self.assertRaises(ProviderError):
                self.provider().extract(TEXT)

    def test_retry_budget_and_permanent_errors(self):
        for code, expected in ((429, 3), (401, 1)):
            error = urllib.error.HTTPError("url", code, "private", {}, None)
            with patch("urllib.request.urlopen", side_effect=error) as call:
                with self.assertRaises(ProviderError):
                    self.provider().extract(TEXT)
                self.assertEqual(call.call_count, expected)

    def test_no_key_fails(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderError):
                Groq()

    def test_retry_after_is_respected_and_bounded(self):
        for retry_after, expected in (("7", 7), ("500", 60), ("bad", 20)):
            error = urllib.error.HTTPError("url", 429, "limited", {"Retry-After": retry_after}, None)
            provider = self.provider()
            sleeps = []
            provider.sleep = sleeps.append
            with patch("urllib.request.urlopen", side_effect=[error, self.response()]):
                provider.extract(TEXT)
            self.assertEqual(sleeps, [expected])
