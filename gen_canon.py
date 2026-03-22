#!/usr/bin/env python3
"""
Generate canon.md by extracting all hard facts from world.md + characters.md.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from anthropic_api import message_text_from_response
from project_paths import readable_planning_artifact_path, require_seed_path

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

WRITER_MODEL = os.environ.get("AUTONOVEL_WRITER_MODEL", "claude-sonnet-4-6")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")

def call_writer(prompt, max_tokens=16000):
    import httpx
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": WRITER_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.2,  # Low temp for factual extraction
        "system": (
            "You are a continuity editor extracting lock-safe canon from novel planning "
            "documents. You are precise, exhaustive, and never invent facts that are not "
            "in the source material. Every retained entry must be traceable to a specific "
            "statement in the source documents and must describe an in-world fact a later "
            "scene should not contradict. Prefer functional judgment over keyword matching: "
            "keep the concrete in-world fact, discard the writer-facing interpretation around it."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = httpx.post(f"{API_BASE}/v1/messages", headers=headers, json=payload, timeout=300)
    return message_text_from_response(resp, context="gen_canon writer request")

world = readable_planning_artifact_path("world", BASE_DIR).read_text(encoding="utf-8")
characters = readable_planning_artifact_path("characters", BASE_DIR).read_text(encoding="utf-8")
seed = require_seed_path(BASE_DIR).read_text(encoding="utf-8")

prompt = f"""Extract EVERY hard fact from these planning documents into a structured canon database.
A "hard fact" is anything a later scene should not contradict: names, ages, dates, durations,
physical descriptions, geography, institutional rules, technological constraints, hidden facts
stated as true, concrete relationships, and established events.

Only include entries that read as in-world continuity.

Use this test for every candidate entry:
- If a later scene could contradict it in a way that would feel like a continuity error, keep it.
- If it mainly exists to help the writer think about structure, emphasis, theme, or performance, leave it out.
- If a line mixes both, extract the concrete underlying fact and discard the planning wrapper.

SOURCE DOCUMENTS:

=== SEED.MD ===
{seed}

=== WORLD.MD ===
{world}

=== CHARACTERS.MD ===
{characters}

FORMAT THE OUTPUT AS CANON.MD with these categories:

## Geography
- Specific facts about locations, distances, physical properties

## Timeline
- Dated events, ages, durations

## Technology / System Rules
- Hard rules of the setting's communication, constitutional, and physical systems
- Costs, limitations, and non-negotiable constraints

## Character Facts
- Ages, physical descriptions, habits, relationships
- One entry per fact (not paragraphs)

## Political / Factional
- Who controls what, alliances, conflicts, contracts

## Cultural
- Customs, taboos, laws, festivals, food, clothing

## Established In-Story
- Events that have already happened in the story's past
- Anything already true by the time the story opens or already completed within the seed

Interpretive material is common in planning docs. Handle it carefully:
- Secrets can be included when they are stated as true hidden facts.
- Subjective or rhetorical phrasing can be included only when it conveys a stable recurring fact the story treats as real.
- Character-planning language such as wants, needs, lies, ratings, arc labels, thematic roles, sample dialogue, or similar scaffolding is usually not canon unless it also states a concrete in-world fact that can be separated and retained.
- If two source documents conflict, do not write discrepancy commentary into canon. Keep only the smallest concrete statement that remains true across the sources; if no such statement exists, leave the contested detail out.

RULES:
- One fact per bullet point. Short. Specific. Checkable.
- Include the source abbreviation in parentheses after each fact.
- Be exhaustive, but never pad canon with writer-facing scaffolding or redundant split facts just to increase count.
- If two documents give slightly different details, do not silently merge them into a more specific claim than the sources support.
- DO NOT invent facts. Only record what's explicitly stated.
- When in doubt, prefer the smallest concrete statement that remains true without the surrounding interpretation.
"""

print("Calling writer model...", file=sys.stderr)
result = call_writer(prompt)
print(result)
