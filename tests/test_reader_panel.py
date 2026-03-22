import unittest
from unittest import mock

from reader_panel import ANTHROPIC_BETA, PANEL_SYSTEM_PROMPT, build_reader_payload, call_reader


class ReaderPanelPromptCachingTests(unittest.TestCase):
    def test_build_reader_payload_caches_shared_prompt_and_leaves_lens_dynamic(self):
        payload = build_reader_payload("editor", "shared evidence prompt")

        self.assertEqual(payload["system"], PANEL_SYSTEM_PROMPT)
        content = payload["messages"][0]["content"]
        self.assertEqual(len(content), 2)
        self.assertEqual(content[0]["cache_control"], {"type": "ephemeral", "ttl": "5m"})
        self.assertNotIn("cache_control", content[1])
        self.assertIn("READING LENS:", content[1]["text"])

    def test_call_reader_sends_beta_header(self):
        payload = {"content": [{"text": '{"notes": ["ok"]}'}]}
        captured = {}

        class FakeResponse:
            def json(self):
                return payload

            def raise_for_status(self):
                return None

        class FakeHttpx:
            @staticmethod
            def post(url, headers=None, json=None, timeout=None):
                captured["url"] = url
                captured["headers"] = headers
                captured["json"] = json
                captured["timeout"] = timeout
                return FakeResponse()

        with mock.patch.dict("sys.modules", {"httpx": FakeHttpx}):
            parsed = call_reader("editor", "shared evidence prompt")

        self.assertEqual(parsed, {"notes": ["ok"]})
        self.assertEqual(captured["headers"]["anthropic-beta"], ANTHROPIC_BETA)
        self.assertEqual(captured["json"]["system"], PANEL_SYSTEM_PROMPT)
        self.assertEqual(
            captured["json"]["messages"][0]["content"][0]["cache_control"],
            {"type": "ephemeral", "ttl": "5m"},
        )


if __name__ == "__main__":
    unittest.main()
