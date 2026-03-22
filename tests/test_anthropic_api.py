import unittest

import httpx

from anthropic_api import extract_error_message, message_text_from_response
from run_pipeline import preview_stderr


class AnthropicApiTests(unittest.TestCase):
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
