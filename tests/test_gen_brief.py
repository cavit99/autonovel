import unittest
from pathlib import Path
from unittest.mock import patch

from gen_brief import (
    build_auto_brief,
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

    def test_build_auto_brief_handles_missing_cuts_data(self):
        full_eval = {
            "weakest_chapter": 3,
            "weakest_dimension": "overall_engagement",
            "top_suggestion": "Tighten the confrontation.",
            "novel_score": 6.8,
        }
        chapter_eval = {
            "overall_score": 6.1,
            "engagement": {"score": 6, "fix": "Sharpen the scene pressure."},
            "top_3_revisions": [],
            "ai_patterns_detected": [],
            "three_strongest_sentences": [],
            "three_weakest_sentences": [],
        }
        with (
            patch("gen_brief.latest_full_eval", return_value=Path("eval_logs/fake_full.json")),
            patch("gen_brief.load_json", side_effect=[full_eval, chapter_eval]),
            patch("gen_brief.chapter_text", return_value="# Chapter 3\n\nCass waits."),
            patch("gen_brief.chapter_title", return_value="Signals"),
            patch("gen_brief.word_count", return_value=2),
            patch("gen_brief.extract_voice_rules", return_value=["Keep the pressure local."]),
            patch("gen_brief.latest_chapter_eval", return_value=Path("eval_logs/fake_ch03.json")),
            patch("gen_brief.load_panel", return_value={}),
            patch("gen_brief.load_cuts", return_value={}),
        ):
            chapter, brief = build_auto_brief()

        self.assertEqual(chapter, 3)
        self.assertIn("# Revision Brief: Chapter 3", brief)
        self.assertNotIn("## Patch Directives", brief)
        self.assertIn("[PRIORITY — full eval] Tighten the confrontation.", brief)


if __name__ == "__main__":
    unittest.main()
