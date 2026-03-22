import unittest

from gen_brief import (
    append_patch_directives_section,
    build_patch_directives_from_cuts,
    has_patch_directives,
)


class GenBriefPatchDirectiveTests(unittest.TestCase):
    def test_build_patch_directives_from_cuts_emits_cut_and_replace(self):
        cuts_data = {
            "cuts": [
                {
                    "type": "OVER-EXPLAIN",
                    "quote": 'He said "too much" here.\nAnd then kept going.',
                    "action": "CUT",
                },
                {
                    "type": "REDUNDANT",
                    "quote": "Opening line.",
                    "action": "REWRITE",
                    "rewrite": 'Sharper "opening" line.',
                },
            ]
        }

        directives = build_patch_directives_from_cuts(cuts_data, limit=5)

        self.assertEqual(
            directives,
            [
                '- replace: "Opening line." => "Sharper \'opening\' line."',
                '- cut: "He said \'too much\' here. And then kept going."',
            ],
        )

    def test_build_patch_directives_filters_and_limits(self):
        cuts_data = {
            "cuts": [
                {"type": "STRUCTURAL", "quote": "Structural note.", "action": "CUT"},
                {"type": "REDUNDANT", "quote": "Redundant note.", "action": "CUT"},
                {"type": "OVER-EXPLAIN", "quote": "Explain note.", "action": "CUT"},
            ]
        }

        directives = build_patch_directives_from_cuts(
            cuts_data,
            limit=1,
            allowed_types={"REDUNDANT", "OVER-EXPLAIN"},
        )

        self.assertEqual(directives, ['- cut: "Redundant note."'])

    def test_append_patch_directives_section_adds_section(self):
        brief = "# Revision Brief\n\n## WHAT TO CHANGE\n1. Tighten this.\n"
        enriched = append_patch_directives_section(
            brief,
            ['- cut: "Redundant note."'],
        )

        self.assertTrue(has_patch_directives(enriched))
        self.assertIn("## Patch Directives", enriched)
        self.assertIn('- cut: "Redundant note."', enriched)

    def test_append_patch_directives_section_is_noop_without_directives(self):
        brief = "# Revision Brief\n"
        self.assertEqual(append_patch_directives_section(brief, []), brief)
        self.assertFalse(has_patch_directives(brief))


if __name__ == "__main__":
    unittest.main()
