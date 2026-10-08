import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from docintel.providers import OpenAI, ProviderError
from docintel.core import baseline
from test_core import TEXT


class ProviderTests(unittest.TestCase):
    def provider(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            return OpenAI("test-model", sleep=lambda _: None)

    def response(self, **changes):
        data = {"status": "completed", "output": [{"content": [{"type": "output_text", "text": json.dumps(baseline(TEXT))}]}]}
        data.update(changes)
        return io.BytesIO(json.dumps(data).encode())

    def test_request_matches_structured_responses_contract(self):
        with patch("urllib.request.urlopen", return_value=self.response()) as send:
            self.assertEqual(self.provider().extract(TEXT), baseline(TEXT))
            request = send.call_args.args[0]
            body = json.loads(request.data)
            self.assertFalse(body["store"])
            self.assertTrue(body["text"]["format"]["strict"])
            self.assertEqual(body["text"]["format"]["type"], "json_schema")
            self.assertEqual(send.call_args.kwargs["timeout"], 30)

    def test_transient_failure_retried(self):
        error = urllib.error.HTTPError("url", 429, "limited", {}, None)
        with patch("urllib.request.urlopen", side_effect=[error, self.response()]) as send:
            self.provider().extract(TEXT)
            self.assertEqual(send.call_count, 2)

    def test_auth_failure_not_retried_or_leaked(self):
        error = urllib.error.HTTPError("secret-url", 401, "secret-body", {}, None)
        with patch("urllib.request.urlopen", side_effect=error) as send:
            with self.assertRaisesRegex(ProviderError, "provider HTTP 401"):
                self.provider().extract(TEXT)
            self.assertEqual(send.call_count, 1)

    def test_retry_budget(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("secret")) as send:
            with self.assertRaisesRegex(ProviderError, "provider network failure"):
                self.provider().extract(TEXT)
            self.assertEqual(send.call_count, 3)

    def test_refusal_and_incomplete(self):
        for response in (self.response(status="incomplete"), self.response(output=[{"content": [{"type": "refusal"}]}])):
            with patch("urllib.request.urlopen", return_value=response):
                with self.assertRaises(ProviderError):
                    self.provider().extract(TEXT)

    def test_no_key_fails(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProviderError):
                OpenAI("test-model")

    def test_model_part_of_cache_identity(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            self.assertNotEqual(OpenAI("a").identity, OpenAI("b").identity)
