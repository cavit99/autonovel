#!/usr/bin/env python3
"""Shared helpers for patch-based revision workflows."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
CHAPTERS_DIR = BASE_DIR / "chapters"
EDIT_LOGS_DIR = BASE_DIR / "edit_logs"

MIN_LOCKS = 3
MAX_LOCKS = 5
DEFAULT_LOCK_COUNT = 4
MIN_QUOTE_LEN = 8
DIRECTIVE_RE = re.compile(
    r"^\s*[-*]\s*(cut|replace|insert after|insert before|move after|move before)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$")
NUMBERED_ITEM_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")


class DeterministicPatchPlanError(ValueError):
    """Raised when a prose brief cannot be converted into a usable local patch plan."""


def chapter_path(chapter_num: int, base_dir: Path = BASE_DIR) -> Path:
    return base_dir / "chapters" / f"ch_{chapter_num:02d}.md"


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_excerpt(text: str, limit: int = 120) -> str:
    squashed = " ".join(text.split())
    if len(squashed) <= limit:
        return squashed
    return squashed[: limit - 3].rstrip() + "..."


def paragraph_spans(text: str) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    cursor = 0
    for paragraph in text.split("\n\n"):
        start = cursor
        end = start + len(paragraph)
        spans.append({"text": paragraph, "start": start, "end": end})
        cursor = end + 2
    return [span for span in spans if span["text"].strip()]


def _passage_reason(passage: str) -> str:
    stripped = passage.strip()
    if '"' in stripped or "\u201c" in stripped or "\u201d" in stripped:
        return "speaker-specific awkwardness"
    if any(token in stripped for token in (";", ":", "?", "!", "...")):
        return "odd but alive syntax"
    return "strong line or passage"


def _passage_score(passage: str) -> float:
    stripped = passage.strip()
    if not stripped:
        return 0.0
    words = re.findall(r"[A-Za-z']+", stripped)
    unique_ratio = len(set(word.lower() for word in words)) / max(1, len(words))
    punctuation_bonus = sum(stripped.count(mark) for mark in ('"', "?", "!", ";", ":")) * 0.4
    length_bonus = min(len(words), 80) / 20
    fragment_bonus = 1.5 if len(stripped.splitlines()) > 1 else 0.0
    return unique_ratio * 10 + punctuation_bonus + length_bonus + fragment_bonus


def identify_roughness_spans(text: str, limit: int = DEFAULT_LOCK_COUNT) -> list[dict[str, Any]]:
    spans = paragraph_spans(text)
    if not spans:
        return []

    ranked = sorted(
        (
            {
                "start": span["start"],
                "end": span["end"],
                "excerpt": normalize_excerpt(span["text"]),
                "reason": _passage_reason(span["text"]),
                "score": round(_passage_score(span["text"]), 3),
            }
            for span in spans
        ),
        key=lambda item: item["score"],
        reverse=True,
    )

    selected = ranked[: max(MIN_LOCKS, min(limit, MAX_LOCKS))]
    return sorted(selected, key=lambda item: item["start"])


def spans_overlap(start: int, end: int, other_start: int, other_end: int) -> bool:
    return not (end <= other_start or start >= other_end)


def overlaps_locked_spans(start: int, end: int, locked_spans: list[dict[str, Any]] | None) -> bool:
    if not locked_spans:
        return False
    return any(spans_overlap(start, end, span["start"], span["end"]) for span in locked_spans)


def find_quote_span(text: str, quote: str) -> tuple[int, int] | None:
    if not quote:
        return None
    exact = text.find(quote)
    if exact >= 0:
        return exact, exact + len(quote)

    for ellipsis in ("...", "\u2026"):
        if quote.endswith(ellipsis):
            prefix = quote[: -len(ellipsis)].rstrip()
            exact = text.find(prefix)
            if exact >= 0:
                return exact, exact + len(prefix)
        if quote.startswith(ellipsis):
            suffix = quote[len(ellipsis) :].lstrip()
            exact = text.find(suffix)
            if exact >= 0:
                return exact, exact + len(suffix)

    ws = re.compile(r"\s+")
    normalized_quote = ws.sub(" ", quote).strip()
    if len(normalized_quote) < MIN_QUOTE_LEN:
        return None
    pattern = r"\s+".join(re.escape(token) for token in normalized_quote.split(" "))
    matches = list(re.finditer(pattern, text))
    if len(matches) == 1:
        match = matches[0]
        return match.start(), match.end()
    return None


def find_anchor_position(text: str, anchor_quote: str, placement: str) -> int | None:
    span = find_quote_span(text, anchor_quote)
    if span is None:
        return None
    start, end = span
    return start if placement == "before" else end


def parse_patch_directives(brief_text: str) -> list[dict[str, str]]:
    directives: list[dict[str, str]] = []
    for line in brief_text.splitlines():
        match = DIRECTIVE_RE.match(line)
        if not match:
            continue
        operation = match.group(1).lower()
        remainder = match.group(2).strip()
        if operation == "cut":
            if quoted := re.findall(r'"([^"]+)"', remainder):
                directives.append({"type": "cut", "quote": quoted[0], "reason": remainder})
        elif operation == "replace":
            parts = re.findall(r'"([^"]+)"', remainder)
            if len(parts) >= 2:
                directives.append(
                    {
                        "type": "replace",
                        "quote": parts[0],
                        "text": parts[1],
                        "reason": remainder,
                    }
                )
        elif operation.startswith("insert"):
            parts = re.findall(r'"([^"]+)"', remainder)
            if len(parts) >= 2:
                directives.append(
                    {
                        "type": "insert",
                        "anchor_quote": parts[0],
                        "placement": "after" if operation.endswith("after") else "before",
                        "text": parts[1],
                        "reason": remainder,
                    }
                )
        elif operation.startswith("move"):
            parts = re.findall(r'"([^"]+)"', remainder)
            if len(parts) >= 2:
                directives.append(
                    {
                        "type": "move",
                        "quote": parts[0],
                        "anchor_quote": parts[1],
                        "placement": "after" if operation.endswith("after") else "before",
                        "reason": remainder,
                    }
                )
    return directives


def extract_markdown_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    target = heading.strip().lower()
    start: int | None = None
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line.strip())
        if not match:
            continue
        found = match.group(1).strip().lower()
        if start is None and found == target:
            start = index + 1
            continue
        if start is not None:
            return "\n".join(lines[start:index]).strip()
    if start is None:
        return ""
    return "\n".join(lines[start:]).strip()


def _strip_markdown_wrapping(text: str) -> str:
    cleaned = text.strip().strip("`").strip()
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    return cleaned


def parse_generated_brief_actions(brief_text: str) -> tuple[list[dict[str, str]], list[str]]:
    section = extract_markdown_section(brief_text, "WHAT TO CHANGE")
    if not section:
        return [], ["Brief did not contain a '## WHAT TO CHANGE' section."]

    directives: list[dict[str, str]] = []
    notes: list[str] = []
    items: list[list[str]] = []
    current: list[str] = []

    for raw_line in section.splitlines():
        line = raw_line.rstrip()
        if HEADING_RE.match(line.strip()):
            break
        if NUMBERED_ITEM_RE.match(line):
            if current:
                items.append(current)
            current = [line]
            continue
        if current:
            current.append(line)
    if current:
        items.append(current)

    for item_lines in items:
        first_line = item_lines[0]
        item_text = "\n".join(line.strip() for line in item_lines if line.strip())
        quote_match = re.search(r'`"(.+?)"`', first_line)
        if not quote_match:
            quote_match = re.search(r'"(.+?)"', first_line)
        quote = _strip_markdown_wrapping(quote_match.group(1)) if quote_match else ""

        rewrite_match = re.search(r'→\s*Rewrite as:\s*"(.+?)"', item_text, re.IGNORECASE | re.DOTALL)
        cut_match = re.search(r'→\s*Cut entirely\b', item_text, re.IGNORECASE)

        if quote and rewrite_match:
            directives.append(
                {
                    "type": "replace",
                    "quote": quote,
                    "text": rewrite_match.group(1).strip(),
                    "reason": item_text,
                }
            )
            continue
        if quote and cut_match:
            directives.append(
                {
                    "type": "cut",
                    "quote": quote,
                    "reason": item_text,
                }
            )
            continue

        if item_text:
            notes.append(f"Non-actionable WHAT TO CHANGE item: {item_text}")

    return directives, notes


def extract_actionable_directives(brief_text: str) -> tuple[list[dict[str, str]], list[str]]:
    directives = parse_patch_directives(brief_text)
    if directives:
        return directives, []
    return parse_generated_brief_actions(brief_text)


def _is_paragraph_boundary_before(text: str, index: int) -> bool:
    return index == 0 or text[max(0, index - 2) : index] == "\n\n"


def _is_paragraph_boundary_after(text: str, index: int) -> bool:
    if index >= len(text):
        return True
    if text[index : index + 2] == "\n\n":
        return True
    return text[index:] in {"", "\n"}


def _expand_removal_span(text: str, start: int, end: int) -> tuple[int, int]:
    span_text = text[start:end]
    if "\n\n" in span_text:
        return start, end
    if not (_is_paragraph_boundary_before(text, start) and _is_paragraph_boundary_after(text, end)):
        return start, end
    if text[end : end + 2] == "\n\n":
        return start, end + 2
    if text[max(0, start - 2) : start] == "\n\n":
        return start - 2, end
    return start, end


def _format_insertion_text(text: str, at: int, inserted: str) -> str:
    payload = inserted.strip("\n")
    if not payload:
        return inserted

    prefix = ""
    suffix = ""
    before = text[at - 1] if at > 0 else ""
    after = text[at] if at < len(text) else ""
    before_sep = text[max(0, at - 2) : at]
    after_sep = text[at : at + 2]

    if after_sep == "\n\n" and before != "\n":
        prefix = "\n\n"
    elif before_sep == "\n\n" and after != "\n":
        suffix = "\n\n"
    else:
        if before and not before.isspace() and payload[0] not in ",.;:!?)]}\"'":
            prefix = " "
        if after and not after.isspace() and payload[-1] not in " ([{\"'":
            suffix = " "

    return f"{prefix}{payload}{suffix}"


def build_deterministic_patch_plan(
    chapter_num: int,
    brief_text: str,
    source_text: str,
    locked_spans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    edits: list[dict[str, Any]] = []
    directives, notes = extract_actionable_directives(brief_text)
    if not directives:
        detail = notes[0] if notes else "No actionable edits found in brief."
        raise DeterministicPatchPlanError(
            "Deterministic patch planning could not derive actionable edits from the brief. "
            f"{detail}"
        )

    for index, directive in enumerate(directives, start=1):
        kind = directive["type"]
        normalized: dict[str, Any] | None = None
        if kind in {"cut", "replace", "move"}:
            span = find_quote_span(source_text, directive.get("quote", ""))
            if span is None:
                notes.append(f"Skipped {kind} directive {index}: quote not found")
                continue
            start, end = span
            if overlaps_locked_spans(start, end, locked_spans):
                notes.append(f"Skipped {kind} directive {index}: overlaps locked span")
                continue
            normalized = {
                "id": f"edit-{index}",
                "type": kind,
                "start": start,
                "end": end,
                "reason": directive.get("reason", ""),
                "excerpt": normalize_excerpt(source_text[start:end]),
            }
            if kind == "replace":
                normalized["text"] = directive["text"]
            if kind == "move":
                target = find_anchor_position(source_text, directive.get("anchor_quote", ""), directive.get("placement", "after"))
                if target is None:
                    notes.append(f"Skipped move directive {index}: anchor not found")
                    continue
                if start <= target <= end:
                    notes.append(f"Skipped move directive {index}: anchor falls inside moved span")
                    continue
                normalized["to"] = target
        elif kind == "insert":
            at = find_anchor_position(source_text, directive.get("anchor_quote", ""), directive.get("placement", "after"))
            if at is None:
                notes.append(f"Skipped insert directive {index}: anchor not found")
                continue
            if overlaps_locked_spans(at, at, locked_spans):
                notes.append(f"Skipped insert directive {index}: anchor overlaps locked span")
                continue
            normalized = {
                "id": f"edit-{index}",
                "type": "insert",
                "at": at,
                "text": directive["text"],
                "reason": directive.get("reason", ""),
            }

        if normalized is not None:
            edits.append(normalized)

    if not edits:
        detail = "; ".join(notes) if notes else "The brief contained actionable-looking items, but none mapped to source spans."
        raise DeterministicPatchPlanError(
            "Deterministic patch planning found no applicable edits for the current chapter text. "
            f"{detail}"
        )

    return {
        "chapter": chapter_num,
        "source_sha256": compute_sha256(source_text),
        "planner": "deterministic",
        "notes": notes,
        "locked_spans": locked_spans or [],
        "edits": edits,
    }


def build_pending_patch_plan(
    chapter_num: int,
    brief_text: str,
    locked_spans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    directives, notes = extract_actionable_directives(brief_text)
    if not directives:
        detail = notes[0] if notes else "No actionable edits found in brief."
        raise DeterministicPatchPlanError(
            "Chapter source text is missing, and the brief does not contain actionable patch directives. "
            f"{detail}"
        )
    return {
        "chapter": chapter_num,
        "source_sha256": compute_sha256(""),
        "planner": "deterministic-pending",
        "notes": [
            "Chapter source text is missing; stored unresolved directives only.",
            *notes,
        ],
        "locked_spans": locked_spans or [],
        "unresolved_directives": directives,
        "edits": [],
    }


def normalize_patch_payload(
    payload: dict[str, Any],
    source_text: str,
    chapter_num: int,
    locked_spans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_edits: list[dict[str, Any]] = []
    notes = list(payload.get("notes", []))

    raw_edits = payload.get("edits", [])
    if not isinstance(raw_edits, list):
        raw_edits = []
        notes.append("Invalid edit payload: edits was not a list")

    for index, raw in enumerate(raw_edits, start=1):
        if not isinstance(raw, dict):
            notes.append(f"Skipped edit {index}: entry was not an object")
            continue
        kind = str(raw.get("type", "")).lower()
        normalized: dict[str, Any] | None = None
        if kind in {"cut", "replace", "move"}:
            if "start" in raw and "end" in raw:
                start = int(raw["start"])
                end = int(raw["end"])
            else:
                span = find_quote_span(source_text, str(raw.get("quote", "")))
                if span is None:
                    notes.append(f"Skipped {kind} edit {index}: quote not found")
                    continue
                start, end = span
            if start < 0 or end < start or end > len(source_text):
                notes.append(f"Skipped {kind} edit {index}: invalid span")
                continue
            if overlaps_locked_spans(start, end, locked_spans):
                notes.append(f"Skipped {kind} edit {index}: overlaps locked span")
                continue
            normalized = {
                "id": str(raw.get("id", f"edit-{index}")),
                "type": kind,
                "start": start,
                "end": end,
                "reason": str(raw.get("reason", "")),
                "excerpt": normalize_excerpt(source_text[start:end]),
            }
            if kind == "replace":
                normalized["text"] = str(raw.get("text", ""))
            if kind == "move":
                if "to" in raw:
                    target = int(raw["to"])
                else:
                    placement = str(raw.get("placement", "after")).lower()
                    target = find_anchor_position(source_text, str(raw.get("anchor_quote", "")), placement)
                    if target is None:
                        notes.append(f"Skipped move edit {index}: anchor not found")
                        continue
                if target < 0 or target > len(source_text) or start <= target <= end:
                    notes.append(f"Skipped move edit {index}: invalid target")
                    continue
                normalized["to"] = target
        elif kind == "insert":
            if "at" in raw:
                at = int(raw["at"])
            else:
                placement = str(raw.get("placement", "after")).lower()
                at = find_anchor_position(source_text, str(raw.get("anchor_quote", "")), placement)
                if at is None:
                    notes.append(f"Skipped insert edit {index}: anchor not found")
                    continue
            if at < 0 or at > len(source_text):
                notes.append(f"Skipped insert edit {index}: invalid insertion point")
                continue
            if overlaps_locked_spans(at, at, locked_spans):
                notes.append(f"Skipped insert edit {index}: insertion point overlaps locked span")
                continue
            normalized = {
                "id": str(raw.get("id", f"edit-{index}")),
                "type": "insert",
                "at": at,
                "text": str(raw.get("text", "")),
                "reason": str(raw.get("reason", "")),
            }
        else:
            notes.append(f"Skipped edit {index}: unsupported type {kind!r}")

        if normalized is not None:
            normalized_edits.append(normalized)

    return {
        "chapter": chapter_num,
        "source_sha256": payload.get("source_sha256", compute_sha256(source_text)),
        "planner": payload.get("planner", "model"),
        "notes": notes,
        "locked_spans": locked_spans or list(payload.get("locked_spans", [])),
        "edits": normalized_edits,
    }


def _validate_edit_conflicts(edits: list[dict[str, Any]]) -> None:
    ranged = [
        (edit["start"], edit["end"], edit["id"])
        for edit in edits
        if edit["type"] in {"cut", "replace", "move"}
    ]
    for idx, (start, end, edit_id) in enumerate(ranged):
        for other_start, other_end, other_id in ranged[idx + 1 :]:
            if spans_overlap(start, end, other_start, other_end):
                raise ValueError(f"Overlapping edits: {edit_id} and {other_id}")


def apply_patch_edits(
    source_text: str,
    edits: list[dict[str, Any]],
    locked_spans: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    replacements: dict[int, dict[str, Any]] = {}
    insertions: dict[int, list[str]] = {}
    normalized_for_conflicts: list[dict[str, Any]] = []

    for edit in edits:
        kind = edit["type"]
        if kind == "insert":
            if overlaps_locked_spans(edit["at"], edit["at"], locked_spans):
                raise ValueError(f"Edit {edit['id']} inserts inside a locked span")
            payload = _format_insertion_text(source_text, edit["at"], edit["text"])
            insertions.setdefault(edit["at"], []).append(payload)
            continue

        start = edit["start"]
        end = edit["end"]
        if overlaps_locked_spans(start, end, locked_spans):
            raise ValueError(f"Edit {edit['id']} overlaps a locked span")
        if kind in {"cut", "move"}:
            remove_start, remove_end = _expand_removal_span(source_text, start, end)
        else:
            remove_start, remove_end = start, end
        normalized_for_conflicts.append({"type": kind, "id": edit["id"], "start": remove_start, "end": remove_end})

        if kind == "cut":
            replacements[remove_start] = {"end": remove_end, "text": "", "edit": edit}
        elif kind == "replace":
            replacements[remove_start] = {"end": remove_end, "text": edit["text"], "edit": edit}
        elif kind == "move":
            segment = source_text[start:end]
            target = edit["to"]
            if start <= target <= end:
                raise ValueError(f"Move target for {edit['id']} falls inside moved span")
            replacements[remove_start] = {"end": remove_end, "text": "", "edit": edit}
            insertions.setdefault(target, []).append(_format_insertion_text(source_text, target, segment))

    _validate_edit_conflicts(normalized_for_conflicts)

    output: list[str] = []
    cursor = 0
    applied: list[dict[str, Any]] = []

    while cursor <= len(source_text):
        if cursor in insertions:
            output.extend(insertions[cursor])
        if cursor == len(source_text):
            break
        replacement = replacements.get(cursor)
        if replacement is not None:
            output.append(replacement["text"])
            applied.append(replacement["edit"])
            cursor = replacement["end"]
            continue
        output.append(source_text[cursor])
        cursor += 1

    for edit in edits:
        if edit["type"] == "insert":
            applied.append(edit)

    return "".join(output), applied


def load_patch_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_patch_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
