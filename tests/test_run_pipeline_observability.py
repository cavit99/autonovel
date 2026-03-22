import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import run_pipeline


class RunPipelineObservabilityTests(unittest.TestCase):
    def test_run_tool_args_streams_output_and_heartbeat_while_preserving_capture(self):
        command = [
            sys.executable,
            "-c",
            (
                "import sys, time; "
                "print('stdout line 1', flush=True); "
                "print('stderr line 1', file=sys.stderr, flush=True); "
                "time.sleep(0.12); "
                "print('stdout line 2', flush=True)"
            ),
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch.object(run_pipeline, "SUBPROCESS_HEARTBEAT_SECONDS", 0.05),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            result = run_pipeline.run_tool_args(command, timeout=2)

        self.assertEqual(result.returncode, 0)
        self.assertIn("stdout line 1", result.stdout)
        self.assertIn("stdout line 2", result.stdout)
        self.assertIn("stderr line 1", result.stderr)
        self.assertIn("RUN:", stdout.getvalue())
        self.assertIn("stdout line 1", stdout.getvalue())
        self.assertIn("stdout line 2", stdout.getvalue())
        self.assertIn("HEARTBEAT: still running after", stdout.getvalue())
        self.assertIn("DONE (", stdout.getvalue())
        self.assertIn("stderr line 1", stderr.getvalue())

    def test_run_tool_args_keeps_failure_stderr_preview_useful(self):
        command = [
            sys.executable,
            "-c",
            (
                "import sys; "
                "print('about to fail', file=sys.stderr, flush=True); "
                "sys.stderr.write('x' * 1800 + 'tail marker\\n'); "
                "sys.stderr.flush(); "
                "raise SystemExit(1)"
            ),
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = run_pipeline.run_tool_args(command, timeout=2)

        self.assertEqual(result.returncode, 1)
        self.assertIn("about to fail", stderr.getvalue())
        self.assertIn("WARN: exit code 1", stdout.getvalue())
        self.assertIn("...<stderr truncated>", stdout.getvalue())
        self.assertIn("tail marker", stdout.getvalue())

    def test_run_foundation_prints_post_step_artifact_summaries(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (root / "edit_logs").mkdir()

            def fake_uv_run_to_file(script, output_path, timeout=600):
                if script == "gen_world.py":
                    output_path.write_text("# World\n", encoding="utf-8")
                elif script == "gen_characters.py --emit-engine":
                    output_path.write_text("# Characters\n", encoding="utf-8")
                    (planning / "character_engine.json").write_text("{}\n", encoding="utf-8")
                elif script == "gen_canon.py":
                    output_path.write_text("# Canon\n", encoding="utf-8")
                return subprocess.CompletedProcess(script, 0, stdout="ok\n", stderr="")

            def fake_uv_run(script, timeout=600, check=False):
                if script == "gen_perspective.py":
                    (planning / "perspective.md").write_text("# Perspective\n", encoding="utf-8")
                elif script.startswith("discover_voice.py"):
                    (planning / "voice.md").write_text("# Voice\n", encoding="utf-8")
                    (planning / "voice_discovery.json").write_text("{}\n", encoding="utf-8")
                elif script == "gen_arc.py":
                    (planning / "arc_outline.md").write_text("# Arc Outline\n", encoding="utf-8")
                elif script == "gen_chapter_cards.py":
                    (planning / "chapter_cards.md").write_text(
                        "# Chapter Cards\n\n"
                        "## Ch 01: One\n"
                        "goal: Goal\npressure: Pressure\nreversal: Reversal\naftermath: Aftermath\n"
                        "irreversible_change: Change\nallowed_ambiguity: Maybe\n"
                        "time_span: One day\nscene_density: medium\nscene_type: quiet\n"
                        "scene_method: close_interiority\nrisk: none\n"
                        "## Ch 02: Two\n"
                        "goal: Goal\npressure: Pressure\nreversal: Reversal\naftermath: Aftermath\n"
                        "irreversible_change: Change\nallowed_ambiguity: Maybe\n"
                        "time_span: One day\nscene_density: medium\nscene_type: quiet\n"
                        "scene_method: close_interiority\nrisk: formal\n",
                        encoding="utf-8",
                    )
                elif script == "gen_thread_registry.py":
                    (planning / "thread_registry.json").write_text(
                        '[{"id": "signal", "description": "Signal", "first_seen": 1, "type": "plot"}]\n',
                        encoding="utf-8",
                    )
                elif script == "gen_outline_part2.py":
                    (planning / "outline.md").write_text(
                        "### Ch 1: One\n\n- BEATS:\n- Something happens.\n\n"
                        "### Ch 2: Two\n\n- BEATS:\n- Something else happens.\n\n"
                        "## Foreshadowing Ledger\n- signal\n",
                        encoding="utf-8",
                    )
                elif script == "voice_fingerprint.py":
                    (root / "edit_logs" / "voice_fingerprint.json").write_text("{}\n", encoding="utf-8")
                elif script == "evaluate.py --phase foundation":
                    return subprocess.CompletedProcess(
                        script,
                        0,
                        stdout="---\noverall_score: 8.1\nlore_score: 7.8\n",
                        stderr="",
                    )
                return subprocess.CompletedProcess(script, 0, stdout="ok\n", stderr="")

            stdout = io.StringIO()
            state = run_pipeline.default_state()
            state["bootstrap_complete"] = True
            state["bootstrap_approved"] = True
            with (
                patch.object(run_pipeline, "BASE_DIR", root),
                patch.object(run_pipeline, "MANIFEST_PATH", root / "manifest.json"),
                patch.object(run_pipeline, "uv_run_to_file", side_effect=fake_uv_run_to_file),
                patch.object(run_pipeline, "uv_run", side_effect=fake_uv_run),
                patch.object(run_pipeline, "build_manifest_and_gate", return_value={}),
                patch.object(run_pipeline, "git_add_commit", return_value="abc123"),
                patch.object(run_pipeline, "save_state"),
                patch.object(run_pipeline, "log_result"),
                patch.object(run_pipeline, "restore_paths"),
                patch.object(run_pipeline, "planned_chapter_count", return_value=2),
                redirect_stdout(stdout),
            ):
                updated = run_pipeline.run_foundation(state)

        self.assertEqual(updated["phase"], "drafting")
        self.assertIn("Chapter cards ready: 2 chapters parsed", stdout.getvalue())
        self.assertIn("Thread registry ready: 1 threads", stdout.getvalue())
        self.assertIn("Legacy outline ready: 2 chapters", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
