#!/usr/bin/env python3
"""Apply a JSON patch plan to a chapter file."""

from __future__ import annotations

import argparse
from pathlib import Path

from revision_patching import BASE_DIR, apply_patch_edits, compute_sha256, load_patch_file


def default_patch_path(chapter_num: int) -> Path:
    return BASE_DIR / "edit_logs" / f"ch{chapter_num:02d}_patch.json"


def resolve_patch_path(args: argparse.Namespace) -> Path:
    if args.patch_file:
        return Path(args.patch_file)
    if args.chapter is None:
        raise SystemExit("Provide a chapter number or --patch-file.")
    return default_patch_path(args.chapter)


def resolve_source_path(args: argparse.Namespace, payload: dict) -> Path:
    if args.source:
        return Path(args.source)
    chapter_path = payload.get("chapter_path")
    if chapter_path:
        return Path(chapter_path)
    if args.chapter is None:
        raise SystemExit("Patch payload does not declare a chapter path. Use --source.")
    return BASE_DIR / "chapters" / f"ch_{args.chapter:02d}.md"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply cut/replace/move/insert edits from a patch JSON file.",
    )
    parser.add_argument("chapter", type=int, nargs="?", help="Chapter number for the default patch path.")
    parser.add_argument("--patch-file", help="Explicit patch file path.")
    parser.add_argument("--source", help="Override the source chapter file path.")
    parser.add_argument("--output", help="Write the revised text to a different file.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview without writing files.")
    parser.add_argument("--force", action="store_true", help="Apply even if the source hash has drifted.")
    parser.add_argument("--cut-only", action="store_true", help="Apply only cut edits from the patch.")
    args = parser.parse_args()

    patch_path = resolve_patch_path(args)
    payload = load_patch_file(patch_path)
    source_path = resolve_source_path(args, payload)
    if not source_path.exists():
        raise SystemExit(f"Source chapter file not found: {source_path}")

    source_text = source_path.read_text(encoding="utf-8")
    source_sha = compute_sha256(source_text)
    expected_sha = payload.get("source_sha256")
    if expected_sha and expected_sha != source_sha and not args.force:
        raise SystemExit(
            "Patch source hash does not match current chapter text. "
            "Rebuild the patch or pass --force."
        )

    edits = payload.get("edits", [])
    if args.cut_only:
        edits = [edit for edit in edits if edit.get("type") == "cut"]

    revised_text, applied = apply_patch_edits(source_text, edits, payload.get("locked_spans", []))
    target_path = Path(args.output) if args.output else source_path

    if args.dry_run:
        print(f"{patch_path}: {len(applied)} edits ready for {target_path}")
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(revised_text, encoding="utf-8")
    print(f"{target_path}: applied {len(applied)} edits from {patch_path}")


if __name__ == "__main__":
    main()
