#!/usr/bin/env python3
"""Generate scene options for a chapter from PR3 planning artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stateful_drafting import (
    generate_scene_options,
    load_chapter_card,
    load_thread_registry,
    local_thread_window,
    previous_chapter_tail,
    read_json_if_exists,
    scene_options_path,
    story_state_path,
)

BASE_DIR = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate scene options for a chapter")
    parser.add_argument("chapter", type=int, help="Chapter number to plan")
    parser.add_argument("--variants", type=int, default=3, help="How many scene options to emit")
    parser.add_argument(
        "--planner-mode",
        choices=("auto", "deterministic", "model"),
        default="auto",
        help="Scene planner mode. Auto prefers the model path when API config is available.",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=BASE_DIR,
        help="Base directory containing planning artifacts and chapters",
    )
    parser.add_argument("--output", type=Path, help="Optional explicit output path")
    args = parser.parse_args()

    previous_state = {}
    if args.chapter > 1:
        previous_state = read_json_if_exists(story_state_path(args.base_dir, args.chapter - 1), {})
    chapter_card = load_chapter_card(args.base_dir, args.chapter)
    thread_window = local_thread_window(load_thread_registry(args.base_dir), args.chapter)
    previous_prose = previous_chapter_tail(args.base_dir, args.chapter)

    options = generate_scene_options(
        args.chapter,
        chapter_card,
        previous_state,
        thread_window,
        args.variants,
        previous_prose=previous_prose,
        mode=args.planner_mode,
    )

    output_path = args.output or scene_options_path(args.base_dir, args.chapter)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(options, indent=2) + "\n")
    print(json.dumps(options, indent=2))


if __name__ == "__main__":
    main()
