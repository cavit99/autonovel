#!/usr/bin/env python3
"""Compatibility wrapper for the legacy foreshadowing-ledger workflow."""

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
from project_paths import ensure_parent_dir, planning_artifact_path

BASE_DIR = Path(__file__).parent
DEFAULT_OUTPUT = planning_artifact_path("outline", BASE_DIR)


def generate_thread_registry(*, output_path: Path) -> list[dict[str, object]]:
    from gen_thread_registry import generate_thread_registry as _generate_thread_registry

    return _generate_thread_registry(output_path=output_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compatibility wrapper for the legacy gen_outline_part2.py flow"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Where to write outline.md")
    parser.add_argument("--arc-output", type=Path, default=planning_artifact_path("arc_outline", BASE_DIR), help="Arc output path")
    parser.add_argument(
        "--cards-output",
        type=Path,
        default=planning_artifact_path("chapter_cards", BASE_DIR),
        help="Chapter cards output path",
    )
    parser.add_argument(
        "--threads-output",
        type=Path,
        default=planning_artifact_path("thread_registry", BASE_DIR),
        help="Thread registry output path",
    )
    parser.add_argument(
        "--refresh-new-planning",
        action="store_true",
        help="Regenerate thread_registry.json before rendering outline.md",
    )
    return parser


def load_existing_arc_and_cards(
    arc_path: Path, cards_path: Path
) -> tuple[dict[str, object], list[dict[str, object]]]:
    missing = [path for path in (arc_path, cards_path) if not path.exists()]
    if missing:
        missing_lines = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(
            "Missing required planning artifact(s):\n"
            f"{missing_lines}\n"
            "gen_outline_part2.py is read-only by default. Generate arc_outline.md and "
            "chapter_cards.md first."
        )

    arc = parse_arc_outline(arc_path.read_text())
    cards = parse_chapter_cards(cards_path.read_text())
    return arc, cards


def load_existing_threads(threads_path: Path) -> list[dict[str, object]]:
    if not threads_path.exists():
        raise FileNotFoundError(
            "Missing required planning artifact(s):\n"
            f"- {threads_path}\n"
            "gen_outline_part2.py is read-only by default. Generate thread_registry.json first, "
            "or rerun with --refresh-new-planning once arc_outline.md and chapter_cards.md exist."
        )
    try:
        return normalize_thread_registry(json.loads(threads_path.read_text()))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse existing thread registry JSON at {threads_path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        arc, cards = load_existing_arc_and_cards(args.arc_output, args.cards_output)
        if args.refresh_new_planning:
            print("Refreshing thread_registry.json for legacy foreshadowing output...", file=sys.stderr)
            threads = generate_thread_registry(output_path=args.threads_output)
        else:
            threads = load_existing_threads(args.threads_output)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    outline = render_legacy_outline(arc.get("title", "Outline"), arc, cards, threads)
    ensure_parent_dir(args.output)
    args.output.write_text(outline + "\n")
    print(f"Saved legacy outline with foreshadowing ledger to {args.output}", file=sys.stderr)
    print(outline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
