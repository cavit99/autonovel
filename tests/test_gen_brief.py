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
    @staticmethod
    def _json_loader(mapping):
        def loader(path):
            name = Path(path).name
            if name not in mapping:
                raise AssertionError(f"unexpected json load: {path}")
            return mapping[name]

        return loader

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

    def test_build_auto_brief_prefers_new_dimensions_and_ingests_audits(self):
        full_eval = {
            "weakest_chapter": 3,
            "weakest_dimension": "theme_pressure",
            "top_suggestion": "Let the chapter breathe between arguments.",
            "novel_score": 6.1,
            "perspective_continuity": {
                "score": 5,
                "note": "Chapter 3 stops feeling filtered through Cass's blind spots.",
            },
            "theme_pressure": {
                "score": 4,
                "note": "Chapter 3 feels overdesigned and too fully on-theme.",
            },
            "surplus_life": {
                "score": 4,
                "note": "Chapter 3 strips away surplus life in favor of pure argument.",
            },
        }
        chapter_eval = {
            "overall_score": 5.9,
            "weakest_dimension": "formal_enactment",
            "perspective_distinctiveness": {
                "score": 5,
                "weakest_moment": "Cass reads the room from nowhere instead of through his own ignorance.",
                "fix": "Re-anchor every observation in Cass's blind spots.",
                "note": "POV drifts outward.",
            },
            "formal_enactment": {
                "score": 4,
                "weakest_moment": "Pain lands in the same neutral syntax as exposition.",
                "fix": "Let sentence shape buckle under strain.",
                "note": "Form stays flat.",
            },
            "character_truthfulness": {
                "score": 6,
                "weakest_moment": "Mira states the scene's logic instead of hiding what she wants.",
                "fix": "Make Mira conceal, misread, and protect herself instead of speaking the thesis cleanly.",
                "note": "People speak too knowingly.",
            },
            "dialogue_separability": {
                "score": 5,
                "weakest_moment": "Cass and Mira answer each other in the same register.",
                "fix": "Separate Cass and Mira through clipped diction and mismatched pressures.",
                "note": "Speakers blur together.",
            },
            "surplus_life": {
                "score": 5,
                "weakest_moment": "Every detail only serves the argument.",
                "fix": "Put back trade, room, and bodily detail that is not there to prove a point.",
                "note": "Scene texture is too obedient.",
            },
            "scene_method_freshness": {
                "score": 4,
                "weakest_moment": "The scene arrives like a checklist instead of a vivid method.",
                "fix": "Open on the bell rope biting Cass's palm rather than a beat summary.",
                "note": "Method feels mechanical.",
            },
            "baseline_voice": {
                "score": 8,
                "weakest_moment": "",
                "fix": "",
                "note": "Mostly on-book.",
            },
            "voice_adherence": {
                "score": 2,
                "weakest_moment": "legacy weakest voice moment",
                "fix": "legacy voice fix",
                "note": "legacy alias should not win",
            },
            "beat_coverage": {
                "score": 1,
                "weakest_moment": "legacy weakest beat moment",
                "fix": "legacy beat fix",
                "note": "legacy alias should not win",
            },
            "character_voice": {
                "score": 2,
                "weakest_moment": "legacy weakest character moment",
                "fix": "legacy character fix",
                "note": "legacy alias should not win",
            },
            "top_3_revisions": [
                "Keep the argument off the nose and back inside the scene.",
            ],
            "ai_patterns_detected": [
                "explanation after the scene already showed the point",
            ],
            "three_strongest_sentences": [
                "The bell rope burned his palm before he let himself think.",
            ],
            "three_weakest_sentences": [
                "He felt sad and then explained why.",
            ],
        }
        dialogue_audit = {
            "generic_lines": [
                {"chapter": 3, "speaker": "Cass", "text": "Yes, I know."},
            ],
            "theme_perfect_lines": [
                {"chapter": 3, "speaker": "Mira", "text": "Truth is not mercy, but order."},
            ],
            "metaphor_domain_leakage": [
                {
                    "chapter": 3,
                    "speaker": "Cass",
                    "text": "The archive in my ribs will not shut.",
                    "other_domains": ["Mira"],
                }
            ],
            "cognitive_ceiling_violations": [
                {"chapter": 3, "speaker": "Cass", "text": "Justice is a recursive obligation."},
            ],
            "speaker_non_separability": [
                {"speakers": ["Cass", "Mira"], "overlap": 0.52},
            ],
        }
        narration_audit = {
            "repeated_sentence_openings": [
                {"opening": "he looked", "count": 3},
            ],
            "repeated_observation_ordering": [
                {"signature": ["smell", "sound", "sight"], "count": 2},
            ],
            "repeated_intensifiers": [
                {"token": "very", "count": 2},
            ],
            "room_entry_examples": [
                {
                    "chapter": 3,
                    "text": (
                        "Cass entered the room. The smell of oil came first, then the ring "
                        "of the pipes, then the pale light off the stone."
                    ),
                }
            ],
        }
        humanity_panel = {
            "evidence_path": "eval_logs/evidence_pack.json",
            "panelists": {
                "novelist": {
                    "strongest_passage_id": "ch03-p02",
                    "weakest_passage_id": "ch03-p01",
                    "overdesigned": "The passage keeps underlining its thesis instead of letting the world breathe.",
                    "notes": ["[ch03-p01] The room is all argument and no surplus life."],
                },
                "dramatist": {
                    "strongest_passage_id": "ch02-p01",
                    "weakest_passage_id": "ch03-p01",
                    "social_dramatic_failure": "The confrontation reads like clean information transfer, not a social event.",
                    "notes": ["[ch03-p01] Mira and Cass know too much about the scene's thesis."],
                },
                "oral_reader": {
                    "strongest_passage_id": "ch03-p02",
                    "weakest_passage_id": "ch03-p01",
                    "oral_reading_issue": "One paragraph tangles in the mouth and runs out of breath.",
                    "notes": ["[ch03-p01] Breath fails before the final clause."],
                },
            },
        }
        humanity_lookup = {
            "ch03-p01": {"chapter": 3, "text": "Weak passage with no room to breathe."},
            "ch03-p02": {"chapter": 3, "text": "Strong passage that keeps the bell rope and breath alive."},
        }

        with (
            patch("gen_brief.latest_full_eval", return_value=Path("eval_logs/fake_full.json")),
            patch("gen_brief.latest_chapter_eval", return_value=Path("eval_logs/fake_ch03.json")),
            patch(
                "gen_brief.load_json",
                side_effect=self._json_loader(
                    {
                        "fake_full.json": full_eval,
                        "fake_ch03.json": chapter_eval,
                    }
                ),
            ),
            patch(
                "gen_brief.chapter_text",
                return_value=(
                    '# Chapter 3\n\n"Yes," Cass said.\n\n"Yes," Mira said.\n\n'
                    "Cass entered the room and kept his hand on the bell rope."
                ),
            ),
            patch("gen_brief.chapter_title", return_value="Signals"),
            patch("gen_brief.word_count", return_value=1200),
            patch("gen_brief.extract_voice_rules", return_value=["Keep the pressure local."]),
            patch("gen_brief.load_panel", return_value={}),
            patch("gen_brief.load_cuts", return_value={}),
            patch("gen_brief.load_dialogue_audit", return_value=dialogue_audit),
            patch("gen_brief.load_narration_audit", return_value=narration_audit),
            patch("gen_brief.load_humanity_panel", return_value=humanity_panel),
            patch("gen_brief.load_humanity_evidence_lookup", return_value=humanity_lookup),
        ):
            chapter, brief = build_auto_brief()

        self.assertEqual(chapter, 3)
        self.assertIn("Perspective distinctiveness", brief)
        self.assertIn("Formal enactment", brief)
        self.assertIn("Character truth", brief)
        self.assertIn("Dialogue separability", brief)
        self.assertIn("Surplus life", brief)
        self.assertIn("Dialogue audit", brief)
        self.assertIn("theme-perfect line", brief)
        self.assertIn("Narration audit", brief)
        self.assertIn("Humanity panel — Novelist", brief)
        self.assertIn("Humanity panel — Dramatist", brief)
        self.assertIn("Humanity panel — Oral Reader", brief)
        self.assertIn("[PRIORITY — full eval] Let the chapter breathe between arguments.", brief)
        self.assertNotIn("legacy voice fix", brief)
        self.assertNotIn("legacy beat fix", brief)
        self.assertNotIn("legacy character fix", brief)

    def test_build_auto_brief_maps_legacy_dimensions_explicitly(self):
        full_eval = {
            "weakest_chapter": 3,
            "weakest_dimension": "voice_consistency",
            "top_suggestion": "Sharpen the opening pressure.",
            "novel_score": 6.4,
            "voice_consistency": {
                "score": 5,
                "note": "Chapter 3 drifts out of Cass's governing perspective.",
            },
            "theme_coherence": {
                "score": 4,
                "note": "Chapter 3 overstates the book's argument.",
            },
        }
        chapter_eval = {
            "overall_score": 6.2,
            "weakest_dimension": "beat_coverage",
            "voice_adherence": {
                "score": 5,
                "weakest_moment": "The prose starts sounding generic instead of book-specific.",
                "fix": "Restore the book's pressure-driven diction.",
                "note": "legacy voice",
            },
            "beat_coverage": {
                "score": 4,
                "weakest_moment": "The scene walks beats mechanically instead of arriving through a vivid method.",
                "fix": "Arrive through a fresher scene method.",
                "note": "legacy beat",
            },
            "character_voice": {
                "score": 5,
                "weakest_moment": "Cass and Mira blur together in dialogue.",
                "fix": "Separate the speakers through clipped diction and mismatched pressure.",
                "note": "legacy character",
            },
            "plants_seeded": {
                "score": 6,
                "weakest_moment": "Foreshadowing feels bolted on instead of embedded in scene life.",
                "fix": "Hide the thread inside scene texture.",
                "note": "legacy plants",
            },
            "top_3_revisions": [],
            "ai_patterns_detected": [],
            "three_strongest_sentences": [],
            "three_weakest_sentences": [],
        }

        with (
            patch("gen_brief.latest_full_eval", return_value=Path("eval_logs/fake_full.json")),
            patch("gen_brief.latest_chapter_eval", return_value=Path("eval_logs/fake_ch03.json")),
            patch(
                "gen_brief.load_json",
                side_effect=self._json_loader(
                    {
                        "fake_full.json": full_eval,
                        "fake_ch03.json": chapter_eval,
                    }
                ),
            ),
            patch("gen_brief.chapter_text", return_value="# Chapter 3\n\nCass waits by the bell."),
            patch("gen_brief.chapter_title", return_value="Signals"),
            patch("gen_brief.word_count", return_value=400),
            patch("gen_brief.extract_voice_rules", return_value=["Keep the pressure local."]),
            patch("gen_brief.load_panel", return_value={}),
            patch("gen_brief.load_cuts", return_value={}),
            patch("gen_brief.load_dialogue_audit", return_value=None),
            patch("gen_brief.load_narration_audit", return_value=None),
            patch("gen_brief.load_humanity_panel", return_value=None),
        ):
            chapter, brief = build_auto_brief()

        self.assertEqual(chapter, 3)
        self.assertIn("Perspective continuity (legacy voice_consistency)", brief)
        self.assertIn("Weakest dimension: **Scene method freshness (legacy beat_coverage)**.", brief)
        self.assertIn("[Baseline voice | fallback from voice_adherence] Restore the book's pressure-driven diction.", brief)
        self.assertIn("[Scene method freshness | fallback from beat_coverage] Arrive through a fresher scene method.", brief)
        self.assertIn("[Dialogue separability | fallback from character_voice] Separate the speakers through clipped diction and mismatched pressure.", brief)
        self.assertIn("[Lore integration | fallback from plants_seeded] Hide the thread inside scene texture.", brief)


if __name__ == "__main__":
    unittest.main()
