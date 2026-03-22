import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from manifest_tools import build_manifest_payload, collect_consistency_issues
from planning_split import render_chapter_cards, render_legacy_outline
from variant_tools import pick_best_variant_deterministically
import run_pipeline


class OrchestratorManifestTests(unittest.TestCase):
    def test_build_manifest_payload_collects_counts_and_risk_chapters(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (root / "chapters").mkdir()
            (root / "eval_logs").mkdir()
            (root / "edit_logs").mkdir()
            (root / "chapters" / "ch_01.md").write_text("# Ch 1\n\nOne two three.\n", encoding="utf-8")
            (planning / "seed.md").write_text("A seed\n", encoding="utf-8")
            (planning / "chapter_cards.md").write_text(
                "# Chapter Cards\n\n"
                "## Ch 01: Signals\n"
                "goal: Test\npressure: Pressure\nreversal: Reversal\naftermath: Aftermath\n"
                "irreversible_change: Change\nallowed_ambiguity: Maybe\n"
                "time_span: One night\nscene_density: high\nscene_type: confrontation\n"
                "scene_method: dialogue_driven\nrisk: formal\n",
                encoding="utf-8",
            )
            (planning / "thread_registry.json").write_text("[]\n", encoding="utf-8")
            (planning / "arc_outline.md").write_text(
                "# Arc Outline\n\n**Working title:** Signals\n\n## Candidate Risk Chapters\n1\n",
                encoding="utf-8",
            )
            (root / "state.json").write_text('{"phase": "drafting", "chapters_total": 12}\n', encoding="utf-8")

            manifest = build_manifest_payload(root, phase="drafting", chapter=1)

        self.assertEqual(manifest["chapter_count"], 1)
        self.assertEqual(manifest["planned_chapter_count"], 1)
        self.assertEqual(manifest["word_count"], 6)
        self.assertEqual(manifest["risk_chapters"], [1])
        self.assertEqual(manifest["phase"], "drafting")
        self.assertEqual(manifest["files"]["seed"], "planning/seed.md")
        self.assertEqual(manifest["files"]["chapter_cards"], "planning/chapter_cards.md")
        self.assertIn("seed", manifest["hashes"])

    def test_consistency_gate_catches_evidence_hash_mismatch(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (root / "chapters").mkdir()
            (root / "eval_logs").mkdir()
            (root / "edit_logs").mkdir()
            (root / "chapters" / "ch_01.md").write_text("# Ch 1\n\nAlpha beta gamma.\n", encoding="utf-8")
            (planning / "chapter_cards.md").write_text(
                "# Chapter Cards\n\n"
                "## Ch 01: Signals\n"
                "goal: Test\npressure: Pressure\nreversal: Reversal\naftermath: Aftermath\n"
                "irreversible_change: Change\nallowed_ambiguity: Maybe\n"
                "time_span: One night\nscene_density: high\nscene_type: confrontation\n"
                "scene_method: dialogue_driven\nrisk: none\n",
                encoding="utf-8",
            )
            (planning / "thread_registry.json").write_text("[]\n", encoding="utf-8")
            (root / "edit_logs" / "reader_panel.json").write_text("{}\n", encoding="utf-8")
            (root / "edit_logs" / "humanity_panel.json").write_text("{}\n", encoding="utf-8")
            (root / "edit_logs" / "dialogue_audit.json").write_text("{}\n", encoding="utf-8")
            (root / "edit_logs" / "narration_audit.json").write_text("{}\n", encoding="utf-8")
            (root / "eval_logs" / "evidence_pack.json").write_text(
                json.dumps(
                    {
                        "generated_from": {
                            "chapter_count": 1,
                            "word_count": 3,
                            "manuscript_sha256": "wrong",
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            manifest = build_manifest_payload(root, phase="revision")
            issues = collect_consistency_issues(root, manifest, phase="revision")

        self.assertTrue(any("evidence pack manuscript hash" in issue for issue in issues))

    def test_foundation_placeholder_cards_do_not_create_fake_outline_mismatch(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (root / "chapters").mkdir()
            (root / "eval_logs").mkdir()
            (root / "edit_logs").mkdir()

            (planning / "seed.md").write_text("A seed\n", encoding="utf-8")
            (planning / "world.md").write_text("# World\n", encoding="utf-8")
            (planning / "characters.md").write_text("# Characters\n", encoding="utf-8")
            (planning / "character_engine.json").write_text("{}\n", encoding="utf-8")
            (planning / "perspective.md").write_text("# Perspective\n", encoding="utf-8")
            (planning / "voice.md").write_text("# Voice\n", encoding="utf-8")
            (planning / "canon.md").write_text("# Canon\n", encoding="utf-8")
            (planning / "arc_outline.md").write_text(
                "# Arc Outline\n\n**Working title:** Signals\n",
                encoding="utf-8",
            )
            (planning / "chapter_cards.md").write_text(render_chapter_cards([]) + "\n", encoding="utf-8")
            (planning / "thread_registry.json").write_text("[]\n", encoding="utf-8")
            (planning / "outline.md").write_text(
                render_legacy_outline(
                    "Signals",
                    {"title": "Signals", "acts": [], "major_reveals": [], "pressure_escalations": []},
                    [],
                    [],
                )
                + "\n",
                encoding="utf-8",
            )

            manifest = build_manifest_payload(root, phase="foundation")
            issues = collect_consistency_issues(root, manifest, phase="foundation")

        self.assertEqual(manifest["planned_chapter_count"], 0)
        self.assertEqual(issues, [])

    def test_deterministic_variant_selection_prefers_cleaner_variant(self):
        candidates = [
            {
                "id": "baseline",
                "path": Path("/tmp/baseline.md"),
                "text": "It is worth noting that the air was thick with dread. Furthermore, he felt angry.",
            },
            {
                "id": "variant_01",
                "path": Path("/tmp/variant_01.md"),
                "text": '"Leave it," Cass said.\n\nHe listened to the bell and refused to look at her.',
            },
        ]

        result = pick_best_variant_deterministically(candidates)

        self.assertEqual(result["winner"], "variant_01")

    def test_foundation_smoke_uses_pr6_generation_order(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (root / "edit_logs").mkdir()

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
                return subprocess.CompletedProcess(script, 0, stdout="ok\n", stderr="")

            def fake_uv_run(script, timeout=600, check=False):
                commands.append(script)
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
                        "scene_method: close_interiority\nrisk: none\n",
                        encoding="utf-8",
                    )
                elif script == "gen_thread_registry.py":
                    (planning / "thread_registry.json").write_text("[]\n", encoding="utf-8")
                elif script == "gen_outline_part2.py":
                    (planning / "outline.md").write_text(
                        "### Ch 1: One\n\n- BEATS:\n- Something happens.\n\n## Foreshadowing Ledger\n- none\n",
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

            state = run_pipeline.default_state()
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
                patch.object(run_pipeline, "planned_chapter_count", return_value=1),
            ):
                updated = run_pipeline.run_foundation(state)

        self.assertEqual(updated["phase"], "drafting")
        self.assertEqual(
            commands[:8],
            [
                "gen_world.py",
                "gen_characters.py --emit-engine",
                "gen_perspective.py",
                "discover_voice.py --trials 8",
                "gen_arc.py",
                "gen_chapter_cards.py",
                "gen_thread_registry.py",
                "gen_outline_part2.py",
            ],
        )
        self.assertIn("gen_canon.py", commands)
        self.assertIn("voice_fingerprint.py", commands)
        self.assertIn("evaluate.py --phase foundation", commands)

    def test_drafting_smoke_runs_new_flow_for_one_chapter(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            chapters_dir = root / "chapters"
            scene_options_dir = root / "scene_options"
            story_state_dir = root / "state" / "story_state"
            eval_logs_dir = root / "eval_logs"
            chapters_dir.mkdir(parents=True)
            scene_options_dir.mkdir(parents=True)
            story_state_dir.mkdir(parents=True)
            eval_logs_dir.mkdir(parents=True)

            commands = []

            def fake_uv_run(script, timeout=600, check=False):
                commands.append(script)
                if script == "plan_scene.py 1 --variants 4":
                    (scene_options_dir / "ch_01.json").write_text("[]\n", encoding="utf-8")
                elif script == "draft_chapter.py 1 --mode auto":
                    (chapters_dir / "ch_01.md").write_text(
                        "# Chapter 1\n\n"
                        + ("Cass listened to the bell and refused to answer.\n" * 8),
                        encoding="utf-8",
                    )
                elif script == "evaluate.py --chapter 1":
                    log_path = eval_logs_dir / "20260322_000000_ch01.json"
                    log_path.write_text(json.dumps({"overall_score": 6.5}) + "\n", encoding="utf-8")
                    return subprocess.CompletedProcess(
                        script,
                        0,
                        stdout=f"---\noverall_score: 6.5\n\neval_log: {log_path}\n",
                        stderr="",
                    )
                return subprocess.CompletedProcess(script, 0, stdout="ok\n", stderr="")

            state = run_pipeline.default_state()
            state["phase"] = "drafting"
            state["chapters_total"] = 1
            with (
                patch.object(run_pipeline, "BASE_DIR", root),
                patch.object(run_pipeline, "CHAPTERS_DIR", chapters_dir),
                patch.object(run_pipeline, "SCENE_OPTIONS_DIR", scene_options_dir),
                patch.object(run_pipeline, "STORY_STATE_DIR", story_state_dir),
                patch.object(run_pipeline, "EVAL_LOGS_DIR", eval_logs_dir),
                patch.object(run_pipeline, "uv_run", side_effect=fake_uv_run),
                patch.object(run_pipeline, "build_manifest_and_gate", return_value={}),
                patch.object(run_pipeline, "git_add_commit", return_value="def456"),
                patch.object(run_pipeline, "save_state"),
                patch.object(run_pipeline, "log_result"),
                patch.object(run_pipeline, "is_critical_chapter", return_value=False),
                patch.object(run_pipeline, "risk_chapters", return_value=[]),
            ):
                updated = run_pipeline.run_drafting(state)

        self.assertEqual(updated["phase"], "revision")
        self.assertEqual(updated["chapters_drafted"], 1)
        self.assertEqual(commands[:3], ["plan_scene.py 1 --variants 4", "draft_chapter.py 1 --mode auto", "evaluate.py --chapter 1"])

    def test_drafting_keeps_final_failed_attempt_for_new_chapter_fallback(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            chapters_dir = root / "chapters"
            scene_options_dir = root / "scene_options"
            story_state_dir = root / "state" / "story_state"
            eval_logs_dir = root / "eval_logs"
            chapters_dir.mkdir(parents=True)
            scene_options_dir.mkdir(parents=True)
            story_state_dir.mkdir(parents=True)
            eval_logs_dir.mkdir(parents=True)

            commands = []
            restore_calls = []
            draft_attempt = 0
            scores = iter([5.1, 5.2, 5.3, 5.4, 5.5])

            def fake_uv_run(script, timeout=600, check=False):
                nonlocal draft_attempt
                commands.append(script)
                if script == "plan_scene.py 1 --variants 4":
                    (scene_options_dir / "ch_01.json").write_text("[]\n", encoding="utf-8")
                elif script == "draft_chapter.py 1 --mode auto":
                    draft_attempt += 1
                    (chapters_dir / "ch_01.md").write_text(
                        "# Chapter 1\n\n"
                        + (f"Attempt {draft_attempt} should stay on disk if fallback keeps this draft.\n" * 8),
                        encoding="utf-8",
                    )
                elif script == "advance_state.py --chapter 1":
                    (story_state_dir / "ch_01.json").write_text('{"chapter": 1}\n', encoding="utf-8")
                return subprocess.CompletedProcess(script, 0, stdout="ok\n", stderr="")

            def fake_evaluate_chapter(chapter_num, include_risk=False):
                return next(scores), {}

            def fake_restore_paths(paths):
                restore_calls.append([path.name for path in paths])
                for path in paths:
                    path.unlink(missing_ok=True)

            state = run_pipeline.default_state()
            state["phase"] = "drafting"
            state["chapters_total"] = 1
            chapter_path = chapters_dir / "ch_01.md"
            with (
                patch.object(run_pipeline, "BASE_DIR", root),
                patch.object(run_pipeline, "CHAPTERS_DIR", chapters_dir),
                patch.object(run_pipeline, "SCENE_OPTIONS_DIR", scene_options_dir),
                patch.object(run_pipeline, "STORY_STATE_DIR", story_state_dir),
                patch.object(run_pipeline, "EVAL_LOGS_DIR", eval_logs_dir),
                patch.object(run_pipeline, "uv_run", side_effect=fake_uv_run),
                patch.object(run_pipeline, "evaluate_chapter", side_effect=fake_evaluate_chapter),
                patch.object(run_pipeline, "build_manifest_and_gate", return_value={}) as build_manifest_mock,
                patch.object(run_pipeline, "git_add_commit", return_value="forced123") as commit_mock,
                patch.object(run_pipeline, "save_state"),
                patch.object(run_pipeline, "log_result"),
                patch.object(run_pipeline, "restore_paths", side_effect=fake_restore_paths),
                patch.object(run_pipeline, "CRITICAL_SCENE_THRESHOLD", 0.0),
                patch.object(run_pipeline, "is_critical_chapter", return_value=False),
                patch.object(run_pipeline, "risk_chapters", return_value=[]),
            ):
                updated = run_pipeline.run_drafting(state)
                chapter_exists = chapter_path.exists()
                chapter_text = chapter_path.read_text(encoding="utf-8") if chapter_exists else ""
                snapshot_exists = (story_state_dir / "ch_01.json").exists()

        self.assertEqual(updated["phase"], "revision")
        self.assertEqual(updated["chapters_drafted"], 1)
        self.assertTrue(chapter_exists)
        self.assertIn("Attempt 5", chapter_text)
        self.assertEqual(len(restore_calls), run_pipeline.MAX_CHAPTER_ATTEMPTS - 1)
        self.assertEqual(build_manifest_mock.call_count, run_pipeline.MAX_CHAPTER_ATTEMPTS + 1)
        self.assertTrue(snapshot_exists)
        self.assertEqual(commands.count("advance_state.py --chapter 1"), 1)
        commit_mock.assert_called_once_with(
            f"ch01: best-effort after {run_pipeline.MAX_CHAPTER_ATTEMPTS} attempts"
        )

    def test_git_add_commit_uses_scoped_pathspecs_and_argument_safe_commit_message(self):
        commands = []
        message = 'revision cycle "safe" $(touch should_not_run)'

        def fake_run_tool_args(args, timeout=600, check=False):
            commands.append(args)
            if args[:3] == ["git", "rev-parse", "--short"]:
                return subprocess.CompletedProcess(args, 0, stdout="abc123\n", stderr="")
            return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")

        with (
            patch.object(run_pipeline, "pipeline_stage_pathspecs", return_value=["manifest.json", ":(glob)chapters/ch_*.md"]),
            patch.object(run_pipeline, "run_tool_args", side_effect=fake_run_tool_args),
        ):
            commit_hash = run_pipeline.git_add_commit(message)

        self.assertEqual(commit_hash, "abc123")
        self.assertEqual(commands[0], ["git", "add", "-A", "--", "manifest.json", ":(glob)chapters/ch_*.md"])
        self.assertEqual(commands[1], ["git", "commit", "-m", message, "--allow-empty"])

    def test_revision_target_chapters_keeps_full_eval_weakest_then_low_scores(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            chapters_dir = root / "chapters"
            eval_logs_dir = root / "eval_logs"
            chapters_dir.mkdir()
            eval_logs_dir.mkdir()
            for chapter_num in range(1, 5):
                (chapters_dir / f"ch_{chapter_num:02d}.md").write_text(f"# Chapter {chapter_num}\n\nText\n", encoding="utf-8")
            (eval_logs_dir / "20260322_000000_full.json").write_text(
                json.dumps({"weakest_chapter": 3}) + "\n",
                encoding="utf-8",
            )
            (eval_logs_dir / "20260322_000000_ch01.json").write_text(json.dumps({"overall_score": 7.2}) + "\n", encoding="utf-8")
            (eval_logs_dir / "20260322_000000_ch02.json").write_text(json.dumps({"overall_score": 5.2}) + "\n", encoding="utf-8")
            (eval_logs_dir / "20260322_000000_ch03.json").write_text(json.dumps({"overall_score": 5.7}) + "\n", encoding="utf-8")
            (eval_logs_dir / "20260322_000000_ch04.json").write_text(json.dumps({"overall_score": 5.2}) + "\n", encoding="utf-8")

            with (
                patch.object(run_pipeline, "CHAPTERS_DIR", chapters_dir),
                patch.object(run_pipeline, "EVAL_LOGS_DIR", eval_logs_dir),
            ):
                targets = run_pipeline.revision_target_chapters()

        self.assertEqual(targets, [3, 2, 4])

    def test_drafting_snapshots_previous_once_and_kept_final_chapter(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            chapters_dir = root / "chapters"
            scene_options_dir = root / "scene_options"
            story_state_dir = root / "state" / "story_state"
            eval_logs_dir = root / "eval_logs"
            chapters_dir.mkdir(parents=True)
            scene_options_dir.mkdir(parents=True)
            story_state_dir.mkdir(parents=True)
            eval_logs_dir.mkdir(parents=True)

            commands = []
            eval_scores = iter([5.4, 5.5, 6.4])

            def fake_uv_run(script, timeout=600, check=False):
                commands.append(script)
                if script == "advance_state.py --chapter 1":
                    (story_state_dir / "ch_01.json").write_text('{"chapter": 1}\n', encoding="utf-8")
                elif script == "advance_state.py --chapter 2":
                    (story_state_dir / "ch_02.json").write_text('{"chapter": 2}\n', encoding="utf-8")
                elif script == "plan_scene.py 2 --variants 4":
                    (scene_options_dir / "ch_02.json").write_text("[]\n", encoding="utf-8")
                elif script == "draft_chapter.py 2 --mode auto":
                    (chapters_dir / "ch_02.md").write_text(
                        "# Chapter 2\n\n" + ("Cass kept the bell hidden in his sleeve.\n" * 8),
                        encoding="utf-8",
                    )
                elif script == "evaluate.py --chapter 2":
                    score = next(eval_scores)
                    call_index = len([command for command in commands if command == script])
                    log_path = eval_logs_dir / f"20260322_000000_ch02_{call_index}.json"
                    log_path.write_text(json.dumps({"overall_score": score}) + "\n", encoding="utf-8")
                    return subprocess.CompletedProcess(
                        script,
                        0,
                        stdout=f"---\noverall_score: {score}\n\neval_log: {log_path}\n",
                        stderr="",
                    )
                return subprocess.CompletedProcess(script, 0, stdout="ok\n", stderr="")

            state = run_pipeline.default_state()
            state["phase"] = "drafting"
            state["chapters_total"] = 2
            state["chapters_drafted"] = 1
            with (
                patch.object(run_pipeline, "BASE_DIR", root),
                patch.object(run_pipeline, "CHAPTERS_DIR", chapters_dir),
                patch.object(run_pipeline, "SCENE_OPTIONS_DIR", scene_options_dir),
                patch.object(run_pipeline, "STORY_STATE_DIR", story_state_dir),
                patch.object(run_pipeline, "EVAL_LOGS_DIR", eval_logs_dir),
                patch.object(run_pipeline, "uv_run", side_effect=fake_uv_run),
                patch.object(run_pipeline, "build_manifest_and_gate", return_value={}),
                patch.object(run_pipeline, "git_add_commit", return_value="def456"),
                patch.object(run_pipeline, "save_state"),
                patch.object(run_pipeline, "log_result"),
                patch.object(run_pipeline, "restore_paths"),
                patch.object(run_pipeline, "is_critical_chapter", return_value=False),
                patch.object(run_pipeline, "risk_chapters", return_value=[]),
            ):
                updated = run_pipeline.run_drafting(state)
                snapshot_exists = (story_state_dir / "ch_02.json").exists()

        self.assertEqual(updated["phase"], "revision")
        self.assertEqual(commands.count("advance_state.py --chapter 1"), 1)
        self.assertEqual(commands.count("advance_state.py --chapter 2"), 1)
        self.assertTrue(snapshot_exists)

    def test_revision_rebuilds_evidence_pack_after_patch_before_full_eval(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            chapters_dir = root / "chapters"
            briefs_dir = root / "briefs"
            edit_logs_dir = root / "edit_logs"
            eval_logs_dir = root / "eval_logs"
            chapters_dir.mkdir(parents=True)
            briefs_dir.mkdir(parents=True)
            edit_logs_dir.mkdir(parents=True)
            eval_logs_dir.mkdir(parents=True)

            chapter_path = chapters_dir / "ch_01.md"
            chapter_path.write_text("# Chapter 1\n\nBEFORE PATCH\n", encoding="utf-8")
            brief_path = briefs_dir / "ch01_auto.md"
            brief_path.write_text("# Brief\n\n## Patch Directives\n- replace: \"BEFORE PATCH\" => \"AFTER PATCH\"\n", encoding="utf-8")
            evidence_path = eval_logs_dir / "evidence_pack.json"
            commands = []
            chapter_eval_calls = 0

            def fake_uv_run(script, timeout=600, check=False):
                nonlocal chapter_eval_calls
                commands.append(script)
                if script == "assemble_evidence_pack.py --novel":
                    snapshot = chapter_path.read_text(encoding="utf-8")
                    evidence_path.write_text(
                        json.dumps(
                            {
                                "generated_from": {
                                    "chapter_count": 1,
                                    "word_count": len(snapshot.split()),
                                    "manuscript_sha256": snapshot,
                                },
                                "snapshot": snapshot,
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                elif script == "apply_edits.py 1":
                    chapter_path.write_text("# Chapter 1\n\nAFTER PATCH\n", encoding="utf-8")
                elif script == "gen_brief.py --auto --require-patch-directives":
                    return subprocess.CompletedProcess(script, 0, stdout="", stderr="")
                return subprocess.CompletedProcess(script, 0, stdout="ok\n", stderr="")

            def fake_evaluate_chapter(chapter_num, include_risk=False):
                nonlocal chapter_eval_calls
                chapter_eval_calls += 1
                return (6.0, {}) if chapter_eval_calls == 1 else (6.6, {})

            def fake_evaluate_full(path):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("AFTER PATCH", payload["snapshot"])
                return 7.4, {}

            state = run_pipeline.default_state()
            state["phase"] = "revision"
            with (
                patch.object(run_pipeline, "BASE_DIR", root),
                patch.object(run_pipeline, "CHAPTERS_DIR", chapters_dir),
                patch.object(run_pipeline, "BRIEFS_DIR", briefs_dir),
                patch.object(run_pipeline, "EDIT_LOGS_DIR", edit_logs_dir),
                patch.object(run_pipeline, "EVAL_LOGS_DIR", eval_logs_dir),
                patch.object(run_pipeline, "uv_run", side_effect=fake_uv_run),
                patch.object(run_pipeline, "evaluate_chapter", side_effect=fake_evaluate_chapter),
                patch.object(run_pipeline, "evaluate_full", side_effect=fake_evaluate_full),
                patch.object(run_pipeline, "full_eval_weakest_chapter", return_value=1),
                patch.object(run_pipeline, "revision_target_chapters", return_value=[1]),
                patch.object(run_pipeline, "build_manifest_and_gate", return_value={}),
                patch.object(run_pipeline, "git_add_commit", return_value="ghi789"),
                patch.object(run_pipeline, "save_state"),
                patch.object(run_pipeline, "log_result"),
                patch.object(run_pipeline, "risk_chapters", return_value=[]),
            ):
                updated = run_pipeline.run_revision(state, max_cycles=1)

        self.assertEqual(updated["phase"], "review")
        self.assertEqual(commands.count("assemble_evidence_pack.py --novel"), 2)
        self.assertLess(commands.index("apply_edits.py 1"), len(commands))
        self.assertGreater(
            commands.index("assemble_evidence_pack.py --novel", commands.index("apply_edits.py 1")),
            commands.index("apply_edits.py 1"),
        )

    def test_apply_patch_revision_re_evaluates_restored_text_after_regression(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            chapters_dir = root / "chapters"
            eval_logs_dir = root / "eval_logs"
            chapters_dir.mkdir(parents=True)
            eval_logs_dir.mkdir(parents=True)

            chapter_path = chapters_dir / "ch_01.md"
            original_text = "# Chapter 1\n\nBEFORE PATCH\n"
            chapter_path.write_text(original_text, encoding="utf-8")
            brief_path = root / "brief.md"
            brief_path.write_text(
                "# Brief\n\n## Patch Directives\n- replace: \"BEFORE PATCH\" => \"AFTER PATCH\"\n",
                encoding="utf-8",
            )

            scores = iter([6.0, 5.5, 6.0])
            eval_call_count = 0

            def fake_uv_run(script, timeout=600, check=False):
                if script == f"patch_revision.py 1 {brief_path} --plan-only":
                    return subprocess.CompletedProcess(script, 0, stdout="ok\n", stderr="")
                if script == "apply_edits.py 1":
                    chapter_path.write_text("# Chapter 1\n\nAFTER PATCH\n", encoding="utf-8")
                    return subprocess.CompletedProcess(script, 0, stdout="ok\n", stderr="")
                raise AssertionError(f"Unexpected command: {script}")

            def fake_evaluate_chapter(chapter_num, include_risk=False):
                nonlocal eval_call_count
                eval_call_count += 1
                score = next(scores)
                log_path = eval_logs_dir / f"20260322_000000_ch01_{eval_call_count}.json"
                log_path.write_text(
                    json.dumps(
                        {
                            "overall_score": score,
                            "text_snapshot": chapter_path.read_text(encoding="utf-8"),
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return score, {"eval_log": str(log_path)}

            with (
                patch.object(run_pipeline, "CHAPTERS_DIR", chapters_dir),
                patch.object(run_pipeline, "EVAL_LOGS_DIR", eval_logs_dir),
                patch.object(run_pipeline, "uv_run", side_effect=fake_uv_run),
                patch.object(run_pipeline, "evaluate_chapter", side_effect=fake_evaluate_chapter),
            ):
                changed = run_pipeline.apply_patch_revision(1, brief_path, set())
                latest_log = run_pipeline.latest_chapter_eval_logs()[1]

            latest_payload = json.loads(latest_log.read_text(encoding="utf-8"))
            self.assertFalse(changed)
            self.assertEqual(eval_call_count, 3)
            self.assertEqual(chapter_path.read_text(encoding="utf-8"), original_text)
            self.assertIn("BEFORE PATCH", latest_payload["text_snapshot"])
            self.assertNotIn("AFTER PATCH", latest_payload["text_snapshot"])

    def test_revision_can_apply_multiple_patch_briefs_in_one_cycle(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            chapters_dir = root / "chapters"
            briefs_dir = root / "briefs"
            edit_logs_dir = root / "edit_logs"
            eval_logs_dir = root / "eval_logs"
            chapters_dir.mkdir(parents=True)
            briefs_dir.mkdir(parents=True)
            edit_logs_dir.mkdir(parents=True)
            eval_logs_dir.mkdir(parents=True)

            chapter_one = chapters_dir / "ch_01.md"
            chapter_two = chapters_dir / "ch_02.md"
            chapter_one.write_text("# Chapter 1\n\nBEFORE PATCH ONE\n", encoding="utf-8")
            chapter_two.write_text("# Chapter 2\n\nBEFORE PATCH TWO\n", encoding="utf-8")
            evidence_path = eval_logs_dir / "evidence_pack.json"
            (eval_logs_dir / "20260322_000000_full.json").write_text(
                json.dumps({"weakest_chapter": 1}) + "\n",
                encoding="utf-8",
            )
            (eval_logs_dir / "20260322_000000_ch01.json").write_text(json.dumps({"overall_score": 5.4}) + "\n", encoding="utf-8")
            (eval_logs_dir / "20260322_000000_ch02.json").write_text(json.dumps({"overall_score": 5.8}) + "\n", encoding="utf-8")
            commands = []
            eval_calls = {1: 0, 2: 0}

            def fake_uv_run(script, timeout=600, check=False):
                commands.append(script)
                if script == "assemble_evidence_pack.py --novel":
                    snapshot = "\n".join(
                        [
                            chapter_one.read_text(encoding="utf-8"),
                            chapter_two.read_text(encoding="utf-8"),
                        ]
                    )
                    evidence_path.write_text(
                        json.dumps({"snapshot": snapshot}) + "\n",
                        encoding="utf-8",
                    )
                elif script == "gen_brief.py --auto --require-patch-directives":
                    (briefs_dir / "ch01_auto.md").write_text(
                        "# Brief\n\n## Patch Directives\n- replace: \"BEFORE PATCH ONE\" => \"AFTER PATCH ONE\"\n",
                        encoding="utf-8",
                    )
                elif script == "gen_brief.py --eval 2 --require-patch-directives":
                    (briefs_dir / "ch02_eval.md").write_text(
                        "# Brief\n\n## Patch Directives\n- replace: \"BEFORE PATCH TWO\" => \"AFTER PATCH TWO\"\n",
                        encoding="utf-8",
                    )
                elif script == "apply_edits.py 1":
                    chapter_one.write_text("# Chapter 1\n\nAFTER PATCH ONE\n", encoding="utf-8")
                elif script == "apply_edits.py 2":
                    chapter_two.write_text("# Chapter 2\n\nAFTER PATCH TWO\n", encoding="utf-8")
                return subprocess.CompletedProcess(script, 0, stdout="ok\n", stderr="")

            def fake_evaluate_chapter(chapter_num, include_risk=False):
                eval_calls[chapter_num] += 1
                chapter_scores = {
                    1: (6.0, 6.4),
                    2: (5.8, 6.2),
                }
                pre_score, post_score = chapter_scores[chapter_num]
                return (pre_score, {}) if eval_calls[chapter_num] == 1 else (post_score, {})

            def fake_evaluate_full(path):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("AFTER PATCH ONE", payload["snapshot"])
                self.assertIn("AFTER PATCH TWO", payload["snapshot"])
                return 7.8, {}

            state = run_pipeline.default_state()
            state["phase"] = "revision"
            with (
                patch.object(run_pipeline, "BASE_DIR", root),
                patch.object(run_pipeline, "CHAPTERS_DIR", chapters_dir),
                patch.object(run_pipeline, "BRIEFS_DIR", briefs_dir),
                patch.object(run_pipeline, "EDIT_LOGS_DIR", edit_logs_dir),
                patch.object(run_pipeline, "EVAL_LOGS_DIR", eval_logs_dir),
                patch.object(run_pipeline, "uv_run", side_effect=fake_uv_run),
                patch.object(run_pipeline, "evaluate_chapter", side_effect=fake_evaluate_chapter),
                patch.object(run_pipeline, "evaluate_full", side_effect=fake_evaluate_full),
                patch.object(run_pipeline, "build_manifest_and_gate", return_value={}),
                patch.object(run_pipeline, "git_add_commit", return_value="ghi789"),
                patch.object(run_pipeline, "save_state"),
                patch.object(run_pipeline, "log_result"),
                patch.object(run_pipeline, "risk_chapters", return_value=[]),
            ):
                updated = run_pipeline.run_revision(state, max_cycles=1)

        self.assertEqual(updated["phase"], "review")
        self.assertIn("gen_brief.py --auto --require-patch-directives", commands)
        self.assertIn("gen_brief.py --eval 2 --require-patch-directives", commands)
        self.assertIn("apply_edits.py 1", commands)
        self.assertIn("apply_edits.py 2", commands)
        self.assertEqual(commands.count("assemble_evidence_pack.py --novel"), 2)


if __name__ == "__main__":
    unittest.main()
