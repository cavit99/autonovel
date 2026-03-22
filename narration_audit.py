#!/usr/bin/env python3
"""Audit non-dialogue narration for repeated templates and habits."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
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
    INTENSIFIERS,
    extract_narration_sentences,
    load_all_chapters,
    observation_signature,
    room_entry_signature,
    sentence_starters,
    split_passages,
    tokenize,
)

load_dotenv(BASE_DIR / ".env")

SMELL_MODEL = os.environ.get(
    "AUTONOVEL_SMELL_MODEL",
    os.environ.get("AUTONOVEL_JUDGE_MODEL", "claude-opus-4-6"),
)


METAPHOR_PATTERNS = {
    "like_x": re.compile(r"\blike\s+[A-Za-z']+"),
    "as_if": re.compile(r"\bas if\b"),
    "something_in_body": re.compile(r"\bsomething\b.+\bchest\b"),
}


def build_narration_audit(chapters: dict[int, str]) -> dict:
    sentences = extract_narration_sentences(chapters)
    passages = []
    for chapter, text in chapters.items():
        for passage in [part.strip() for part in text.split("\n\n") if part.strip()]:
            passages.append({"chapter": chapter, "text": passage})

    opening_counts = Counter()
    for record in sentences:
        for starter in sentence_starters(record["text"]):
            opening_counts[starter] += 1

    repeated_openings = [
        {"opening": opening, "count": count}
        for opening, count in opening_counts.most_common()
        if count >= 2
    ][:10]

    metaphor_counts = Counter()
    for record in sentences:
        lower = record["text"].lower()
        for label, pattern in METAPHOR_PATTERNS.items():
            if pattern.search(lower):
                metaphor_counts[label] += 1

    repeated_metaphors = [
        {"pattern": label, "count": count}
        for label, count in metaphor_counts.items()
        if count >= 2
    ]

    observation_orders = Counter()
    room_entries = Counter()
    for passage in passages:
        signature = observation_signature(passage["text"])
        if len(signature) >= 2:
            observation_orders[signature] += 1
        if room_entry_signature(passage["text"]):
            room_entries[signature or ("entry_only",)] += 1

    repeated_observation_orders = [
        {"signature": list(signature), "count": count}
        for signature, count in observation_orders.items()
        if count >= 2
    ]

    repeated_room_entries = [
        {"signature": list(signature), "count": count}
        for signature, count in room_entries.items()
        if count >= 2
    ]

    token_counts = Counter()
    for record in sentences:
        token_counts.update(token for token in tokenize(record["text"]) if token in INTENSIFIERS)

    repeated_intensifiers = [
        {"token": token, "count": count}
        for token, count in token_counts.items()
        if count >= 2
    ]

    repeated_templates = []
    for record in sentences:
        lower = record["text"].lower()
        if re.search(r"\b(?:entered|stepped into|walked into)\b", lower):
            repeated_templates.append(record)

    return {
        "generated_at": datetime.now().isoformat(),
        "model": SMELL_MODEL,
        "narration_sentence_count": len(sentences),
        "repeated_sentence_openings": repeated_openings,
        "repeated_metaphor_structures": repeated_metaphors,
        "repeated_observation_ordering": repeated_observation_orders,
        "repeated_intensifiers": repeated_intensifiers,
        "room_entry_patterning": repeated_room_entries,
        "room_entry_examples": repeated_templates[:10],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit manuscript narration for repeated patterns.",
    )
    parser.add_argument("--all", action="store_true", help="Audit all available chapter files.")
    parser.add_argument("--chapter", type=int, help="Audit a single chapter.")
    parser.add_argument(
        "--output",
        default=str(EDIT_LOG_DIR / "narration_audit.json"),
        help="Where to write the JSON audit report.",
    )
    args = parser.parse_args()

    chapters = load_all_chapters()
    if args.chapter is not None:
        chapters = {args.chapter: chapters.get(args.chapter, "")}
    elif not args.all:
        chapters = chapters

    audit = build_narration_audit(chapters)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
