import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *_args, **_kwargs: None))

import discover_voice
from foundation_mind import VOICE_PART2_HEADING, render_voice_identity


class DiscoverVoiceTests(unittest.TestCase):
    def _write_required_inputs(self, root: Path) -> None:
        planning = root / "planning"
        planning.mkdir()
        (root / "seed.md").write_text("A bellmaker's son chases the wrong ledger.", encoding="utf-8")
        (planning / "world.md").write_text("# World\n\nGuild bells govern the city.", encoding="utf-8")
        (planning / "characters.md").write_text("# Characters\n\nCass Bellwright wants the truth.", encoding="utf-8")
        (planning / "perspective.md").write_text(
            "# Perspective\n\n## Obsessions\n- sound before sight\n",
            encoding="utf-8",
        )

    def _registers(self) -> list[dict[str, str]]:
        return [
            {"name": "register_1", "label": "Register 1", "description": "First option."},
            {"name": "register_2", "label": "Register 2", "description": "Second option."},
            {"name": "register_3", "label": "Register 3", "description": "Third option."},
            {"name": "register_4", "label": "Register 4", "description": "Fourth option."},
            {"name": "register_5", "label": "Register 5", "description": "Fifth option."},
        ]

    def _voice_profile(self) -> dict[str, object]:
        return {
            "tone": "Stone-heavy but intimate.",
            "sentence_rhythm": "Long observation broken by abrupt admissions.",
            "vocabulary_register": "Trade grit mixed with ritual residue.",
            "pov_and_tense": "Third-person limited past, close enough to feel the flinch.",
            "dialogue_conventions": "Short lines, pressure living in what is withheld.",
            "exemplar_passages": [
                "The ledger clicked shut like teeth.",
                "Cass counted the tremor before he counted the lie.",
                "The room listened harder than the men inside it.",
            ],
            "anti_exemplars": [
                "Generic cinematic grandeur.",
                "Modern quips that dissolve the pressure.",
                "Explanatory moralizing after the scene has landed.",
            ],
        }

    def _model_responses(self) -> list[str]:
        scores = [
            {"quality": 9, "distinctiveness": 9, "perspective_fit": 9},
            {"quality": 8, "distinctiveness": 8, "perspective_fit": 8},
            {"quality": 7, "distinctiveness": 7, "perspective_fit": 7},
            {"quality": 6, "distinctiveness": 6, "perspective_fit": 6},
            {"quality": 5, "distinctiveness": 5, "perspective_fit": 5},
        ]
        responses: list[str] = []
        for index, score in enumerate(scores, start=1):
            responses.append(f"Trial passage {index}")
            responses.append(
                json.dumps(
                    {
                        **score,
                        "strengths": [f"strength {index}"],
                        "risks": [f"risk {index}"],
                        "one_line_verdict": f"verdict {index}",
                    }
                )
            )
        responses.append(
            json.dumps(
                {
                    "winner": "A",
                    "reason": "Candidate A is sharper.",
                    "what_the_winner_has": ["clean pressure"],
                    "what_to_avoid_from_the_loser": ["ornamental drag"],
                }
            )
        )
        responses.append(json.dumps(self._voice_profile()))
        return responses

    def _run_discovery(self, root: Path, voice_output: Path) -> tuple[str, str, Path, int]:
        discovery_output = root / "planning" / "voice_discovery.json"
        responses = iter(self._model_responses())
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("discover_voice.BASE_DIR", root),
            patch("discover_voice.PERSPECTIVE_PATH", root / "planning" / "perspective.md"),
            patch("discover_voice.API_KEY", "test-key"),
            patch("discover_voice.available_registers", return_value=self._registers()),
            patch("discover_voice.call_model", side_effect=lambda **_kwargs: next(responses)) as mock_call_model,
            patch(
                "sys.argv",
                [
                    "discover_voice.py",
                    "--trials",
                    "5",
                    "--voice-output",
                    str(voice_output),
                    "--discovery-output",
                    str(discovery_output),
                ],
            ),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            discover_voice.main()

        return stdout.getvalue(), stderr.getvalue(), discovery_output, mock_call_model.call_count

    def test_main_updates_existing_voice_file_in_place(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_required_inputs(root)
            voice_output = root / "planning" / "voice.md"
            voice_output.write_text(
                "# Voice Profile\n\n"
                "## Part 1: Guardrails (permanent, all novels)\n"
                "Guardrails stay custom.\n\n"
                f"{VOICE_PART2_HEADING}\n"
                "Old body.\n",
                encoding="utf-8",
            )

            stdout, stderr, discovery_output, call_count = self._run_discovery(root, voice_output)
            expected_part2 = render_voice_identity(self._voice_profile())
            updated_voice = voice_output.read_text(encoding="utf-8")
            discovery = json.loads(discovery_output.read_text(encoding="utf-8"))

            self.assertEqual(call_count, 12)
            self.assertIn("Guardrails stay custom.", updated_voice)
            self.assertIn(expected_part2, updated_voice)
            self.assertNotIn("Old body.", updated_voice)
            self.assertEqual(updated_voice.count(VOICE_PART2_HEADING), 1)
            self.assertEqual(stdout.strip(), expected_part2.strip())
            self.assertIn(f"Saved updated voice profile to {voice_output}", stderr)
            self.assertEqual(discovery["winner"], "register_1")
            self.assertEqual(discovery["finalists"], ["register_1", "register_2"])

    def test_main_bootstraps_voice_file_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_required_inputs(root)
            voice_output = root / "planning" / "voice.md"

            stdout, stderr, discovery_output, call_count = self._run_discovery(root, voice_output)
            expected_part2 = render_voice_identity(self._voice_profile())
            bootstrapped_voice = voice_output.read_text(encoding="utf-8")

            self.assertEqual(call_count, 12)
            self.assertTrue(voice_output.exists())
            self.assertIn("# Voice Profile", bootstrapped_voice)
            self.assertIn("## Part 1: Guardrails (permanent, all novels)", bootstrapped_voice)
            self.assertIn("### Tier 1: Banned words -- kill on sight", bootstrapped_voice)
            self.assertIn(VOICE_PART2_HEADING, bootstrapped_voice)
            self.assertIn(expected_part2, bootstrapped_voice)
            self.assertEqual(stdout.strip(), expected_part2.strip())
            self.assertIn(f"Saved updated voice profile to {voice_output}", stderr)
            self.assertTrue(discovery_output.exists())


if __name__ == "__main__":
    unittest.main()
