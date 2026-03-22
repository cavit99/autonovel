#!/usr/bin/env python3
"""Build the single-source-of-truth manifest for the current pipeline state."""

from __future__ import annotations

import argparse
from pathlib import Path

from manifest_tools import BASE_DIR, MANIFEST_PATH, build_manifest_payload, save_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build manifest.json from current project artifacts.")
    parser.add_argument(
        "--phase",
        choices=["foundation", "drafting", "revision", "review", "export", "complete"],
        help="Override the manifest phase.",
    )
    parser.add_argument("--chapter", type=int, help="Optional current chapter context for the manifest.")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=BASE_DIR,
        help="Project root containing chapters/, planning docs, and logs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=MANIFEST_PATH,
        help="Where to write the manifest JSON.",
    )
    args = parser.parse_args()

    payload = build_manifest_payload(args.base_dir, phase=args.phase, chapter=args.chapter)
    save_manifest(payload, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
