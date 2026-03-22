#!/usr/bin/env python3
"""Pure helpers for PR1 foundation-mind tooling."""

from __future__ import annotations

import json
import re

PERSPECTIVE_SECTIONS = (
    "Obsessions",
    "Blind Spots",
    "Sense of Humor",
    "The Unbearable",
    "Self-Awareness",
    "Formal Signatures",
)

VOICE_SECTIONS = (
    "Tone",
    "Sentence Rhythm",
    "Vocabulary Register",
    "POV and Tense",
    "Dialogue Conventions",
    "Exemplar Passages",
    "Anti-Exemplars",
)

TRIAL_REGISTERS = (
    {
        "name": "mythic_weight",
        "label": "Mythic and weighty",
        "description": "Sentences feel ceremonial, grave, and old without becoming purple.",
    },
    {
        "name": "spare_precision",
        "label": "Spare and exact",
        "description": "Language is lean, cold, and concrete; emotion arrives through restraint.",
    },
    {
        "name": "warm_intimate",
        "label": "Warm and intimate",
        "description": "Narration feels close to breath and body; tenderness sits beside tension.",
    },
    {
        "name": "bruised_lyric",
        "label": "Bruised lyricism",
        "description": "The prose is musical and image-rich, but always under pressure.",
    },
    {
        "name": "scholarly_strange",
        "label": "Scholarly and strange",
        "description": "The voice is analytical, slightly obsessive, and alive to systems and anomalies.",
    },
    {
        "name": "streetwise_dry",
        "label": "Dry and streetwise",
        "description": "Humor, friction, and quick observation keep the prose moving and unsentimental.",
    },
    {
        "name": "sensory_fever",
        "label": "Sensory and fevered",
        "description": "Perception leads; syntax bends under pressure and bodily intensity.",
    },
    {
        "name": "plainspoken_gravity",
        "label": "Plainspoken gravity",
        "description": "Every line is readable and direct, but the rhythm carries weight.",
    },
)

CHARACTER_ENGINE_FIELDS = (
    "wound",
    "want",
    "need",
    "lie",
    "unresolvable_contradictions",
    "speech_sample",
    "metaphor_domain",
    "taboo_topics",
    "default_dodge",
    "stress_transform",
    "cognitive_ceiling",
)

COGNITIVE_CEILING_LEVELS = {"low", "medium", "high"}
VOICE_PART2_HEADING = "## Part 2: Voice Identity (generated per novel)"


def strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def extract_json_object(text: str):
    """Extract a JSON object or array from a model response."""
    cleaned = strip_code_fences(text)
    start_candidates = [idx for idx in (cleaned.find("{"), cleaned.find("[")) if idx >= 0]
    if not start_candidates:
        raise ValueError("No JSON object found in response")
    start = min(start_candidates)

    try:
        return json.loads(cleaned[start:], strict=False)
    except json.JSONDecodeError:
        opening = cleaned[start]
        closing = "}" if opening == "{" else "]"
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(cleaned)):
            char = cleaned[idx]
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
            if char == opening:
                depth += 1
            elif char == closing:
                depth -= 1
                if depth == 0:
                    return json.loads(cleaned[start : idx + 1], strict=False)
        raise


def ensure_string(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def ensure_string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value)
    return [ensure_string(item) for item in items if ensure_string(item)]


def normalize_perspective_profile(profile: dict) -> dict[str, object]:
    return {
        "obsessions": ensure_string_list(profile.get("obsessions")),
        "blind_spots": ensure_string_list(profile.get("blind_spots")),
        "sense_of_humor": ensure_string_list(profile.get("sense_of_humor")),
        "the_unbearable": ensure_string_list(profile.get("the_unbearable")),
        "self_awareness": ensure_string(profile.get("self_awareness")),
        "formal_signatures": ensure_string_list(profile.get("formal_signatures")),
    }


def render_perspective_markdown(profile: dict[str, object]) -> str:
    normalized = normalize_perspective_profile(profile)
    lines = ["# Perspective", ""]

    lines.extend(["## Obsessions"])
    lines.extend(_render_bullets(normalized["obsessions"], "No obsessions generated yet."))
    lines.append("")

    lines.extend(["## Blind Spots"])
    lines.extend(_render_bullets(normalized["blind_spots"], "No blind spots generated yet."))
    lines.append("")

    lines.extend(["## Sense of Humor"])
    lines.extend(_render_bullets(normalized["sense_of_humor"], "No humor signature generated yet."))
    lines.append("")

    lines.extend(["## The Unbearable"])
    lines.extend(_render_bullets(normalized["the_unbearable"], "No unbearable zones generated yet."))
    lines.append("")

    lines.extend(["## Self-Awareness"])
    self_awareness = normalized["self_awareness"] or "No self-awareness note generated yet."
    lines.append(self_awareness)
    lines.append("")

    lines.extend(["## Formal Signatures"])
    lines.extend(_render_bullets(normalized["formal_signatures"], "No formal signatures generated yet."))
    lines.append("")

    return "\n".join(lines)


def normalize_character_engine(engine: dict) -> dict[str, object]:
    if not isinstance(engine, dict) or not engine:
        raise ValueError("character engine must be a non-empty object")

    normalized = {}
    for raw_name, raw_payload in engine.items():
        name = ensure_string(raw_name)
        if not name:
            continue
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        stress_transform = payload.get("stress_transform")
        if not isinstance(stress_transform, dict):
            stress_transform = {}
        cognitive = payload.get("cognitive_ceiling")
        if not isinstance(cognitive, dict):
            cognitive = {}

        abstraction_level = ensure_string(cognitive.get("abstraction_level")).lower()
        if abstraction_level not in COGNITIVE_CEILING_LEVELS:
            abstraction_level = "medium"

        normalized[name] = {
            "wound": ensure_string(payload.get("wound")),
            "want": ensure_string(payload.get("want")),
            "need": ensure_string(payload.get("need")),
            "lie": ensure_string(payload.get("lie")),
            "unresolvable_contradictions": ensure_string_list(payload.get("unresolvable_contradictions")),
            "speech_sample": ensure_string_list(payload.get("speech_sample")),
            "metaphor_domain": ensure_string_list(payload.get("metaphor_domain")),
            "taboo_topics": ensure_string_list(payload.get("taboo_topics")),
            "default_dodge": ensure_string(payload.get("default_dodge")),
            "stress_transform": {
                key: ensure_string(value)
                for key, value in stress_transform.items()
                if ensure_string(key) and ensure_string(value)
            },
            "cognitive_ceiling": {
                "abstraction_level": abstraction_level,
                "reasoning_style": ensure_string(cognitive.get("reasoning_style")),
                "failure_mode": ensure_string(cognitive.get("failure_mode")),
            },
        }

    if not normalized:
        raise ValueError("character engine has no usable character entries")
    return normalized


def normalize_voice_profile(profile: dict) -> dict[str, object]:
    return {
        "tone": ensure_string(profile.get("tone")),
        "sentence_rhythm": ensure_string(profile.get("sentence_rhythm")),
        "vocabulary_register": ensure_string(profile.get("vocabulary_register")),
        "pov_and_tense": ensure_string(profile.get("pov_and_tense")),
        "dialogue_conventions": ensure_string(profile.get("dialogue_conventions")),
        "exemplar_passages": ensure_string_list(profile.get("exemplar_passages")),
        "anti_exemplars": ensure_string_list(profile.get("anti_exemplars")),
    }


def render_voice_identity(profile: dict[str, object]) -> str:
    normalized = normalize_voice_profile(profile)
    lines = []

    lines.extend(["### Tone", normalized["tone"] or "No tone generated yet.", ""])
    lines.extend(["### Sentence Rhythm", normalized["sentence_rhythm"] or "No sentence rhythm generated yet.", ""])
    lines.extend(["### Vocabulary Register", normalized["vocabulary_register"] or "No vocabulary register generated yet.", ""])
    lines.extend(["### POV and Tense", normalized["pov_and_tense"] or "No POV/tense guidance generated yet.", ""])
    lines.extend(["### Dialogue Conventions", normalized["dialogue_conventions"] or "No dialogue conventions generated yet.", ""])
    lines.extend(["### Exemplar Passages"])
    lines.extend(_render_paragraphs(normalized["exemplar_passages"], "No exemplar passages generated yet."))
    lines.append("")
    lines.extend(["### Anti-Exemplars"])
    lines.extend(_render_bullets(normalized["anti_exemplars"], "No anti-exemplars generated yet."))
    lines.append("")

    return "\n".join(lines)


def replace_voice_part2(voice_text: str, part2_body: str) -> str:
    marker = VOICE_PART2_HEADING
    start = voice_text.find(marker)
    if start == -1:
        raise ValueError("voice.md is missing Part 2 heading")
    return voice_text[: start + len(marker)] + "\n\n" + part2_body.strip() + "\n"


def available_registers(count: int) -> list[dict[str, str]]:
    if count < 5 or count > len(TRIAL_REGISTERS):
        raise ValueError(f"trial count must be between 5 and {len(TRIAL_REGISTERS)}")
    return list(TRIAL_REGISTERS[:count])


def _render_bullets(items: list[str], fallback: str) -> list[str]:
    if not items:
        return [fallback]
    return [f"- {item}" for item in items]


def _render_paragraphs(items: list[str], fallback: str) -> list[str]:
    if not items:
        return [fallback]
    lines = []
    for item in items:
        lines.append(item)
        lines.append("")
    return lines[:-1]
