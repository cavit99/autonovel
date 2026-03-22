#!/usr/bin/env python3
"""
4-reader panel for full-arc novel evaluation.

Usage:
  python reader_panel.py
  python reader_panel.py --evidence eval_logs/evidence_pack.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for bare Python test runners
    def load_dotenv(*_args, **_kwargs):
        return False

from evidence_tools import BASE_DIR, EDIT_LOG_DIR, load_all_chapters, load_json, render_evidence_pack

load_dotenv(BASE_DIR / ".env")

JUDGE_MODEL = os.environ.get("AUTONOVEL_JUDGE_MODEL", "claude-opus-4-6")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")
ANTHROPIC_BETA = "context-1m-2025-08-07"

READERS = {
    "editor": {
        "name": "The Editor",
        "system": (
            "You are a senior fiction editor at a major publishing house. "
            "You've edited 200+ novels. You care about prose texture, subtext, "
            "sentence-level craft, and whether the voice is consistent and earned. "
            "You respond with valid JSON only."
        ),
    },
    "genre_reader": {
        "name": "The Genre Reader",
        "system": (
            "You are an avid fantasy reader who reads 50+ novels a year. "
            "You care about pacing, payoff, momentum, and whether the book earns continued attention. "
            "You respond with valid JSON only."
        ),
    },
    "writer": {
        "name": "The Writer",
        "system": (
            "You are a published fantasy novelist reading for structure, scene method, and the gap "
            "between ambition and achieved effect. You respond with valid JSON only."
        ),
    },
    "first_reader": {
        "name": "The First Reader",
        "system": (
            "You are a thoughtful general reader responding emotionally rather than analytically. "
            "You respond with valid JSON only."
        ),
    },
}

LEGACY_READER_PROMPT = """You have just read a complete fantasy novel in summary form.
The summaries include chapter-by-chapter events, opening and closing passages
from each chapter, and key dialogue.

{arc_summary}

Now answer these questions about the NOVEL AS A WHOLE. Be specific.

Respond with JSON:
{{
  "momentum_loss": "Where does the story lose momentum? Name the specific chapter(s) and what causes the drag. If it never loses momentum, say so.",
  "earned_ending": "Does the ending feel earned by everything before it? What, if anything, feels unearned?",
  "cut_candidate": "If the novel had to be 10% shorter, which chapter or section would you cut first and why?",
  "missing_scene": "Is there a scene the novel needs that it doesn't have? Be specific about where it would go.",
  "thinnest_character": "Which character feels thinnest by the end?",
  "best_scene": "What's the single best scene in the novel and why?",
  "worst_scene": "What's the single weakest scene? What goes wrong? How would you fix it?",
  "would_recommend": "Would you recommend this novel? To whom?",
  "haunts_you": "Is there a line or moment that stays with you after reading?",
  "next_book": "Would you read the author's next book? Why or why not?"
}}
"""

EVIDENCE_READER_PROMPT = """You have not read a summary. You have read an evidence pack of real passages from the novel.
Ground your claims in the cited passage ids whenever possible.

{evidence}

Now answer these questions about the NOVEL AS A WHOLE. Be specific. Mention passage ids and chapter numbers when you can.

Respond with JSON:
{{
  "momentum_loss": "Where does the story lose momentum? Name the specific chapter(s), passage ids, and what causes the drag.",
  "earned_ending": "Does the ending feel earned by everything before it? What, if anything, feels unearned?",
  "cut_candidate": "If the novel had to be shorter, which chapter or section would you cut first and why?",
  "missing_scene": "Is there a scene the novel needs that it doesn't have? Where would it go?",
  "thinnest_character": "Which character feels thinnest by the end?",
  "best_scene": "What's the single best scene in the evidence pack and why?",
  "worst_scene": "What's the single weakest scene in the evidence pack? What goes wrong?",
  "would_recommend": "Would you recommend this novel? To whom?",
  "haunts_you": "Is there a line or moment that stays with you after reading?",
  "next_book": "Would you read the author's next book? Why or why not?",
  "evidence_cited": ["list the passage ids you relied on most"]
}}
"""


def parse_json_blob(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    start = raw.find("{")
    if start >= 0:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(raw)):
            char = raw[index]
            if escape:
                escape = False
                continue
            if char == "\\" and in_string:
                escape = True
                continue
            if char == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(raw[start:index + 1], strict=False)
    return json.loads(raw, strict=False)


def call_reader(reader_key: str, prompt: str) -> dict:
    import httpx

    reader = READERS[reader_key]
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": ANTHROPIC_BETA,
        "content-type": "application/json",
    }
    payload = {
        "model": JUDGE_MODEL,
        "max_tokens": 4000,
        "temperature": 0.7,
        "system": reader["system"],
        "messages": [{"role": "user", "content": prompt}],
    }
    response = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=300)
    response.raise_for_status()
    return parse_json_blob(response.json()["content"][0]["text"])


def find_disagreements(results: dict) -> list[dict]:
    disagreements = []
    for question in ["momentum_loss", "cut_candidate", "thinnest_character", "worst_scene"]:
        answers = {reader: payload.get(question, "") for reader, payload in results.items()}
        chapters_mentioned = {}
        for reader, answer in answers.items():
            mentions = set(re.findall(r"Ch(?:apter)?\s*(\d+)", str(answer), re.IGNORECASE))
            chapters_mentioned[reader] = mentions

        all_chapters = set()
        for mentions in chapters_mentioned.values():
            all_chapters.update(mentions)

        for chapter in all_chapters:
            flagged_by = [reader for reader, mentions in chapters_mentioned.items() if chapter in mentions]
            not_flagged = [reader for reader, mentions in chapters_mentioned.items() if chapter not in mentions]
            if flagged_by and not_flagged:
                disagreements.append(
                    {
                        "question": question,
                        "chapter": int(chapter),
                        "flagged_by": flagged_by,
                        "not_flagged": not_flagged,
                        "details": {reader: str(answers[reader])[:200] for reader in flagged_by},
                    }
                )
    return disagreements


def build_legacy_prompt() -> str:
    summary_path = BASE_DIR / "arc_summary.md"
    if summary_path.exists():
        arc_summary = summary_path.read_text(encoding="utf-8")
    else:
        chapters = load_all_chapters(BASE_DIR / "chapters")
        if not chapters:
            raise FileNotFoundError(
                "arc_summary.md not found and no chapter files are available for legacy panel fallback."
            )
        summaries = []
        for chapter_num in sorted(chapters):
            text = chapters[chapter_num]
            head = text[:300].strip()
            tail = text[-300:].strip() if len(text) > 300 else text.strip()
            summaries.append(
                f"Chapter {chapter_num}:\n"
                f"  Opening: {head}\n"
                f"  Closing: {tail}"
            )
        arc_summary = "\n\n".join(summaries)
    return LEGACY_READER_PROMPT.format(arc_summary=arc_summary)


def build_evidence_prompt(evidence_path: Path) -> str:
    evidence_pack = load_json(evidence_path)
    return EVIDENCE_READER_PROMPT.format(evidence=render_evidence_pack(evidence_pack))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the 4-reader novel panel.")
    parser.add_argument("--evidence", help="Path to an evidence-pack JSON file for prose-based panel mode.")
    parser.add_argument(
        "--output",
        default=str(EDIT_LOG_DIR / "reader_panel.json"),
        help="Where to write the JSON panel results.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the assembled prompt instead of calling the model.")
    args = parser.parse_args()

    prompt = build_evidence_prompt(Path(args.evidence)) if args.evidence else build_legacy_prompt()
    mode = "evidence" if args.evidence else "legacy"

    if args.dry_run:
        print(prompt)
        return

    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    results = {}
    for reader_key, reader_info in READERS.items():
        print(f"\n{'=' * 50}")
        print(f"READING: {reader_info['name']}")
        print(f"{'=' * 50}")
        try:
            result = call_reader(reader_key, prompt)
            results[reader_key] = result
            print(f"  Momentum loss: {str(result.get('momentum_loss', ''))[:150]}...")
            print(f"  Best scene: {str(result.get('best_scene', ''))[:150]}...")
            print(f"  Would recommend: {str(result.get('would_recommend', ''))[:150]}...")
        except Exception as exc:
            print(f"  ERROR: {exc}")

    disagreements = find_disagreements(results)

    output = {
        "mode": mode,
        "evidence_path": args.evidence,
        "readers": results,
        "disagreements": disagreements,
        "timestamp": datetime.now().isoformat(),
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
