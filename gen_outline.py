#!/usr/bin/env python3
"""Compatibility wrapper that renders legacy outline.md from PR2 artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from planning_split import (
    normalize_thread_registry,
    parse_arc_outline,
    parse_chapter_cards,
    render_legacy_outline,
)

BASE_DIR = Path(__file__).parent
DEFAULT_OUTPUT = BASE_DIR / "outline.md"


def generate_arc(*, output_path: Path) -> dict[str, object]:
    from gen_arc import generate_arc as _generate_arc

    return _generate_arc(output_path=output_path)


def generate_chapter_cards(*, output_path: Path) -> list[dict[str, object]]:
    from gen_chapter_cards import generate_chapter_cards as _generate_chapter_cards

    return _generate_chapter_cards(output_path=output_path)


def generate_thread_registry(*, output_path: Path) -> list[dict[str, object]]:
    from gen_thread_registry import generate_thread_registry as _generate_thread_registry

    return _generate_thread_registry(output_path=output_path)


def build_parser() -> argparse.ArgumentParser:
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
    parser.add_argument(
        "--refresh-new-planning",
        action="store_true",
        help="Regenerate arc_outline.md, chapter_cards.md, and thread_registry.json before rendering outline.md",
    )
    return parser


def load_existing_planning_artifacts(
    arc_path: Path, cards_path: Path, threads_path: Path
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    missing = [path for path in (arc_path, cards_path, threads_path) if not path.exists()]
    if missing:
        missing_lines = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(
            "Missing required planning artifact(s):\n"
            f"{missing_lines}\n"
            "gen_outline.py is read-only by default. Generate arc_outline.md, chapter_cards.md, "
            "and thread_registry.json first, or rerun with --refresh-new-planning."
        )

    arc = parse_arc_outline(arc_path.read_text())
    cards = parse_chapter_cards(cards_path.read_text())
    try:
        threads = normalize_thread_registry(json.loads(threads_path.read_text()))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse existing thread registry JSON at {threads_path}: {exc}") from exc
    return arc, cards, threads


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.refresh_new_planning:
            print("Running gen_arc.py compatibility step...", file=sys.stderr)
            arc = generate_arc(output_path=args.arc_output)
            print("Running gen_chapter_cards.py compatibility step...", file=sys.stderr)
            cards = generate_chapter_cards(output_path=args.cards_output)
            print("Running gen_thread_registry.py compatibility step...", file=sys.stderr)
            threads = generate_thread_registry(output_path=args.threads_output)
        else:
            arc, cards, threads = load_existing_planning_artifacts(
                args.arc_output, args.cards_output, args.threads_output
            )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    title = arc.get("title", "Outline")
    outline = render_legacy_outline(title, arc, cards, threads)
    args.output.write_text(outline + "\n")
    print(f"Saved legacy outline to {args.output}", file=sys.stderr)
    print(outline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
