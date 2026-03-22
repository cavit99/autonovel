#!/usr/bin/env python3
"""Fail fast when manifest metadata and on-disk artifacts disagree."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from manifest_tools import BASE_DIR, MANIFEST_PATH, collect_consistency_issues, load_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate manifest metadata against current project artifacts.")
    parser.add_argument(
        "--phase",
        choices=["foundation", "drafting", "revision", "review", "export", "complete"],
        help="Validate against a specific phase instead of the phase stored in manifest.json.",
    )
    parser.add_argument("--chapter", type=int, help="Optional current chapter context for drafting checks.")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=BASE_DIR,
        help="Project root containing manifest.json and project artifacts.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help="Manifest file to validate.",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    issues = collect_consistency_issues(args.base_dir, manifest, phase=args.phase, chapter=args.chapter)
    if issues:
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        raise SystemExit(1)

    print("consistency_gate: OK")


if __name__ == "__main__":
    main()
