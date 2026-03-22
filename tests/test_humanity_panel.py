import unittest
from unittest import mock

from humanity_panel import ANTHROPIC_BETA, PANELISTS, call_panel, parse_json_blob, run_panelists


class HumanityPanelTests(unittest.TestCase):
    def test_parse_json_blob_handles_nested_braces_inside_strings(self):
        payload = (
            'Preamble\n'
            '{"strongest_passage_id": "ch01-p01", "notes": ["Keep the line with {the bell}."]}\n'
            'Postscript'
        )

        parsed = parse_json_blob(payload)

        self.assertEqual(parsed["strongest_passage_id"], "ch01-p01")
        self.assertEqual(parsed["notes"], ["Keep the line with {the bell}."])

    def test_parse_json_blob_handles_fenced_payload(self):
        payload = """```json
{"weakest_passage_id": "ch02-p03", "overdesigned": "None"}
```"""

        parsed = parse_json_blob(payload)

        self.assertEqual(parsed["weakest_passage_id"], "ch02-p03")

    def test_run_panelists_preserves_successes_and_collects_failures(self):
        def fake_call(system, prompt):
            self.assertEqual(prompt, "assembled prompt")
            if system == PANELISTS["dramatist"]:
                raise RuntimeError("rate limited")
            if system == PANELISTS["novelist"]:
                return {"strongest_passage_id": "ch01-p01"}
            return {"oral_reading_issue": "Breath fails near the semicolon."}

        results, errors = run_panelists("assembled prompt", panel_call=fake_call)

        self.assertEqual(results["novelist"], {"strongest_passage_id": "ch01-p01"})
        self.assertEqual(results["oral_reader"], {"oral_reading_issue": "Breath fails near the semicolon."})
        self.assertNotIn("dramatist", results)
        self.assertEqual(errors, {"dramatist": "rate limited"})

    def test_call_panel_sends_beta_header(self):
        payload = {"content": [{"text": '{"notes": ["ok"]}'}]}
        captured = {}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return payload

        class FakeHttpx:
            @staticmethod
            def post(url, headers=None, json=None, timeout=None):
                captured["url"] = url
                captured["headers"] = headers
                captured["json"] = json
                captured["timeout"] = timeout
                return FakeResponse()

        with mock.patch.dict("sys.modules", {"httpx": FakeHttpx}):
            parsed = call_panel("system prompt", "user prompt")

        self.assertEqual(parsed, {"notes": ["ok"]})
        self.assertEqual(captured["headers"]["anthropic-beta"], ANTHROPIC_BETA)
        self.assertEqual(captured["headers"]["anthropic-version"], "2023-06-01")


if __name__ == "__main__":
    unittest.main()
