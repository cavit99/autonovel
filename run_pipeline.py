#!/usr/bin/env python3
"""
run_pipeline.py — Orchestrate the autonovel pipeline from foundation to export.

Usage:
  python run_pipeline.py                    # run from current state
  python run_pipeline.py --from-scratch     # start fresh from planning/seed.md
  python run_pipeline.py --approve-bootstrap
                                         # continue foundation after bootstrap review
  python run_pipeline.py --phase foundation # run only foundation
  python run_pipeline.py --phase drafting   # run only drafting
  python run_pipeline.py --phase revision   # run only revision
  python run_pipeline.py --phase review     # run only review
  python run_pipeline.py --phase export     # run only export
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import shlex
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from manifest_tools import MANIFEST_PATH, load_manifest, planned_chapter_count, risk_chapters
from planning_split import normalize_thread_registry, parse_chapter_cards, parse_thread_registry
from project_paths import (
    ensure_parent_dir,
    ensure_planning_dir,
    legacy_planning_artifact_paths,
    migrate_planning_artifacts,
    planning_artifact_path,
    planning_artifact_paths,
    require_seed_path,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "state.json"
RESULTS_FILE = BASE_DIR / "results.tsv"
CHAPTERS_DIR = BASE_DIR / "chapters"
BRIEFS_DIR = BASE_DIR / "briefs"
EDIT_LOGS_DIR = BASE_DIR / "edit_logs"
EVAL_LOGS_DIR = BASE_DIR / "eval_logs"
SCENE_OPTIONS_DIR = BASE_DIR / "scene_options"
STORY_STATE_DIR = BASE_DIR / "state" / "story_state"
VARIANTS_DIR = CHAPTERS_DIR / "variants"

FOUNDATION_THRESHOLD = 7.5
CHAPTER_THRESHOLD = 6.0
RISK_INTERESTINGNESS_FLOOR = 7.0
RISK_COHERENCE_FLOOR = 5.0
CRITICAL_SCENE_THRESHOLD = 6.3
PATCH_REVISION_SCORE_CUTOFF = 7.0
MAX_FOUNDATION_ITERS = 20
MAX_CHAPTER_ATTEMPTS = 5
MIN_REVISION_CYCLES = 3
MAX_REVISION_CYCLES = 6
MAX_PATCH_REVISIONS_PER_CYCLE = 3
PLATEAU_DELTA = 0.3

PHASE_ORDER = ["foundation", "drafting", "revision", "review", "export"]
BOOTSTRAP_ARTIFACT_NAMES = (
    "world",
    "characters",
    "character_engine",
    "perspective",
    "voice",
    "voice_discovery",
    "canon",
)
FOUNDATION_STRUCTURAL_ARTIFACT_NAMES = (
    "arc_outline",
    "chapter_cards",
    "thread_registry",
    "outline",
)
PIPELINE_GIT_STAGE_PATHSPECS = (
    "planning/world.md",
    "planning/characters.md",
    "planning/character_engine.json",
    "planning/perspective.md",
    "planning/voice.md",
    "planning/voice_discovery.json",
    "planning/arc_outline.md",
    "planning/chapter_cards.md",
    "planning/thread_registry.json",
    "planning/outline.md",
    "planning/canon.md",
    "world.md",
    "characters.md",
    "character_engine.json",
    "perspective.md",
    "voice.md",
    "voice_discovery.json",
    "arc_outline.md",
    "chapter_cards.md",
    "thread_registry.json",
    "outline.md",
    "canon.md",
    "manifest.json",
    "results.tsv",
    "state.json",
    "manuscript.md",
    "arc_summary.md",
    "reviews.md",
    "typeset/novel.tex",
    "typeset/novel.pdf",
    ":(glob)chapters/ch_*.md",
    ":(glob)chapters/variants/ch_*.md",
    ":(glob)briefs/ch*_*.md",
    ":(glob)scene_options/ch_*.json",
    ":(glob)state/story_state/ch_*.json",
    ":(glob)edit_logs/*.json",
    ":(glob)eval_logs/*.json",
)


# ---------------------------------------------------------------------------
# Helpers: state management
# ---------------------------------------------------------------------------

def default_state() -> dict:
    return {
        "phase": "foundation",
        "current_focus": "bootstrap",
        "bootstrap_complete": False,
        "bootstrap_approved": False,
        "iteration": 0,
        "foundation_score": 0.0,
        "lore_score": 0.0,
        "chapters_drafted": 0,
        "chapters_total": 0,
        "novel_score": 0.0,
        "revision_cycle": 0,
        "debts": [],
    }


def load_state() -> dict:
    state = default_state()
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            state.update(loaded)

    if state.get("bootstrap_approved"):
        state["bootstrap_complete"] = True

    phase = str(state.get("phase", "foundation"))
    if phase in {"drafting", "revision", "review", "export", "complete"}:
        state["bootstrap_complete"] = True
        state["bootstrap_approved"] = True
    elif phase == "foundation":
        if all(planning_artifact_path(name, BASE_DIR).exists() for name in FOUNDATION_STRUCTURAL_ARTIFACT_NAMES):
            state["bootstrap_complete"] = True
            state["bootstrap_approved"] = True
        elif all(planning_artifact_path(name, BASE_DIR).exists() for name in BOOTSTRAP_ARTIFACT_NAMES):
            state["bootstrap_complete"] = True

    return state


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


# ---------------------------------------------------------------------------
# Helpers: logging
# ---------------------------------------------------------------------------

def log_result(commit: str, phase: str, score, word_count: int, status: str, description: str) -> None:
    header = "commit\tphase\tscore\tword_count\tstatus\tdescription\n"
    if not RESULTS_FILE.exists() or RESULTS_FILE.stat().st_size == 0:
        RESULTS_FILE.write_text(header, encoding="utf-8")
    with open(RESULTS_FILE, "a", encoding="utf-8") as handle:
        handle.write(f"{commit}\t{phase}\t{score}\t{word_count}\t{status}\t{description}\n")


def banner(text: str, char: str = "=", width: int = 60) -> None:
    print(f"\n{char * width}")
    print(f"  {text}")
    print(f"{char * width}")


def step(text: str) -> None:
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] {text}")


# ---------------------------------------------------------------------------
# Helpers: subprocess execution
# ---------------------------------------------------------------------------

STDERR_PREVIEW_CHARS = 1600
SUBPROCESS_HEARTBEAT_SECONDS = 30.0
OUTLINE_CHAPTER_HEADING_RE = re.compile(r"^###\s*Ch(?:apter)?\s*(\d+)", re.MULTILINE)
OUTLINE_CHAPTER_TITLE_RE = re.compile(r"^###\s*Ch(?:apter)?\s*(\d+)\s*:\s*(.+)$", re.MULTILINE)


def preview_stderr(text: str, limit: int = STDERR_PREVIEW_CHARS) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return "...<stderr truncated>\n" + text[-limit:]


def _relay_child_stream(
    stream, sink, buffer: list[str]
) -> None:
    if stream is None:
        return
    try:
        for line in iter(stream.readline, ""):
            buffer.append(line)
            print(line, end="", file=sink, flush=True)
    finally:
        stream.close()


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if hasattr(os, "killpg"):
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        return


def _run_subprocess(
    command: str | list[str],
    *,
    display_cmd: str,
    shell: bool,
    timeout: int,
) -> subprocess.CompletedProcess:
    step(f"RUN: {display_cmd}")
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    started_at = time.monotonic()
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    timed_out = False
    returncode = -1

    process: subprocess.Popen[str] | None = None
    stdout_thread: threading.Thread | None = None
    stderr_thread: threading.Thread | None = None
    try:
        process = subprocess.Popen(
            command,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(BASE_DIR),
            env=env,
            start_new_session=hasattr(os, "killpg"),
        )
        stdout_thread = threading.Thread(
            target=_relay_child_stream,
            args=(process.stdout, sys.stdout, stdout_chunks),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_relay_child_stream,
            args=(process.stderr, sys.stderr, stderr_chunks),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        next_heartbeat = started_at + SUBPROCESS_HEARTBEAT_SECONDS
        while True:
            now = time.monotonic()
            elapsed = now - started_at
            remaining = timeout - elapsed
            if remaining <= 0:
                raise subprocess.TimeoutExpired(display_cmd, timeout)
            if now >= next_heartbeat:
                step(f"HEARTBEAT: still running after {elapsed:.1f}s: {display_cmd}")
                next_heartbeat += SUBPROCESS_HEARTBEAT_SECONDS
                continue
            wait_timeout = min(remaining, next_heartbeat - now)
            try:
                returncode = process.wait(timeout=wait_timeout)
                break
            except subprocess.TimeoutExpired:
                continue
    except subprocess.TimeoutExpired:
        timed_out = True
        print(f"    ERROR: timed out after {timeout}s")
        if process is not None:
            _terminate_process(process)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
    finally:
        if process is not None:
            if stdout_thread is not None:
                stdout_thread.join()
            if stderr_thread is not None:
                stderr_thread.join()

    elapsed = time.monotonic() - started_at
    stdout_text = "".join(stdout_chunks)
    stderr_text = "".join(stderr_chunks)
    if timed_out:
        if stderr_text and not stderr_text.endswith("\n"):
            stderr_text += "\n"
        stderr_text += "TIMEOUT"
        returncode = -1

    result = subprocess.CompletedProcess(command, returncode=returncode, stdout=stdout_text, stderr=stderr_text)
    step(f"DONE ({elapsed:.1f}s, exit {result.returncode}): {display_cmd}")

    if result.returncode != 0:
        print(f"    WARN: exit code {result.returncode}")
        stderr_text = preview_stderr(result.stderr or "")
        if stderr_text:
            print(f"    stderr: {stderr_text}")
    return result


def run_tool(cmd: str, timeout: int = 600, check: bool = False) -> subprocess.CompletedProcess:
    result = _run_subprocess(cmd, display_cmd=cmd, shell=True, timeout=timeout)
    if result.returncode != 0 and check:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result


def run_tool_args(args: list[str], timeout: int = 600, check: bool = False) -> subprocess.CompletedProcess:
    result = _run_subprocess(args, display_cmd=shlex.join(args), shell=False, timeout=timeout)
    if result.returncode != 0 and check:
        raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
    return result


def uv_run(script: str, timeout: int = 600, check: bool = False) -> subprocess.CompletedProcess:
    return run_tool(f"uv run python {script}", timeout=timeout, check=check)


def uv_run_to_file(script: str, output_path: Path, timeout: int = 600) -> subprocess.CompletedProcess:
    result = uv_run(script, timeout=timeout)
    if result.returncode == 0:
        ensure_parent_dir(output_path)
        output_path.write_text(result.stdout.rstrip() + "\n", encoding="utf-8")
    return result


def require_success(result: subprocess.CompletedProcess, context: str) -> subprocess.CompletedProcess:
    if result.returncode != 0:
        raise RuntimeError(f"{context} failed with exit code {result.returncode}")
    return result


# ---------------------------------------------------------------------------
# Helpers: git operations
# ---------------------------------------------------------------------------

def git_pathspec_has_matches(pathspec: str) -> bool:
    result = run_tool_args(
        ["git", "ls-files", "--cached", "--others", "--ignored", "--exclude-standard", "--", pathspec],
        timeout=30,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def pipeline_stage_pathspecs() -> list[str]:
    return [pathspec for pathspec in PIPELINE_GIT_STAGE_PATHSPECS if git_pathspec_has_matches(pathspec)]


def git_add_commit(message: str) -> str:
    stage_pathspecs = pipeline_stage_pathspecs()
    if stage_pathspecs:
        require_success(
            run_tool_args(["git", "add", "-f", "-A", "--", *stage_pathspecs], timeout=120),
            "git add",
        )
    else:
        step("GIT: no pipeline artifact paths matched for staging")
    result = run_tool_args(["git", "commit", "-m", message, "--allow-empty"], timeout=120)
    if result.returncode != 0:
        step("GIT: nothing to commit or commit failed")
        return ""
    hash_result = run_tool_args(["git", "rev-parse", "--short", "HEAD"], timeout=30)
    commit_hash = hash_result.stdout.strip()
    step(f"GIT COMMIT: {commit_hash} — {message}")
    return commit_hash


def git_short_hash() -> str:
    result = run_tool_args(["git", "rev-parse", "--short", "HEAD"], timeout=30)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def is_git_tracked(path: Path) -> bool:
    rel = shlex.quote(str(path.relative_to(BASE_DIR)))
    result = run_tool(f"git ls-files --error-unmatch {rel}", timeout=30)
    return result.returncode == 0


def restore_path(path: Path) -> None:
    if not path.exists() and not is_git_tracked(path):
        return
    if path.exists() and path.is_dir():
        shutil.rmtree(path)
        return
    if is_git_tracked(path):
        rel = shlex.quote(str(path.relative_to(BASE_DIR)))
        run_tool(f"git restore --source=HEAD --staged --worktree -- {rel}", timeout=30)
        return
    if path.exists():
        path.unlink()


def restore_paths(paths: list[Path]) -> None:
    for path in paths:
        restore_path(path)


def clear_directory_contents(path: Path) -> list[Path]:
    removed: list[Path] = []
    if not path.exists():
        return removed
    for child in sorted(path.iterdir()):
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed.append(child)
    return removed


def generated_planning_files() -> list[Path]:
    # These are regenerated from planning/seed.md during the foundation phase.
    return list(planning_artifact_paths(BASE_DIR).values())


def foundation_structural_generated_files() -> list[Path]:
    return [planning_artifact_path(name, BASE_DIR) for name in FOUNDATION_STRUCTURAL_ARTIFACT_NAMES] + [MANIFEST_PATH]


def legacy_generated_planning_files() -> list[Path]:
    return list(legacy_planning_artifact_paths(BASE_DIR).values())


def clear_from_scratch_artifacts() -> list[Path]:
    removed: list[Path] = []

    for path in generated_planning_files() + legacy_generated_planning_files():
        if path.exists():
            path.unlink()
            removed.append(path)

    for path in (
        MANIFEST_PATH,
        RESULTS_FILE,
        BASE_DIR / "arc_summary.md",
        BASE_DIR / "manuscript.md",
        BASE_DIR / "reviews.md",
    ):
        if path.exists():
            path.unlink()
            removed.append(path)

    for path in sorted(CHAPTERS_DIR.glob("ch_*.md")):
        path.unlink()
        removed.append(path)

    for path in sorted(BRIEFS_DIR.glob("ch[0-9][0-9]_*.md")):
        path.unlink()
        removed.append(path)

    for directory in (SCENE_OPTIONS_DIR, STORY_STATE_DIR, EDIT_LOGS_DIR, EVAL_LOGS_DIR, VARIANTS_DIR):
        removed.extend(clear_directory_contents(directory))

    return removed


# ---------------------------------------------------------------------------
# Helpers: score parsing and manifests
# ---------------------------------------------------------------------------

def parse_score(stdout: str, key: str = "overall_score") -> float:
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}:"):
            value = stripped.split(":", 1)[1].strip()
            try:
                return float(value)
            except ValueError:
                continue
    return -1.0


def parse_lore_score(stdout: str) -> float:
    return parse_score(stdout, "lore_score")


def parse_eval_log_path(stdout: str) -> Path | None:
    match = re.search(r"eval_log:\s*(.+)$", stdout, re.MULTILINE)
    if not match:
        return None
    path = Path(match.group(1).strip())
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def load_eval_result(stdout: str) -> dict:
    path = parse_eval_log_path(stdout)
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def summarize_chapter_cards_artifact() -> None:
    path = planning_artifact_path("chapter_cards", BASE_DIR)
    try:
        cards = parse_chapter_cards(path.read_text(encoding="utf-8"))
    except OSError as exc:
        step(f"Chapter cards summary unavailable: {exc}")
        return
    step(f"Chapter cards ready: {len(cards)} chapters parsed")


def summarize_thread_registry_artifact() -> None:
    path = planning_artifact_path("thread_registry", BASE_DIR)
    try:
        threads = normalize_thread_registry(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        step(f"Thread registry summary unavailable: {exc}")
        return
    step(f"Thread registry ready: {len(threads)} threads")


def summarize_outline_artifact() -> None:
    path = planning_artifact_path("outline", BASE_DIR)
    try:
        chapter_count = len(OUTLINE_CHAPTER_HEADING_RE.findall(path.read_text(encoding="utf-8")))
    except OSError as exc:
        step(f"Legacy outline summary unavailable: {exc}")
        return
    step(f"Legacy outline ready: {chapter_count} chapters")


def validate_chapter_cards_artifact() -> list[dict[str, object]]:
    path = planning_artifact_path("chapter_cards", BASE_DIR)
    try:
        cards = parse_chapter_cards(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"gen_chapter_cards.py did not produce a readable {path}") from exc
    if not cards:
        raise RuntimeError(f"gen_chapter_cards.py produced {path} but it parsed to 0 chapter cards")
    return cards


def validate_thread_registry_artifact() -> list[dict[str, object]]:
    path = planning_artifact_path("thread_registry", BASE_DIR)
    try:
        threads = parse_thread_registry(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"gen_thread_registry.py did not produce a readable {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gen_thread_registry.py produced invalid JSON in {path}") from exc

    if not threads:
        raise RuntimeError(f"gen_thread_registry.py produced an empty {path}")
    if not any(
        str(thread.get("description", "")).strip()
        or int(thread.get("first_seen") or thread.get("planted") or 0) > 0
        or int(thread.get("payoff") or 0) > 0
        for thread in threads
    ):
        raise RuntimeError(f"gen_thread_registry.py produced a non-meaningful {path}")
    return threads


def validate_outline_matches_chapter_cards(cards: list[dict[str, object]]) -> None:
    path = planning_artifact_path("outline", BASE_DIR)
    try:
        outline_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"gen_outline_part2.py did not produce a readable {path}") from exc

    outline_count = len(OUTLINE_CHAPTER_HEADING_RE.findall(outline_text))
    if outline_count != len(cards):
        raise RuntimeError(
            f"gen_outline_part2.py produced {path} with {outline_count} chapters, "
            f"but planning/chapter_cards.md has {len(cards)}"
        )

    outline_titles = {
        int(match.group(1)): match.group(2).strip()
        for match in OUTLINE_CHAPTER_TITLE_RE.finditer(outline_text)
    }
    for card in cards:
        number = int(card.get("number", 0) or 0)
        outline_title = outline_titles.get(number, "")
        if outline_title and outline_title != str(card.get("title", "")).strip():
            raise RuntimeError(
                f"gen_outline_part2.py produced {path} with title mismatch for chapter {number}: "
                f"{outline_title!r} != {str(card.get('title', '')).strip()!r}"
            )


def count_words_in_chapters() -> int:
    return sum(len(path.read_text(encoding="utf-8").split()) for path in CHAPTERS_DIR.glob("ch_*.md"))


def count_chapter_files() -> int:
    return len(list(CHAPTERS_DIR.glob("ch_*.md")))


def bootstrap_approval_pending(state: dict) -> bool:
    return bool(state.get("bootstrap_complete")) and not bool(state.get("bootstrap_approved"))


def bootstrap_review_message() -> str:
    return (
        "Bootstrap artifacts are ready for review in planning/world.md, planning/characters.md, "
        "planning/perspective.md, planning/voice.md, and planning/canon.md. "
        "Re-run with --approve-bootstrap to continue into structural planning."
    )


def get_total_chapters(state: dict) -> int:
    total = int(state.get("chapters_total", 0) or 0)
    if total > 0:
        return total
    return planned_chapter_count(BASE_DIR) or count_chapter_files() or 0


def build_manifest_and_gate(phase: str, chapter: int | None = None) -> dict:
    command = f"build_manifest.py --phase {phase}"
    if chapter is not None:
        command += f" --chapter {chapter}"
    require_success(uv_run(command, timeout=300), f"build_manifest ({phase})")

    gate_command = f"consistency_gate.py --phase {phase}"
    if chapter is not None:
        gate_command += f" --chapter {chapter}"
    require_success(uv_run(gate_command, timeout=120), f"consistency_gate ({phase})")
    return load_manifest(MANIFEST_PATH)


def evaluate_chapter(chapter_num: int, *, include_risk: bool = False) -> tuple[float, dict]:
    command = f"evaluate.py --chapter {chapter_num}"
    if include_risk:
        command += " --risk"
    result = require_success(uv_run(command, timeout=600), f"evaluate chapter {chapter_num}")
    return parse_score(result.stdout, "overall_score"), load_eval_result(result.stdout)


def evaluate_full(evidence_path: Path | None = None) -> tuple[float, dict]:
    command = "evaluate.py --full"
    if evidence_path is not None:
        command += f" --evidence {shlex.quote(str(evidence_path))}"
    result = require_success(uv_run(command, timeout=900), "evaluate full novel")
    score = parse_score(result.stdout, "novel_score")
    if score < 0:
        score = parse_score(result.stdout, "overall_score")
    return score, load_eval_result(result.stdout)


def chapter_meets_threshold(score: float, eval_data: dict, *, is_risk: bool) -> bool:
    if score < CHAPTER_THRESHOLD:
        return False
    if not is_risk:
        return True
    risk = eval_data.get("risk_assessment", {}) if isinstance(eval_data, dict) else {}
    interestingness = float(risk.get("interestingness", 0) or 0)
    coherence = float(risk.get("coherence_floor", 0) or 0)
    return interestingness >= RISK_INTERESTINGNESS_FLOOR and coherence >= RISK_COHERENCE_FLOOR


def is_critical_chapter(chapter_num: int, total_chapters: int) -> bool:
    if total_chapters <= 2:
        return True
    midpoint = max(1, total_chapters // 2)
    return chapter_num in {1, midpoint, total_chapters}


def latest_auto_brief() -> Path | None:
    briefs = sorted(BRIEFS_DIR.glob("ch*_auto.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    return briefs[0] if briefs else None


def extract_chapter_number_from_path(path: Path) -> int | None:
    match = re.search(r"ch(\d+)", path.name)
    if not match:
        return None
    return int(match.group(1))


def clear_variant_artifacts(chapter_num: int) -> None:
    for path in VARIANTS_DIR.glob(f"ch_{chapter_num:02d}_*.md"):
        path.unlink(missing_ok=True)
    for path in EDIT_LOGS_DIR.glob(f"ch{chapter_num:02d}_variant*.json"):
        path.unlink(missing_ok=True)


def evidence_pack_path() -> Path:
    return EVAL_LOGS_DIR / "evidence_pack.json"


def story_state_snapshot_path(chapter_num: int) -> Path:
    return STORY_STATE_DIR / f"ch_{chapter_num:02d}.json"


def snapshot_story_state(chapter_num: int) -> None:
    require_success(uv_run(f"advance_state.py --chapter {chapter_num}", timeout=300), f"advance_state.py --chapter {chapter_num}")


def ensure_story_state_snapshot(chapter_num: int) -> None:
    if chapter_num < 1:
        return
    if story_state_snapshot_path(chapter_num).exists():
        return
    snapshot_story_state(chapter_num)


def load_json_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def latest_full_eval_log() -> Path | None:
    fulls = sorted(EVAL_LOGS_DIR.glob("*_full.json"))
    return fulls[-1] if fulls else None


def full_eval_weakest_chapter() -> int | None:
    full_eval_path = latest_full_eval_log()
    if full_eval_path is None:
        return None
    full_eval = load_json_file(full_eval_path) or {}
    weakest = full_eval.get("weakest_chapter")
    return weakest if isinstance(weakest, int) and weakest > 0 else None


def latest_chapter_eval_logs() -> dict[int, Path]:
    latest_logs: dict[int, Path] = {}
    for path in sorted(EVAL_LOGS_DIR.glob("*_ch*.json")):
        chapter_num = extract_chapter_number_from_path(path)
        if chapter_num is not None:
            latest_logs[chapter_num] = path
    return latest_logs


def revision_target_chapters(limit: int = MAX_PATCH_REVISIONS_PER_CYCLE) -> list[int]:
    if limit <= 0:
        return []

    targets: list[int] = []
    seen: set[int] = set()
    weakest = full_eval_weakest_chapter()
    if weakest is not None and (CHAPTERS_DIR / f"ch_{weakest:02d}.md").exists():
        targets.append(weakest)
        seen.add(weakest)

    scored_candidates: list[tuple[float, int]] = []
    for chapter_num, eval_path in latest_chapter_eval_logs().items():
        if chapter_num in seen:
            continue
        if not (CHAPTERS_DIR / f"ch_{chapter_num:02d}.md").exists():
            continue
        payload = load_json_file(eval_path)
        if payload is None:
            continue
        try:
            score = float(payload.get("overall_score"))
        except (TypeError, ValueError):
            continue
        if score <= PATCH_REVISION_SCORE_CUTOFF:
            scored_candidates.append((score, chapter_num))

    for _score, chapter_num in sorted(scored_candidates, key=lambda item: (item[0], item[1])):
        targets.append(chapter_num)
        seen.add(chapter_num)
        if len(targets) >= limit:
            break
    return targets[:limit]


def revision_brief_path(chapter_num: int, suffix: str) -> Path:
    return BRIEFS_DIR / f"ch{chapter_num:02d}_{suffix}.md"


def generate_patch_brief(chapter_num: int, *, use_auto: bool) -> Path | None:
    if use_auto:
        command = "gen_brief.py --auto --require-patch-directives"
        brief_path = revision_brief_path(chapter_num, "auto")
    else:
        command = f"gen_brief.py --eval {chapter_num} --require-patch-directives"
        brief_path = revision_brief_path(chapter_num, "eval")

    result = uv_run(command, timeout=300)
    if result.returncode != 0:
        step(f"No patch-friendly brief available for Chapter {chapter_num}; skipping")
        return None
    if brief_path.exists():
        return brief_path
    if use_auto:
        fallback = latest_auto_brief()
        if fallback is not None and extract_chapter_number_from_path(fallback) == chapter_num:
            return fallback
    step(f"WARNING: brief generation succeeded but {brief_path.name} was not found")
    return None


def apply_patch_revision(chapter_num: int, brief_path: Path, risk_set: set[int]) -> bool:
    step(f"Applying patch revision for Chapter {chapter_num}...")
    chapter_path = CHAPTERS_DIR / f"ch_{chapter_num:02d}.md"
    pre_text = chapter_path.read_text(encoding="utf-8") if chapter_path.exists() else ""
    pre_score, _pre_eval = evaluate_chapter(chapter_num, include_risk=chapter_num in risk_set)
    require_success(
        uv_run(
            f"patch_revision.py {chapter_num} {shlex.quote(str(brief_path))} --plan-only",
            timeout=600,
        ),
        f"patch_revision.py {chapter_num}",
    )
    require_success(uv_run(f"apply_edits.py {chapter_num}", timeout=120), f"apply_edits.py {chapter_num}")
    post_score, _post_eval = evaluate_chapter(chapter_num, include_risk=chapter_num in risk_set)
    step(f"Chapter {chapter_num} revision score: {pre_score} -> {post_score}")
    if post_score < pre_score and chapter_path.exists():
        chapter_path.write_text(pre_text, encoding="utf-8")
        step("Patch revision regressed; restored pre-revision chapter text")
        restored_score, _restored_eval = evaluate_chapter(chapter_num, include_risk=chapter_num in risk_set)
        step(f"Restored Chapter {chapter_num} re-evaluated at {restored_score}")
        return False
    return True


def build_manuscript() -> Path:
    manuscript_path = BASE_DIR / "manuscript.md"
    parts = []
    for chapter_path in sorted(CHAPTERS_DIR.glob("ch_*.md")):
        text = chapter_path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(text)
    if parts:
        manuscript_path.write_text("\n\n---\n\n".join(parts) + "\n", encoding="utf-8")
    return manuscript_path


# ---------------------------------------------------------------------------
# PHASE 1 — FOUNDATION
# ---------------------------------------------------------------------------

def run_foundation_bootstrap(state: dict) -> dict:
    if state.get("bootstrap_complete"):
        return state

    banner("FOUNDATION BOOTSTRAP", "-")

    step("Generating world bible...")
    require_success(
        uv_run_to_file("gen_world.py", planning_artifact_path("world", BASE_DIR), timeout=300),
        "gen_world.py",
    )

    step("Generating characters and character engine...")
    require_success(
        uv_run_to_file(
            "gen_characters.py --emit-engine",
            planning_artifact_path("characters", BASE_DIR),
            timeout=300,
        ),
        "gen_characters.py --emit-engine",
    )

    step("Generating governing perspective...")
    require_success(uv_run("gen_perspective.py", timeout=300), "gen_perspective.py")

    step("Discovering voice...")
    require_success(uv_run("discover_voice.py --trials 8", timeout=900), "discover_voice.py")

    step("Generating canon...")
    require_success(
        uv_run_to_file("gen_canon.py", planning_artifact_path("canon", BASE_DIR), timeout=300),
        "gen_canon.py",
    )

    state["bootstrap_complete"] = True
    state["bootstrap_approved"] = False
    state["current_focus"] = "awaiting_bootstrap_approval"
    save_state(state)

    banner("BOOTSTRAP COMPLETE — AWAITING APPROVAL")
    print(f"  {bootstrap_review_message()}")
    return state


def run_foundation(state: dict, *, max_iters: int = MAX_FOUNDATION_ITERS) -> dict:
    banner("PHASE 1: FOUNDATION", "=")

    state = run_foundation_bootstrap(state)
    if bootstrap_approval_pending(state):
        step(bootstrap_review_message())
        return state

    best_score = state.get("foundation_score", 0.0)
    iteration = state.get("iteration", 0)
    generated_paths = foundation_structural_generated_files()
    state["current_focus"] = "structural_planning"

    for i in range(iteration + 1, max_iters + 1):
        banner(f"Foundation Iteration {i}", "-")
        state["iteration"] = i

        step("Generating arc outline...")
        require_success(uv_run("gen_arc.py", timeout=300), "gen_arc.py")

        step("Generating chapter cards...")
        require_success(uv_run("gen_chapter_cards.py", timeout=300), "gen_chapter_cards.py")
        cards = validate_chapter_cards_artifact()
        summarize_chapter_cards_artifact()

        step("Generating thread registry...")
        require_success(uv_run("gen_thread_registry.py", timeout=300), "gen_thread_registry.py")
        validate_thread_registry_artifact()
        summarize_thread_registry_artifact()

        step("Refreshing legacy outline compatibility artifact...")
        require_success(uv_run("gen_outline_part2.py", timeout=300), "gen_outline_part2.py")
        validate_outline_matches_chapter_cards(cards)
        summarize_outline_artifact()

        build_manifest_and_gate("foundation")

        step("Running voice fingerprint telemetry...")
        require_success(uv_run("voice_fingerprint.py", timeout=120), "voice_fingerprint.py")

        step("Evaluating foundation...")
        eval_result = require_success(uv_run("evaluate.py --phase foundation", timeout=600), "evaluate foundation")
        score = parse_score(eval_result.stdout, "overall_score")
        lore = parse_lore_score(eval_result.stdout)
        step(f"Foundation score: {score} (lore: {lore}, prev best: {best_score})")

        if score > best_score:
            commit_hash = git_add_commit(f"foundation iter {i}: score {score} (lore {lore})")
            log_result(commit_hash, "foundation", score, 0, "keep", f"Iteration {i}: score improved {best_score} -> {score}")
            best_score = score
            state["foundation_score"] = score
            state["lore_score"] = lore
            save_state(state)
        else:
            step(f"Score did not improve ({score} <= {best_score}), restoring generated artifacts")
            restore_paths(generated_paths)
            log_result("discarded", "foundation", score, 0, "discard", f"Iteration {i}: no improvement")

        if best_score >= FOUNDATION_THRESHOLD:
            step(f"Foundation score {best_score} >= {FOUNDATION_THRESHOLD} — PASSED")
            break
    else:
        step(f"WARNING: max iterations ({max_iters}) reached with score {best_score}")

    total = planned_chapter_count(BASE_DIR)
    state["chapters_total"] = total
    state["phase"] = "drafting"
    state["current_focus"] = "chapter_drafting"
    state["bootstrap_approved"] = True
    save_state(state)

    banner(f"FOUNDATION COMPLETE — score {best_score}, {total} chapters planned")
    return state


# ---------------------------------------------------------------------------
# PHASE 2 — DRAFTING
# ---------------------------------------------------------------------------

def run_drafting(state: dict) -> dict:
    banner("PHASE 2: DRAFTING", "=")

    total = get_total_chapters(state)
    risk_set = set(risk_chapters(BASE_DIR))
    start_chapter = state.get("chapters_drafted", 0) + 1

    CHAPTERS_DIR.mkdir(exist_ok=True)
    SCENE_OPTIONS_DIR.mkdir(exist_ok=True)

    for ch in range(start_chapter, total + 1):
        banner(f"Drafting Chapter {ch}/{total}", "-")
        drafted = False
        is_risk = ch in risk_set

        if ch > 1:
            ensure_story_state_snapshot(ch - 1)

        for attempt in range(1, MAX_CHAPTER_ATTEMPTS + 1):
            step(f"Attempt {attempt}/{MAX_CHAPTER_ATTEMPTS}")

            require_success(uv_run(f"plan_scene.py {ch} --variants 4", timeout=300), f"plan_scene.py {ch}")
            require_success(uv_run(f"draft_chapter.py {ch} --mode auto", timeout=900), f"draft_chapter.py {ch}")

            ch_file = CHAPTERS_DIR / f"ch_{ch:02d}.md"
            if not ch_file.exists() or ch_file.stat().st_size < 100:
                step("Chapter file missing or too short, retrying...")
                continue

            word_count = len(ch_file.read_text(encoding="utf-8").split())
            score, eval_data = evaluate_chapter(ch, include_risk=is_risk)
            step(f"Chapter {ch} score: {score}")

            baseline_text = ch_file.read_text(encoding="utf-8")
            baseline_score = score
            baseline_eval = eval_data

            if is_critical_chapter(ch, total) or is_risk or score < CRITICAL_SCENE_THRESHOLD:
                step("Running variant drafting/selection pass...")
                require_success(uv_run(f"draft_variant.py {ch} --variants 3 --mode auto", timeout=1200), f"draft_variant.py {ch}")
                require_success(uv_run(f"compare_variants.py {ch}", timeout=600), f"compare_variants.py {ch}")
                variant_score, variant_eval = evaluate_chapter(ch, include_risk=is_risk)
                step(f"Variant pass score: {variant_score}")
                if variant_score >= baseline_score:
                    score = variant_score
                    eval_data = variant_eval
                else:
                    step("Variant pass regressed chapter score; restoring baseline draft")
                    ch_file.write_text(baseline_text, encoding="utf-8")
                    score = baseline_score
                    eval_data = baseline_eval

            build_manifest_and_gate("drafting", chapter=ch)

            if chapter_meets_threshold(score, eval_data, is_risk=is_risk):
                snapshot_story_state(ch)
                commit_hash = git_add_commit(f"ch{ch:02d}: score {score}, {word_count}w")
                log_result(commit_hash, f"ch{ch:02d}", score, word_count, "keep", f"Chapter {ch} (attempt {attempt})")
                state["chapters_drafted"] = ch
                save_state(state)
                drafted = True
                break

            is_final_attempt = attempt == MAX_CHAPTER_ATTEMPTS
            action = "preserving final chapter attempt for fallback" if is_final_attempt else "restoring chapter attempt"
            step(f"Score {score} did not meet chapter gate, {action}")
            log_result("discarded", f"ch{ch:02d}", score, word_count, "discard", f"Chapter {ch} attempt {attempt}")
            if not is_final_attempt:
                restore_paths([ch_file])
            clear_variant_artifacts(ch)

        if not drafted:
            step(f"WARNING: Chapter {ch} failed all {MAX_CHAPTER_ATTEMPTS} attempts, keeping last attempt")
            ch_file = CHAPTERS_DIR / f"ch_{ch:02d}.md"
            if ch_file.exists():
                word_count = len(ch_file.read_text(encoding="utf-8").split())
                build_manifest_and_gate("drafting", chapter=ch)
                snapshot_story_state(ch)
                commit_hash = git_add_commit(f"ch{ch:02d}: best-effort after {MAX_CHAPTER_ATTEMPTS} attempts")
                log_result(commit_hash, f"ch{ch:02d}", "?", word_count, "forced", f"Chapter {ch}: kept after max attempts")
                state["chapters_drafted"] = ch
                save_state(state)

    state["phase"] = "revision"
    state["current_focus"] = "full_novel"
    state["chapters_drafted"] = total
    state["revision_cycle"] = 0
    save_state(state)

    banner(f"DRAFTING COMPLETE — {total} chapters, {count_words_in_chapters()} words")
    return state


# ---------------------------------------------------------------------------
# PHASE 3 — REVISION
# ---------------------------------------------------------------------------

def run_revision(state: dict, max_cycles: int = MAX_REVISION_CYCLES) -> dict:
    banner("PHASE 3: REVISION", "=")

    BRIEFS_DIR.mkdir(exist_ok=True)
    EDIT_LOGS_DIR.mkdir(exist_ok=True)

    prev_score = state.get("novel_score", 0.0)
    start_cycle = state.get("revision_cycle", 0) + 1
    max_cycles = min(max_cycles, MAX_REVISION_CYCLES)

    for cycle in range(start_cycle, max_cycles + 1):
        banner(f"Revision Cycle {cycle}/{max_cycles}", "-")

        require_success(uv_run("adversarial_edit.py all", timeout=1200), "adversarial_edit.py all")
        require_success(uv_run("dialogue_audit.py --all", timeout=300), "dialogue_audit.py --all")
        require_success(uv_run("narration_audit.py --all", timeout=300), "narration_audit.py --all")
        require_success(uv_run("assemble_evidence_pack.py --novel", timeout=120), "assemble_evidence_pack.py --novel")

        evidence_path = evidence_pack_path()
        require_success(uv_run(f"reader_panel.py --evidence {shlex.quote(str(evidence_path))}", timeout=900), "reader_panel.py --evidence")
        require_success(uv_run(f"humanity_panel.py --evidence {shlex.quote(str(evidence_path))}", timeout=900), "humanity_panel.py --evidence")

        evidence_dirty = False
        auto_chapter = full_eval_weakest_chapter()
        risk_set = set(risk_chapters(BASE_DIR))
        revised_chapters = 0
        for chapter_num in revision_target_chapters():
            brief_path = generate_patch_brief(chapter_num, use_auto=chapter_num == auto_chapter)
            if brief_path is None:
                continue
            evidence_dirty = apply_patch_revision(chapter_num, brief_path, risk_set) or evidence_dirty
            revised_chapters += 1

        if revised_chapters == 0:
            step("No patch-friendly brief available this cycle; skipping targeted patch application")

        if evidence_dirty:
            step("Refreshing evidence pack after patch edits...")
            require_success(uv_run("assemble_evidence_pack.py --novel", timeout=120), "refresh evidence pack after patch")

        novel_score, _full_eval = evaluate_full(evidence_path)
        build_manifest_and_gate("revision")

        total_words = count_words_in_chapters()
        commit_hash = git_add_commit(f"revision cycle {cycle} complete: novel_score {novel_score}")
        log_result(commit_hash, f"revision-cycle-{cycle}", novel_score, total_words, "cycle", f"Cycle {cycle}: novel score {prev_score}->{novel_score}")

        state["novel_score"] = novel_score
        state["revision_cycle"] = cycle
        save_state(state)

        if cycle >= MIN_REVISION_CYCLES and abs(novel_score - prev_score) < PLATEAU_DELTA:
            step(f"Plateau detected (delta {abs(novel_score - prev_score):.2f} < {PLATEAU_DELTA}) after {cycle} cycles — stopping")
            break
        prev_score = novel_score

    state["phase"] = "review"
    state["current_focus"] = "full_manuscript_review"
    save_state(state)

    banner(f"REVISION COMPLETE — {state.get('revision_cycle', 0)} cycles, novel_score {state.get('novel_score', 0)}")
    return state


# ---------------------------------------------------------------------------
# PHASE 4 — REVIEW
# ---------------------------------------------------------------------------

def run_review(state: dict) -> dict:
    banner("PHASE 4: REVIEW", "=")

    require_success(uv_run("review.py --output reviews.md", timeout=1200), "review.py --output reviews.md")
    require_success(uv_run("review.py --parse", timeout=120), "review.py --parse")
    build_manifest_and_gate("review")

    commit_hash = git_add_commit("review: full-manuscript opus pass")
    log_result(commit_hash, "review", state.get("novel_score", "?"), count_words_in_chapters(), "review", "Full-manuscript review complete")

    state["phase"] = "export"
    state["current_focus"] = "export"
    save_state(state)

    banner("REVIEW COMPLETE")
    return state


# ---------------------------------------------------------------------------
# PHASE 5 — EXPORT
# ---------------------------------------------------------------------------

def run_export(state: dict) -> dict:
    banner("PHASE 5: EXPORT", "=")

    if (BASE_DIR / "build_outline.py").exists():
        require_success(uv_run("build_outline.py", timeout=600), "build_outline.py")
    if (BASE_DIR / "build_arc_summary.py").exists():
        require_success(uv_run("build_arc_summary.py", timeout=600), "build_arc_summary.py")

    manuscript = build_manuscript()
    if manuscript.exists():
        step(f"Built manuscript.md ({len(manuscript.read_text(encoding='utf-8').split())} words)")

    build_tex = BASE_DIR / "typeset" / "build_tex.py"
    if build_tex.exists():
        step("Building LaTeX content...")
        run_tool("uv run python typeset/build_tex.py", timeout=180)
        novel_tex = BASE_DIR / "typeset" / "novel.tex"
        if novel_tex.exists():
            tectonic = run_tool("which tectonic", timeout=10)
            if tectonic.returncode == 0:
                run_tool("tectonic typeset/novel.tex", timeout=300)

    build_manifest_and_gate("export")

    commit_hash = git_add_commit("export: manuscript, outline, arc summary, PDF")
    log_result(commit_hash, "export", state.get("novel_score", "?"), count_words_in_chapters(), "export", "Final export")

    state["phase"] = "complete"
    state["current_focus"] = "done"
    save_state(state)

    banner(f"EXPORT COMPLETE — {count_chapter_files()} chapters, {count_words_in_chapters()} words")
    return state


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_pipeline(args: argparse.Namespace) -> None:
    migrated = migrate_planning_artifacts(BASE_DIR)
    if migrated:
        step(f"Migrated {len(migrated)} legacy planning artifact(s) into planning/")

    if args.from_scratch:
        banner("STARTING FROM SCRATCH")
        try:
            seed_file = require_seed_path(BASE_DIR)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)
        removed = clear_from_scratch_artifacts()
        step(f"Cleared {len(removed)} generated artifact(s) before restarting from {seed_file.name}")
        state = default_state()
        save_state(state)
    else:
        state = load_state()

    if args.from_scratch and args.approve_bootstrap:
        raise SystemExit(
            "--approve-bootstrap only applies after bootstrap has paused for review. "
            "Run --from-scratch first, inspect the bootstrap artifacts, then rerun with --approve-bootstrap."
        )

    ensure_planning_dir(BASE_DIR)
    CHAPTERS_DIR.mkdir(exist_ok=True)
    BRIEFS_DIR.mkdir(exist_ok=True)
    EDIT_LOGS_DIR.mkdir(exist_ok=True)
    EVAL_LOGS_DIR.mkdir(exist_ok=True)
    SCENE_OPTIONS_DIR.mkdir(exist_ok=True)
    STORY_STATE_DIR.mkdir(parents=True, exist_ok=True)
    VARIANTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.approve_bootstrap:
        if not state.get("bootstrap_complete"):
            raise SystemExit(
                "Bootstrap artifacts are not ready yet. Run the pipeline once without --approve-bootstrap first."
            )
        if not state.get("bootstrap_approved"):
            state["bootstrap_approved"] = True
            state["current_focus"] = "structural_planning"
            save_state(state)
            step("Bootstrap approval recorded. Continuing into structural planning.")

    if args.phase and args.phase != "foundation" and bootstrap_approval_pending(state):
        raise SystemExit(
            "Bootstrap review is still pending. Re-run with --phase foundation --approve-bootstrap "
            "or simply --approve-bootstrap to continue."
        )

    max_cycles = args.max_cycles if args.max_cycles else MAX_REVISION_CYCLES

    if args.phase:
        phases = [args.phase]
    else:
        current = state.get("phase", "foundation")
        if current == "complete":
            print("Pipeline already complete. Use --from-scratch to restart or --phase to run a specific phase.")
            return
        try:
            start_index = PHASE_ORDER.index(current)
        except ValueError:
            start_index = 0
        phases = PHASE_ORDER[start_index:]

    banner(f"AUTONOVEL PIPELINE — phases: {', '.join(phases)}")
    print(
        f"  State: phase={state.get('phase')}, "
        f"foundation_score={state.get('foundation_score', 0)}, "
        f"chapters={state.get('chapters_drafted', 0)}/{state.get('chapters_total', '?')}, "
        f"novel_score={state.get('novel_score', 0)}"
    )

    start_time = datetime.now()

    for phase in phases:
        try:
            if phase == "foundation":
                state = run_foundation(state, max_iters=args.max_foundation_iters)
                if bootstrap_approval_pending(state):
                    break
            elif phase == "drafting":
                state = run_drafting(state)
            elif phase == "revision":
                state = run_revision(state, max_cycles=max_cycles)
            elif phase == "review":
                state = run_review(state)
            elif phase == "export":
                state = run_export(state)
            else:
                raise RuntimeError(f"Unknown phase: {phase}")
        except KeyboardInterrupt:
            banner("INTERRUPTED — state saved")
            save_state(state)
            sys.exit(130)
        except Exception as exc:
            print(f"\n  FATAL ERROR in {phase}: {exc}")
            save_state(state)
            raise

    elapsed = datetime.now() - start_time
    hours = elapsed.total_seconds() / 3600

    if bootstrap_approval_pending(state):
        banner("PIPELINE PAUSED")
        print(f"  Time:       {hours:.1f} hours")
        print(f"  Phase:      {state.get('phase')}")
        print(f"  Focus:      {state.get('current_focus')}")
        print(f"  Bootstrap:  complete, awaiting approval")
        print(f"  Next step:  uv run python run_pipeline.py --approve-bootstrap")
        return

    banner("PIPELINE COMPLETE")
    print(f"  Time:       {hours:.1f} hours")
    print(f"  Phase:      {state.get('phase')}")
    print(f"  Foundation: {state.get('foundation_score', 0)}")
    print(f"  Chapters:   {state.get('chapters_drafted', 0)}/{state.get('chapters_total', '?')}")
    print(f"  Words:      {count_words_in_chapters()}")
    print(f"  Novel:      {state.get('novel_score', 0)}")
    print(f"  Cycles:     {state.get('revision_cycle', 0)}")
    print(f"  Commit:     {git_short_hash()}")


def positive_int_arg(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Autonovel pipeline orchestrator — foundation to export",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python run_pipeline.py                     # resume from current state
  python run_pipeline.py --from-scratch      # start fresh from planning/seed.md
  python run_pipeline.py --approve-bootstrap # continue after bootstrap review
  python run_pipeline.py --phase foundation  # run only foundation
  python run_pipeline.py --phase drafting    # run only drafting
  python run_pipeline.py --phase revision    # run only revision
  python run_pipeline.py --phase review      # run only review
  python run_pipeline.py --phase export      # run only export
""",
    )
    parser.add_argument("--from-scratch", action="store_true", help="Reset state and start from planning/seed.md")
    parser.add_argument(
        "--approve-bootstrap",
        action="store_true",
        help="Approve the generated bootstrap artifacts and continue into structural planning",
    )
    parser.add_argument("--phase", choices=PHASE_ORDER, help="Run only a specific phase")
    parser.add_argument(
        "--max-foundation-iters",
        type=positive_int_arg,
        default=MAX_FOUNDATION_ITERS,
        help=f"Maximum foundation iterations (default: {MAX_FOUNDATION_ITERS})",
    )
    parser.add_argument("--max-cycles", type=int, default=None, help=f"Maximum revision cycles (default: {MAX_REVISION_CYCLES})")
    args = parser.parse_args()
    run_pipeline(args)


if __name__ == "__main__":
    main()
