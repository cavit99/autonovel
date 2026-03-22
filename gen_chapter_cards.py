#!/usr/bin/env python3
"""Generate chapter_cards.md for the PR2 planning split."""

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
from planning_split import (
    derive_chapter_cards_from_outline,
    extract_json_object,
    normalize_chapter_cards,
    parse_chapter_cards,
    read_text_if_exists,
    render_chapter_cards,
)
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
DEFAULT_OUTPUT = planning_artifact_path("chapter_cards", BASE_DIR)

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
    return message_text_from_response(resp, context="gen_chapter_cards writer request")


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
- focus_character
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
- focus_character should name the locked POV character when the chapter has one
- scene_density must be one of: high, medium, low
- scene_type must be one of: investigation, confrontation, revelation, quiet, crisis, preparation, aftermath, digression
- scene_method must be one of: close_interiority, observed_action, dialogue_driven, environmental, epistolary, panoramic, fragmented
- risk must be one of: none, formal, pov, document, temporal
- JSON only
"""


def derive_cards() -> list[dict[str, object]]:
    legacy_outline = read_text_if_exists(readable_planning_artifact_path("outline", BASE_DIR))
    return derive_chapter_cards_from_outline(legacy_outline)


def import_cards_from_outline(*, output_path: Path = DEFAULT_OUTPUT) -> list[dict[str, object]]:
    legacy_outline = read_text_if_exists(readable_planning_artifact_path("outline", BASE_DIR))
    if not legacy_outline.strip():
        raise RuntimeError("planning/outline.md is missing or empty; cannot import chapter cards")
    cards = derive_cards()
    ensure_parent_dir(output_path)
    output_path.write_text(render_chapter_cards(cards) + "\n")
    return cards


def generate_chapter_cards(
    *, output_path: Path = DEFAULT_OUTPUT, import_from_outline: bool = False
) -> list[dict[str, object]]:
    if import_from_outline:
        return import_cards_from_outline(output_path=output_path)

    if not API_KEY:
        raise RuntimeError("missing API key")
    seed = require_seed_path(BASE_DIR).read_text(encoding="utf-8")
    world = read_required(readable_planning_artifact_path("world", BASE_DIR))
    characters = read_required(readable_planning_artifact_path("characters", BASE_DIR))
    perspective = read_required(readable_planning_artifact_path("perspective", BASE_DIR))
    voice = read_required(readable_planning_artifact_path("voice", BASE_DIR))
    arc = read_required(readable_planning_artifact_path("arc_outline", BASE_DIR))
    raw = call_writer(build_prompt(seed, world, characters, perspective, voice, arc))
    cards = normalize_chapter_cards(extract_json_object(raw))

    ensure_parent_dir(output_path)
    output_path.write_text(render_chapter_cards(cards) + "\n")
    return cards


def load_chapter_cards(path: Path) -> list[dict[str, object]]:
    if path.exists():
        return parse_chapter_cards(path.read_text())
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the PR2 chapter cards artifact")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write chapter_cards.md")
    parser.add_argument(
        "--import-from-outline",
        action="store_true",
        help="Explicitly derive chapter_cards.md from the legacy planning/outline.md compatibility artifact",
    )
    args = parser.parse_args()

    cards = generate_chapter_cards(output_path=args.output, import_from_outline=args.import_from_outline)
    print(f"Saved chapter cards to {args.output}", file=sys.stderr)
    print(render_chapter_cards(cards))


if __name__ == "__main__":
    main()
