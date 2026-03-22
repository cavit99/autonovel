#!/usr/bin/env python3
"""
Revision chapter generator. Rewrites a chapter from a specific revision brief.
Usage: python gen_revision.py <chapter_num> <brief_file>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for bare Python test runners
    def load_dotenv(*_args, **_kwargs):
        return False

from patch_revision import default_patch_path, generate_patch_plan
from revision_patching import (
    BASE_DIR,
    DeterministicPatchPlanError,
    apply_patch_edits,
    chapter_path,
    write_patch_file,
)
from roughness_guard import build_guard_report

load_dotenv(BASE_DIR / ".env")

WRITER_MODEL = os.environ.get("AUTONOVEL_WRITER_MODEL", "claude-sonnet-4-6")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")


def call_writer(prompt: str, max_tokens: int = 16000) -> str:
    import httpx

    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "context-1m-2025-08-07",
        "content-type": "application/json",
    }
    payload = {
        "model": WRITER_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.8,
        "system": (
            "You are rewriting a fantasy novel chapter based on a specific revision brief. "
            "You follow the brief exactly. You preserve the voice, world, and characters "
            "from the existing draft while making the structural changes specified. "
            "You write the FULL chapter. Do not truncate or summarize."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=600)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def load_full_revision_context(ch_num: int, brief_file: str) -> dict[str, str | Path]:
    voice = (BASE_DIR / "voice.md").read_text(encoding="utf-8")
    characters = (BASE_DIR / "characters.md").read_text(encoding="utf-8")
    world = (BASE_DIR / "world.md").read_text(encoding="utf-8")
    brief = Path(brief_file).read_text(encoding="utf-8")

    prev_path = chapter_path(ch_num - 1)
    next_path = chapter_path(ch_num + 1)
    prev_tail = prev_path.read_text(encoding="utf-8")[-2000:] if prev_path.exists() else "(first chapter)"
    next_head = next_path.read_text(encoding="utf-8")[:1500] if next_path.exists() else "(last chapter)"

    current_path = chapter_path(ch_num)
    old_text = current_path.read_text(encoding="utf-8") if current_path.exists() else "(no existing draft)"
    return {
        "voice": voice,
        "characters": characters,
        "world": world,
        "brief": brief,
        "prev_tail": prev_tail,
        "next_head": next_head,
        "old_text": old_text,
        "output_path": current_path,
    }


def build_full_revision_prompt(ch_num: int, context: dict[str, str | Path]) -> str:
    return f"""Rewrite Chapter {ch_num} of "The Second Son of the House of Bells."

REVISION BRIEF (follow this exactly):
{context["brief"]}

VOICE DEFINITION:
{context["voice"]}

CHARACTER REGISTRY:
{context["characters"]}

WORLD BIBLE:
{context["world"]}

PREVIOUS CHAPTER ENDING (maintain continuity):
{context["prev_tail"]}

NEXT CHAPTER OPENING (end so this flows into it):
{context["next_head"]}

THE EXISTING DRAFT (use as raw material -- keep what works, cut what doesn't):
{context["old_text"]}

ANTI-PATTERN RULES:
- NO triadic sensory lists (X. Y. Z.)
- NO "He did not [verb]" more than once
- NO "He thought about [X]" constructions
- NO "the way [X] did [Y]" more than twice
- NO "not X, but Y" formula in narration
- NO over-explaining after showing
- MAX 2 section breaks
- At least one moment that genuinely surprises
- 70%+ in-scene (dialogue and action, not summary)
- Dialogue should sound like speech, not prose

Write the FULL revised chapter now."""


def run_full_revision(
    ch_num: int,
    brief_file: str,
    writer_call: Callable[[str], str] | None = None,
    dry_run: bool = False,
) -> Path:
    context = load_full_revision_context(ch_num, brief_file)
    prompt = build_full_revision_prompt(ch_num, context)
    if dry_run:
        print(prompt)
        return Path(context["output_path"])

    print(f"Rewriting Chapter {ch_num}...", file=sys.stderr)
    result = (writer_call or call_writer)(prompt)
    out_path = Path(context["output_path"])
    out_path.write_text(result, encoding="utf-8")
    print(f"Saved to {out_path}", file=sys.stderr)
    print(f"Word count: {len(result.split())}", file=sys.stderr)
    return out_path


def run_patch_revision(
    ch_num: int,
    brief_file: str,
    planner_mode: str = "auto",
    planner_call: Callable[[str], str] | None = None,
    dry_run: bool = False,
) -> Path:
    brief_path = Path(brief_file)
    brief_text = brief_path.read_text(encoding="utf-8")
    source_path = chapter_path(ch_num)
    source_text = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
    guard_report = build_guard_report(source_text, 4) if source_text else {"locked_spans": [], "lock_count": 0, "policy": []}
    try:
        patch = generate_patch_plan(
            ch_num,
            brief_text,
            source_text,
            guard_report=guard_report,
            planner_mode=planner_mode,
            planner_call=planner_call,
        )
    except DeterministicPatchPlanError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    patch["chapter_path"] = str(source_path)
    patch["brief_path"] = str(brief_path)
    patch["roughness_guard"] = guard_report

    patch_path = default_patch_path(ch_num)
    if not dry_run:
        write_patch_file(patch_path, patch)
        print(f"Saved patch plan to {patch_path}", file=sys.stderr)

    if not source_path.exists():
        print(f"Chapter source missing at {source_path}; patch plan saved but not applied.", file=sys.stderr)
        return patch_path

    revised_text, applied = apply_patch_edits(source_text, patch["edits"], patch.get("locked_spans", []))
    if not dry_run:
        source_path.write_text(revised_text, encoding="utf-8")
        print(f"Patched {source_path} with {len(applied)} edits", file=sys.stderr)
    return source_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Revise a chapter from a revision brief.",
    )
    parser.add_argument("chapter_num", type=int, help="Chapter number to revise.")
    parser.add_argument("brief_file", help="Path to the revision brief markdown file.")
    parser.add_argument(
        "--mode",
        choices=["full", "patch"],
        default="full",
        help="Revision strategy. Defaults to the legacy full-chapter rewrite.",
    )
    parser.add_argument(
        "--planner-mode",
        choices=["auto", "deterministic", "model"],
        default="auto",
        help="Patch planning mode when --mode patch is selected.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build prompts/patches without writing chapter files.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.mode == "full":
        run_full_revision(args.chapter_num, args.brief_file, dry_run=args.dry_run)
        return
    run_patch_revision(
        args.chapter_num,
        args.brief_file,
        planner_mode=args.planner_mode,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
