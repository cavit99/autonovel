#!/usr/bin/env python3
"""Identify locally strong or productively rough passages to preserve in revision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from revision_patching import BASE_DIR, identify_roughness_spans


def load_source_text(args: argparse.Namespace) -> tuple[str, str]:
    if args.text_file:
        path = Path(args.text_file)
        return path.read_text(encoding="utf-8"), str(path)

    if args.chapter is None:
        raise SystemExit("Provide a chapter number or --text-file.")

    path = BASE_DIR / "chapters" / f"ch_{args.chapter:02d}.md"
    if not path.exists():
        raise SystemExit(f"Chapter file not found: {path}")
    return path.read_text(encoding="utf-8"), str(path)


def build_guard_report(text: str, count: int) -> dict:
    locks = identify_roughness_spans(text, limit=count)
    return {
        "lock_count": len(locks),
        "locked_spans": locks,
        "policy": [
            "Preserve the locked spans byte-for-byte unless the brief directly targets them.",
            "Do not normalize speaker-specific awkwardness into generic clarity.",
            "Prefer local repairs over global smoothing.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Identify passages that should be protected from smoothing revisions.",
    )
    parser.add_argument("chapter", type=int, nargs="?", help="Chapter number to inspect.")
    parser.add_argument("--text-file", help="Analyze an explicit text file instead of chapters/ch_XX.md.")
    parser.add_argument(
        "--count",
        type=int,
        default=4,
        help="How many passages to lock. Clamped to the 3-5 range.",
    )
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    text, source_path = load_source_text(args)
    count = max(3, min(args.count, 5))
    report = build_guard_report(text, count)
    report["source_path"] = source_path

    if args.output:
        output_path = Path(args.output)
    elif args.chapter is not None and not args.text_file:
        output_path = BASE_DIR / "edit_logs" / f"ch{args.chapter:02d}_roughness.json"
    else:
        output_path = None

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print(output_path)
    else:
        print(json.dumps(report, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
