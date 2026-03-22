#!/usr/bin/env python3
"""Rebuild arc_summary.md from accepted chapters and current planning artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from export_rebuild import BASE_DIR, render_arc_summary_text


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild arc_summary.md from accepted chapters, arc_outline.md, "
            "chapter_cards.md, thread_registry.json, and manifest.json."
        )
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=BASE_DIR,
        help="Project root containing chapters/, planning docs, and manifest.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to write the rebuilt arc summary (defaults to <base-dir>/arc_summary.md).",
    )
    args = parser.parse_args()

    output_path = args.output or (args.base_dir / "arc_summary.md")
    output_path.write_text(render_arc_summary_text(args.base_dir) + "\n", encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
