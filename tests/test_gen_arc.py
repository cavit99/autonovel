import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import gen_arc


class GenArcTests(unittest.TestCase):
    def test_generate_arc_uses_seed_and_bootstrap_artifacts_without_root_mystery_template(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (planning / "seed.md").write_text("Seed with the real central secret.\n", encoding="utf-8")
            (planning / "world.md").write_text("# World\nWorld facts.\n", encoding="utf-8")
            (planning / "characters.md").write_text("# Characters\nCharacter facts.\n", encoding="utf-8")
            (planning / "perspective.md").write_text("# Perspective\nPOV facts.\n", encoding="utf-8")
            (planning / "voice.md").write_text("# Voice\nVoice facts.\n", encoding="utf-8")

            output_path = planning / "arc_outline.md"
            captured = {}

            def fake_call_writer(prompt: str, max_tokens: int = 3000) -> str:
                captured["prompt"] = prompt
                return json.dumps(
                    {
                        "title": "Signals",
                        "acts": [{"name": "Act I", "irreversible_turns": ["The mandate is issued."]}],
                        "major_reveals": ["Juno curated the feed."],
                        "pressure_escalations": ["The orbit drifts."],
                        "candidate_risk_chapters": [7],
                    }
                )

            with (
                patch.object(gen_arc, "BASE_DIR", root),
                patch.object(gen_arc, "API_KEY", "test-key"),
                patch.object(gen_arc, "call_writer", side_effect=fake_call_writer),
            ):
                arc = gen_arc.generate_arc(output_path=output_path)
                output_exists = output_path.exists()

        self.assertEqual(arc["title"], "Signals")
        self.assertTrue(output_exists)
        self.assertIn("Seed with the real central secret.", captured["prompt"])
        self.assertNotIn("THE CENTRAL MYSTERY", captured["prompt"])


if __name__ == "__main__":
    unittest.main()
