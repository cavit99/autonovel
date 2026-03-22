#!/usr/bin/env python3
"""Shared helpers for export-time outline and arc-summary rebuilds."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from manifest_tools import build_manifest_payload, chapter_paths, load_manifest
from planning_split import normalize_thread_registry, parse_arc_outline, parse_chapter_cards

BASE_DIR = Path(__file__).resolve().parent

_CHAPTER_HEADING_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
_CHAPTER_NUMBER_RE = re.compile(r"ch_(\d+)\.md$")


@dataclass(frozen=True)
class ChapterSnapshot:
    number: int
    title: str
    status: str
    word_count: int
    path: str
    opening_excerpt: str
    closing_excerpt: str
    card: dict[str, Any]
    plants: list[dict[str, Any]]
    reinforcements: list[dict[str, Any]]
    payoffs: list[dict[str, Any]]


@dataclass(frozen=True)
class ExportContext:
    base_dir: Path
    title: str
    manifest: dict[str, Any]
    manifest_source: str
    arc: dict[str, Any]
    cards: list[dict[str, Any]]
    threads: list[dict[str, Any]]
    chapters: list[ChapterSnapshot]
    accepted_chapter_count: int
    planned_chapter_count: int
    accepted_word_count: int
    risk_chapters: list[int]


def read_text_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_arc(base_dir: Path) -> dict[str, Any]:
    path = base_dir / "arc_outline.md"
    if not path.exists():
        return {
            "title": "",
            "acts": [],
            "major_reveals": [],
            "pressure_escalations": [],
            "candidate_risk_chapters": [],
        }
    return parse_arc_outline(path.read_text(encoding="utf-8"))


def load_cards(base_dir: Path) -> list[dict[str, Any]]:
    path = base_dir / "chapter_cards.md"
    if not path.exists():
        return []
    return parse_chapter_cards(path.read_text(encoding="utf-8"))


def load_threads(base_dir: Path) -> list[dict[str, Any]]:
    path = base_dir / "thread_registry.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return normalize_thread_registry(payload)


def chapter_number_from_path(path: Path) -> int:
    match = _CHAPTER_NUMBER_RE.search(path.name)
    return int(match.group(1)) if match else 0


def chapter_title(text: str, fallback: str) -> str:
    match = _CHAPTER_HEADING_RE.search(text)
    if match:
        return match.group(1).strip()
    return fallback


def chapter_body(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def paragraph_excerpt(text: str, *, from_end: bool = False, max_words: int = 45) -> str:
    body = chapter_body(text)
    if not body:
        return ""

    paragraphs = [
        compact_text(part)
        for part in re.split(r"\n\s*\n", body)
        if compact_text(part) and not compact_text(part).startswith("#")
    ]
    if not paragraphs:
        paragraphs = [compact_text(body)]

    chosen = paragraphs[-1] if from_end else paragraphs[0]
    words = chosen.split()
    if len(words) <= max_words:
        return chosen
    clipped = " ".join(words[:max_words]) if not from_end else " ".join(words[-max_words:])
    return f"{clipped} ..."


def format_chapter_ref(chapter_number: int) -> str:
    return f"Ch {chapter_number:02d}"


def stored_manifest(base_dir: Path) -> dict[str, Any]:
    manifest_path = base_dir / "manifest.json"
    stored = load_manifest(manifest_path) if manifest_path.exists() else {}
    return stored if isinstance(stored, dict) else {}


def meaningful_title(title: str) -> bool:
    cleaned = title.strip()
    return bool(cleaned) and cleaned not in {"Outline", "Arc Outline"}


def effective_manifest(base_dir: Path) -> tuple[dict[str, Any], str]:
    stored = stored_manifest(base_dir)
    live = build_manifest_payload(base_dir)

    if not stored:
        return live, "live-snapshot"

    keys_to_compare = (
        "phase",
        "current_chapter",
        "chapter_count",
        "planned_chapter_count",
        "word_count",
        "title",
        "risk_chapters",
    )
    for key in keys_to_compare:
        if stored.get(key) != live.get(key):
            return live, "live-snapshot"
    return stored, "manifest.json"


def thread_events_for_chapter(threads: list[dict[str, Any]], chapter_number: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    plants = []
    reinforcements = []
    payoffs = []
    for thread in threads:
        if int(thread.get("first_seen", 0) or 0) == chapter_number:
            plants.append(thread)
        if chapter_number in {int(item) for item in thread.get("reinforced", [])}:
            reinforcements.append(thread)
        if int(thread.get("payoff", 0) or 0) == chapter_number:
            payoffs.append(thread)
    return plants, reinforcements, payoffs


def thread_status(thread: dict[str, Any], accepted_chapter_count: int) -> str:
    first_seen = int(thread.get("first_seen", 0) or 0)
    payoff = int(thread.get("payoff", 0) or 0)
    if payoff and payoff <= accepted_chapter_count:
        return "paid-off"
    if first_seen and first_seen <= accepted_chapter_count:
        return "open"
    return "planned"


def chapter_numbers_for_export(cards: list[dict[str, Any]], accepted_numbers: list[int], planned_count: int) -> list[int]:
    if accepted_numbers:
        return accepted_numbers
    card_numbers = sorted(int(card.get("number", 0)) for card in cards if int(card.get("number", 0)) > 0)
    if card_numbers:
        return card_numbers
    if planned_count > 0:
        return list(range(1, planned_count + 1))
    return []


def resolve_title(arc: dict[str, Any], manifest: dict[str, Any], chapters: list[Path]) -> str:
    arc_title = str(arc.get("title", "")).strip()
    if meaningful_title(arc_title):
        return arc_title

    manifest_title = str(manifest.get("title", "")).strip()
    if meaningful_title(manifest_title):
        return manifest_title

    if chapters:
        first_text = read_text_if_exists(chapters[0])
        first_heading = chapter_title(first_text, "").strip()
        if first_heading:
            return first_heading

    return manifest_title or arc_title or "Outline"


def resolve_planned_chapter_count(
    cards: list[dict[str, Any]],
    accepted_numbers: list[int],
    manifest: dict[str, Any],
    manifest_source: str,
) -> int:
    if cards:
        return len(cards)
    if accepted_numbers:
        return len(accepted_numbers)
    if manifest_source == "manifest.json":
        return int(manifest.get("planned_chapter_count", 0) or 0)
    return 0


def dedupe_threads(threads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for thread in threads:
        key = str(thread.get("id", "")).strip() or str(thread.get("description", "")).strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(thread)
    return deduped


def load_export_context(base_dir: Path = BASE_DIR) -> ExportContext:
    stored = stored_manifest(base_dir)
    manifest, manifest_source = effective_manifest(base_dir)
    arc = load_arc(base_dir)
    cards = load_cards(base_dir)
    threads = load_threads(base_dir)

    accepted_paths = chapter_paths(base_dir)
    accepted_numbers = []
    for path in accepted_paths:
        number = chapter_number_from_path(path)
        if number > 0:
            accepted_numbers.append(number)
    cards_by_number = {int(card.get("number", 0)): card for card in cards if int(card.get("number", 0)) > 0}
    planned_chapter_count = resolve_planned_chapter_count(cards, accepted_numbers, stored or manifest, manifest_source)
    title = resolve_title(arc, stored or manifest, accepted_paths)

    chapters: list[ChapterSnapshot] = []
    for number in chapter_numbers_for_export(cards, accepted_numbers, planned_chapter_count):
        card = cards_by_number.get(number, {})
        path = base_dir / "chapters" / f"ch_{number:02d}.md"
        text = read_text_if_exists(path)
        title_fallback = str(card.get("title", "")).strip() or f"Chapter {number}"
        plants, reinforcements, payoffs = thread_events_for_chapter(threads, number)
        chapters.append(
            ChapterSnapshot(
                number=number,
                title=chapter_title(text, title_fallback),
                status="accepted" if path.exists() else "planned",
                word_count=len(text.split()) if text else 0,
                path=str(path.relative_to(base_dir)) if path.exists() else "",
                opening_excerpt=paragraph_excerpt(text, from_end=False),
                closing_excerpt=paragraph_excerpt(text, from_end=True),
                card=card,
                plants=plants,
                reinforcements=reinforcements,
                payoffs=payoffs,
            )
        )

    accepted_word_count = sum(chapter.word_count for chapter in chapters if chapter.status == "accepted")
    risk_chapters = [int(item) for item in manifest.get("risk_chapters", []) if int(item) > 0]

    return ExportContext(
        base_dir=base_dir,
        title=title,
        manifest=manifest,
        manifest_source=manifest_source,
        arc=arc,
        cards=cards,
        threads=threads,
        chapters=chapters,
        accepted_chapter_count=len(accepted_numbers),
        planned_chapter_count=planned_chapter_count,
        accepted_word_count=accepted_word_count,
        risk_chapters=risk_chapters,
    )


def render_compact_list(items: list[str], empty_value: str = "(none)") -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    return ", ".join(cleaned) if cleaned else empty_value


def render_thread_refs(threads: list[dict[str, Any]], *, include_payoff: bool = False) -> list[str]:
    rendered = []
    for thread in threads:
        description = str(thread.get("description", "")).strip() or str(thread.get("id", "thread")).strip()
        thread_type = str(thread.get("type", "plot")).strip()
        parts = [description, f"type={thread_type}"]
        if include_payoff:
            payoff = int(thread.get("payoff", 0) or 0)
            if payoff > 0:
                parts.append(f"payoff={format_chapter_ref(payoff)}")
        rendered.append(" | ".join(parts))
    return rendered


def render_outline_text(base_dir: Path = BASE_DIR) -> str:
    context = load_export_context(base_dir)
    lines = [f"# {context.title}", ""]

    lines.append("## Runtime Snapshot")
    lines.append(
        "- Source of truth: accepted chapters plus arc_outline.md, chapter_cards.md, "
        "thread_registry.json, and manifest.json"
    )
    lines.append(
        f"- Phase: {context.manifest.get('phase', 'unknown')} | accepted chapters: "
        f"{context.accepted_chapter_count} / planned chapters: {context.planned_chapter_count} | "
        f"accepted words: {context.accepted_word_count:,}"
    )
    lines.append(
        f"- Risk chapters: {render_compact_list([format_chapter_ref(item) for item in context.risk_chapters])}"
    )
    lines.append(f"- Manifest source used for export metadata: {context.manifest_source}")
    lines.append("")

    lines.append("## Compatibility Note")
    lines.append(
        "outline.md is a compatibility/export artifact. Planning truth lives in arc_outline.md, "
        "chapter_cards.md, thread_registry.json, and manifest.json."
    )
    lines.append("")

    lines.append("## Structure")
    acts = context.arc.get("acts", [])
    if acts:
        for act in acts:
            lines.append(f"### {str(act.get('name', 'Act')).strip()}")
            turns = [str(item).strip() for item in act.get("irreversible_turns", []) if str(item).strip()]
            if turns:
                for turn in turns:
                    lines.append(f"- {turn}")
            else:
                lines.append("- (no irreversible turns recorded)")
            lines.append("")
    else:
        lines.append("- (no arc acts recorded)")
        lines.append("")

    lines.append("## Major Reveals")
    reveals = [str(item).strip() for item in context.arc.get("major_reveals", []) if str(item).strip()]
    if reveals:
        for reveal in reveals:
            lines.append(f"- {reveal}")
    else:
        lines.append("- (none recorded)")
    lines.append("")

    lines.append("## Pressure Escalations")
    escalations = [str(item).strip() for item in context.arc.get("pressure_escalations", []) if str(item).strip()]
    if escalations:
        for item in escalations:
            lines.append(f"- {item}")
    else:
        lines.append("- (none recorded)")
    lines.append("")

    lines.append("## Chapters")
    if not context.chapters:
        lines.append("- (no accepted chapters or chapter cards found)")
        lines.append("")
    else:
        for chapter in context.chapters:
            lines.append(f"### Ch {chapter.number}: {chapter.title}")
            status_parts = [chapter.status]
            if chapter.word_count:
                status_parts.append(f"{chapter.word_count:,} words")
            risk = str(chapter.card.get("risk", "")).strip().lower()
            if risk and risk != "none":
                status_parts.append(f"risk={risk}")
            elif chapter.number in context.risk_chapters:
                status_parts.append("risk=candidate")
            if chapter.path:
                status_parts.append(chapter.path)
            lines.append(f"- STATUS: {' | '.join(status_parts)}")

            lines.append("- BEATS:")
            beats = [
                ("Goal", str(chapter.card.get("goal", "")).strip()),
                ("Pressure", str(chapter.card.get("pressure", "")).strip()),
                ("Reversal", str(chapter.card.get("reversal", "")).strip()),
                ("Aftermath", str(chapter.card.get("aftermath", "")).strip()),
            ]
            wrote_beat = False
            beat_index = 1
            for label, value in beats:
                if value:
                    lines.append(f"  {beat_index}. {label}: {value}")
                    beat_index += 1
                    wrote_beat = True
            if not wrote_beat:
                lines.append("  1. (no chapter-card beats recorded)")

            lines.append("- PLANTS:")
            plant_lines = render_thread_refs(chapter.plants, include_payoff=True)
            if plant_lines:
                for item in plant_lines:
                    lines.append(f"  - {item}")
            else:
                lines.append("  - (none)")

            lines.append("- HARVESTS:")
            harvest_threads = dedupe_threads(chapter.reinforcements + chapter.payoffs)
            harvest_lines = render_thread_refs(harvest_threads, include_payoff=False)
            if harvest_lines:
                for item in harvest_lines:
                    lines.append(f"  - {item}")
            else:
                lines.append("  - (none)")

            change = str(chapter.card.get("irreversible_change", "")).strip()
            ambiguity = str(chapter.card.get("allowed_ambiguity", "")).strip()
            emotional_arc = render_compact_list([part for part in (change, ambiguity) if part], empty_value="(not recorded)")
            lines.append(f"- EMOTIONAL ARC: {emotional_arc}")

            if chapter.opening_excerpt:
                lines.append(f"- ACTUAL OPENING: {chapter.opening_excerpt}")
            if chapter.closing_excerpt:
                lines.append(f"- ACTUAL CLOSING: {chapter.closing_excerpt}")
            lines.append("")

    lines.append("## Foreshadowing Ledger")
    lines.append("| ID | Thread | Type | Planted | Reinforced | Payoff | Required | Status |")
    lines.append("|----|--------|------|---------|------------|--------|----------|--------|")
    if context.threads:
        for thread in context.threads:
            first_seen = int(thread.get("first_seen", 0) or 0)
            reinforced = [format_chapter_ref(int(item)) for item in thread.get("reinforced", []) if int(item) > 0]
            payoff = int(thread.get("payoff", 0) or 0)
            lines.append(
                "| {id} | {description} | {type} | {planted} | {reinforced} | {payoff} | {required} | {status} |".format(
                    id=str(thread.get("id", "")).strip() or "thread",
                    description=str(thread.get("description", "")).strip() or "(unnamed thread)",
                    type=str(thread.get("type", "plot")).strip() or "plot",
                    planted=format_chapter_ref(first_seen) if first_seen > 0 else "",
                    reinforced=", ".join(reinforced),
                    payoff=format_chapter_ref(payoff) if payoff > 0 else "",
                    required="yes" if bool(thread.get("required")) else "no",
                    status=thread_status(thread, context.accepted_chapter_count),
                )
            )
    else:
        lines.append("| - | (no threads recorded) | - | - | - | - | - | - |")
    lines.append("")

    return "\n".join(lines).rstrip()


def render_arc_summary_text(base_dir: Path = BASE_DIR) -> str:
    context = load_export_context(base_dir)
    lines = [f"# {context.title}", "", "## Full-Arc Summary", ""]
    lines.append(
        "This summary is rebuilt from accepted chapters plus arc_outline.md, chapter_cards.md, "
        "thread_registry.json, and manifest.json."
    )
    lines.append(
        f"Current phase: {context.manifest.get('phase', 'unknown')}. Accepted chapters: "
        f"{context.accepted_chapter_count} / planned chapters: {context.planned_chapter_count}. "
        f"Accepted words: {context.accepted_word_count:,}."
    )
    lines.append(
        f"Risk chapters: {render_compact_list([format_chapter_ref(item) for item in context.risk_chapters])}."
    )
    lines.append("")

    lines.append("## Arc Signals")
    acts = context.arc.get("acts", [])
    if acts:
        for act in acts:
            lines.append(f"### {str(act.get('name', 'Act')).strip()}")
            turns = [str(item).strip() for item in act.get("irreversible_turns", []) if str(item).strip()]
            if turns:
                for turn in turns:
                    lines.append(f"- {turn}")
            else:
                lines.append("- (no irreversible turns recorded)")
            lines.append("")
    else:
        lines.append("- No arc acts recorded.")
        lines.append("")

    lines.append("### Major Reveals")
    reveals = [str(item).strip() for item in context.arc.get("major_reveals", []) if str(item).strip()]
    if reveals:
        for reveal in reveals:
            lines.append(f"- {reveal}")
    else:
        lines.append("- (none recorded)")
    lines.append("")

    lines.append("### Pressure Escalations")
    escalations = [str(item).strip() for item in context.arc.get("pressure_escalations", []) if str(item).strip()]
    if escalations:
        for item in escalations:
            lines.append(f"- {item}")
    else:
        lines.append("- (none recorded)")
    lines.append("")

    lines.append("## Thread Registry Snapshot")
    if context.threads:
        by_type: dict[str, int] = {}
        open_count = 0
        paid_off_count = 0
        for thread in context.threads:
            thread_type = str(thread.get("type", "plot")).strip() or "plot"
            by_type[thread_type] = by_type.get(thread_type, 0) + 1
            if thread_status(thread, context.accepted_chapter_count) == "paid-off":
                paid_off_count += 1
            elif thread_status(thread, context.accepted_chapter_count) == "open":
                open_count += 1
        lines.append(
            f"- Thread counts by type: {render_compact_list([f'{kind}={count}' for kind, count in sorted(by_type.items())])}"
        )
        lines.append(f"- Open threads in accepted prose: {open_count}")
        lines.append(f"- Paid-off threads in accepted prose: {paid_off_count}")
    else:
        lines.append("- No typed threads recorded yet.")
    lines.append("")

    lines.append("## Chapter Capsules")
    if not context.chapters:
        lines.append("- No accepted chapters or chapter cards found.")
        lines.append("")
        return "\n".join(lines).rstrip()

    for chapter in context.chapters:
        lines.append(f"### Ch {chapter.number}: {chapter.title}")
        risk = str(chapter.card.get("risk", "")).strip().lower()
        if not risk or risk == "none":
            risk = "candidate" if chapter.number in context.risk_chapters else "none"
        lines.append(
            f"- Status: {chapter.status} | words={chapter.word_count:,} | risk={risk}"
        )

        planned_parts = []
        for label, key in (
            ("Goal", "goal"),
            ("Pressure", "pressure"),
            ("Reversal", "reversal"),
            ("Aftermath", "aftermath"),
            ("Irreversible change", "irreversible_change"),
        ):
            value = str(chapter.card.get(key, "")).strip()
            if value:
                planned_parts.append(f"{label}: {value}")
        lines.append(
            f"- Planned move: {render_compact_list(planned_parts, empty_value='(no chapter-card structure recorded)')}"
        )

        thread_moves = []
        if chapter.plants:
            thread_moves.append(f"plants={render_compact_list(render_thread_refs(chapter.plants, include_payoff=True))}")
        if chapter.reinforcements:
            thread_moves.append(
                f"reinforces={render_compact_list(render_thread_refs(chapter.reinforcements, include_payoff=False))}"
            )
        if chapter.payoffs:
            thread_moves.append(
                f"payoffs={render_compact_list(render_thread_refs(chapter.payoffs, include_payoff=False))}"
            )
        lines.append(f"- Thread movement: {render_compact_list(thread_moves)}")

        if chapter.opening_excerpt:
            lines.append(f"- Opening signal: {chapter.opening_excerpt}")
        if chapter.closing_excerpt:
            lines.append(f"- Closing signal: {chapter.closing_excerpt}")
        lines.append("")

    return "\n".join(lines).rstrip()
