#!/usr/bin/env python3
"""
Draft a single chapter using the writer model.
Usage: python draft_chapter.py 1
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from stateful_drafting import (
    build_legacy_prompt,
    build_new_mode_prompt,
    build_system_prompt,
    resolve_mode,
)

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

WRITER_MODEL = os.environ.get("AUTONOVEL_WRITER_MODEL", "claude-sonnet-4-6")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")


def call_writer(prompt: str, system_prompt: str, max_tokens: int = 16000) -> str:
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
        "system": system_prompt,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=600)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def build_prompt_for_mode(base_dir: Path, chapter_num: int, mode: str) -> tuple[str, str]:
    if mode == "new":
        return build_system_prompt("new"), build_new_mode_prompt(base_dir, chapter_num)
    return build_system_prompt("legacy"), build_legacy_prompt(base_dir, chapter_num)


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft a single chapter")
    parser.add_argument("chapter", type=int, help="Chapter number to draft")
    parser.add_argument(
        "--mode",
        choices=("auto", "legacy", "new"),
        default="auto",
        help="Drafting mode. Auto uses new mode when the PR3 artifacts are present.",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=BASE_DIR,
        help="Base directory containing planning artifacts and chapters",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the system and user prompts instead of calling the writer model",
    )
    args = parser.parse_args()

    mode = resolve_mode(args.base_dir, args.chapter, args.mode)
    system_prompt, prompt = build_prompt_for_mode(args.base_dir, args.chapter, mode)

    if args.dry_run:
        print(f"MODE: {mode}")
        print("=== SYSTEM PROMPT ===")
        print(system_prompt)
        print("=== USER PROMPT ===")
        print(prompt)
        return

    print(f"Drafting Chapter {args.chapter} in {mode} mode...", file=sys.stderr)
    result = call_writer(prompt, system_prompt)

    chapters_dir = args.base_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    out_path = chapters_dir / f"ch_{args.chapter:02d}.md"
    out_path.write_text(result)
    print(f"Saved to {out_path}", file=sys.stderr)
    print(f"Word count: {len(result.split())}", file=sys.stderr)
    print(result)


if __name__ == "__main__":
    main()
