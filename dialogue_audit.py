#!/usr/bin/env python3
"""Audit dialogue for sameness, abstraction drift, and speaker bleed."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for bare Python test runners
    def load_dotenv(*_args, **_kwargs):
        return False

from evidence_tools import (
    BASE_DIR,
    EDIT_LOG_DIR,
    cognitive_ceiling_violation,
    extract_dialogue_records,
    generic_dialogue,
    load_all_chapters,
    load_character_engine,
    speaker_domain_leaks,
    speaker_similarity,
    theme_perfect_dialogue,
)

load_dotenv(BASE_DIR / ".env")

DIALOGUE_MODEL = os.environ.get("AUTONOVEL_DIALOGUE_MODEL", os.environ.get("AUTONOVEL_SMELL_MODEL", os.environ.get("AUTONOVEL_JUDGE_MODEL", "claude-opus-4-6")))


def build_dialogue_audit(chapters: dict[int, str], character_engine: dict) -> dict:
    known_names = set(character_engine)
    records = []
    for chapter, text in chapters.items():
        records.extend(extract_dialogue_records(text, chapter=chapter, known_names=known_names))

    generic_lines = []
    theme_perfect_lines = []
    metaphor_leaks = []
    ceiling_violations = []

    for record in records:
        if generic_dialogue(record["text"]):
            generic_lines.append(record)
        if theme_perfect_dialogue(record["text"]):
            theme_perfect_lines.append(record)
        leaks = speaker_domain_leaks(record, character_engine)
        if leaks:
            metaphor_leaks.append({**record, "other_domains": leaks})
        if cognitive_ceiling_violation(record, character_engine):
            ceiling_violations.append(record)

    return {
        "generated_at": datetime.now().isoformat(),
        "model": DIALOGUE_MODEL,
        "total_lines": len(records),
        "speaker_count": len({record["speaker"] for record in records if record["speaker"] != "Unknown"}),
        "speaker_non_separability": speaker_similarity(records),
        "generic_lines": generic_lines[:20],
        "theme_perfect_lines": theme_perfect_lines[:20],
        "metaphor_domain_leakage": metaphor_leaks[:20],
        "cognitive_ceiling_violations": ceiling_violations[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit dialogue across the manuscript or a single chapter.",
    )
    parser.add_argument("--all", action="store_true", help="Audit all available chapter files.")
    parser.add_argument("--chapter", type=int, help="Audit a single chapter.")
    parser.add_argument(
        "--output",
        default=str(EDIT_LOG_DIR / "dialogue_audit.json"),
        help="Where to write the JSON audit report.",
    )
    args = parser.parse_args()

    chapters = load_all_chapters()
    if args.chapter is not None:
        chapters = {args.chapter: chapters.get(args.chapter, "")}
    elif not args.all:
        chapters = chapters

    audit = build_dialogue_audit(chapters, load_character_engine())

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
