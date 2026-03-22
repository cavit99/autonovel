#!/usr/bin/env python3
"""Generate perspective.md for the novel's governing consciousness."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for bare Python test runners
    def load_dotenv(*_args, **_kwargs):
        return False

from anthropic_api import message_text_from_response
from foundation_mind import extract_json_object, render_perspective_markdown
from project_paths import (
    ensure_parent_dir,
    planning_artifact_path,
    readable_planning_artifact_path,
    require_seed_path,
)

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

WRITER_MODEL = os.environ.get("AUTONOVEL_WRITER_MODEL", "claude-sonnet-4-6")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")
DEFAULT_OUTPUT = planning_artifact_path("perspective", BASE_DIR)

SYSTEM_PROMPT = (
    "You design the governing perspective for novels. You think in terms of "
    "obsessions, blind spots, humor, aversion, and content-to-form rules. "
    "You return precise, concrete JSON only."
)


def call_writer(prompt: str, max_tokens: int = 4000) -> str:
    import httpx

    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": WRITER_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.4,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=300)
    return message_text_from_response(resp, context="gen_perspective writer request")


def read_required(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError as exc:
        raise SystemExit(f"ERROR: required file not found: {path}") from exc


def build_prompt(seed: str, world: str, characters: str) -> str:
    return f"""Create the governing consciousness for this novel.

SEED CONCEPT:
{seed}

WORLD BIBLE:
{world}

CHARACTER REGISTRY:
{characters}

Return valid JSON with these keys:
- obsessions: list of 2-3 things this narrator notices disproportionately
- blind_spots: list of 1-2 categories this narrator misses or misreads
- sense_of_humor: list of 2-3 things this narrator finds funny or darkly absurd
- the_unbearable: list of 2-3 things that make the prose tighten, flatten, or look away
- self_awareness: one concise paragraph about how aware the narrator is of their own telling
- formal_signatures: list of 3-5 content-to-form rules

Rules:
- make the obsessions perceptual, not thematic
- blind spots should create real omissions, not decorative flaws
- humor should be specific to this narrator, not generic wit
- formal signatures should read like content -> prose behavior rules
- concrete, compact values only
- JSON only, no markdown
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the governing perspective for the novel")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write perspective markdown")
    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    seed = require_seed_path(BASE_DIR).read_text(encoding="utf-8")
    world = read_required(readable_planning_artifact_path("world", BASE_DIR))
    characters = read_required(readable_planning_artifact_path("characters", BASE_DIR))

    print("Calling writer model...", file=sys.stderr)
    raw = call_writer(build_prompt(seed, world, characters))
    data = extract_json_object(raw)
    markdown = render_perspective_markdown(data)
    ensure_parent_dir(args.output)
    args.output.write_text(markdown + "\n")
    print(f"Saved perspective to {args.output}", file=sys.stderr)
    print(markdown)


if __name__ == "__main__":
    main()
