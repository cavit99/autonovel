#!/usr/bin/env python3
"""Generate alternative chapter drafts for critical, risky, or weak chapters."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

import draft_chapter
from variant_tools import baseline_variant_path, scene_options_for_prompt, variant_instruction, variant_path

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft chapter variants into chapters/variants/.")
    parser.add_argument("chapter", type=int, help="Chapter number to variant-draft")
    parser.add_argument("--variants", type=int, default=3, help="How many new variants to generate")
    parser.add_argument(
        "--mode",
        choices=("auto", "legacy", "new"),
        default="auto",
        help="Drafting mode. Auto matches draft_chapter.py behavior.",
    )
    parser.add_argument("--base-dir", type=Path, default=BASE_DIR, help="Project root")
    parser.add_argument("--dry-run", action="store_true", help="Print one assembled variant prompt and exit")
    args = parser.parse_args()

    mode = draft_chapter.resolve_mode(args.base_dir, args.chapter, args.mode)
    system_prompt, base_prompt = draft_chapter.build_prompt_for_mode(args.base_dir, args.chapter, mode)
    scene_options = scene_options_for_prompt(args.base_dir, args.chapter)

    variants_dir = args.base_dir / "chapters" / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)

    current_path = args.base_dir / "chapters" / f"ch_{args.chapter:02d}.md"
    if current_path.exists():
        shutil.copy2(current_path, baseline_variant_path(args.chapter, args.base_dir))

    if args.dry_run:
        prompt = (
            base_prompt
            + "\n\n---\n\n"
            + variant_instruction(args.chapter, 1, args.variants, scene_options)
        )
        print(f"MODE: {mode}")
        print("=== SYSTEM PROMPT ===")
        print(system_prompt)
        print("=== VARIANT PROMPT ===")
        print(prompt)
        return

    if not API_KEY:
        raise SystemExit("ERROR: ANTHROPIC_API_KEY not set; cannot generate chapter variants.")

    for variant_index in range(1, args.variants + 1):
        prompt = (
            base_prompt
            + "\n\n---\n\n"
            + variant_instruction(args.chapter, variant_index, args.variants, scene_options)
        )
        print(f"Drafting variant {variant_index}/{args.variants} for Chapter {args.chapter}...", file=sys.stderr)
        result = draft_chapter.call_writer(prompt, system_prompt)
        output_path = variant_path(args.chapter, variant_index, args.base_dir)
        output_path.write_text(result, encoding="utf-8")
        print(f"Saved {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
