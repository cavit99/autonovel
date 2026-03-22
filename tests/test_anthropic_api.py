import io
import json
import sys
import types
import unittest
from contextlib import redirect_stderr

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - lightweight fallback for bare runners
    class HTTPStatusError(Exception):
        def __init__(self, message, *, request=None, response=None):
            super().__init__(message)
            self.request = request
            self.response = response

    class Request:
        def __init__(self, method, url):
            self.method = method
            self.url = url

    class Response:
        def __init__(self, status_code, *, request=None, json_body=None, json=None, text=""):
            self.status_code = status_code
            self.request = request
            if json_body is None and json is not None:
                json_body = json
            self._json = json_body
            self.text = text or ("" if json_body is None else json.dumps(json_body))

        def json(self):
            if self._json is None:
                raise json.JSONDecodeError("No JSON", self.text, 0)
            return self._json

        def raise_for_status(self):
            if self.status_code >= 400:
                raise HTTPStatusError(
                    f"HTTP {self.status_code}",
                    request=self.request,
                    response=self,
                )

    httpx = types.SimpleNamespace(Request=Request, Response=Response, HTTPStatusError=HTTPStatusError)
    sys.modules["httpx"] = httpx

from anthropic_api import (
    enable_automatic_prompt_cache,
    extract_error_message,
    log_response_usage,
    message_text_from_response,
    text_block,
)
from run_pipeline import preview_stderr


class AnthropicApiTests(unittest.TestCase):
    def test_text_block_applies_ephemeral_cache_control(self):
        block = text_block("Large reusable prefix", cache=True)

        self.assertEqual(block["type"], "text")
        self.assertEqual(block["text"], "Large reusable prefix")
        self.assertEqual(block["cache_control"], {"type": "ephemeral", "ttl": "5m"})

    def test_enable_automatic_prompt_cache_sets_top_level_cache_control(self):
        payload = {"messages": [{"role": "user", "content": "hello"}]}

        enable_automatic_prompt_cache(payload)

        self.assertEqual(payload["cache_control"], {"type": "ephemeral", "ttl": "5m"})

    def test_log_response_usage_prints_cache_activity(self):
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            log_response_usage(
                {
                    "usage": {
                        "input_tokens": 12,
                        "output_tokens": 34,
                        "cache_creation_input_tokens": 56,
                        "cache_read_input_tokens": 78,
                    }
                },
                context="unit-test",
            )

        self.assertIn("[anthropic] unit-test", stderr.getvalue())
        self.assertIn("cache_write=56", stderr.getvalue())
        self.assertIn("cache_read=78", stderr.getvalue())

    def test_message_text_from_response_surfaces_low_credit_hint(self):
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(
            400,
            request=request,
            json={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.",
                },
            },
        )

        with self.assertRaises(RuntimeError) as ctx:
            message_text_from_response(response, context="writer request")

        message = str(ctx.exception)
        self.assertIn("credit balance is too low", message)
        self.assertIn("Claude Max subscription does not cover direct API usage", message)

    def test_extract_error_message_handles_non_json_bodies(self):
        request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        response = httpx.Response(502, request=request, text="upstream unavailable")

        self.assertEqual(extract_error_message(response), "upstream unavailable")

    def test_preview_stderr_keeps_tail_when_long(self):
        text = "a" * 1700 + "final useful line"

        preview = preview_stderr(text, limit=100)

        self.assertTrue(preview.startswith("...<stderr truncated>"))
        self.assertIn("final useful line", preview)
        self.assertNotIn("a" * 200, preview)


if __name__ == "__main__":
    unittest.main()
