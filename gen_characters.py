#!/usr/bin/env python3
"""
One-shot characters.md generator for foundation phase.
Reads seed.md + planning/voice.md + planning/world.md, calls the writer model, and prints
the generated markdown. Optionally emits a structured character engine.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for bare Python test runners
    def load_dotenv(*_args, **_kwargs):
        return False

from foundation_mind import (
    extract_json_object,
    normalize_character_engine,
)
from project_paths import (
    ensure_parent_dir,
    planning_artifact_path,
    readable_planning_artifact_path,
    require_seed_path,
)

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

WRITER_MODEL = os.environ.get("AUTONOVEL_WRITER_MODEL", "claude-sonnet-4-6")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")
DEFAULT_ENGINE_PATH = planning_artifact_path("character_engine", BASE_DIR)

CHARACTER_SYSTEM = (
    "You are a character designer for literary fiction with deep knowledge of "
    "wound/want/need/lie frameworks, Sanderson's three sliders, and dialogue "
    "distinctiveness. You create characters who feel like real people with "
    "contradictions, secrets, and speech patterns you can hear. "
    "You never use AI slop words. You write in clean, direct prose."
)

ENGINE_SYSTEM = (
    "You are a fiction development editor converting a character registry into a "
    "strict JSON character engine. Preserve the novel's specifics. Infer only when "
    "the registry strongly supports it. Return valid JSON only."
)


def call_writer(prompt: str, *, max_tokens: int = 16000, temperature: float = 0.7, system: str = CHARACTER_SYSTEM) -> str:
    import httpx

    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": WRITER_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def extract_voice_part2(voice_text: str) -> str:
    voice_lines = voice_text.splitlines()
    try:
        part2_start = next(i for i, line in enumerate(voice_lines) if "Part 2" in line)
    except StopIteration as exc:
        raise ValueError("voice.md is missing the Part 2 heading") from exc
    return "\n".join(voice_lines[part2_start:])


def read_required(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError as exc:
        raise SystemExit(f"ERROR: required file not found: {path}") from exc


BOOTSTRAP_VOICE_GUIDANCE = (
    "Voice identity has not been discovered yet. Build the cast from the seed's implied "
    "social world, power relations, wounds, habits, and speech patterns. Favor concrete "
    "human pressure over generic archetypes."
)


def load_voice_guidance(base_dir: Path) -> str:
    voice_path = readable_planning_artifact_path("voice", base_dir)
    if not voice_path.exists():
        return BOOTSTRAP_VOICE_GUIDANCE
    try:
        voice_text = voice_path.read_text(encoding="utf-8")
    except OSError:
        return BOOTSTRAP_VOICE_GUIDANCE
    try:
        return extract_voice_part2(voice_text)
    except ValueError:
        return BOOTSTRAP_VOICE_GUIDANCE


def build_character_prompt(seed: str, world: str, voice_part2: str) -> str:
    return f"""Build a complete character registry for this fantasy novel. This is CHARACTERS.MD --
the definitive reference for WHO exists in this story, what drives them, how they speak,
and what secrets they carry.

SEED CONCEPT:
{seed}

WORLD BIBLE (the world these characters inhabit):
{world}

VOICE IDENTITY (the novel's tone):
{voice_part2}

CHARACTER CRAFT REQUIREMENTS (from CRAFT.md):

### The Three Sliders (Sanderson)
Every character has three independent dials (0-10):
  PROACTIVITY -- Do they drive the plot or react to it?
  LIKABILITY  -- Does the reader empathize with them?
  COMPETENCE  -- Are they good at what they do?
Rule: compelling = HIGH on at least TWO, or HIGH on one with clear growth.

### Wound / Want / Need / Lie Framework
A causal chain:
  GHOST (backstory event) -> WOUND (ongoing damage) -> LIE (false belief to cope)
    -> WANT (external goal driven by Lie) -> NEED (internal truth, opposes Lie)
Rules: Want and Need must be IN TENSION. Lie statable in one sentence.
  Truth is its direct opposite.

### Dialogue Distinctiveness (8 dimensions)
1. Vocabulary level  2. Sentence length  3. Contractions/formality
4. Verbal tics  5. Question vs statement ratio  6. Interruption patterns
7. Metaphor domain  8. Directness vs indirectness
Test: Remove dialogue tags. Can you tell who's speaking?

BUILD THE REGISTRY AROUND THE CAST THE SEED ACTUALLY IMPLIES.
Preserve any names, titles, factions, and relationships already present in the seed/world/voice.
Do NOT import characters, surnames, or setting details from some other project.

Develop at least these story roles, using the novel's actual names:

1. **The protagonist / primary viewpoint character**
   - Full wound/want/need/lie chain
   - Three sliders with justification
   - Arc type (positive/negative/flat)
   - Detailed speech pattern (8 dimensions)
   - Physical habits and tells
   - At least 2 secrets
   - Key relationships mapped

2. **The closest pressure character**
   - A parent, sibling, mentor, spouse, patron, rival, or intimate counterpart
   - Same depth as the protagonist
   - What they know, what they hide, and how they exert pressure

3. **The primary opposing force**
   - A person, faction representative, or intimate antagonist
   - Not a cardboard villain; give them an understandable logic
   - Their own wound/want/need/lie if they are a major on-page character

4. **The institutional or systemic pressure figure**
   - The character who personifies the rules, hierarchy, or machine of the world
   - If the story has no such figure, replace this slot with the next-most-essential major character

5. **The absent but plot-shaping figure**
   - Someone whose off-page choices, disappearance, debt, death, betrayal, or legacy still drives the story
   - If no absent figure matters, use the next-most-essential supporting character instead

6. **At least 2 additional characters** the story materially needs
   - A peer, confidant, foil, or rival
   - Someone tied to the story's family/community/power structure
   - Anyone else required for the plot to function on the page

FOR EACH CHARACTER INCLUDE:
- Name, age, role
- Ghost/Wound/Want/Need/Lie chain (for major characters)
- Three sliders (proactivity/likability/competence) with numbers and justification
- Arc type and arc trajectory
- Speech pattern (all 8 dimensions, with example lines)
- Physical appearance (specific, not generic)
- Physical habits and unconscious tells
- Secrets (what the reader doesn't learn immediately)
- Key relationships (mapped to other characters)
- Thematic role (what question does this character embody?)

IMPORTANT:
- Characters must INTERCONNECT. Their wants should conflict with each other.
- Every secret should be something that would CHANGE the story if revealed.
- Speech patterns must be distinct enough to pass the no-tags test.
- Preserve seed-specific names and invented terms when they already exist.
- If the seed implies a gift, curse, wound, profession, or bodily cost, let it shape habits, perception, and dialogue.
- If family pressure is central, make close relatives or caretakers as fully realized as the protagonist.
- The main antagonist or opposing force should be as fully realized as the protagonist -- a worthy source of pressure.
- Target ~3000-4000 words. Dense character work, not padding.
"""


def build_engine_prompt(seed: str, world: str, characters_markdown: str) -> str:
    return f"""Convert the following character registry into CHARACTER_ENGINE.JSON.

SEED CONCEPT:
{seed}

WORLD BIBLE:
{world}

CHARACTER REGISTRY:
{characters_markdown}

Return a JSON object keyed by major character name. For each character include:
- wound
- want
- need
- lie
- unresolvable_contradictions (list of 1-3)
- speech_sample (list of 5-10 lines)
- metaphor_domain (list of 1-4 domains)
- taboo_topics (list)
- default_dodge
- stress_transform (object with concise keys like syntax/dialogue/perception)
- cognitive_ceiling (object with abstraction_level, reasoning_style, failure_mode)

Rules:
- abstraction_level must be one of: low, medium, high
- preserve story-specific detail
- prefer concrete, short values over essays
- if a field is unclear, make the least-creative inference supported by the registry
- valid JSON only, no markdown fences
"""


def write_engine(engine_text: str, output_path: Path) -> Path:
    raw = extract_json_object(engine_text)
    normalized = normalize_character_engine(raw)
    ensure_parent_dir(output_path)
    output_path.write_text(json.dumps(normalized, indent=2) + "\n")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the character registry for the novel")
    parser.add_argument("--emit-engine", action="store_true", help="Also emit character_engine.json")
    parser.add_argument(
        "--engine-output",
        type=Path,
        default=DEFAULT_ENGINE_PATH,
        help="Path for the emitted character engine JSON",
    )
    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    seed = require_seed_path(BASE_DIR).read_text(encoding="utf-8")
    world = read_required(readable_planning_artifact_path("world", BASE_DIR))
    voice_part2 = load_voice_guidance(BASE_DIR)
    if voice_part2 == BOOTSTRAP_VOICE_GUIDANCE:
        print("Voice identity not discovered yet; bootstrapping character generation from seed and world.", file=sys.stderr)

    prompt = build_character_prompt(seed, world, voice_part2)
    print("Calling writer model...", file=sys.stderr)
    characters_markdown = call_writer(prompt)

    if args.emit_engine:
        print(f"Emitting character engine to {args.engine_output}...", file=sys.stderr)
        engine_prompt = build_engine_prompt(seed, world, characters_markdown)
        engine_text = call_writer(
            engine_prompt,
            max_tokens=12000,
            temperature=0.3,
            system=ENGINE_SYSTEM,
        )
        out_path = write_engine(engine_text, args.engine_output)
        print(f"Saved engine to {out_path}", file=sys.stderr)

    print(characters_markdown)


if __name__ == "__main__":
    main()
