#!/usr/bin/env python3
"""Pure helpers for PR2 planning-split tooling."""

from __future__ import annotations

import json
import re
from pathlib import Path

CHAPTER_CARD_FIELDS = (
    "focus_character",
    "goal",
    "pressure",
    "reversal",
    "aftermath",
    "irreversible_change",
    "allowed_ambiguity",
    "time_span",
    "scene_density",
    "scene_type",
    "scene_method",
    "risk",
)
CHAPTER_CARD_FIELD_ALIASES = {
    "focus": "focus_character",
    "pov_character": "focus_character",
}

THREAD_TYPES = ("plot", "pressure", "echo", "texture")
SCENE_DENSITIES = {"high", "medium", "low"}
SCENE_TYPES = {
    "investigation",
    "confrontation",
    "revelation",
    "quiet",
    "crisis",
    "preparation",
    "aftermath",
    "digression",
}
SCENE_METHODS = {
    "close_interiority",
    "observed_action",
    "dialogue_driven",
    "environmental",
    "epistolary",
    "panoramic",
    "fragmented",
}
RISK_VALUES = {"none", "formal", "pov", "document", "temporal"}
DEFAULT_SCENE_DENSITY = "medium"
DEFAULT_SCENE_TYPE = "investigation"
DEFAULT_SCENE_METHOD = "close_interiority"
DEFAULT_RISK = "none"
DEFAULT_ARC_TITLE = "Arc Outline"
DEFAULT_LEGACY_CHAPTER_COUNT = 24

_CHAPTER_BLOCK_RE = re.compile(
    r"^###\s*Ch(?:apter)?\s*(\d+)\s*:?\s*([^\n]*?)\s*$\n?"
    r"(.*?)(?=^###\s*Ch(?:apter)?\s*\d+\s*:?\s*[^\n]*\s*$|^##\s*Act\b|^##\s*Foreshadowing|\Z)",
    re.MULTILINE | re.DOTALL,
)
_CHAPTER_CARD_HEADING_RE = re.compile(r"^##\s*Ch(?:apter)?\s*(\d+)\s*:?\s*(.*)$")
_ACT_HEADING_RE = re.compile(r"^##\s*(Act[^:\n]*:?)(.*)$", re.MULTILINE)
_THREAD_ROW_RE = re.compile(r"^\|(.*)\|$", re.MULTILINE)


def ensure_string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def ensure_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return default


def ensure_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def ensure_int_list(value: object) -> list[int]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = re.findall(r"\d+", ensure_string(value))
    ints = [ensure_int(item, default=0) for item in raw_items]
    return [item for item in ints if item > 0]


def ensure_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    else:
        items = list(value)
    return [item for item in (ensure_string(raw) for raw in items) if item]


def safe_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", ensure_string(text).lower()).strip("_")
    return slug or "thread"


def extract_json_object(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    start_candidates = [idx for idx in (text.find("{"), text.find("[")) if idx >= 0]
    if not start_candidates:
        raise ValueError("No JSON object found in response")
    start = min(start_candidates)
    try:
        return json.loads(text[start:], strict=False)
    except json.JSONDecodeError:
        opening = text[start]
        closing = "}" if opening == "{" else "]"
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(text)):
            char = text[idx]
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
                    return json.loads(text[start : idx + 1], strict=False)
        raise


def normalize_arc_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        payload = {}
    acts = []
    for raw_act in payload.get("acts", []):
        act = raw_act if isinstance(raw_act, dict) else {}
        acts.append(
            {
                "name": ensure_string(act.get("name")) or "Act",
                "irreversible_turns": ensure_string_list(
                    act.get("irreversible_turns") or act.get("major_turns")
                ),
            }
        )
    return {
        "title": ensure_string(payload.get("title")) or DEFAULT_ARC_TITLE,
        "acts": acts,
        "major_reveals": ensure_string_list(payload.get("major_reveals")),
        "pressure_escalations": ensure_string_list(payload.get("pressure_escalations")),
        "candidate_risk_chapters": ensure_int_list(payload.get("candidate_risk_chapters")),
    }


def normalize_chapter_cards(payload: object) -> list[dict[str, object]]:
    raw_cards = payload.get("chapters", payload) if isinstance(payload, dict) else payload
    cards = []
    if not isinstance(raw_cards, list):
        raw_cards = []
    for index, raw_card in enumerate(raw_cards, start=1):
        card = raw_card if isinstance(raw_card, dict) else {}
        number = ensure_int(card.get("number") or card.get("chapter"), default=index)
        focus_character = ensure_string(
            card.get("focus_character") or card.get("pov_character") or card.get("focus")
        )
        scene_density = ensure_string(card.get("scene_density")).lower() or DEFAULT_SCENE_DENSITY
        if scene_density not in SCENE_DENSITIES:
            scene_density = DEFAULT_SCENE_DENSITY
        scene_type = ensure_string(card.get("scene_type")).lower() or DEFAULT_SCENE_TYPE
        if scene_type not in SCENE_TYPES:
            scene_type = DEFAULT_SCENE_TYPE
        scene_method = ensure_string(card.get("scene_method")).lower() or DEFAULT_SCENE_METHOD
        if scene_method not in SCENE_METHODS:
            scene_method = DEFAULT_SCENE_METHOD
        risk = ensure_string(card.get("risk")).lower() or DEFAULT_RISK
        if risk not in RISK_VALUES:
            risk = DEFAULT_RISK
        cards.append(
            {
                "number": number,
                "title": ensure_string(card.get("title")) or f"Chapter {number}",
                "focus_character": focus_character,
                "goal": ensure_string(card.get("goal")),
                "pressure": ensure_string(card.get("pressure")),
                "reversal": ensure_string(card.get("reversal")),
                "aftermath": ensure_string(card.get("aftermath")),
                "irreversible_change": ensure_string(card.get("irreversible_change")),
                "allowed_ambiguity": ensure_string(card.get("allowed_ambiguity")),
                "time_span": ensure_string(card.get("time_span")),
                "scene_density": scene_density,
                "scene_type": scene_type,
                "scene_method": scene_method,
                "risk": risk,
            }
        )
    return sorted(cards, key=lambda card: card["number"])


def normalize_thread_registry(payload: object) -> list[dict[str, object]]:
    raw_threads = payload.get("threads", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_threads, list):
        raw_threads = []
    threads = []
    for raw_thread in raw_threads:
        thread = raw_thread if isinstance(raw_thread, dict) else {}
        description = ensure_string(thread.get("description") or thread.get("thread"))
        first_seen = ensure_int(thread.get("first_seen") or thread.get("planted"), default=0)
        thread_type = ensure_string(thread.get("type")).lower() or "plot"
        if thread_type not in THREAD_TYPES:
            thread_type = "plot"
        threads.append(
            {
                "id": ensure_string(thread.get("id")) or safe_slug(description),
                "type": thread_type,
                "description": description,
                "first_seen": first_seen,
                "planted": first_seen,
                "reinforced": ensure_int_list(thread.get("reinforced")),
                "payoff": ensure_int(thread.get("payoff"), default=0),
                "required": ensure_bool(thread.get("required"), default=thread_type == "plot"),
                "notes": ensure_string(thread.get("notes")),
            }
        )
    return threads


def render_arc_outline(arc: dict[str, object]) -> str:
    lines = ["# Arc Outline", ""]
    title = ensure_string(arc.get("title"))
    if title:
        lines.append(f"**Working title:** {title}")
        lines.append("")

    lines.append("## Irreversible Turns")
    acts = arc.get("acts", [])
    if acts:
        for act in acts:
            lines.append(f"### {act['name']}")
            turns = ensure_string_list(act.get("irreversible_turns"))
            if turns:
                lines.extend(f"- {turn}" for turn in turns)
            else:
                lines.append("<!-- No irreversible turns generated yet -->")
            lines.append("")
    else:
        lines.append("<!-- Generated during PR2. Populate with irreversible turns only. -->")
        lines.append("")

    lines.append("## Major Reveals")
    reveals = ensure_string_list(arc.get("major_reveals"))
    if reveals:
        lines.extend(f"- {reveal}" for reveal in reveals)
    else:
        lines.append("<!-- None generated yet -->")
    lines.append("")

    lines.append("## Pressure Escalations")
    escalations = ensure_string_list(arc.get("pressure_escalations"))
    if escalations:
        lines.extend(f"- {item}" for item in escalations)
    else:
        lines.append("<!-- None generated yet -->")
    lines.append("")

    lines.append("## Candidate Risk Chapters")
    risks = ensure_int_list(arc.get("candidate_risk_chapters"))
    if risks:
        lines.append(", ".join(f"Ch {number}" for number in risks))
    else:
        lines.append("<!-- None generated yet -->")
    lines.append("")

    return "\n".join(lines)


def render_chapter_cards(cards: list[dict[str, object]]) -> str:
    lines = ["# Chapter Cards", ""]
    if not cards:
        lines.append("<!-- Generated during PR2. One chapter card per chapter. -->")
        lines.append("")
        lines.append("## Ch 01")
        for field in CHAPTER_CARD_FIELDS:
            lines.append(f"{field}:")
        lines.append("")
        return "\n".join(lines)

    for card in cards:
        lines.append(f"## Ch {card['number']:02d}: {card['title']}")
        for field in CHAPTER_CARD_FIELDS:
            lines.append(f"{field}: {ensure_string(card.get(field))}")
        lines.append("")
    return "\n".join(lines)


def render_legacy_outline(title: str, arc: dict[str, object], cards: list[dict[str, object]], threads: list[dict[str, object]]) -> str:
    clean_title = ensure_string(title) or ensure_string(arc.get("title")) or "Outline"
    lines = [f"# {clean_title}", ""]

    lines.append("## Structure")
    acts = arc.get("acts", [])
    if acts:
        for act in acts:
            heading = act["name"]
            turns = ensure_string_list(act.get("irreversible_turns"))
            summary = "; ".join(turns[:2])
            if summary:
                lines.append(f"- **{heading}**: {summary}")
            else:
                lines.append(f"- **{heading}**")
    else:
        lines.append("<!-- Total chapters, act breakdown, target word count -->")
    lines.append("")

    lines.append("## Themes")
    reveals = ensure_string_list(arc.get("major_reveals"))
    if reveals:
        lines.extend(f"- {item}" for item in reveals[:5])
    else:
        lines.append("<!-- Core themes the story explores -->")
    lines.append("")

    if cards:
        current_act = None
        for card in cards:
            act_name = act_name_for_chapter(card["number"], acts)
            if act_name != current_act:
                current_act = act_name
                lines.append(f"## {act_name}")
                lines.append("")
            lines.append(f"### Ch {card['number']}: {card['title']}")
            lines.append(f"- **Goal:** {card['goal']}")
            lines.append(f"- **Pressure:** {card['pressure']}")
            lines.append(f"- **Reversal:** {card['reversal']}")
            lines.append(f"- **Aftermath:** {card['aftermath']}")
            lines.append(f"- **Irreversible change:** {card['irreversible_change']}")
            lines.append(f"- **Allowed ambiguity:** {card['allowed_ambiguity']}")
            lines.append(f"- **Time span:** {card['time_span']}")
            lines.append(f"- **Scene density:** {card['scene_density']}")
            lines.append(f"- **Scene type:** {card['scene_type']}")
            lines.append(f"- **Scene method:** {card['scene_method']}")
            lines.append(f"- **Risk:** {card['risk']}")
            lines.append("")
    else:
        current_act = None
        for chapter_number in range(1, DEFAULT_LEGACY_CHAPTER_COUNT + 1):
            act_name = act_name_for_chapter(chapter_number, acts)
            if act_name != current_act:
                current_act = act_name
                lines.append(f"## {act_name}")
                lines.append("")
            lines.append(f"### Ch {chapter_number}: Chapter {chapter_number}")
            lines.append("- BEATS:")
            lines.append(f"  1. Placeholder beat for Chapter {chapter_number}.")
            lines.append("- PLANTS: (foreshadowing seeded here)")
            lines.append("  - description (payoff: Ch M)")
            lines.append("- HARVESTS: (foreshadowing paid off here)")
            lines.append("  - description (planted: Ch N)")
            lines.append("- EMOTIONAL ARC: start -> end")
            lines.append("- STATUS: unwritten")
            lines.append("")

    lines.append("## Foreshadowing Ledger")
    if threads:
        lines.append("| ID | Thread | Planted | Reinforced | Payoff | Type |")
        lines.append("|----|--------|---------|------------|--------|------|")
        for thread in threads:
            planted = f"Ch {thread['planted']}" if thread["planted"] else ""
            reinforced = ", ".join(f"Ch {item}" for item in thread["reinforced"])
            payoff = f"Ch {thread['payoff']}" if thread["payoff"] else ""
            lines.append(
                f"| {thread['id']} | {thread['description']} | {planted} | {reinforced} | {payoff} | {thread['type']} |"
            )
    else:
        lines.append("| ID   | Planted | Payoff | Thread           | Status    |")
        lines.append("|------|---------|--------|------------------|-----------|")
    lines.append("")
    return "\n".join(lines)


def parse_arc_outline(text: str) -> dict[str, object]:
    arc = {
        "title": "",
        "acts": [],
        "major_reveals": [],
        "pressure_escalations": [],
        "candidate_risk_chapters": [],
    }
    section = ""
    current_act: dict[str, object] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("<!--"):
            continue
        if line.startswith("**Working title:**"):
            match = re.match(r"^\*\*Working title:\*\*\s*(.+)$", line)
            if match:
                arc["title"] = ensure_string(match.group(1))
            continue
        if line == "## Irreversible Turns":
            section = "turns"
            current_act = None
            continue
        if line == "## Major Reveals":
            section = "reveals"
            current_act = None
            continue
        if line == "## Pressure Escalations":
            section = "pressure"
            current_act = None
            continue
        if line == "## Candidate Risk Chapters":
            section = "risks"
            current_act = None
            continue
        if section == "turns" and line.startswith("### "):
            current_act = {"name": ensure_string(line.removeprefix("### ")), "irreversible_turns": []}
            arc["acts"].append(current_act)
            continue
        if line.startswith("- "):
            value = ensure_string(line.removeprefix("- "))
            if section == "turns" and current_act is not None:
                current_act["irreversible_turns"].append(value)
            elif section == "reveals":
                arc["major_reveals"].append(value)
            elif section == "pressure":
                arc["pressure_escalations"].append(value)
            continue
        if section == "risks":
            arc["candidate_risk_chapters"] = ensure_int_list(line)

    if not arc["title"]:
        for raw_line in text.splitlines():
            if raw_line.startswith("# "):
                fallback = raw_line.removeprefix("# ").strip()
                if fallback and fallback != "Arc Outline":
                    arc["title"] = fallback
                    break
    return normalize_arc_payload(arc)


def parse_chapter_cards(text: str) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    def flush_current() -> None:
        nonlocal current
        if current is not None:
            cards.append(current)
            current = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading_match = _CHAPTER_CARD_HEADING_RE.match(line.strip())
        if heading_match:
            flush_current()
            number = ensure_int(heading_match.group(1), default=len(cards) + 1)
            current = {
                "number": number,
                "title": ensure_string(heading_match.group(2)) or f"Chapter {number}",
            }
            continue
        if current is None:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        normalized_key = CHAPTER_CARD_FIELD_ALIASES.get(ensure_string(key), ensure_string(key))
        if normalized_key in CHAPTER_CARD_FIELDS:
            current[normalized_key] = ensure_string(value)

    flush_current()
    normalized = normalize_chapter_cards(cards)
    return [card for card in normalized if not is_placeholder_card(card)]


def is_placeholder_card(card: dict[str, object]) -> bool:
    number = ensure_int(card.get("number"), default=0)
    if ensure_string(card.get("title")) != f"Chapter {number}":
        return False
    text_fields = (
        "focus_character",
        "goal",
        "pressure",
        "reversal",
        "aftermath",
        "irreversible_change",
        "allowed_ambiguity",
        "time_span",
    )
    if any(ensure_string(card.get(field)) for field in text_fields):
        return False
    return (
        ensure_string(card.get("scene_density")) == DEFAULT_SCENE_DENSITY
        and ensure_string(card.get("scene_type")) == DEFAULT_SCENE_TYPE
        and ensure_string(card.get("scene_method")) == DEFAULT_SCENE_METHOD
        and ensure_string(card.get("risk")) == DEFAULT_RISK
    )


def act_name_for_chapter(chapter_number: int, acts: list[dict[str, object]]) -> str:
    if not acts:
        if chapter_number <= 8:
            return "Act 1"
        if chapter_number <= 16:
            return "Act 2"
        return "Act 3"

    if len(acts) == 1:
        return acts[0]["name"]
    if len(acts) == 2:
        return acts[0]["name"] if chapter_number <= 12 else acts[1]["name"]
    if chapter_number <= 8:
        return acts[0]["name"]
    if chapter_number <= 16:
        return acts[1]["name"]
    return acts[2]["name"]


def derive_arc_from_outline(text: str) -> dict[str, object]:
    title = "Outline"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped.removeprefix("# ").strip() or title
            break

    acts = []
    for match in _ACT_HEADING_RE.finditer(text):
        name = ensure_string(match.group(1) + match.group(2)).strip(": ") or "Act"
        acts.append({"name": name, "irreversible_turns": []})

    return normalize_arc_payload({"title": title, "acts": acts})


def derive_chapter_cards_from_outline(text: str) -> list[dict[str, object]]:
    cards = []
    for match in _CHAPTER_BLOCK_RE.finditer(text):
        number = ensure_int(match.group(1), default=len(cards) + 1)
        title = ensure_string(match.group(2)) or f"Chapter {number}"
        block = match.group(3)
        cards.append(
            {
                "number": number,
                "title": title,
                "focus_character": first_markdown_value(block, "Focus character")
                or first_markdown_value(block, "POV")
                or first_markdown_value(block, "Focus"),
                "goal": first_markdown_value(block, "Goal") or first_beat(block),
                "pressure": first_markdown_value(block, "Pressure"),
                "reversal": first_markdown_value(block, "Reversal"),
                "aftermath": first_markdown_value(block, "Aftermath"),
                "irreversible_change": first_markdown_value(block, "Character movement"),
                "allowed_ambiguity": first_markdown_value(block, "The lie"),
                "time_span": first_markdown_value(block, "Time span") or first_markdown_value(block, "~Word count target"),
                "scene_density": first_markdown_value(block, "Scene density") or DEFAULT_SCENE_DENSITY,
                "scene_type": first_markdown_value(block, "Scene type") or DEFAULT_SCENE_TYPE,
                "scene_method": first_markdown_value(block, "Scene method") or DEFAULT_SCENE_METHOD,
                "risk": first_markdown_value(block, "Risk") or DEFAULT_RISK,
            }
        )
    return normalize_chapter_cards(cards)


def derive_thread_registry_from_outline(text: str) -> list[dict[str, object]]:
    threads = []
    for match in _THREAD_ROW_RE.finditer(text):
        columns = [ensure_string(column) for column in match.group(1).split("|")]
        header = columns[0].lower()
        if header in {"id", "thread", "----", "------"}:
            continue
        if len(columns) < 5:
            continue
        if len(columns) >= 6:
            maybe_id = safe_slug(columns[0])
            description = columns[1]
            planted_text = columns[2]
            reinforced_text = columns[3]
            payoff_text = columns[4]
            thread_type = columns[5]
        else:
            is_status_layout = bool(first_chapter_number(columns[1]) or first_chapter_number(columns[2]))
            maybe_id = safe_slug(columns[0])
            if is_status_layout:
                description = columns[3]
                planted_text = columns[1]
                reinforced_text = ""
                payoff_text = columns[2]
            else:
                description = columns[1]
                planted_text = columns[2]
                reinforced_text = columns[3]
                payoff_text = columns[4]
            thread_type = "plot"
        threads.append(
            {
                "id": maybe_id,
                "description": description,
                "first_seen": first_chapter_number(planted_text),
                "reinforced": ensure_int_list(reinforced_text),
                "payoff": first_chapter_number(payoff_text),
                "type": ensure_string(thread_type).lower() or "plot",
                "required": bool(first_chapter_number(payoff_text)),
            }
        )
    return normalize_thread_registry(threads)


def first_markdown_value(block: str, label: str) -> str:
    patterns = (
        rf"-\s*\*\*{re.escape(label)}:\*\*\s*(.+)",
        rf"-\s*\*\*{re.escape(label)}\*\*\s*[:|-]?\s*(.+)",
        rf"{re.escape(label)}:\s*(.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, block, re.IGNORECASE)
        if match:
            return ensure_string(match.group(1))
    return ""


def first_beat(block: str) -> str:
    match = re.search(r"^\s*\d+\.\s+(.+)$", block, re.MULTILINE)
    if match:
        return ensure_string(match.group(1))
    for raw_line in block.splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("-"):
            continue
        candidate = ensure_string(stripped.removeprefix("-"))
        if candidate and not candidate.endswith(":"):
            return candidate
    return ""


def first_chapter_number(text: str) -> int:
    match = re.search(r"(\d+)", ensure_string(text))
    return ensure_int(match.group(1), default=0) if match else 0


def read_text_if_exists(path: Path) -> str:
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""
