#!/usr/bin/env python3
"""Advance the consolidated per-chapter story state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stateful_drafting import (
    build_story_state,
    load_character_engine,
    load_chapter_card,
    load_thread_registry,
    local_thread_window,
    read_text_if_exists,
    read_json_if_exists,
    story_state_path,
)

BASE_DIR = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Advance consolidated story state for a chapter")
    parser.add_argument("--chapter", type=int, required=True, help="Chapter number to snapshot")
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
    threads = load_thread_registry(args.base_dir)
    thread_window = local_thread_window(threads, args.chapter)
    chapter_text = read_text_if_exists(args.base_dir / "chapters" / f"ch_{args.chapter:02d}.md")
    character_engine = load_character_engine(args.base_dir)

    state = build_story_state(
        args.chapter,
        chapter_card,
        previous_state,
        chapter_text,
        thread_window,
        character_engine,
    )

    output_path = args.output or story_state_path(args.base_dir, args.chapter)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
