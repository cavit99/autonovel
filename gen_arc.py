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

from anthropic_api import enable_automatic_prompt_cache, message_text_from_response
from planning_split import (
    derive_arc_from_outline,
    extract_json_object,
    normalize_arc_payload,
    parse_arc_outline,
    read_text_if_exists,
    render_arc_outline,
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
DEFAULT_OUTPUT = planning_artifact_path("arc_outline", BASE_DIR)

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
    enable_automatic_prompt_cache(payload)
    resp = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=300)
    return message_text_from_response(resp, context="gen_arc writer request")


def read_required(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"required file not found: {path}") from exc


def build_prompt(seed: str, world: str, characters: str, perspective: str, voice: str) -> str:
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
- derive the central mystery/reveal structure from the seed and approved bootstrap materials above; do not rely on any external template
- JSON only
"""


def derive_arc() -> dict[str, object]:
    legacy_outline = read_text_if_exists(readable_planning_artifact_path("outline", BASE_DIR))
    return derive_arc_from_outline(legacy_outline)


def import_arc_from_outline(*, output_path: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    legacy_outline = read_text_if_exists(readable_planning_artifact_path("outline", BASE_DIR))
    if not legacy_outline.strip():
        raise RuntimeError("planning/outline.md is missing or empty; cannot import arc outline")
    arc = derive_arc()
    ensure_parent_dir(output_path)
    output_path.write_text(render_arc_outline(arc) + "\n")
    return arc


def generate_arc(*, output_path: Path = DEFAULT_OUTPUT, import_from_outline: bool = False) -> dict[str, object]:
    if import_from_outline:
        return import_arc_from_outline(output_path=output_path)

    if not API_KEY:
        raise RuntimeError("missing API key")
    seed = require_seed_path(BASE_DIR).read_text(encoding="utf-8")
    world = read_required(readable_planning_artifact_path("world", BASE_DIR))
    characters = read_required(readable_planning_artifact_path("characters", BASE_DIR))
    perspective = read_required(readable_planning_artifact_path("perspective", BASE_DIR))
    voice = read_required(readable_planning_artifact_path("voice", BASE_DIR))
    raw = call_writer(build_prompt(seed, world, characters, perspective, voice))
    arc = normalize_arc_payload(extract_json_object(raw))

    ensure_parent_dir(output_path)
    output_path.write_text(render_arc_outline(arc) + "\n")
    return arc


def load_arc(path: Path) -> dict[str, object]:
    if path.exists():
        return parse_arc_outline(path.read_text())
    return normalize_arc_payload({})


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the PR2 arc outline artifact")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write arc_outline.md")
    parser.add_argument(
        "--import-from-outline",
        action="store_true",
        help="Explicitly derive arc_outline.md from the legacy planning/outline.md compatibility artifact",
    )
    args = parser.parse_args()

    arc = generate_arc(output_path=args.output, import_from_outline=args.import_from_outline)
    print(f"Saved arc outline to {args.output}", file=sys.stderr)
    print(render_arc_outline(arc))


if __name__ == "__main__":
    main()
