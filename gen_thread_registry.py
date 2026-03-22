#!/usr/bin/env python3
"""Generate thread_registry.json for the PR2 planning split."""

from __future__ import annotations

import argparse
import json
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
    derive_thread_registry_from_outline,
    extract_json_object,
    normalize_thread_registry,
    read_text_if_exists,
)
from project_paths import ensure_parent_dir, planning_artifact_path, readable_planning_artifact_path

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

WRITER_MODEL = os.environ.get("AUTONOVEL_WRITER_MODEL", "claude-sonnet-4-6")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")
DEFAULT_OUTPUT = planning_artifact_path("thread_registry", BASE_DIR)

SYSTEM_PROMPT = (
    "You convert novel planning materials into a typed thread registry. "
    "Classify threads as plot, pressure, echo, or texture. Return valid JSON only."
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
        "temperature": 0.3,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }
    enable_automatic_prompt_cache(payload)
    resp = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=300)
    return message_text_from_response(resp, context="gen_thread_registry writer request")


def read_required(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"required file not found: {path}") from exc


def build_prompt(arc: str, chapter_cards: str) -> str:
    return f"""Create THREAD_REGISTRY.JSON for this novel.

ARC OUTLINE:
{arc[:4000]}

CHAPTER CARDS:
{chapter_cards[:5000]}

Return valid JSON as an array of thread objects with:
- id
- description
- type (plot | pressure | echo | texture)
- first_seen
- reinforced (array of chapter numbers)
- payoff
- required
- notes

Rules:
- not every thread should be plot
- echo and texture threads do not require a payoff
- keep descriptions short and specific
- JSON only
"""


def derive_threads() -> list[dict[str, object]]:
    legacy_outline = read_text_if_exists(readable_planning_artifact_path("outline", BASE_DIR))
    return derive_thread_registry_from_outline(legacy_outline)


def import_threads_from_outline(*, output_path: Path = DEFAULT_OUTPUT) -> list[dict[str, object]]:
    legacy_outline = read_text_if_exists(readable_planning_artifact_path("outline", BASE_DIR))
    if not legacy_outline.strip():
        raise RuntimeError("planning/outline.md is missing or empty; cannot import thread registry")
    threads = derive_threads()
    ensure_parent_dir(output_path)
    output_path.write_text(json.dumps(threads, indent=2) + "\n")
    return threads


def generate_thread_registry(
    *, output_path: Path = DEFAULT_OUTPUT, import_from_outline: bool = False
) -> list[dict[str, object]]:
    if import_from_outline:
        return import_threads_from_outline(output_path=output_path)

    if not API_KEY:
        raise RuntimeError("missing API key")
    arc = read_required(readable_planning_artifact_path("arc_outline", BASE_DIR))
    chapter_cards = read_required(readable_planning_artifact_path("chapter_cards", BASE_DIR))
    raw = call_writer(build_prompt(arc, chapter_cards))
    threads = normalize_thread_registry(extract_json_object(raw))

    ensure_parent_dir(output_path)
    output_path.write_text(json.dumps(threads, indent=2) + "\n")
    return threads


def load_thread_registry(path: Path) -> list[dict[str, object]]:
    if path.exists():
        return normalize_thread_registry(json.loads(path.read_text()))
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the PR2 thread registry artifact")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write thread_registry.json")
    parser.add_argument(
        "--import-from-outline",
        action="store_true",
        help="Explicitly derive thread_registry.json from the legacy planning/outline.md compatibility artifact",
    )
    args = parser.parse_args()

    threads = generate_thread_registry(output_path=args.output, import_from_outline=args.import_from_outline)
    print(f"Saved thread registry to {args.output}", file=sys.stderr)
    print(json.dumps(threads, indent=2))


if __name__ == "__main__":
    main()
