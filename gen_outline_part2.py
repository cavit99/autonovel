#!/usr/bin/env python3
"""Compatibility wrapper for the legacy foreshadowing-ledger workflow."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gen_arc import load_arc
from gen_chapter_cards import load_chapter_cards
from gen_thread_registry import generate_thread_registry
from planning_split import render_legacy_outline

BASE_DIR = Path(__file__).parent
DEFAULT_OUTPUT = BASE_DIR / "outline.md"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper for the legacy gen_outline_part2.py flow"
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

    print("Refreshing thread_registry.json for legacy foreshadowing output...", file=sys.stderr)
    threads = generate_thread_registry(output_path=args.threads_output)
    arc = load_arc(args.arc_output)
    cards = load_chapter_cards(args.cards_output)
    outline = render_legacy_outline(arc.get("title", "Outline"), arc, cards, threads)
    args.output.write_text(outline + "\n")
    print(f"Saved legacy outline with foreshadowing ledger to {args.output}", file=sys.stderr)
    print(outline)


if __name__ == "__main__":
    main()
