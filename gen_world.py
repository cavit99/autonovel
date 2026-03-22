#!/usr/bin/env python3
"""
One-shot world.md generator for foundation phase.
Reads seed.md and optional planning/voice.md, calls the writer model,
and outputs planning/world.md content.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for bare Python test runners
    def load_dotenv(*_args, **_kwargs):
        return False

from anthropic_api import enable_automatic_prompt_cache, message_text_from_response
from project_paths import readable_planning_artifact_path, require_seed_path

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

WRITER_MODEL = os.environ.get("AUTONOVEL_WRITER_MODEL", "claude-sonnet-4-6")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")

BOOTSTRAP_VOICE_GUIDANCE = (
    "Voice identity has not been discovered yet. Build the world from the seed's implied "
    "social pressures, bodily costs, material textures, and concrete lived details. Prefer "
    "specificity, consequence, and atmosphere over generic fantasy phrasing."
)


def call_writer(prompt: str, max_tokens: int = 16000) -> str:
    import httpx

    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": WRITER_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "system": (
            "You are a fantasy worldbuilder with deep knowledge of Sanderson's Laws, "
            "Le Guin's prose philosophy, and TTRPG-quality lore design. "
            "You write world bibles that are specific, interconnected, and imply depth "
            "beyond what's stated. You never use AI slop words (delve, tapestry, myriad, etc). "
            "You write in clean, direct prose. Every rule has a cost. Every cultural detail "
            "implies a history. Every location has a sensory signature."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    enable_automatic_prompt_cache(payload)
    resp = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=300)
    return message_text_from_response(resp, context="gen_world writer request")


def extract_voice_part2(voice_text: str) -> str:
    voice_lines = voice_text.splitlines()
    try:
        part2_start = next(i for i, line in enumerate(voice_lines) if "Part 2" in line)
    except StopIteration as exc:
        raise ValueError("voice.md is missing the Part 2 heading") from exc
    return "\n".join(voice_lines[part2_start:]).strip()


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


def build_world_prompt(seed: str, voice_guidance: str) -> str:
    return f"""Build a complete world bible for this fantasy novel. This is the WORLD.MD file --
the definitive reference for everything that EXISTS in this world. A writer should be able
to resolve any worldbuilding question from this document alone.

SEED CONCEPT:
{seed}

VOICE / TONE GUIDANCE:
{voice_guidance}

CRAFT REQUIREMENTS (from CRAFT.md -- follow these):
- Magic or speculative systems need HARD RULES with COSTS and LIMITATIONS when the story supports them
- Limitations >= powers in narrative prominence
- Trace implications of speculative rules through society, economy, law, religion, or daily life
- At least 2-3 societal implications of the world's governing pressures explored in depth
- History must create PRESENT-DAY TENSIONS that drive the plot (not just backdrop)
- Geography must be specific and sensory (not generic fantasy)
- Iceberg principle: imply more than you state
- Interconnection: pulling one thread should move everything

STRUCTURE THE DOCUMENT WITH THESE SECTIONS:

## Cosmology & History
A timeline of major events. Focus on events that create PRESENT-DAY tensions.
Include the founding myth, key turning points, and recent events that matter to the plot.

## Governing Rules and Costs
Specific, testable rules when the story implies them. What forces, institutions,
taboos, or systems govern life here? What happens when people break or bend them?
Include COSTS and LIMITATIONS prominently.

## Edge Cases / Gifts / Curses / Unstable Phenomena
If the seed implies a gift, curse, rupture, anomaly, or unstable system, define
what it does, how it is perceived, and what it costs the people closest to it.
This can stay partly mysterious, but it needs consistent internal logic.

## Societal Implications
How do the world's rules and pressures shape governance, commerce, education,
class structure, crime, family life, childhood, aging, disability, ritual, labor?

## Geography
Describe the story's primary location(s), their physical layout, neighboring places,
and the sensory signatures that distinguish them.

## Factions & Politics
Who holds power, who wants it, and who is being crushed by it?
At least 3-4 factions or power centers with opposing interests.

## Bestiary / Flora / Natural World
What is specific and distinctive about the natural world in and around the story?

## Cultural Details
Customs, taboos, festivals, food, clothing, coming-of-age rituals.
Things that make daily life feel SPECIFIC.

## Internal Consistency Rules
Hard constraints a writer must not violate. What is possible here and what is not?

IMPORTANT:
- Be SPECIFIC. Not "the city has districts" but name them, describe them,
  give them sensory signatures.
- Every rule should have a COST or LIMITATION stated alongside it.
- Include 2-3 facts per section that are unexplained, hinting at deeper systems
  (iceberg depth).
- Facts should INTERCONNECT: the rules should shape the politics, the geography
  should shape the culture, the history should explain current faction conflicts.
- Write in clean, direct prose. No AI slop. No "rich tapestry." No "delving."
- The world should feel grounded and LIVED-IN, not merely invented. Think: what does
  breakfast smell like? What do children play? How do old people complain?
- Target ~3000-4000 words. Dense, not padded.
"""


def main() -> None:
    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    seed = require_seed_path(BASE_DIR).read_text(encoding="utf-8")
    voice_guidance = load_voice_guidance(BASE_DIR)
    if voice_guidance == BOOTSTRAP_VOICE_GUIDANCE:
        print("Voice identity not discovered yet; bootstrapping world generation from seed only.", file=sys.stderr)
    prompt = build_world_prompt(seed, voice_guidance)

    print("Calling writer model...", file=sys.stderr)
    result = call_writer(prompt)
    print(result)


if __name__ == "__main__":
    main()
