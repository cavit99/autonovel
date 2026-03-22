#!/usr/bin/env python3
"""Discover the novel's voice via trial passages and pairwise comparison."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from foundation_mind import (
    available_registers,
    extract_json_object,
    normalize_voice_profile,
    render_voice_identity,
    replace_or_bootstrap_voice_part2,
)

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

WRITER_MODEL = os.environ.get("AUTONOVEL_WRITER_MODEL", "claude-sonnet-4-6")
JUDGE_MODEL = os.environ.get("AUTONOVEL_JUDGE_MODEL", WRITER_MODEL)
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")

VOICE_PATH = BASE_DIR / "voice.md"
PERSPECTIVE_PATH = BASE_DIR / "perspective.md"
DEFAULT_DISCOVERY_PATH = BASE_DIR / "voice_discovery.json"

WRITER_SYSTEM = (
    "You are trying out candidate prose registers for a single fantasy novel. "
    "Each passage should be vivid, specific, and clearly different in texture "
    "from the others while still fitting the same story."
)

JUDGE_SYSTEM = (
    "You evaluate candidate prose passages for novels. You care about quality, "
    "distinctiveness, and whether the passage sounds governed by the supplied "
    "perspective. Return valid JSON only."
)


def call_model(*, prompt: str, system: str, model: str, temperature: float, max_tokens: int) -> str:
    import httpx

    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def read_required(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError as exc:
        raise SystemExit(f"ERROR: required file not found: {path}") from exc


def build_trial_prompt(register: dict[str, str], seed: str, world: str, characters: str, perspective: str) -> str:
    return f"""Write a trial passage for this novel.

REGISTER TO TRY:
- Name: {register["label"]}
- Description: {register["description"]}

SEED CONCEPT:
{seed}

WORLD BIBLE (excerpt):
{world[:3500]}

CHARACTER REGISTRY (excerpt):
{characters[:3500]}

PERSPECTIVE:
{perspective}

Write 3-4 paragraphs, around 300-500 words, from the same kind of scene every time:
- a charged encounter where the protagonist tries to get information,
- the scene should reveal character pressure and the world's texture,
- it should not be the climax,
- it should not summarize the novel.

Requirements:
- keep the story facts consistent across registers
- change HOW the prose perceives and sounds, not WHAT the scene is about
- third-person limited past tense unless the perspective strongly implies otherwise
- no markdown fences
"""


def build_score_prompt(register: dict[str, str], perspective: str, passage: str) -> str:
    return f"""Evaluate this trial passage for the novel's voice-discovery phase.

REGISTER:
- {register["label"]}: {register["description"]}

PERSPECTIVE:
{perspective}

PASSAGE:
{passage}

Return JSON only:
{{
  "quality": 0-10,
  "distinctiveness": 0-10,
  "perspective_fit": 0-10,
  "strengths": ["2-4 short bullets"],
  "risks": ["2-4 short bullets"],
  "one_line_verdict": "..."
}}
"""


def build_compare_prompt(first: dict, second: dict, perspective: str) -> str:
    return f"""Choose the stronger voice candidate for this novel.

PERSPECTIVE:
{perspective}

CANDIDATE A ({first["label"]}):
{first["passage"]}

CANDIDATE B ({second["label"]}):
{second["passage"]}

Return JSON only:
{{
  "winner": "A" or "B",
  "reason": "short explanation",
  "what_the_winner_has": ["2-4 bullets"],
  "what_to_avoid_from_the_loser": ["2-4 bullets"]
}}
"""


def build_profile_prompt(winner: dict, perspective: str, comparison: dict) -> str:
    return f"""Convert the winning trial passage into a voice profile for voice.md Part 2.

PERSPECTIVE:
{perspective}

WINNING REGISTER:
- {winner["label"]}: {winner["description"]}

WINNING PASSAGE:
{winner["passage"]}

PAIRWISE COMPARISON NOTES:
{json.dumps(comparison, indent=2)}

Return JSON only:
{{
  "tone": "1 short paragraph",
  "sentence_rhythm": "1 short paragraph",
  "vocabulary_register": "1 short paragraph",
  "pov_and_tense": "1 short paragraph",
  "dialogue_conventions": "1 short paragraph",
  "exemplar_passages": ["3 short exemplar passages"],
  "anti_exemplars": ["3-5 bullets about what this voice should avoid"]
}}
"""


def trial_total(score: dict) -> float:
    return float(score["quality"]) + float(score["distinctiveness"]) + float(score["perspective_fit"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover the novel's voice through trial passages")
    parser.add_argument("--trials", type=int, default=5, help="Number of trial registers to generate (5-8)")
    parser.add_argument("--voice-output", type=Path, default=VOICE_PATH, help="Path to voice.md")
    parser.add_argument(
        "--discovery-output",
        type=Path,
        default=DEFAULT_DISCOVERY_PATH,
        help="Where to write voice-discovery metadata",
    )
    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    registers = available_registers(args.trials)
    seed = read_required(BASE_DIR / "seed.txt")
    world = read_required(BASE_DIR / "world.md")
    characters = read_required(BASE_DIR / "characters.md")
    perspective = read_required(PERSPECTIVE_PATH)
    voice_text = args.voice_output.read_text() if args.voice_output.exists() else None

    trials = []
    for register in registers:
        print(f"Generating trial passage: {register['label']}...", file=sys.stderr)
        passage = call_model(
            prompt=build_trial_prompt(register, seed, world, characters, perspective),
            system=WRITER_SYSTEM,
            model=WRITER_MODEL,
            temperature=0.9,
            max_tokens=1600,
        ).strip()
        score = extract_json_object(
            call_model(
                prompt=build_score_prompt(register, perspective, passage),
                system=JUDGE_SYSTEM,
                model=JUDGE_MODEL,
                temperature=0.2,
                max_tokens=1200,
            )
        )
        trial = {
            "name": register["name"],
            "label": register["label"],
            "description": register["description"],
            "passage": passage,
            "score": score,
            "total": trial_total(score),
        }
        trials.append(trial)

    ranked = sorted(trials, key=lambda item: item["total"], reverse=True)
    finalists = ranked[:2]
    compare = extract_json_object(
        call_model(
            prompt=build_compare_prompt(finalists[0], finalists[1], perspective),
            system=JUDGE_SYSTEM,
            model=JUDGE_MODEL,
            temperature=0.2,
            max_tokens=1000,
        )
    )
    winner = finalists[0] if compare.get("winner") == "A" else finalists[1]
    profile = normalize_voice_profile(
        extract_json_object(
            call_model(
                prompt=build_profile_prompt(winner, perspective, compare),
                system=JUDGE_SYSTEM,
                model=JUDGE_MODEL,
                temperature=0.2,
                max_tokens=1600,
            )
        )
    )

    rendered_part2 = render_voice_identity(profile)
    updated_voice = replace_or_bootstrap_voice_part2(voice_text, rendered_part2)
    args.voice_output.write_text(updated_voice)

    discovery = {
        "writer_model": WRITER_MODEL,
        "judge_model": JUDGE_MODEL,
        "trials": ranked,
        "finalists": [finalists[0]["name"], finalists[1]["name"]],
        "comparison": compare,
        "winner": winner["name"],
        "voice_profile": profile,
    }
    args.discovery_output.write_text(json.dumps(discovery, indent=2) + "\n")

    print(f"Saved updated voice profile to {args.voice_output}", file=sys.stderr)
    print(f"Saved discovery metadata to {args.discovery_output}", file=sys.stderr)
    print(rendered_part2)


if __name__ == "__main__":
    main()
