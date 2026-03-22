import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import gen_characters
import gen_world
import gen_revision
import run_pipeline
import voice_fingerprint
from stateful_drafting import build_legacy_prompt


class GenericSeedSupportTests(unittest.TestCase):
    def test_character_prompt_uses_generic_role_scaffolding(self):
        prompt = gen_characters.build_character_prompt("A seed", "# World", "## Part 2")

        self.assertIn("The protagonist / primary viewpoint character", prompt)
        self.assertIn("Preserve any names, titles, factions, and relationships", prompt)
        self.assertNotIn("Cass Bellwright", prompt)
        self.assertNotIn("The Second Son of the House of Bells", prompt)

    def test_world_prompt_uses_generic_world_scaffolding(self):
        prompt = gen_world.build_world_prompt("A seed", "Voice guidance")

        self.assertIn("story's primary location(s)", prompt)
        self.assertIn("Edge Cases / Gifts / Curses / Unstable Phenomena", prompt)
        self.assertNotIn("Cantamura", prompt)
        self.assertNotIn("Cass's Gift", prompt)

    def test_world_and_character_generators_bootstrap_without_voice_file(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            self.assertEqual(gen_world.load_voice_guidance(root), gen_world.BOOTSTRAP_VOICE_GUIDANCE)
            self.assertEqual(gen_characters.load_voice_guidance(root), gen_characters.BOOTSTRAP_VOICE_GUIDANCE)

    def test_world_and_character_generators_bootstrap_without_valid_voice_part2(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (planning / "voice.md").write_text("# Voice\n\nNo part two here.\n", encoding="utf-8")

            self.assertEqual(gen_world.load_voice_guidance(root), gen_world.BOOTSTRAP_VOICE_GUIDANCE)
            self.assertEqual(gen_characters.load_voice_guidance(root), gen_characters.BOOTSTRAP_VOICE_GUIDANCE)

    def test_revision_prompt_uses_derived_title_when_available(self):
        context = {
            "brief": "# Brief",
            "voice": "# Voice",
            "characters": "# Characters",
            "world": "# World",
            "prev_tail": "(first chapter)",
            "next_head": "(last chapter)",
            "old_text": "Old draft",
            "output_path": Path("/tmp/ch_03.md"),
        }

        with patch.object(gen_revision, "derive_title", return_value="Glass Choir"):
            prompt = gen_revision.build_full_revision_prompt(3, context)

        self.assertIn('Rewrite Chapter 3 of "Glass Choir".', prompt)
        self.assertNotIn("House of Bells", prompt)

    def test_revision_prompt_falls_back_to_neutral_reference_without_title(self):
        context = {
            "brief": "# Brief",
            "voice": "# Voice",
            "characters": "# Characters",
            "world": "# World",
            "prev_tail": "(first chapter)",
            "next_head": "(last chapter)",
            "old_text": "Old draft",
            "output_path": Path("/tmp/ch_03.md"),
        }

        with patch.object(gen_revision, "derive_title", return_value=""):
            prompt = gen_revision.build_full_revision_prompt(3, context)

        self.assertIn("Rewrite Chapter 3 of this novel.", prompt)

    def test_legacy_prompt_uses_neutral_reference_and_generic_viewpoint_language(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (planning / "voice.md").write_text("# Voice\n", encoding="utf-8")
            (planning / "world.md").write_text("# World\n", encoding="utf-8")
            (planning / "characters.md").write_text("# Characters\n", encoding="utf-8")
            (planning / "outline.md").write_text(
                "### Ch 1: Signals\n\n1. Beat one.\n\n### Ch 2: Echoes\n\n1. Beat two.\n",
                encoding="utf-8",
            )

            prompt = build_legacy_prompt(root, 1)

        self.assertIn("Write Chapter 1 of this novel.", prompt)
        self.assertIn("governing viewpoint", prompt)
        self.assertIn("viewpoint character's experience", prompt)
        self.assertNotIn("Cass's POV", prompt)
        self.assertNotIn("House of Bells", prompt)

    def test_voice_fingerprint_counts_each_section_break_once(self):
        with TemporaryDirectory() as tmpdir:
            chapter_path = Path(tmpdir) / "ch_01.md"
            chapter_path.write_text(
                "# Chapter 1\n\nAlpha sentence here.\n\n---\n\nBeta sentence here.\n---\nGamma sentence here.\n",
                encoding="utf-8",
            )

            metrics = voice_fingerprint.analyze_chapter(chapter_path)

        self.assertEqual(metrics["section_breaks"], 2)

    def test_voice_fingerprint_main_handles_sparse_chapters(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            chapters_dir = root / "chapters"
            edit_logs_dir = root / "edit_logs"
            chapters_dir.mkdir()
            edit_logs_dir.mkdir()
            (chapters_dir / "ch_01.md").write_text('# Chapter 1\n\n"Leave it," Mara said.\n\nHe waited.\n', encoding="utf-8")
            (chapters_dir / "ch_03.md").write_text("# Chapter 3\n\nThe bell rang once.\n\nHe answered.\n", encoding="utf-8")

            with (
                patch.object(voice_fingerprint, "BASE_DIR", root),
                patch.object(voice_fingerprint, "CHAPTERS_DIR", chapters_dir),
                patch.object(voice_fingerprint, "planned_chapter_count", return_value=4),
            ):
                voice_fingerprint.main()

            payload = json.loads((edit_logs_dir / "voice_fingerprint.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["available_chapters"], [1, 3])
        self.assertEqual(payload["missing_chapters"], [2, 4])
        self.assertIn("ch_01", payload["chapters"])
        self.assertIn("ch_03", payload["chapters"])
        self.assertNotIn("ch_02", payload["chapters"])
        self.assertEqual(set(payload["chapters"]), {"ch_01", "ch_03"})
        self.assertIn("novel_average", payload)
        self.assertIsInstance(payload["novel_average"], dict)
        self.assertIn("word_count", payload["novel_average"])

    def test_clear_from_scratch_artifacts_keeps_seed_and_user_example_inputs(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            chapters_dir = root / "chapters"
            variants_dir = chapters_dir / "variants"
            briefs_dir = root / "briefs"
            scene_options_dir = root / "scene_options"
            story_state_dir = root / "state" / "story_state"
            edit_logs_dir = root / "edit_logs"
            eval_logs_dir = root / "eval_logs"
            for path in (chapters_dir, variants_dir, briefs_dir, scene_options_dir, story_state_dir, edit_logs_dir, eval_logs_dir):
                path.mkdir(parents=True, exist_ok=True)

            planning = root / "planning"
            planning.mkdir()
            (planning / "seed.md").write_text("A new seed\n", encoding="utf-8")
            (root / "seed.txt").write_text("Legacy seed\n", encoding="utf-8")
            (briefs_dir / "example.md").write_text("# Example\n", encoding="utf-8")
            (chapters_dir / ".gitkeep").write_text("", encoding="utf-8")

            for path in (
                planning / "world.md",
                planning / "characters.md",
                planning / "character_engine.json",
                planning / "perspective.md",
                planning / "voice.md",
                planning / "voice_discovery.json",
                planning / "arc_outline.md",
                planning / "chapter_cards.md",
                planning / "thread_registry.json",
                planning / "outline.md",
                planning / "canon.md",
                root / "manifest.json",
                root / "results.tsv",
                root / "arc_summary.md",
                root / "manuscript.md",
                root / "reviews.md",
                chapters_dir / "ch_01.md",
                variants_dir / "ch_01_variant_01.md",
                briefs_dir / "ch01_auto.md",
                scene_options_dir / "ch_01.json",
                story_state_dir / "ch_01.json",
                edit_logs_dir / "voice_fingerprint.json",
                eval_logs_dir / "evidence_pack.json",
            ):
                path.write_text("generated\n", encoding="utf-8")

            with (
                patch.object(run_pipeline, "BASE_DIR", root),
                patch.object(run_pipeline, "MANIFEST_PATH", root / "manifest.json"),
                patch.object(run_pipeline, "RESULTS_FILE", root / "results.tsv"),
                patch.object(run_pipeline, "CHAPTERS_DIR", chapters_dir),
                patch.object(run_pipeline, "BRIEFS_DIR", briefs_dir),
                patch.object(run_pipeline, "EDIT_LOGS_DIR", edit_logs_dir),
                patch.object(run_pipeline, "EVAL_LOGS_DIR", eval_logs_dir),
                patch.object(run_pipeline, "SCENE_OPTIONS_DIR", scene_options_dir),
                patch.object(run_pipeline, "STORY_STATE_DIR", story_state_dir),
                patch.object(run_pipeline, "VARIANTS_DIR", variants_dir),
            ):
                removed = run_pipeline.clear_from_scratch_artifacts()
                self.assertTrue(removed)
                self.assertTrue((planning / "seed.md").exists())
                self.assertTrue((root / "seed.txt").exists())
                self.assertTrue((briefs_dir / "example.md").exists())
                self.assertTrue((chapters_dir / ".gitkeep").exists())
                self.assertFalse((planning / "world.md").exists())
                self.assertFalse((root / "manifest.json").exists())
                self.assertFalse((chapters_dir / "ch_01.md").exists())
                self.assertFalse((variants_dir / "ch_01_variant_01.md").exists())
                self.assertFalse((briefs_dir / "ch01_auto.md").exists())
                self.assertFalse((scene_options_dir / "ch_01.json").exists())
                self.assertFalse((story_state_dir / "ch_01.json").exists())
                self.assertFalse((edit_logs_dir / "voice_fingerprint.json").exists())
                self.assertFalse((eval_logs_dir / "evidence_pack.json").exists())


if __name__ == "__main__":
    unittest.main()
