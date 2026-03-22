import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dialogue_audit import build_dialogue_audit
from evidence_tools import build_evidence_pack
from evaluate import normalize_chapter_result, normalize_full_result
from narration_audit import build_narration_audit
from reader_panel import build_legacy_prompt
import review


class EvidenceEvalTests(unittest.TestCase):
    def test_build_evidence_pack_collects_expected_categories(self):
        chapters = {
            1: '# Chapter 1\n\n"Leave it," Cass said.\n\nHe waited in the corridor and listened to the bell.\n\nThe history of the ward had always mattered because the contract still held.\n',
            2: '# Chapter 2\n\n"You lied to me," Mira said.\n\n"No," Torvald said. "I told you what would keep you moving."\n\nThey stood in the rain and refused each other.\n',
            3: '# Chapter 3\n\nCass entered the room. The smell of oil came first, then the ring of the pipes, then the pale light off the stone.\n\nHe sat and watched the dust drift.\n',
            4: '# Chapter 4\n\nThe green coin turned and turned and turned in his palm.\n\nThe green coin turned and turned and turned in his palm.\n',
        }

        pack = build_evidence_pack(chapters, eval_log_dir=None)  # type: ignore[arg-type]

        self.assertEqual(pack["generated_from"]["chapter_count"], 4)
        self.assertIn("openings", pack["categories"])
        self.assertIn("confrontations", pack["categories"])
        self.assertIn("dialogue_heavy", pack["categories"])
        self.assertGreaterEqual(len(pack["categories"]["openings"]), 3)

    def test_dialogue_audit_flags_generic_theme_and_ceiling_issues(self):
        chapters = {
            1: '"Truth is not order, but obligation," Cass said.\n\n"Yes," Mira said.\n\n"Yes," Torvald said.\n'
        }
        character_engine = {
            "Cass": {
                "metaphor_domain": ["bell", "rope"],
                "cognitive_ceiling": {"abstraction_level": "low"},
            },
            "Mira": {
                "metaphor_domain": ["history", "archive"],
                "cognitive_ceiling": {"abstraction_level": "high"},
            },
            "Torvald": {
                "metaphor_domain": ["iron", "market"],
                "cognitive_ceiling": {"abstraction_level": "low"},
            },
        }

        audit = build_dialogue_audit(chapters, character_engine)

        self.assertTrue(audit["theme_perfect_lines"])
        self.assertTrue(audit["generic_lines"])
        self.assertTrue(audit["cognitive_ceiling_violations"])

    def test_narration_audit_flags_repetition(self):
        chapters = {
            1: (
                'Cass entered the room. The smell of oil came first, then the ring of the pipes, then the pale light off the stone.\n\n'
                'Cass entered the room. The smell of oil came first, then the ring of the pipes, then the pale light off the stone.\n\n'
                'Very quietly, he waited. Very quietly, he listened.'
            )
        }

        audit = build_narration_audit(chapters)

        self.assertTrue(audit["repeated_sentence_openings"])
        self.assertTrue(audit["repeated_observation_ordering"])
        self.assertTrue(audit["repeated_intensifiers"])

    def test_chapter_normalization_populates_compatibility_aliases(self):
        result = normalize_chapter_result(
            {
                "baseline_voice": {"score": 7, "weakest_moment": "x", "fix": "y", "note": "z"},
                "dialogue_separability": {"score": 6, "weakest_moment": "x", "fix": "y", "note": "z"},
                "scene_method_freshness": {"score": 5, "weakest_moment": "x", "fix": "y", "note": "z"},
                "lore_integration": {"score": 8, "weakest_moment": "x", "fix": "y", "note": "z"},
            },
            include_risk=True,
        )

        self.assertIn("voice_adherence", result)
        self.assertIn("character_voice", result)
        self.assertIn("beat_coverage", result)
        self.assertIn("plants_seeded", result)
        self.assertIn("risk_assessment", result)

    def test_full_normalization_populates_compatibility_aliases(self):
        result = normalize_full_result(
            {
                "theme_pressure": {"score": 8, "note": "high"},
                "arc_completion": {"score": 7, "note": "solid"},
                "perspective_continuity": {"score": 9, "note": "steady"},
            }
        )

        self.assertIn("theme_coherence", result)
        self.assertIn("foreshadowing_resolution", result)
        self.assertIn("voice_consistency", result)

    def test_reader_panel_legacy_prompt_falls_back_to_chapters_without_arc_summary(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            chapters_dir = root / "chapters"
            chapters_dir.mkdir()
            (chapters_dir / "ch_01.md").write_text(
                "# Chapter 1\n\nCass waited by the bell.\n\nHe left before dawn.\n",
                encoding="utf-8",
            )

            with patch("reader_panel.BASE_DIR", root):
                prompt = build_legacy_prompt()

        self.assertIn("Chapter 1:", prompt)
        self.assertIn("Cass waited by the bell.", prompt)

    def test_review_parse_mode_does_not_require_api_key(self):
        with patch.object(review, "API_KEY", ""), patch.object(review, "cmd_parse") as cmd_parse:
            with patch("sys.argv", ["review.py", "--parse"]):
                review.main()
        cmd_parse.assert_called_once()


if __name__ == "__main__":
    unittest.main()
