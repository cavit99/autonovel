import unittest

from humanity_panel import parse_json_blob


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


if __name__ == "__main__":
    unittest.main()
