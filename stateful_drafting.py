#!/usr/bin/env python3
"""Pure helpers for PR3 stateful drafting and scene planning."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from planning_split import extract_json_object, normalize_thread_registry, parse_chapter_cards

SCENE_OPTION_FIELDS = (
    "goal",
    "pressure",
    "social_imbalance",
    "wrong_inference",
    "surprise_slot",
    "residue",
)

PERSPECTIVE_SECTION_MAP = {
    "Obsessions": "obsessions",
    "Blind Spots": "blind_spots",
    "Sense of Humor": "sense_of_humor",
    "The Unbearable": "the_unbearable",
    "Self-Awareness": "self_awareness",
    "Formal Signatures": "formal_signatures",
}

DEFAULT_STORY_STATE = {
    "world_clock": {
        "weather": "",
        "institutional_motion": [],
        "district_rumours": [],
        "market_changes": [],
        "offstage_consequences": [],
    },
    "knowledge_state": {},
    "minor_character_memory": {},
    "active_pressures": [],
}
PROSE_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
PROSE_NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b")
PROSE_NAME_STOPWORDS = {
    "A",
    "An",
    "And",
    "After",
    "As",
    "Before",
    "But",
    "Chapter",
    "Council",
    "Court",
    "Guild",
    "He",
    "Her",
    "His",
    "If",
    "It",
    "Later",
    "Now",
    "She",
    "That",
    "The",
    "Their",
    "There",
    "They",
    "Then",
    "This",
    "When",
    "While",
}
ALLOWED_NAME_TITLES = {"Captain", "Doctor", "Dr", "Lady", "Lord", "Master", "Mistress", "Ser", "Sir"}
TOKEN_STOPWORDS = {
    "about",
    "after",
    "before",
    "being",
    "could",
    "from",
    "have",
    "into",
    "just",
    "must",
    "room",
    "said",
    "some",
    "that",
    "their",
    "them",
    "there",
    "they",
    "this",
    "under",
    "were",
    "with",
    "would",
}
KNOWLEDGE_MARKERS = (
    "found out",
    "discovered",
    "learned",
    "noticed",
    "realized",
    "recognized",
    "understood",
    "heard",
    "knew",
    "saw",
)
SUSPECT_MARKERS = ("suspected", "wondered whether", "wondered if", "wondered", "guessed", "figured", "thought", "assumed")
MISREAD_MARKERS = ("mistook", "misread", "misjudged")
HIDE_MARKERS = ("withheld", "pretended", "concealed", "covered", "hid", "lied")
SELF_STORY_MARKERS = (
    "told himself",
    "told herself",
    "told themselves",
    "promised himself",
    "promised herself",
    "insisted to himself",
)
PRESSURE_MARKERS = (
    "bell",
    "bells",
    "clerks",
    "could not",
    "couldn't",
    "crowd",
    "deadline",
    "guard",
    "guards",
    "guild",
    "had to",
    "letters",
    "public",
    "rain",
    "scrutiny",
    "storm",
    "teacher",
    "teachers",
    "under",
    "waiting",
    "watching",
    "witness",
    "witnesses",
)
PRESSURE_EXCERPT_MARKERS = ("under", "before", "while", "against", "because", "until", "had to", "couldn't", "could not")
INSTITUTIONAL_MARKERS = {
    "bell",
    "bells",
    "clerk",
    "clerks",
    "council",
    "court",
    "crowd",
    "guard",
    "guards",
    "guild",
    "law",
    "market",
    "public",
    "scrutiny",
    "teacher",
    "teachers",
    "witness",
    "witnesses",
}
CONSEQUENCE_MARKERS = {
    "agreed",
    "broke",
    "changed",
    "committed",
    "decided",
    "ended",
    "left",
    "lost",
    "promised",
    "refused",
    "turned",
    "vowed",
}


def read_text_if_exists(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


def read_json_if_exists(path: Path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def ensure_string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def ensure_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value)
    normalized = [ensure_string(item) for item in items]
    return [item for item in normalized if item]


def ensure_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def sanitize_note(text: str) -> str:
    note = re.sub(r"\s+", " ", ensure_string(text))
    return note[:200]


def extract_markdown_section(text: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def markdown_section_to_list(text: str, heading: str) -> list[str]:
    section = extract_markdown_section(text, heading)
    items = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("<!--"):
            continue
        if line.startswith("- "):
            items.append(line.removeprefix("- ").strip())
        elif not items:
            items.append(line)
    return [item for item in items if item]


def parse_perspective_markdown(text: str) -> dict[str, object]:
    profile: dict[str, object] = {}
    for heading, key in PERSPECTIVE_SECTION_MAP.items():
        if heading == "Self-Awareness":
            section = extract_markdown_section(text, heading)
            lines = [line.strip() for line in section.splitlines() if line.strip() and not line.strip().startswith("<!--")]
            profile[key] = lines[0] if lines else ""
        else:
            profile[key] = markdown_section_to_list(text, heading)
    return profile


def chapter_card_for(cards: list[dict[str, object]], chapter_num: int) -> dict[str, object]:
    for card in cards:
        if int(card.get("number", 0)) == chapter_num:
            return card
    return {
        "number": chapter_num,
        "title": f"Chapter {chapter_num}",
        "focus_character": "",
        "goal": "",
        "pressure": "",
        "reversal": "",
        "aftermath": "",
        "irreversible_change": "",
        "allowed_ambiguity": "",
        "time_span": "",
        "scene_density": "medium",
        "scene_type": "investigation",
        "scene_method": "close_interiority",
        "risk": "none",
    }


def load_chapter_card(base_dir: Path, chapter_num: int) -> dict[str, object]:
    cards = parse_chapter_cards(read_text_if_exists(base_dir / "chapter_cards.md"))
    return chapter_card_for(cards, chapter_num)


def load_thread_registry(base_dir: Path) -> list[dict[str, object]]:
    payload = read_json_if_exists(base_dir / "thread_registry.json", [])
    return normalize_thread_registry(payload)


def local_thread_window(threads: list[dict[str, object]], chapter_num: int, limit: int = 6) -> list[dict[str, object]]:
    ranked = []
    for thread in threads:
        first_seen = ensure_int(thread.get("first_seen") or thread.get("planted"), default=0)
        payoff = ensure_int(thread.get("payoff"), default=0)
        required = bool(thread.get("required"))
        if first_seen and first_seen > chapter_num:
            continue
        if payoff and payoff < max(1, chapter_num - 1) and not required:
            continue
        score = 0
        score += 5 if required else 0
        score += 3 if ensure_string(thread.get("type")) == "pressure" else 0
        score += max(0, 4 - abs(chapter_num - first_seen)) if first_seen else 0
        score += 2 if not payoff or payoff >= chapter_num else 0
        ranked.append((score, thread))
    ranked.sort(key=lambda item: (-item[0], ensure_string(item[1].get("id"))))
    return [thread for _, thread in ranked[:limit]]


def render_thread_window(threads: list[dict[str, object]]) -> str:
    if not threads:
        return "(no local thread pressure available)"
    lines = []
    for thread in threads:
        description = ensure_string(thread.get("description")) or ensure_string(thread.get("id"))
        thread_type = ensure_string(thread.get("type")) or "plot"
        required = "required" if thread.get("required") else "optional"
        payoff = ensure_int(thread.get("payoff"), default=0)
        payoff_text = f", payoff Ch {payoff}" if payoff else ""
        lines.append(f"- [{thread_type}, {required}] {description}{payoff_text}")
    return "\n".join(lines)


def normalize_story_state(payload: object, chapter_num: int) -> dict[str, object]:
    state = payload if isinstance(payload, dict) else {}
    world_clock = state.get("world_clock") if isinstance(state.get("world_clock"), dict) else {}
    knowledge_state = state.get("knowledge_state") if isinstance(state.get("knowledge_state"), dict) else {}
    minor_memory = state.get("minor_character_memory") if isinstance(state.get("minor_character_memory"), dict) else {}
    active_pressures = ensure_string_list(state.get("active_pressures"))
    return {
        "chapter": chapter_num,
        "world_clock": {
            "weather": ensure_string(world_clock.get("weather")),
            "institutional_motion": ensure_string_list(world_clock.get("institutional_motion")),
            "district_rumours": ensure_string_list(world_clock.get("district_rumours")),
            "market_changes": ensure_string_list(world_clock.get("market_changes")),
            "offstage_consequences": ensure_string_list(world_clock.get("offstage_consequences")),
        },
        "knowledge_state": {
            ensure_string(name): {
                "knows": ensure_string_list(details.get("knows")),
                "suspects": ensure_string_list(details.get("suspects")),
                "hides": ensure_string_list(details.get("hides")),
                "misreads": ensure_string_list(details.get("misreads")),
                "self_story": ensure_string(details.get("self_story")),
            }
            for name, details in knowledge_state.items()
            if ensure_string(name) and isinstance(details, dict)
        },
        "minor_character_memory": {
            ensure_string(name): {
                "last_seen": ensure_int(details.get("last_seen"), default=chapter_num),
                "remembers": ensure_string_list(details.get("remembers")),
            }
            for name, details in minor_memory.items()
            if ensure_string(name) and isinstance(details, dict)
        },
        "active_pressures": active_pressures,
    }


def blank_character_state() -> dict[str, object]:
    return {"knows": [], "suspects": [], "hides": [], "misreads": [], "self_story": ""}


def clone_knowledge_state(knowledge_state: dict[str, object]) -> dict[str, dict[str, object]]:
    cloned: dict[str, dict[str, object]] = {}
    for name, details in knowledge_state.items():
        if not isinstance(details, dict):
            continue
        cloned[name] = {
            "knows": ensure_string_list(details.get("knows")),
            "suspects": ensure_string_list(details.get("suspects")),
            "hides": ensure_string_list(details.get("hides")),
            "misreads": ensure_string_list(details.get("misreads")),
            "self_story": ensure_string(details.get("self_story")),
        }
    return cloned


def clone_minor_character_memory(minor_memory: dict[str, object], chapter_num: int) -> dict[str, dict[str, object]]:
    cloned: dict[str, dict[str, object]] = {}
    for name, details in minor_memory.items():
        if not isinstance(details, dict):
            continue
        cloned[name] = {
            "last_seen": ensure_int(details.get("last_seen"), default=chapter_num),
            "remembers": ensure_string_list(details.get("remembers")),
        }
    return cloned


def prose_sentences(chapter_text: str) -> list[str]:
    cleaned_lines = []
    for raw_line in chapter_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        cleaned_lines.append(line)
    if not cleaned_lines:
        return []
    collapsed = re.sub(r"\s+", " ", " ".join(cleaned_lines)).strip()
    return [sentence.strip(" \"'") for sentence in PROSE_SENTENCE_RE.split(collapsed) if sentence.strip()]


def name_variants(name: str) -> list[str]:
    normalized = ensure_string(name)
    if not normalized:
        return []
    parts = normalized.split()
    if len(parts) == 1:
        return [normalized]
    return [normalized, parts[0]]


def count_name_mentions(text: str, name: str) -> int:
    counts = [
        len(re.findall(rf"\b{re.escape(variant)}\b", text))
        for variant in name_variants(name)
        if variant
    ]
    return max(counts, default=0)


def significant_words(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z']+", ensure_string(text).lower())
    return {word for word in words if len(word) >= 4 and word not in TOKEN_STOPWORDS}


def contains_marker(text: str, markers: tuple[str, ...] | set[str]) -> bool:
    lowered = text.lower()
    return any(re.search(rf"\b{re.escape(marker)}\b", lowered) for marker in markers)


def extract_clause_from_sentence(sentence: str, markers: tuple[str, ...]) -> str:
    lowered = sentence.lower()
    best_match = None
    for marker in markers:
        match = re.search(rf"\b{re.escape(marker)}\b", lowered)
        if match and (best_match is None or match.start() < best_match.start()):
            best_match = match
    if best_match is None:
        return ""
    clause = sentence[best_match.end() :].strip(" ,.;:-")
    clause = re.sub(r"^(that|if|whether)\s+", "", clause, flags=re.IGNORECASE)
    return sanitize_note(clause or sentence)


def pressure_excerpt(sentence: str) -> str:
    lowered = sentence.lower()
    for marker in PRESSURE_EXCERPT_MARKERS:
        match = re.search(rf"\b{re.escape(marker)}\b", lowered)
        if match:
            excerpt = sentence[match.start() :].strip(" ,.;:-")
            return sanitize_note(excerpt or sentence)
    return sanitize_note(sentence)


def resolve_sentence_subject(
    sentence: str,
    known_names: list[str],
    previous_subject: str,
    focus: str,
) -> str:
    leading_match = re.match(r'^\W*"?(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', sentence)
    if leading_match:
        leading = ensure_string(leading_match.group("name"))
        for name in known_names:
            if leading == name or leading == name.split()[0]:
                return name

    positions = []
    for name in known_names:
        for variant in name_variants(name):
            match = re.search(rf"\b{re.escape(variant)}\b", sentence)
            if match:
                positions.append((match.start(), name))
                break
    if positions:
        positions.sort(key=lambda item: (item[0], item[1]))
        return positions[0][1]

    if re.match(r'^\W*"?(He|She|They|I)\b', sentence):
        return previous_subject or focus
    return ""


def extract_named_entities(sentence: str) -> list[str]:
    entities = []
    seen = set()
    for match in PROSE_NAME_RE.finditer(sentence):
        candidate = ensure_string(match.group(0))
        tokens = candidate.split()
        if not tokens:
            continue
        first = tokens[0]
        if len(tokens) == 1 and first in PROSE_NAME_STOPWORDS:
            continue
        if len(tokens) > 1 and first in PROSE_NAME_STOPWORDS and first not in ALLOWED_NAME_TITLES:
            continue
        lowered = candidate.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        entities.append(candidate)
    return entities


def extract_prose_story_signals(
    chapter_text: str,
    focus: str,
    character_engine: dict[str, object],
    thread_window: list[dict[str, object]],
) -> dict[str, object]:
    sentences = prose_sentences(chapter_text)
    if not sentences:
        return {
            "knowledge_state": {},
            "minor_character_memory": {},
            "active_pressures": [],
            "institutional_motion": [],
            "offstage_consequences": [],
        }

    known_names = sorted({ensure_string(name) for name in character_engine.keys() if ensure_string(name)})
    if focus and focus != "POV":
        known_names = sorted(set(known_names) | {focus})

    knowledge_state: dict[str, dict[str, object]] = {}
    minor_character_memory: dict[str, dict[str, object]] = {}
    active_pressures: list[str] = []
    institutional_motion: list[str] = []
    offstage_consequences: list[str] = []
    previous_subject = focus
    prose_words = significant_words(" ".join(sentences))
    known_names_lower = {name.lower() for name in known_names}

    for sentence in sentences:
        subject = resolve_sentence_subject(sentence, known_names, previous_subject, focus)
        if subject:
            previous_subject = subject
            state = knowledge_state.setdefault(subject, blank_character_state())
            knows = extract_clause_from_sentence(sentence, KNOWLEDGE_MARKERS)
            if knows:
                state["knows"].append(knows)
            suspects = extract_clause_from_sentence(sentence, SUSPECT_MARKERS)
            if suspects:
                state["suspects"].append(suspects)
            misreads = extract_clause_from_sentence(sentence, MISREAD_MARKERS)
            if misreads:
                state["misreads"].append(misreads)
            hides = extract_clause_from_sentence(sentence, HIDE_MARKERS)
            if hides:
                state["hides"].append(hides)
            self_story = extract_clause_from_sentence(sentence, SELF_STORY_MARKERS)
            if self_story:
                state["self_story"] = self_story

        if contains_marker(sentence, PRESSURE_MARKERS):
            excerpt = pressure_excerpt(sentence)
            if excerpt:
                active_pressures.append(excerpt)
        if contains_marker(sentence, INSTITUTIONAL_MARKERS):
            institutional_motion.append(sanitize_note(sentence))
        if contains_marker(sentence, CONSEQUENCE_MARKERS):
            offstage_consequences.append(sanitize_note(sentence))

        for name in extract_named_entities(sentence):
            if focus and name.lower() == focus.lower():
                continue
            if name.lower() in known_names_lower:
                continue
            memory = minor_character_memory.setdefault(name, {"last_seen": 0, "remembers": []})
            memory["remembers"].append(sanitize_note(sentence))

    for thread in thread_window:
        if ensure_string(thread.get("type")) != "pressure":
            continue
        description = sanitize_note(thread.get("description", ""))
        words = significant_words(description)
        if not description or not words:
            continue
        threshold = 1 if len(words) <= 2 else 2
        if len(words & prose_words) >= threshold:
            active_pressures.append(description)
            institutional_motion.append(description)

    if not offstage_consequences and sentences:
        offstage_consequences.append(sanitize_note(sentences[-1]))

    for details in knowledge_state.values():
        details["knows"] = dedupe_strings(details["knows"])[-4:]
        details["suspects"] = dedupe_strings(details["suspects"])[-4:]
        details["hides"] = dedupe_strings(details["hides"])[-4:]
        details["misreads"] = dedupe_strings(details["misreads"])[-4:]
        details["self_story"] = sanitize_note(details.get("self_story", ""))

    for details in minor_character_memory.values():
        details["remembers"] = dedupe_strings(details["remembers"])[:2]

    return {
        "knowledge_state": knowledge_state,
        "minor_character_memory": minor_character_memory,
        "active_pressures": dedupe_strings(active_pressures)[-6:],
        "institutional_motion": dedupe_strings(institutional_motion)[-6:],
        "offstage_consequences": dedupe_strings(offstage_consequences)[-6:],
    }


def infer_focus_character(chapter_card: dict[str, object], character_engine: dict[str, object], chapter_text: str = "") -> str:
    explicit_focus = ensure_string(
        chapter_card.get("focus_character") or chapter_card.get("pov_character") or chapter_card.get("focus")
    )
    if explicit_focus:
        return explicit_focus

    names = sorted({ensure_string(name) for name in character_engine.keys() if ensure_string(name)})
    if not names:
        return "POV"
    if len(names) == 1:
        return names[0]

    focus_source = " ".join(
        ensure_string(chapter_card.get(field))
        for field in ("title", "goal", "pressure", "reversal", "aftermath", "allowed_ambiguity")
    )
    if chapter_text:
        focus_source = f"{focus_source} {chapter_text[:4000]}"
    counts = {name: count_name_mentions(focus_source, name) for name in names}
    top_count = max(counts.values())
    if top_count > 0:
        ranked = sorted(name for name, count in counts.items() if count == top_count)
        return ranked[0]
    return names[0]


def build_story_state(
    chapter_num: int,
    chapter_card: dict[str, object],
    previous_state: dict[str, object] | None,
    chapter_text: str,
    thread_window: list[dict[str, object]],
    character_engine: dict[str, object],
) -> dict[str, object]:
    previous = normalize_story_state(previous_state or {}, max(chapter_num - 1, 0))
    focus = infer_focus_character(chapter_card, character_engine, chapter_text)
    pressure = sanitize_note(chapter_card.get("pressure", ""))
    aftermath = sanitize_note(chapter_card.get("aftermath", ""))
    irreversible = sanitize_note(chapter_card.get("irreversible_change", ""))
    reversal = sanitize_note(chapter_card.get("reversal", ""))
    ambiguity = sanitize_note(chapter_card.get("allowed_ambiguity", ""))
    prose_signals = extract_prose_story_signals(chapter_text, focus, character_engine, thread_window)

    world_clock = previous["world_clock"]
    institutional_motion = list(world_clock["institutional_motion"])
    if prose_signals["institutional_motion"]:
        institutional_motion.extend(prose_signals["institutional_motion"])
    elif pressure:
        institutional_motion.append(pressure)
    offstage_consequences = list(world_clock["offstage_consequences"])
    if prose_signals["offstage_consequences"]:
        offstage_consequences.extend(prose_signals["offstage_consequences"])
    elif irreversible:
        offstage_consequences.append(irreversible)

    knowledge_state = clone_knowledge_state(previous["knowledge_state"])
    for name, signals in prose_signals["knowledge_state"].items():
        state = knowledge_state.get(name, blank_character_state())
        state["knows"] = dedupe_strings(state["knows"] + ensure_string_list(signals.get("knows")))
        state["suspects"] = dedupe_strings(state["suspects"] + ensure_string_list(signals.get("suspects")))
        state["hides"] = dedupe_strings(state["hides"] + ensure_string_list(signals.get("hides")))
        state["misreads"] = dedupe_strings(state["misreads"] + ensure_string_list(signals.get("misreads")))
        if ensure_string(signals.get("self_story")):
            state["self_story"] = ensure_string(signals["self_story"])
        knowledge_state[name] = state

    focus_state = knowledge_state.get(
        focus,
        blank_character_state(),
    )
    if reversal and not focus_state["knows"]:
        focus_state["knows"] = dedupe_strings(focus_state["knows"] + [reversal])
    if ambiguity and not focus_state["misreads"]:
        focus_state["misreads"] = dedupe_strings(focus_state["misreads"] + [ambiguity])
    if aftermath and not ensure_string(focus_state.get("self_story")):
        focus_state["self_story"] = aftermath
    knowledge_state[focus] = focus_state

    active_pressures = list(previous["active_pressures"])
    if prose_signals["active_pressures"]:
        active_pressures.extend(prose_signals["active_pressures"])
    elif pressure:
        active_pressures.append(pressure)

    minor_character_memory = clone_minor_character_memory(previous["minor_character_memory"], chapter_num)
    for name, details in prose_signals["minor_character_memory"].items():
        memory = minor_character_memory.get(name, {"last_seen": chapter_num, "remembers": []})
        memory["last_seen"] = chapter_num
        memory["remembers"] = dedupe_strings(memory["remembers"] + ensure_string_list(details.get("remembers")))
        minor_character_memory[name] = memory

    return normalize_story_state(
        {
            "chapter": chapter_num,
            "world_clock": {
                "weather": world_clock["weather"],
                "institutional_motion": institutional_motion[-6:],
                "district_rumours": world_clock["district_rumours"],
                "market_changes": world_clock["market_changes"],
                "offstage_consequences": offstage_consequences[-6:],
            },
            "knowledge_state": knowledge_state,
            "minor_character_memory": minor_character_memory,
            "active_pressures": dedupe_strings(active_pressures),
        },
        chapter_num,
    )


def dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for value in values:
        text = ensure_string(value)
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def build_scene_options(
    chapter_num: int,
    chapter_card: dict[str, object],
    previous_state: dict[str, object] | None,
    thread_window: list[dict[str, object]],
    variants: int,
) -> list[dict[str, object]]:
    previous = normalize_story_state(previous_state or {}, max(chapter_num - 1, 0))
    goal = sanitize_note(chapter_card.get("goal", "")) or f"Advance the pressure of Chapter {chapter_num}"
    pressure = sanitize_note(chapter_card.get("pressure", "")) or "Pressure is latent rather than explicit."
    reversal = sanitize_note(chapter_card.get("reversal", ""))
    aftermath = sanitize_note(chapter_card.get("aftermath", ""))
    ambiguity = sanitize_note(chapter_card.get("allowed_ambiguity", ""))
    irreversible = sanitize_note(chapter_card.get("irreversible_change", ""))
    active_pressures = previous.get("active_pressures", [])
    thread_hint = sanitize_note(thread_window[0]["description"]) if thread_window else ""

    templates = [
        {
            "social_imbalance": pressure or "The scene starts with one side having institutional leverage.",
            "wrong_inference": ambiguity or "The POV mistakes the stakes and responds too early.",
            "surprise_slot": reversal or irreversible or "The scene turns where the chapter card least expects it.",
            "residue": aftermath or "The chapter ends with more pressure than clarity.",
        },
        {
            "social_imbalance": thread_hint or "A secondary thread quietly tilts the room.",
            "wrong_inference": ambiguity or "The POV treats caution as hostility.",
            "surprise_slot": irreversible or reversal or "The irreversible change lands through action rather than explanation.",
            "residue": aftermath or "One relationship is less stable on exit.",
        },
        {
            "social_imbalance": active_pressures[0] if active_pressures else "Private need and public pressure pull in opposite directions.",
            "wrong_inference": ambiguity or "A character answers the wrong threat first.",
            "surprise_slot": reversal or "A line lands too late and changes what the scene means.",
            "residue": aftermath or "The cost is emotional rather than logistical.",
        },
        {
            "social_imbalance": pressure or "Someone is exposed to a room they cannot control.",
            "wrong_inference": ambiguity or "The narrator reads motive through the wrong frame.",
            "surprise_slot": thread_hint or reversal or "A background thread suddenly matters in-scene.",
            "residue": irreversible or aftermath or "The chapter closes on a changed relation to the problem.",
        },
    ]

    options = []
    count = max(2, min(4, variants))
    for index in range(count):
        template = templates[index]
        options.append(
            {
                "option": index + 1,
                "goal": goal,
                "pressure": pressure,
                "social_imbalance": template["social_imbalance"],
                "wrong_inference": template["wrong_inference"],
                "surprise_slot": template["surprise_slot"],
                "residue": template["residue"],
                "scene_type": ensure_string(chapter_card.get("scene_type")),
                "scene_method": ensure_string(chapter_card.get("scene_method")),
                "risk": ensure_string(chapter_card.get("risk")),
            }
        )
    return options


def scene_planner_model() -> str:
    return os.environ.get("AUTONOVEL_SCENE_PLANNER_MODEL") or os.environ.get(
        "AUTONOVEL_WRITER_MODEL",
        "claude-sonnet-4-6",
    )


def scene_planner_api_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def scene_planner_api_base() -> str:
    return os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")


def scene_planner_available() -> bool:
    return bool(scene_planner_api_key())


def build_scene_planner_prompt(
    chapter_num: int,
    chapter_card: dict[str, object],
    previous_state: dict[str, object] | None,
    thread_window: list[dict[str, object]],
    previous_prose: str,
    variants: int,
) -> str:
    normalized_previous = normalize_story_state(previous_state or {}, max(chapter_num - 1, 0))
    prose_tail = previous_prose[-1500:] if previous_prose else "(no accepted prose yet)"
    return f"""Create JSON scene options for Chapter {chapter_num}.

CURRENT CHAPTER CARD:
{json.dumps(chapter_card, indent=2)}

PREVIOUS STORY STATE:
{json.dumps(normalized_previous, indent=2)}

LOCAL THREAD WINDOW:
{render_thread_window(thread_window)}

PREVIOUS ACCEPTED PROSE TAIL:
{prose_tail}

Return valid JSON only as either:
- a top-level array of scene option objects, or
- an object with `scene_options`

Emit {max(2, min(4, variants))} scene options.

Each option must include:
- goal
- pressure
- social_imbalance
- wrong_inference
- surprise_slot
- residue

Rules:
- Ground every option in the current chapter card, prior state, local thread window, and previous prose tail.
- Keep options structurally distinct from one another.
- Let wrong inference and residue feel social, not merely informational.
- Preserve the chapter card's irreversible change pressure, but do not reduce the scene to obedient beat execution.
- Keep values concise and concrete.
- JSON only.
"""


def call_scene_planner(prompt: str, max_tokens: int = 2500) -> str:
    import httpx

    headers = {
        "x-api-key": scene_planner_api_key(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": scene_planner_model(),
        "max_tokens": max_tokens,
        "temperature": 0.6,
        "system": (
            "You generate scene options for a novel chapter. "
            "Return strict JSON only and keep each option sharply differentiated."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    response = httpx.post(
        f"{scene_planner_api_base()}/v1/messages",
        headers=headers,
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["content"][0]["text"]


def normalize_scene_option(
    raw_option: object,
    chapter_card: dict[str, object],
    fallback_option: dict[str, object],
    option_number: int,
) -> dict[str, object]:
    option = raw_option if isinstance(raw_option, dict) else {}
    goal = sanitize_note(option.get("goal", "")) or sanitize_note(chapter_card.get("goal", "")) or fallback_option["goal"]
    pressure = sanitize_note(option.get("pressure", "")) or sanitize_note(chapter_card.get("pressure", "")) or fallback_option["pressure"]
    social_imbalance = sanitize_note(option.get("social_imbalance", "")) or fallback_option["social_imbalance"]
    wrong_inference = sanitize_note(option.get("wrong_inference", "")) or fallback_option["wrong_inference"]
    surprise_slot = sanitize_note(option.get("surprise_slot", "")) or fallback_option["surprise_slot"]
    residue = sanitize_note(option.get("residue", "")) or fallback_option["residue"]
    return {
        "option": option_number,
        "goal": goal,
        "pressure": pressure,
        "social_imbalance": social_imbalance,
        "wrong_inference": wrong_inference,
        "surprise_slot": surprise_slot,
        "residue": residue,
        "scene_type": ensure_string(option.get("scene_type")) or fallback_option["scene_type"],
        "scene_method": ensure_string(option.get("scene_method")) or fallback_option["scene_method"],
        "risk": ensure_string(option.get("risk")) or fallback_option["risk"],
    }


def normalize_scene_options(
    payload: object,
    chapter_card: dict[str, object],
    variants: int,
    fallback_options: list[dict[str, object]],
) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        raw_options = payload.get("scene_options") or payload.get("options") or payload.get("variants") or []
    elif isinstance(payload, list):
        raw_options = payload
    else:
        raw_options = []

    target_count = max(2, min(4, variants))
    normalized: list[dict[str, object]] = []
    seen_signatures: set[tuple[str, ...]] = set()
    for index, raw_option in enumerate(raw_options[:target_count]):
        fallback_option = fallback_options[min(index, len(fallback_options) - 1)]
        option = normalize_scene_option(raw_option, chapter_card, fallback_option, index + 1)
        signature = tuple(option[field] for field in SCENE_OPTION_FIELDS)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        normalized.append(option)

    fallback_index = 0
    while len(normalized) < target_count and fallback_index < len(fallback_options):
        fallback_option = dict(fallback_options[fallback_index])
        fallback_option["option"] = len(normalized) + 1
        signature = tuple(ensure_string(fallback_option.get(field)) for field in SCENE_OPTION_FIELDS)
        fallback_index += 1
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        normalized.append(fallback_option)

    return normalized[:target_count]


def generate_scene_options(
    chapter_num: int,
    chapter_card: dict[str, object],
    previous_state: dict[str, object] | None,
    thread_window: list[dict[str, object]],
    variants: int,
    previous_prose: str = "",
    mode: str = "auto",
    planner_call=None,
) -> list[dict[str, object]]:
    fallback_options = build_scene_options(chapter_num, chapter_card, previous_state, thread_window, variants)
    if mode == "deterministic":
        return fallback_options

    use_model = bool(planner_call) or scene_planner_available()
    if mode == "model" and planner_call is None and not scene_planner_available():
        use_model = False
    if not use_model:
        return fallback_options

    prompt = build_scene_planner_prompt(
        chapter_num,
        chapter_card,
        previous_state,
        thread_window,
        previous_prose,
        variants,
    )
    call = planner_call or call_scene_planner
    try:
        payload = extract_json_object(call(prompt))
    except Exception:
        return fallback_options
    return normalize_scene_options(payload, chapter_card, variants, fallback_options)


def render_scene_options(options: list[dict[str, object]]) -> str:
    if not options:
        return "(no scene options generated)"
    lines = []
    for option in options:
        lines.append(f"### Option {option['option']}")
        for field in SCENE_OPTION_FIELDS:
            lines.append(f"- {field}: {ensure_string(option.get(field))}")
        lines.append(f"- scene_type: {ensure_string(option.get('scene_type'))}")
        lines.append(f"- scene_method: {ensure_string(option.get('scene_method'))}")
        lines.append(f"- risk: {ensure_string(option.get('risk'))}")
        lines.append("")
    return "\n".join(lines).strip()


def story_state_path(base_dir: Path, chapter_num: int) -> Path:
    return base_dir / "state" / "story_state" / f"ch_{chapter_num:02d}.json"


def scene_options_path(base_dir: Path, chapter_num: int) -> Path:
    return base_dir / "scene_options" / f"ch_{chapter_num:02d}.json"


def detect_new_planning_mode(base_dir: Path, chapter_num: int) -> bool:
    required = [
        base_dir / "perspective.md",
        base_dir / "voice.md",
        base_dir / "character_engine.json",
        base_dir / "chapter_cards.md",
        base_dir / "thread_registry.json",
        base_dir / "world.md",
        base_dir / "canon.md",
        scene_options_path(base_dir, chapter_num),
    ]
    if chapter_num > 1:
        required.append(story_state_path(base_dir, chapter_num - 1))
    if not all(path.exists() for path in required):
        return False
    chapter_card = load_chapter_card(base_dir, chapter_num)
    return bool(chapter_card.get("number"))


def extract_chapter_outline(outline_text: str, chapter_num: int) -> str:
    pattern = rf"### Ch {chapter_num}:.*?(?=### Ch {chapter_num + 1}:|## Foreshadowing|$)"
    match = re.search(pattern, outline_text, re.DOTALL)
    return match.group(0).strip() if match else "(not found)"


def extract_next_chapter_outline(outline_text: str, chapter_num: int) -> str:
    next_entry = extract_chapter_outline(outline_text, chapter_num + 1)
    if next_entry == "(not found)":
        return "(final chapter)"
    return "\n".join(next_entry.splitlines()[:10])


def previous_chapter_tail(base_dir: Path, chapter_num: int) -> str:
    prev_path = base_dir / "chapters" / f"ch_{chapter_num - 1:02d}.md"
    prev_text = read_text_if_exists(prev_path)
    if not prev_text:
        return "(first chapter -- no previous)"
    return prev_text[-2000:] if len(prev_text) > 2000 else prev_text


def load_character_engine(base_dir: Path) -> dict[str, object]:
    payload = read_json_if_exists(base_dir / "character_engine.json", {})
    return payload if isinstance(payload, dict) else {}


def build_legacy_prompt(base_dir: Path, chapter_num: int) -> str:
    voice = read_text_if_exists(base_dir / "voice.md")
    world = read_text_if_exists(base_dir / "world.md")
    characters = read_text_if_exists(base_dir / "characters.md")
    outline = read_text_if_exists(base_dir / "outline.md")

    chapter_outline = extract_chapter_outline(outline, chapter_num)
    next_chapter = extract_next_chapter_outline(outline, chapter_num)
    prev_tail = previous_chapter_tail(base_dir, chapter_num)

    return f"""Write Chapter {chapter_num} of "The Second Son of the House of Bells."

VOICE DEFINITION (follow this exactly):
{voice}

THIS CHAPTER'S OUTLINE (hit every beat):
{chapter_outline}

NEXT CHAPTER'S OUTLINE (for continuity -- end this chapter so it flows into the next):
{next_chapter}

PREVIOUS CHAPTER'S ENDING (continue from here):
{prev_tail}

WORLD BIBLE (reference for worldbuilding details):
{world}

CHARACTER REGISTRY (reference for speech patterns and behavior):
{characters}

WRITING INSTRUCTIONS:
1. Write the COMPLETE chapter. Target ~3,200 words. Do not truncate or summarize.
2. Third-person limited, past tense, locked to Cass's POV.
3. Hit ALL numbered beats from the outline in order.
4. Plant ALL foreshadowing elements listed under "Plants."
5. Show sensory detail: what Cass hears, smells, feels physically.
6. The under-note causes specific physical pain (needle behind left eye, not vague discomfort).
7. Dialogue follows the speech patterns defined in characters.md.
8. No banned words from voice.md Part 1 guardrails.
9. No AI fiction tells: no "a sense of," no "couldn't help but feel," no "eyes widened."
10. Vary sentence length. Short sentences for impact. Longer ones to build.
11. Metaphors from Cass's experience: sound, bronze, craft, the body's response to pitch.
12. Trust the reader. Don't explain what scenes mean. Let them land.
13. Start the chapter in scene, not with exposition. End on a moment, not a summary.

PATTERNS TO AVOID (these have been flagged in previous chapters):
14. NO triadic sensory lists. Never "X. Y. Z." or "X and Y and Z" as three
    separate items in a row. Combine two, cut one, or restructure.
15. NO "He did not [verb]" more than once per chapter. Convert negatives
    to active alternatives or just cut them.
16. NO "He thought about [X]" constructions. Replace with: the thought
    itself as a fragment, a physical action, or dialogue.
17. NO "the way [X] did [Y]" as a simile connector more than twice per
    chapter. Use different simile structures or cut the comparison.
18. NO over-explaining after showing. If a scene demonstrates something,
    do not have the narrator restate it. Trust the scene.
19. NO section breaks (---) as rhythm crutches. Only use for genuine
    time/location jumps. Max 2 per chapter.
20. VARY paragraph length deliberately. Never more than 3 consecutive
    paragraphs of similar length. Include at least one 1-2 sentence
    paragraph and one 6+ sentence paragraph.
21. END the chapter differently from previous chapters. Do NOT end with
    Cass outside listening to his father work. Find the ending that
    belongs to THIS chapter specifically.
22. INCLUDE at least one moment that surprises -- a character saying
    the wrong thing, an emotional beat arriving early or late, a detail
    that doesn't fit the expected pattern. Predictable excellence is
    still predictable.
23. FAVOR scene over summary. At least 70% of the chapter should be
    in-scene (moment by moment, with dialogue and action) rather than
    summary (narrator compressing time).
24. DIALOGUE should sound like speech, not prose. Characters should
    occasionally stumble, interrupt, trail off, or say something
    slightly wrong. A 14-year-old does not speak in polished epigrams.

Write the chapter now. Full text, beginning to end.
"""


def build_new_mode_prompt(base_dir: Path, chapter_num: int) -> str:
    perspective_text = read_text_if_exists(base_dir / "perspective.md")
    perspective = parse_perspective_markdown(perspective_text)
    voice = read_text_if_exists(base_dir / "voice.md")
    world = read_text_if_exists(base_dir / "world.md")
    canon = read_text_if_exists(base_dir / "canon.md")
    character_engine = read_text_if_exists(base_dir / "character_engine.json")
    chapter_card = load_chapter_card(base_dir, chapter_num)
    scene_options = read_json_if_exists(scene_options_path(base_dir, chapter_num), [])
    prior_state = read_json_if_exists(story_state_path(base_dir, chapter_num - 1), {}) if chapter_num > 1 else {}
    thread_window = local_thread_window(load_thread_registry(base_dir), chapter_num)

    blind_spots = ", ".join(ensure_string_list(perspective.get("blind_spots"))) or "(none recorded)"
    humor = ", ".join(ensure_string_list(perspective.get("sense_of_humor"))) or "(none recorded)"
    unbearable = ", ".join(ensure_string_list(perspective.get("the_unbearable"))) or "(none recorded)"
    obsessions = ", ".join(ensure_string_list(perspective.get("obsessions"))) or "(none recorded)"
    formal_signatures = ", ".join(ensure_string_list(perspective.get("formal_signatures"))) or "(none recorded)"

    return f"""Write Chapter {chapter_num} using the new planning mode.

PERSPECTIVE (hard constraint):
{perspective_text}

VOICE DEFINITION:
{voice}

CHARACTER ENGINE:
{character_engine}

PREVIOUS STORY STATE:
{json.dumps(normalize_story_state(prior_state, max(chapter_num - 1, 0)), indent=2)}

CURRENT CHAPTER CARD:
{json.dumps(chapter_card, indent=2)}

SCENE OPTIONS (choose the most alive path):
{render_scene_options(scene_options)}

LOCAL THREAD WINDOW:
{render_thread_window(thread_window)}

WORLD BIBLE:
{world}

CANON:
{canon}

NEW-MODE WRITING INSTRUCTIONS:
- This chapter is perceived through perspective.md.
- The narrator notices what this consciousness notices: {obsessions}.
- Blind spots are active constraints: {blind_spots}. If blind-spot material appears, register it late, partially, or through reactions rather than omniscient exposition.
- Humor is part of the mind: {humor}. If the scene affords incongruity, let the comic register surface once without forcing a joke.
- If the chapter enters the unbearable, enact the strain in prose rather than merely describing it: {unbearable}.
- Formal signatures should visibly shape the prose when relevant: {formal_signatures}.
- Preserve the chapter card's irreversible change: {ensure_string(chapter_card.get("irreversible_change")) or '(none recorded)'}.
- Choose the most alive path from scene_options; do not obediently execute every possible beat.
- You may defer, migrate, or drop non-plot threads unless they are marked required in the local thread window.
- Characters must think and speak within their cognitive ceiling. Do not let every character reason with maximum model clarity.
- Dialogue should emerge from local desire, concealment, pressure, and misreading, not from the chapter's thematic argument.
- Keep third-person limited, past tense, full chapter length, strong scene presence, and sensory specificity.
- Trust the reader. Do not smooth away contradiction, embarrassment, or wrong inference just to keep the chapter tidy.

Write the chapter now. Full text, beginning to end.
"""


def build_system_prompt(mode: str) -> str:
    if mode == "new":
        return (
            "You are a literary fiction writer drafting a fantasy novel chapter. "
            "You write in third-person limited past tense, locked to one POV character. "
            "The governing perspective is a hard constraint. This narrator has active obsessions and active blind spots. "
            "Do not compensate for blind spots by becoming omniscient elsewhere. "
            "If the material becomes unbearable, the prose must enact that strain rather than merely describe it. "
            "Characters must think and speak within their cognitive ceiling. "
            "You follow the voice definition exactly, preserve productive roughness, and write the FULL chapter."
        )
    return (
        "You are a literary fiction writer drafting a fantasy novel chapter. "
        "You write in third-person limited past tense, locked to one POV character. "
        "You follow the voice definition exactly. You hit every beat in the outline. "
        "You never use words from the banned list. You show, never tell emotions. "
        "Your prose is specific, sensory, grounded. Metaphors come from the character's "
        "experience. You vary sentence length. You trust the reader. "
        "You write the FULL chapter -- do not truncate, summarize, or skip ahead."
    )


def resolve_mode(base_dir: Path, chapter_num: int, requested_mode: str) -> str:
    if requested_mode in {"legacy", "new"}:
        return requested_mode
    return "new" if detect_new_planning_mode(base_dir, chapter_num) else "legacy"
