#!/usr/bin/env python3
"""Generate arc_outline.md for the PR2 planning split."""

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

from planning_split import (
    derive_arc_from_outline,
    extract_json_object,
    normalize_arc_payload,
    parse_arc_outline,
    read_text_if_exists,
    render_arc_outline,
)

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

WRITER_MODEL = os.environ.get("AUTONOVEL_WRITER_MODEL", "claude-sonnet-4-6")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")
DEFAULT_OUTPUT = BASE_DIR / "arc_outline.md"

SYSTEM_PROMPT = (
    "You are a novel architect converting planning materials into a lean arc outline. "
    "You focus on irreversible turns, reveals, and pressure escalation. Return valid JSON only."
)


def call_writer(prompt: str, max_tokens: int = 3000) -> str:
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
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def read_required(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"required file not found: {path}") from exc


def build_prompt(seed: str, world: str, characters: str, perspective: str, mystery: str, voice: str) -> str:
    return f"""Create ARC_OUTLINE.JSON for this novel.

SEED:
{seed}

WORLD:
{world[:4000]}

CHARACTERS:
{characters[:4000]}

PERSPECTIVE:
{perspective[:2500]}

VOICE:
{voice[:2500]}

CENTRAL MYSTERY:
{mystery[:2500]}

Return valid JSON with:
- title
- acts: list of 3-4 objects with name and irreversible_turns
- major_reveals: list of strings
- pressure_escalations: list of strings
- candidate_risk_chapters: list of chapter numbers

Rules:
- keep the arc lean; this is not the full chapter outline
- only capture irreversible turns, major reveals, pressure escalations, and candidate risk chapters
- candidate_risk_chapters should be 0-3 chapter numbers
- JSON only
"""


def derive_arc() -> dict[str, object]:
    legacy_outline = read_text_if_exists(BASE_DIR / "outline.md")
    return derive_arc_from_outline(legacy_outline)


def generate_arc(*, output_path: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    try:
        if not API_KEY:
            raise RuntimeError("missing API key")
        seed = read_required(BASE_DIR / "seed.txt")
        world = read_required(BASE_DIR / "world.md")
        characters = read_required(BASE_DIR / "characters.md")
        perspective = read_required(BASE_DIR / "perspective.md")
        mystery = read_required(BASE_DIR / "MYSTERY.md")
        voice = read_required(BASE_DIR / "voice.md")
        raw = call_writer(build_prompt(seed, world, characters, perspective, mystery, voice))
        arc = normalize_arc_payload(extract_json_object(raw))
    except Exception as exc:
        print(f"WARNING: gen_arc.py falling back to derived arc outline: {exc}", file=sys.stderr)
        arc = derive_arc()

    output_path.write_text(render_arc_outline(arc) + "\n")
    return arc


def load_arc(path: Path) -> dict[str, object]:
    if path.exists():
        return parse_arc_outline(path.read_text())
    return derive_arc()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the PR2 arc outline artifact")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write arc_outline.md")
    args = parser.parse_args()

    arc = generate_arc(output_path=args.output)
    print(f"Saved arc outline to {args.output}", file=sys.stderr)
    print(render_arc_outline(arc))


if __name__ == "__main__":
    main()
