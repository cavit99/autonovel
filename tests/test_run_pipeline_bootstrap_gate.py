import argparse
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import run_pipeline


class RunPipelineBootstrapGateTests(unittest.TestCase):
    def test_run_foundation_bootstrap_stops_before_structural_planning(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            commands = []

            def fake_uv_run_to_file(script, output_path, timeout=600):
                commands.append(script)
                if script == "gen_world.py":
                    output_path.write_text("# World\n", encoding="utf-8")
                elif script == "gen_characters.py --emit-engine":
                    output_path.write_text("# Characters\n", encoding="utf-8")
                    (planning / "character_engine.json").write_text("{}\n", encoding="utf-8")
                elif script == "gen_canon.py":
                    output_path.write_text("# Canon\n", encoding="utf-8")
                else:
                    raise AssertionError(f"Unexpected bootstrap file command: {script}")
                return subprocess.CompletedProcess(script, 0, stdout="ok\n", stderr="")

            def fake_uv_run(script, timeout=600, check=False):
                commands.append(script)
                if script == "gen_perspective.py":
                    (planning / "perspective.md").write_text("# Perspective\n", encoding="utf-8")
                elif script.startswith("discover_voice.py"):
                    (planning / "voice.md").write_text("# Voice\n", encoding="utf-8")
                    (planning / "voice_discovery.json").write_text("{}\n", encoding="utf-8")
                else:
                    raise AssertionError(f"Structural planning should not run before approval: {script}")
                return subprocess.CompletedProcess(script, 0, stdout="ok\n", stderr="")

            state = run_pipeline.default_state()
            with (
                patch.object(run_pipeline, "BASE_DIR", root),
                patch.object(run_pipeline, "MANIFEST_PATH", root / "manifest.json"),
                patch.object(run_pipeline, "uv_run_to_file", side_effect=fake_uv_run_to_file),
                patch.object(run_pipeline, "uv_run", side_effect=fake_uv_run),
                patch.object(run_pipeline, "build_manifest_and_gate", return_value={}) as build_manifest_mock,
                patch.object(run_pipeline, "save_state") as save_state_mock,
            ):
                updated = run_pipeline.run_foundation(state)

        self.assertEqual(updated["phase"], "foundation")
        self.assertEqual(updated["current_focus"], "awaiting_bootstrap_approval")
        self.assertTrue(updated["bootstrap_complete"])
        self.assertFalse(updated["bootstrap_approved"])
        self.assertEqual(
            commands,
            [
                "gen_world.py",
                "gen_characters.py --emit-engine",
                "gen_perspective.py",
                "discover_voice.py --trials 8",
                "gen_canon.py",
            ],
        )
        build_manifest_mock.assert_not_called()
        save_state_mock.assert_called()

    def test_run_pipeline_rejects_later_phase_while_bootstrap_review_is_pending(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_path = root / "state.json"
            state = run_pipeline.default_state()
            state["bootstrap_complete"] = True
            state["bootstrap_approved"] = False
            state["current_focus"] = "awaiting_bootstrap_approval"
            state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

            args = argparse.Namespace(
                from_scratch=False,
                approve_bootstrap=False,
                phase="drafting",
                max_cycles=None,
            )

            with (
                patch.object(run_pipeline, "BASE_DIR", root),
                patch.object(run_pipeline, "STATE_FILE", state_path),
                patch.object(run_pipeline, "CHAPTERS_DIR", root / "chapters"),
                patch.object(run_pipeline, "BRIEFS_DIR", root / "briefs"),
                patch.object(run_pipeline, "EDIT_LOGS_DIR", root / "edit_logs"),
                patch.object(run_pipeline, "EVAL_LOGS_DIR", root / "eval_logs"),
                patch.object(run_pipeline, "SCENE_OPTIONS_DIR", root / "scene_options"),
                patch.object(run_pipeline, "STORY_STATE_DIR", root / "state" / "story_state"),
                patch.object(run_pipeline, "VARIANTS_DIR", root / "chapters" / "variants"),
            ):
                with self.assertRaisesRegex(SystemExit, "Bootstrap review is still pending"):
                    run_pipeline.run_pipeline(args)

    def test_run_pipeline_approve_bootstrap_continues_foundation(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            state_path = root / "state.json"
            state = run_pipeline.default_state()
            state["bootstrap_complete"] = True
            state["bootstrap_approved"] = False
            state["current_focus"] = "awaiting_bootstrap_approval"
            state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")

            args = argparse.Namespace(
                from_scratch=False,
                approve_bootstrap=True,
                phase="foundation",
                max_cycles=None,
            )

            def fake_run_foundation(state):
                self.assertTrue(state["bootstrap_complete"])
                self.assertTrue(state["bootstrap_approved"])
                state["phase"] = "drafting"
                return state

            with (
                patch.object(run_pipeline, "BASE_DIR", root),
                patch.object(run_pipeline, "STATE_FILE", state_path),
                patch.object(run_pipeline, "CHAPTERS_DIR", root / "chapters"),
                patch.object(run_pipeline, "BRIEFS_DIR", root / "briefs"),
                patch.object(run_pipeline, "EDIT_LOGS_DIR", root / "edit_logs"),
                patch.object(run_pipeline, "EVAL_LOGS_DIR", root / "eval_logs"),
                patch.object(run_pipeline, "SCENE_OPTIONS_DIR", root / "scene_options"),
                patch.object(run_pipeline, "STORY_STATE_DIR", root / "state" / "story_state"),
                patch.object(run_pipeline, "VARIANTS_DIR", root / "chapters" / "variants"),
                patch.object(run_pipeline, "run_foundation", side_effect=fake_run_foundation) as run_foundation_mock,
                patch.object(run_pipeline, "count_words_in_chapters", return_value=0),
                patch.object(run_pipeline, "git_short_hash", return_value="abc123"),
            ):
                run_pipeline.run_pipeline(args)

        run_foundation_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
