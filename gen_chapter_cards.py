#!/usr/bin/env python3
"""Generate chapter_cards.md for the PR2 planning split."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from planning_split import (
    derive_chapter_cards_from_outline,
    extract_json_object,
    normalize_chapter_cards,
    parse_chapter_cards,
    read_text_if_exists,
    render_chapter_cards,
)

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

WRITER_MODEL = os.environ.get("AUTONOVEL_WRITER_MODEL", "claude-sonnet-4-6")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")
DEFAULT_OUTPUT = BASE_DIR / "chapter_cards.md"

SYSTEM_PROMPT = (
    "You convert novel planning materials into chapter cards. "
    "Each card should be concise, concrete, and structurally useful. Return valid JSON only."
)


def call_writer(prompt: str, max_tokens: int = 6000) -> str:
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


def build_prompt(seed: str, world: str, characters: str, perspective: str, voice: str, arc: str) -> str:
    return f"""Create CHAPTER_CARDS.JSON for this novel.

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

ARC OUTLINE:
{arc[:4000]}

Return valid JSON with a top-level "chapters" array. Each chapter card must include:
- number
- title
- goal
- pressure
- reversal
- aftermath
- irreversible_change
- allowed_ambiguity
- time_span
- scene_density
- scene_type
- scene_method
- risk

Rules:
- target 22-26 cards if the source materials support it
- use concise values, not essays
- scene_density must be one of: high, medium, low
- scene_type must be one of: investigation, confrontation, revelation, quiet, crisis, preparation, aftermath, digression
- scene_method must be one of: close_interiority, observed_action, dialogue_driven, environmental, epistolary, panoramic, fragmented
- risk must be one of: none, formal, pov, document, temporal
- JSON only
"""


def derive_cards() -> list[dict[str, object]]:
    legacy_outline = read_text_if_exists(BASE_DIR / "outline.md")
    return derive_chapter_cards_from_outline(legacy_outline)


def generate_chapter_cards(*, output_path: Path = DEFAULT_OUTPUT) -> list[dict[str, object]]:
    try:
        if not API_KEY:
            raise RuntimeError("missing API key")
        seed = read_required(BASE_DIR / "seed.txt")
        world = read_required(BASE_DIR / "world.md")
        characters = read_required(BASE_DIR / "characters.md")
        perspective = read_required(BASE_DIR / "perspective.md")
        voice = read_required(BASE_DIR / "voice.md")
        arc = read_required(BASE_DIR / "arc_outline.md")
        raw = call_writer(build_prompt(seed, world, characters, perspective, voice, arc))
        cards = normalize_chapter_cards(extract_json_object(raw))
    except Exception:
        cards = derive_cards()

    output_path.write_text(render_chapter_cards(cards) + "\n")
    return cards


def load_chapter_cards(path: Path) -> list[dict[str, object]]:
    if path.exists():
        return parse_chapter_cards(path.read_text())
    return derive_cards()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the PR2 chapter cards artifact")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write chapter_cards.md")
    args = parser.parse_args()

    cards = generate_chapter_cards(output_path=args.output)
    print(f"Saved chapter cards to {args.output}", file=sys.stderr)
    print(render_chapter_cards(cards))


if __name__ == "__main__":
    main()
