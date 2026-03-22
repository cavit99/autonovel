#!/usr/bin/env python3
"""Evidence-pack panel focused on overdesign, drama, and oral readability."""

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

from evidence_tools import BASE_DIR, EDIT_LOG_DIR, load_json, render_evidence_pack

load_dotenv(BASE_DIR / ".env")

SMELL_MODEL = os.environ.get("AUTONOVEL_SMELL_MODEL", os.environ.get("AUTONOVEL_JUDGE_MODEL", "claude-opus-4-6"))
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")

PANELISTS = {
    "novelist": (
        "You are a novelist reading for overdesign, over-explanation, and false balance. "
        "You want the world to feel bigger than the argument. Respond with valid JSON only."
    ),
    "dramatist": (
        "You are a dramatist reading for social event, concealment, wrong inference, and lines that arrive too perfectly. "
        "You respond with valid JSON only."
    ),
    "oral_reader": (
        "You are an oral reader listening for breath, bodily response, and whether prose survives being spoken aloud. "
        "You respond with valid JSON only."
    ),
}

PROMPT = """You are reviewing a fantasy novel through an evidence pack of real passages.

{evidence}

Return JSON:
{{
  "strongest_passage_id": "passage id",
  "weakest_passage_id": "passage id",
  "overdesigned": "Where, if anywhere, does the book feel overdesigned or too fully on-theme?",
  "social_dramatic_failure": "Where does a scene feel like information exchange instead of social event?",
  "oral_reading_issue": "What line or passage feels unnatural aloud?",
  "notes": ["3-5 concise passage-grounded notes with passage ids when possible"]
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
            if char == '"':
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


def call_panel(system: str, prompt: str) -> dict:
    import httpx

    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": SMELL_MODEL,
        "max_tokens": 2500,
        "temperature": 0.5,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    response = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=300)
    response.raise_for_status()
    raw = response.json()["content"][0]["text"].strip()
    return parse_json_blob(raw)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the humanity panel against a JSON evidence pack.",
    )
    parser.add_argument("--evidence", required=True, help="Path to the evidence pack JSON.")
    parser.add_argument(
        "--output",
        default=str(EDIT_LOG_DIR / "humanity_panel.json"),
        help="Where to write the JSON panel output.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the assembled prompt instead of calling the model.")
    args = parser.parse_args()

    evidence_pack = load_json(Path(args.evidence))
    prompt = PROMPT.format(evidence=render_evidence_pack(evidence_pack))

    if args.dry_run:
        print(prompt)
        return

    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    results = {}
    for key, system in PANELISTS.items():
        results[key] = call_panel(system, prompt)

    output = {
        "mode": "evidence",
        "model": SMELL_MODEL,
        "evidence_path": args.evidence,
        "generated_at": datetime.now().isoformat(),
        "panelists": results,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
