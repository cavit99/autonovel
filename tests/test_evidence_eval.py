import unittest
from contextlib import redirect_stderr
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import io

from dialogue_audit import build_dialogue_audit
from evidence_tools import build_evidence_pack
import evaluate
from evaluate import normalize_chapter_result, normalize_full_result
from narration_audit import build_narration_audit
from reader_panel import build_legacy_prompt
import review


class EvidenceEvalTests(unittest.TestCase):
    def test_load_foundation_layer_files_reads_structural_artifacts(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (planning / "voice.md").write_text("Voice marker\n", encoding="utf-8")
            (planning / "world.md").write_text("World marker\n", encoding="utf-8")
            (planning / "characters.md").write_text("Characters marker\n", encoding="utf-8")
            (planning / "perspective.md").write_text("Perspective marker\n", encoding="utf-8")
            (planning / "canon.md").write_text("Canon marker\n", encoding="utf-8")
            (planning / "arc_outline.md").write_text("Arc marker\n", encoding="utf-8")
            (planning / "chapter_cards.md").write_text("Cards marker\n", encoding="utf-8")
            (planning / "outline.md").write_text("Outline marker\n", encoding="utf-8")
            (planning / "thread_registry.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "consent",
                            "description": "The bell asks for consent",
                            "type": "plot",
                            "first_seen": 1,
                            "reinforced": [2],
                            "payoff": 5,
                            "required": True,
                        }
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch.object(evaluate, "BASE_DIR", root):
                layers = evaluate.load_foundation_layer_files()

        self.assertEqual(layers["perspective"], "Perspective marker\n")
        self.assertEqual(layers["arc_outline"], "Arc marker\n")
        self.assertEqual(layers["chapter_cards"], "Cards marker\n")
        self.assertEqual(layers["outline"], "Outline marker\n")
        self.assertIn("entries: 1", layers["thread_registry_window"])
        self.assertIn("id=consent", layers["thread_registry_window"])

    def test_build_foundation_prompt_includes_structural_planning_layer(self):
        prompt = evaluate.build_foundation_prompt(
            {
                "perspective": "Perspective marker",
                "voice": "Voice marker",
                "world": "World marker",
                "characters": "Characters marker",
                "canon": "Canon marker",
                "arc_outline": "Arc marker",
                "chapter_cards": "Cards marker",
                "thread_registry": json.dumps(
                    [
                        {
                            "id": "consent",
                            "description": "The bell asks for consent",
                            "type": "plot",
                            "first_seen": 1,
                            "payoff": 3,
                        }
                    ]
                ),
                "outline": "Outline marker",
            }
        )

        self.assertIn("CURRENT STRUCTURAL PLANNING LAYER UNDER REVIEW", prompt)
        self.assertIn("GOVERNING PERSPECTIVE:\nPerspective marker", prompt)
        self.assertIn("ARC OUTLINE:\nArc marker", prompt)
        self.assertIn("CHAPTER CARDS:\nCards marker", prompt)
        self.assertIn("THREAD REGISTRY WINDOW (rendered from thread_registry.json):", prompt)
        self.assertIn("id=consent", prompt)
        self.assertIn("LEGACY OUTLINE REBUILD / EXPORT VIEW:\nOutline marker", prompt)
        self.assertIn("not just the legacy outline", prompt)

    def test_evaluate_foundation_uses_structural_payload_and_backfills_lore_score(self):
        layers = {
            "perspective": "Perspective marker",
            "voice": "Voice marker",
            "world": "World marker",
            "characters": "Characters marker",
            "canon": "Canon marker",
            "arc_outline": "Arc marker",
            "chapter_cards": "Cards marker",
            "thread_registry": json.dumps(
                [
                    {
                        "id": "consent",
                        "description": "The bell asks for consent",
                        "type": "plot",
                        "first_seen": 1,
                        "payoff": 3,
                    }
                ]
            ),
            "outline": "Outline marker",
        }
        judge_response = json.dumps(
            {
                "perspective_alignment": {"score": 8, "gap": "g", "fix": "f", "note": "n"},
                "arc_coherence": {"score": 7, "gap": "g", "fix": "f", "note": "n"},
                "chapter_card_specificity": {"score": 6, "gap": "g", "fix": "f", "note": "n"},
                "thread_payoff_design": {"score": 9, "gap": "g", "fix": "f", "note": "n"},
                "outline_synthesis": {"score": 8, "gap": "g", "fix": "f", "note": "n"},
                "world_support": {"score": 7, "gap": "g", "fix": "f", "note": "n"},
                "character_support": {"score": 8, "gap": "g", "fix": "f", "note": "n"},
                "canon_readiness": {"score": 9, "gap": "g", "fix": "f", "note": "n"},
                "voice_guardrails": {"score": 6, "gap": "g", "fix": "f", "note": "n"},
                "internal_consistency": {"score": 7, "gap": "g", "fix": "f", "note": "n"},
                "overall_score": 7.4,
            }
        )

        with (
            patch.object(evaluate, "load_foundation_layer_files", return_value=layers),
            patch.object(evaluate, "call_judge", return_value=judge_response) as mock_call,
        ):
            result = evaluate.evaluate_foundation()

        prompt = mock_call.call_args.args[0]
        self.assertIn("Perspective marker", prompt)
        self.assertIn("Arc marker", prompt)
        self.assertIn("Cards marker", prompt)
        self.assertIn("id=consent", prompt)
        self.assertIn("Outline marker", prompt)
        self.assertEqual(mock_call.call_args.kwargs["max_tokens"], 16000)
        self.assertEqual(result["structure_score"], 7.6)
        self.assertEqual(result["lore_score"], 8.0)
        self.assertEqual(
            result["structural_artifacts_used"],
            [
                "planning/perspective.md",
                "planning/arc_outline.md",
                "planning/chapter_cards.md",
                "planning/thread_registry.json",
                "planning/outline.md",
            ],
        )

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

    def test_evaluate_full_summary_mode_warns_and_normalizes(self):
        stderr = io.StringIO()
        with (
            patch.object(evaluate, "load_layer_files", return_value={"voice": "", "world": "", "characters": "", "outline": ""}),
            patch.object(evaluate, "load_all_chapters", return_value={1: "Opening text", 2: "Closing text"}),
            patch.object(
                evaluate,
                "call_judge",
                return_value='{"theme_pressure":{"score":8,"note":"sharp"},"arc_completion":{"score":7,"note":"complete"},"perspective_continuity":{"score":6,"note":"steady"},"novel_score":7.2}',
            ),
            redirect_stderr(stderr),
        ):
            result = evaluate.evaluate_full()

        self.assertIn("theme_coherence", result)
        self.assertIn("foreshadowing_resolution", result)
        self.assertIn("voice_consistency", result)
        self.assertEqual(result["evaluation_mode"], "summary_fallback")
        self.assertIn("degraded summary-mode judging", result["warning"])
        self.assertIn("degraded summary-mode judging", stderr.getvalue())

    def test_evaluate_full_evidence_mode_uses_expanded_token_budget(self):
        with TemporaryDirectory() as tmpdir:
            evidence_path = Path(tmpdir) / "evidence.json"
            evidence_path.write_text("{}\n", encoding="utf-8")

            with (
                patch.object(
                    evaluate,
                    "load_extended_layer_files",
                    return_value={
                        "voice": "",
                        "perspective": "",
                        "world": "",
                        "characters": "",
                        "canon": "",
                        "thread_registry": "",
                    },
                ),
                patch.object(evaluate, "load_json", return_value={}),
                patch.object(evaluate, "render_evidence_pack", return_value="PACK"),
                patch.object(
                    evaluate,
                    "call_judge",
                    return_value='{"theme_pressure":{"score":8,"note":"sharp"},"arc_completion":{"score":7,"note":"complete"},"perspective_continuity":{"score":6,"note":"steady"},"novel_score":7.8}',
                ) as mock_call,
            ):
                result = evaluate.evaluate_full(str(evidence_path))

        self.assertEqual(result["evaluation_mode"], "evidence")
        self.assertIn("theme_coherence", result)
        self.assertEqual(mock_call.call_args.kwargs["max_tokens"], evaluate.FULL_EVIDENCE_MAX_TOKENS)

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
