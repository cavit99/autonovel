#!/usr/bin/env python3
"""Compatibility wrapper that renders legacy outline.md from PR2 artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gen_arc import generate_arc
from gen_chapter_cards import generate_chapter_cards
from gen_thread_registry import generate_thread_registry
from planning_split import render_legacy_outline

BASE_DIR = Path(__file__).parent
DEFAULT_OUTPUT = BASE_DIR / "outline.md"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper for the legacy outline.md pipeline"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write outline.md")
    parser.add_argument("--arc-output", type=Path, default=BASE_DIR / "arc_outline.md", help="Arc output path")
    parser.add_argument(
        "--cards-output",
        type=Path,
        default=BASE_DIR / "chapter_cards.md",
        help="Chapter cards output path",
    )
    parser.add_argument(
        "--threads-output",
        type=Path,
        default=BASE_DIR / "thread_registry.json",
        help="Thread registry output path",
    )
    args = parser.parse_args()

    print("Running gen_arc.py compatibility step...", file=sys.stderr)
    arc = generate_arc(output_path=args.arc_output)
    print("Running gen_chapter_cards.py compatibility step...", file=sys.stderr)
    cards = generate_chapter_cards(output_path=args.cards_output)
    print("Running gen_thread_registry.py compatibility step...", file=sys.stderr)
    threads = generate_thread_registry(output_path=args.threads_output)

    title = arc.get("title", "Outline")
    outline = render_legacy_outline(title, arc, cards, threads)
    args.output.write_text(outline + "\n")
    print(f"Saved legacy outline to {args.output}", file=sys.stderr)
    print(outline)


if __name__ == "__main__":
    main()
