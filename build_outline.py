#!/usr/bin/env python3
"""Rebuild outline.md from accepted chapters and current planning artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from export_rebuild import BASE_DIR, render_outline_text
from project_paths import ensure_parent_dir, planning_artifact_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild planning/outline.md as a compatibility/export artifact from accepted chapters, "
            "planning/arc_outline.md, planning/chapter_cards.md, planning/thread_registry.json, and manifest.json."
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
        help="Where to write the rebuilt outline (defaults to <base-dir>/planning/outline.md).",
    )
    args = parser.parse_args()

    output_path = args.output or planning_artifact_path("outline", args.base_dir)
    ensure_parent_dir(output_path)
    output_path.write_text(render_outline_text(args.base_dir) + "\n", encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
