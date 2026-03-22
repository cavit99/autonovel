#!/usr/bin/env python3
"""Choose the strongest chapter variant and apply it to the canonical chapter path."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from anthropic_api import enable_automatic_prompt_cache, message_text_from_response
from variant_tools import (
    BASE_DIR,
    comparison_log_path,
    load_variant_candidates,
    parse_json_blob,
    pick_best_variant_deterministically,
    variant_compare_model,
)

load_dotenv(BASE_DIR / ".env")

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")
JUDGE_MODEL = variant_compare_model()


def build_compare_prompt(chapter_num: int, candidates: list[dict[str, Any]]) -> str:
    sections = []
    for candidate in candidates:
        excerpt = candidate["text"]
        words = excerpt.split()
        if len(words) > 2200:
            excerpt = " ".join(words[:2200]) + "\n[truncated]"
        sections.append(
            f"## {candidate['id']}\n"
            f"Path: {candidate['path']}\n\n"
            f"{excerpt}"
        )
    joined = "\n\n---\n\n".join(sections)
    return f"""Compare these candidate drafts for Chapter {chapter_num} of the same novel.

Pick a primary winner. You may optionally nominate a splice plan, but you must still name a winner.

Judge on:
- sharper prose
- stronger scene method
- truer character pressure
- less over-explaining
- more distinct perspective

Return valid JSON only:
{{
  "decision": "select" or "splice",
  "winner": "candidate id",
  "reason": "why this draft wins",
  "splice_plan": ["optional bullet", "optional bullet"],
  "notes": ["2-4 concise observations"]
}}

CANDIDATES:
{joined}
"""


def call_judge(prompt: str) -> dict[str, Any]:
    import httpx

    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": JUDGE_MODEL,
        "max_tokens": 2500,
        "temperature": 0.2,
        "system": (
            "You are comparing alternate drafts of the same fantasy chapter. "
            "Pick the strongest primary winner. Tie-break in favor of liveliness over polish. "
            "Return JSON only."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    enable_automatic_prompt_cache(payload)
    response = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=300)
    raw = message_text_from_response(response, context="compare_variants judge request")
    return parse_json_blob(raw)


def apply_winner(chapter_num: int, winner_path: Path, base_dir: Path) -> Path:
    target = base_dir / "chapters" / f"ch_{chapter_num:02d}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(winner_path, target)
    return target


def resolve_winner_candidate(candidates: list[dict[str, Any]], result: dict[str, Any]) -> dict[str, Any]:
    winner_id = str(result.get("winner", "")).strip()
    winner = next((candidate for candidate in candidates if candidate["id"] == winner_id), None)
    if winner is None:
        raise ValueError(f"Unknown winner id: {winner_id or '<empty>'}")
    return winner


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare chapter variants and apply the primary winner.")
    parser.add_argument("chapter", type=int, help="Chapter number whose variants should be compared")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=BASE_DIR,
        help="Project root containing chapters/variants/",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the assembled compare prompt instead of running the judge/applying a winner.",
    )
    args = parser.parse_args()

    candidates = load_variant_candidates(args.chapter, args.base_dir)
    if len(candidates) < 2:
        raise SystemExit(f"ERROR: need at least two candidates for Chapter {args.chapter}")

    if args.dry_run:
        print(build_compare_prompt(args.chapter, candidates))
        return

    if API_KEY:
        result = call_judge(build_compare_prompt(args.chapter, candidates))
        try:
            winner = resolve_winner_candidate(candidates, result)
        except ValueError:
            result = pick_best_variant_deterministically(candidates)
            winner = resolve_winner_candidate(candidates, result)
            result["notes"] = ["Model compare returned an unknown winner id; used deterministic fallback."]
    else:
        result = pick_best_variant_deterministically(candidates)
        winner = resolve_winner_candidate(candidates, result)

    applied_path = apply_winner(args.chapter, Path(winner["path"]), args.base_dir)
    payload = {
        "chapter": args.chapter,
        "generated_at": datetime.now().isoformat(),
        "model": JUDGE_MODEL if API_KEY else "deterministic",
        "decision": result.get("decision", "select"),
        "winner": winner["id"],
        "winner_path": str(winner["path"]),
        "applied_path": str(applied_path),
        "reason": result.get("reason", ""),
        "splice_plan": result.get("splice_plan", []),
        "notes": result.get("notes", []),
        "candidates": [{"id": candidate["id"], "path": str(candidate["path"])} for candidate in candidates],
    }

    log_path = comparison_log_path(args.chapter, args.base_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(log_path)


if __name__ == "__main__":
    main()
