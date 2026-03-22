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
VOICE_BOOTSTRAP_TEMPLATE = """# Voice Profile

This file has two parts:
1. **Guardrails** -- universal rules to avoid AI-generated slop. These
   apply to ALL voices and are non-negotiable.
2. **Voice Identity** -- the specific voice for THIS novel. Generated
   during the foundation phase. Could be anything: dense and mythic,
   spare and brutal, warm and whimsical. The voice emerges from the
   story's needs.

---

## Part 1: Guardrails (permanent, all novels)

These are the cliff edges. Stay away from them regardless of voice.

### Tier 1: Banned words -- kill on sight

These are statistically overrepresented in LLM output vs. human writing.
If one appears, rewrite the sentence. No exceptions.

| Kill this         | Use instead                                    |
|-------------------|------------------------------------------------|
| delve             | dig into, examine, look at                     |
| utilize           | use                                            |
| leverage (verb)   | use, take advantage of                         |
| facilitate        | help, enable, make possible                    |
| elucidate         | explain, clarify                               |
| embark            | start, begin                                   |
| endeavor          | effort, try                                    |
| encompass         | include, cover                                 |
| multifaceted      | complex, varied                                |
| tapestry          | (describe the actual thing)                    |
| testament to      | shows, proves, demonstrates                    |
| paradigm          | model, approach, framework                     |
| synergy           | (delete the sentence and start over)           |
| holistic          | whole, complete, full-picture                  |
| catalyze          | trigger, cause, spark                          |
| juxtapose         | compare, contrast, set against                 |
| nuanced (filler)  | (cut it -- if it's nuanced, show how)          |
| realm             | area, field, domain                            |
| landscape (metaphorical) | field, space, situation                 |
| myriad            | many, lots of                                  |
| plethora          | many, a lot                                    |

### Tier 2: Suspicious in clusters

Fine alone. Three in one paragraph = rewrite that paragraph.

robust, comprehensive, seamless, cutting-edge, innovative, streamline,
empower, foster, enhance, elevate, optimize, pivotal, intricate,
profound, resonate, underscore, harness, navigate (metaphorical),
cultivate, bolster, galvanize, cornerstone, game-changer, scalable

### Tier 3: Filler phrases -- delete on sight

These add zero information. The sentence is always better without them.

- "It's worth noting that..." -> just state it
- "It's important to note that..." -> just state it
- "Importantly, ..." / "Notably, ..." / "Interestingly, ..." -> just state it
- "Let's dive into..." / "Let's explore..." -> start with the content
- "As we can see..." -> they can see
- "Furthermore, ..." / "Moreover, ..." / "Additionally, ..." -> and, also, or just start
- "In today's [fast-paced/digital/modern] world..." -> delete the clause
- "At the end of the day..." -> delete
- "It goes without saying..." -> then don't say it
- "When it comes to..." -> just talk about the thing
- "One might argue that..." -> argue it or don't
- "Not just X, but Y" -> restructure (the #1 LLM rhetorical crutch)

### Structural slop patterns

These are the shapes that betray machine origin. Avoid them in any voice.

**Paragraph template machine**: Don't repeat the same paragraph
structure (topic sentence -> elaboration -> example -> wrap-up).
Vary it. Sometimes the point comes last. Sometimes a paragraph is
one sentence. Sometimes three long ones in a row.

**Sentence length uniformity**: If every sentence is 15-25 words,
it reads as synthetic. Mix in fragments. And long, winding,
clause-heavy sentences that carry the reader through a thought
the way a river carries a leaf. Then a short one.

**Transition word addiction**: If consecutive paragraphs start with
"However," "Furthermore," "Additionally," "Moreover," "Nevertheless"
-- rewrite. Start with the subject. Start with action. Start with
dialogue. Start with a sense detail.

**Symmetry addiction**: Don't balance everything. Three pros, three
cons, five steps -- that's a tell. Real writing is lumpy. Some
sections are long because they need to be. Some are two lines.

**Hedge parade**: "may," "might," "could potentially," "it's possible
that" -- pick one per page, max. State things or don't.

**Em dash overload**: One or two per page is fine. Five per paragraph
is a dead giveaway. Use commas, parentheses, or two sentences instead.

**List abuse**: Prose, not bullets. If the scene calls for a list
(a merchant's inventory, a spell's components), earn it. Don't
default to bullet points because it's easy.

### The smell test

After writing any passage, ask:
- Read it aloud. Does it sound like a person talking?
- Is there a single surprising sentence? Human writing surprises.
- Does it say something specific? Could you swap the topic and the
  words would still work? Specificity kills slop.
- Would a reader think "AI wrote this"? If yes, rewrite.

---

## Part 2: Voice Identity (generated per novel)

Everything below is discovered during the foundation phase.
The agent proposes a voice that serves THIS story, writes exemplar
passages, and calibrates against them throughout drafting.

### Tone
<!-- Generated during foundation. Examples:
     "Mythic and weighty, like stone tablets being read aloud."
     "Warm, slightly breathless, like a traveler telling stories by firelight."
     "Spare and cold. Sentences like knife cuts." -->

### Sentence Rhythm
<!-- Generated during foundation. Not rules -- tendencies.
     "Long sentences for worldbuilding, short for violence."
     "Dialogue is clipped. Narration flows." -->

### Vocabulary Register
<!-- Generated during foundation. The word-hoard for this world.
     What does this world SOUND like? Anglo-Saxon blunt? Latinate
     baroque? Colloquial modern? A mix? -->

### POV and Tense
<!-- Generated during foundation.
     Third limited? First? Rotating? Omniscient?
     Past tense? Present? Does it shift for effect? -->

### Dialogue Conventions
<!-- Generated during foundation.
     Tags: "said" only? Action beats? No tags at all?
     How do characters sound different from each other?
     Subtext rules: do characters say what they mean? -->

### Exemplar Passages
<!-- 3-5 paragraphs that ARE the voice. Written during foundation.
     The agent calibrates every chapter against these.
     These are the tuning fork. -->

### Anti-Exemplars
<!-- 3-5 paragraphs showing what this voice is NOT.
     Not the generic anti-slop stuff above -- specific to this novel.
     "This is too flowery for our tone." "This is too modern." -->
"""


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


def replace_or_bootstrap_voice_part2(voice_text: str | None, part2_body: str) -> str:
    """Update Part 2 in-place, or build the default voice.md scaffold when the file is missing."""
    template = voice_text if voice_text is not None else VOICE_BOOTSTRAP_TEMPLATE
    return replace_voice_part2(template, part2_body)


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
