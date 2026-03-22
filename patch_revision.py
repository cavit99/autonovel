#!/usr/bin/env python3
"""Generate a patch plan for revising a chapter from a revision brief."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Callable

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for bare Python test runners
    def load_dotenv(*_args, **_kwargs):
        return False

from revision_patching import (
    BASE_DIR,
    DeterministicPatchPlanError,
    build_pending_patch_plan,
    build_deterministic_patch_plan,
    chapter_path,
    normalize_patch_payload,
    write_patch_file,
)
from anthropic_api import enable_automatic_prompt_cache, message_text_from_response
from roughness_guard import build_guard_report

load_dotenv(BASE_DIR / ".env")

WRITER_MODEL = os.environ.get("AUTONOVEL_WRITER_MODEL", "claude-sonnet-4-6")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")


def build_patch_prompt(chapter_num: int, brief_text: str, source_text: str, guard_report: dict) -> str:
    locked = guard_report.get("locked_spans", [])
    locked_lines = "\n".join(
        f"- [{span['start']}:{span['end']}] {span['reason']}: {span['excerpt']}"
        for span in locked
    ) or "- (no locked spans)"

    return f"""Propose a patch plan for revising Chapter {chapter_num}.

Return JSON only with this shape:
{{
  "notes": ["..."],
  "edits": [
    {{"id": "edit-1", "type": "cut", "quote": "exact text", "reason": "..."}},
    {{"id": "edit-2", "type": "replace", "quote": "exact text", "text": "replacement text", "reason": "..."}},
    {{"id": "edit-3", "type": "insert", "anchor_quote": "exact anchor", "placement": "after", "text": "inserted text", "reason": "..."}},
    {{"id": "edit-4", "type": "move", "quote": "exact text", "anchor_quote": "exact anchor", "placement": "before", "reason": "..."}}
  ]
}}

Rules:
- Prefer 1-5 targeted edits over a full rewrite.
- Preserve untouched text byte-for-byte.
- Do not touch any locked span unless the brief explicitly targets it.
- Do not smooth the chapter into generic clarity.
- Use exact quotes from the source text when possible.

LOCKED SPANS:
{locked_lines}

REVISION BRIEF:
{brief_text}

SOURCE CHAPTER:
{source_text}
"""


def extract_json_object(text: str) -> dict:
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    candidate = fence_match.group(1) if fence_match else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end < start:
        raise ValueError("No JSON object found in planner response")
    return json.loads(candidate[start : end + 1])


def call_patch_planner(prompt: str, max_tokens: int = 4000) -> str:
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
        "temperature": 0.2,
        "system": (
            "You are preparing revision patches for a fantasy novel chapter. "
            "Return JSON only. Prefer a small set of precise edits. "
            "Protect productive roughness, awkwardness, and idiosyncratic syntax."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    enable_automatic_prompt_cache(payload)
    resp = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=600)
    return message_text_from_response(resp, context="patch_revision planner request")


def generate_patch_plan(
    chapter_num: int,
    brief_text: str,
    source_text: str,
    guard_report: dict | None = None,
    planner_mode: str = "auto",
    planner_call: Callable[[str], str] | None = None,
) -> dict:
    guard_report = guard_report or build_guard_report(source_text, 4)
    locked_spans = guard_report.get("locked_spans", [])

    if not source_text:
        return build_pending_patch_plan(chapter_num, brief_text, locked_spans)

    if planner_mode not in {"auto", "deterministic", "model"}:
        raise ValueError(f"Unsupported planner mode: {planner_mode}")

    if planner_mode == "deterministic":
        return build_deterministic_patch_plan(chapter_num, brief_text, source_text, locked_spans)

    if planner_mode == "auto" and not API_KEY:
        try:
            return build_deterministic_patch_plan(chapter_num, brief_text, source_text, locked_spans)
        except DeterministicPatchPlanError as exc:
            raise DeterministicPatchPlanError(
                "No patch planner API key is configured, and the local deterministic fallback "
                f"could not build a usable patch plan: {exc}"
            ) from exc

    prompt = build_patch_prompt(chapter_num, brief_text, source_text, guard_report)
    raw = (planner_call or call_patch_planner)(prompt)
    try:
        payload = extract_json_object(raw)
    except (json.JSONDecodeError, ValueError):
        if planner_mode == "model":
            raise
        try:
            return build_deterministic_patch_plan(chapter_num, brief_text, source_text, locked_spans)
        except DeterministicPatchPlanError as exc:
            raise DeterministicPatchPlanError(
                "The model patch plan could not be parsed, and the local deterministic fallback "
                f"could not build a usable patch plan: {exc}"
            ) from exc

    normalized = normalize_patch_payload(payload, source_text, chapter_num, locked_spans=locked_spans)
    if not normalized["edits"] and planner_mode == "auto":
        try:
            return build_deterministic_patch_plan(chapter_num, brief_text, source_text, locked_spans)
        except DeterministicPatchPlanError as exc:
            raise DeterministicPatchPlanError(
                "The model returned no actionable patch edits, and the local deterministic fallback "
                f"could not build a usable patch plan: {exc}"
            ) from exc
    return normalized


def default_patch_path(chapter_num: int) -> Path:
    return BASE_DIR / "edit_logs" / f"ch{chapter_num:02d}_patch.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a span-level patch plan from a revision brief.",
    )
    parser.add_argument("chapter", type=int, help="Chapter number to revise.")
    parser.add_argument("brief_file", help="Path to the revision brief markdown file.")
    parser.add_argument(
        "--planner-mode",
        choices=["auto", "deterministic", "model"],
        default="auto",
        help="How to generate the patch plan.",
    )
    parser.add_argument("--output", help="Optional output path for the patch JSON.")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Write the patch JSON but do not apply it to the chapter file.",
    )
    args = parser.parse_args()

    brief_path = Path(args.brief_file)
    brief_text = brief_path.read_text(encoding="utf-8")
    source_path = chapter_path(args.chapter)
    source_text = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
    guard_report = build_guard_report(source_text, 4) if source_text else {"locked_spans": []}
    try:
        patch = generate_patch_plan(
            args.chapter,
            brief_text,
            source_text,
            guard_report=guard_report,
            planner_mode=args.planner_mode,
        )
    except DeterministicPatchPlanError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    patch["chapter_path"] = str(source_path)
    patch["brief_path"] = str(brief_path)
    patch["roughness_guard"] = guard_report

    output_path = Path(args.output) if args.output else default_patch_path(args.chapter)
    write_patch_file(output_path, patch)
    print(output_path)

    if args.plan_only:
        return

    if not source_path.exists():
        print(f"Chapter source missing at {source_path}; patch plan saved but not applied.")
        return

    from revision_patching import apply_patch_edits, compute_sha256

    revised_text, applied = apply_patch_edits(source_text, patch["edits"], patch.get("locked_spans", []))
    source_path.write_text(revised_text, encoding="utf-8")
    patch["applied_edit_count"] = len(applied)
    patch["post_apply_sha256"] = compute_sha256(revised_text)
    write_patch_file(output_path, patch)
    print(f"Applied {len(applied)} edits to {source_path}")


if __name__ == "__main__":
    main()
