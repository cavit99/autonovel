#!/usr/bin/env python3
"""
Auto-generate revision briefs from reader panel feedback, evaluation results,
or adversarial cuts.

Usage:
  python gen_brief.py --panel 12    # brief from panel feedback for ch 12
  python gen_brief.py --eval 12     # brief from eval callouts for ch 12
  python gen_brief.py --cuts 12     # brief from adversarial cuts for ch 12
  python gen_brief.py --auto        # auto-detect weakest chapter and generate
"""
import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
CHAPTERS_DIR = BASE_DIR / "chapters"
EDIT_LOGS_DIR = BASE_DIR / "edit_logs"
EVAL_LOGS_DIR = BASE_DIR / "eval_logs"
BRIEFS_DIR = BASE_DIR / "briefs"
VOICE_PATH = BASE_DIR / "voice.md"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def chapter_path(ch: int) -> Path:
    return CHAPTERS_DIR / f"ch_{ch:02d}.md"


def chapter_text(ch: int) -> str:
    p = chapter_path(ch)
    if not p.exists():
        sys.exit(f"ERROR: chapter file not found: {p}")
    return p.read_text(encoding="utf-8")


def chapter_title(text: str) -> str:
    """Extract the chapter title from the first line of the md file."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            # strip leading hashes and any "Chapter N/One/Two/..." prefix
            title = re.sub(r"^#+\s*", "", line)
            title = re.sub(
                r"^Chapter\s+(?:\d+|[A-Z][a-z]+(?:-[A-Z][a-z]+)*)\s*[:—–-]*\s*",
                "", title, flags=re.I
            )
            return title.strip() if title.strip() else "Untitled"
    return "Untitled"


def word_count(text: str) -> int:
    return len(text.split())


def extract_voice_rules() -> list[str]:
    """Pull the key guardrail / voice rules from voice.md Part 1 + Part 2."""
    if not VOICE_PATH.exists():
        return ["(voice.md not found)"]
    voice = VOICE_PATH.read_text(encoding="utf-8")

    rules: list[str] = []

    # Part 2 identity rules we always want
    rules.append("Body-first emotion (jaw, ribs, tongue before naming the feeling)")
    rules.append("No telling after showing")
    rules.append("No triadic sensory lists")
    rules.append("70%+ in-scene (dialogue and action, not summary)")
    rules.append("Dialogue: clipped, subtext-heavy, 'said' default, no adverb tags")
    rules.append("Sentence rhythm: mixed meter, fragments for pain, long for perception")
    rules.append("Vocabulary from craft/trade/body wells — no generic fantasy diction")

    # Part 1 structural slop
    rules.append("No paragraph-template-machine (vary structure)")
    rules.append("Max 1-2 em dashes per page")

    return rules


def latest_full_eval() -> Path | None:
    """Find the most recent *_full.json in eval_logs/."""
    if not EVAL_LOGS_DIR.exists():
        return None
    fulls = sorted(EVAL_LOGS_DIR.glob("*_full.json"))
    return fulls[-1] if fulls else None


def latest_chapter_eval(ch: int) -> Path | None:
    """Find the most recent per-chapter eval for ch N."""
    if not EVAL_LOGS_DIR.exists():
        return None
    pattern = f"*_ch{ch:02d}.json"
    matches = sorted(EVAL_LOGS_DIR.glob(pattern))
    # Also try without zero-pad
    matches += sorted(EVAL_LOGS_DIR.glob(f"*_ch{ch}.json"))
    matches = sorted(set(matches))
    return matches[-1] if matches else None


def load_panel() -> dict | None:
    p = EDIT_LOGS_DIR / "reader_panel.json"
    if not p.exists():
        return None
    return load_json(p)


def load_cuts(ch: int) -> dict | None:
    p = EDIT_LOGS_DIR / f"ch{ch:02d}_cuts.json"
    if not p.exists():
        return None
    return load_json(p)


PATCH_TYPE_PRIORITY = {
    "REDUNDANT": 0,
    "OVER-EXPLAIN": 1,
    "FAT": 2,
    "TELL": 3,
    "GENERIC": 4,
    "STRUCTURAL": 5,
    "OTHER": 6,
}


def _normalize_patch_literal(text: str) -> str:
    return " ".join(text.split()).replace('"', "'").strip()


def build_patch_directives_from_cuts(
    cuts_data: dict | None,
    *,
    limit: int | None = None,
    allowed_types: set[str] | None = None,
) -> list[str]:
    if not cuts_data:
        return []

    directives: list[str] = []
    seen: set[str] = set()

    cuts = cuts_data.get("cuts", [])
    ranked_cuts = sorted(
        cuts,
        key=lambda cut: (
            PATCH_TYPE_PRIORITY.get(str(cut.get("type", "OTHER")).upper(), 99),
            len(str(cut.get("quote", ""))),
        ),
    )

    for cut in ranked_cuts:
        cut_type = str(cut.get("type", "OTHER")).upper()
        if allowed_types and cut_type not in allowed_types:
            continue

        quote = _normalize_patch_literal(str(cut.get("quote", "")))
        if not quote:
            continue

        action = str(cut.get("action", "CUT")).upper()
        rewrite = _normalize_patch_literal(str(cut.get("rewrite", "")))

        directive = ""
        if action == "REWRITE" and rewrite:
            directive = f'- replace: "{quote}" => "{rewrite}"'
        elif action == "CUT":
            directive = f'- cut: "{quote}"'
        else:
            continue

        if directive in seen:
            continue
        seen.add(directive)
        directives.append(directive)

        if limit is not None and len(directives) >= limit:
            break

    return directives


def append_patch_directives_section(brief_text: str, directives: list[str]) -> str:
    if not directives:
        return brief_text

    body = brief_text.rstrip() + "\n\n"
    body += "## Patch Directives\n"
    body += "\n".join(directives) + "\n"
    return body


def has_patch_directives(brief_text: str) -> bool:
    return "## Patch Directives" in brief_text


CHAPTER_DIMENSION_SPECS = [
    {"key": "perspective_distinctiveness", "label": "Perspective distinctiveness"},
    {"key": "formal_enactment", "label": "Formal enactment"},
    {"key": "character_truthfulness", "label": "Character truth"},
    {
        "key": "dialogue_separability",
        "label": "Dialogue separability",
        "fallback_keys": ["character_voice"],
    },
    {"key": "surplus_life", "label": "Surplus life"},
    {
        "key": "scene_method_freshness",
        "label": "Scene method freshness",
        "fallback_keys": ["beat_coverage"],
    },
    {
        "key": "baseline_voice",
        "label": "Baseline voice",
        "fallback_keys": ["voice_adherence"],
    },
    {"key": "humor_signature", "label": "Humor signature"},
    {"key": "prose_quality", "label": "Prose quality"},
    {"key": "continuity", "label": "Continuity"},
    {"key": "canon_compliance", "label": "Canon compliance"},
    {
        "key": "lore_integration",
        "label": "Lore integration",
        "fallback_keys": ["plants_seeded"],
    },
    {"key": "engagement", "label": "Engagement"},
]

FULL_DIMENSION_SPECS = [
    {
        "key": "perspective_continuity",
        "label": "Perspective continuity",
        "fallback_keys": ["voice_consistency"],
    },
    {"key": "formal_variety", "label": "Formal variety"},
    {"key": "temporal_variety", "label": "Temporal variety"},
    {
        "key": "theme_pressure",
        "label": "Theme pressure",
        "fallback_keys": ["theme_coherence"],
    },
    {"key": "surplus_life", "label": "Surplus life"},
    {"key": "human_texture", "label": "Human texture"},
    {"key": "over_determinedness_penalty", "label": "Over-determinedness penalty"},
    {
        "key": "arc_completion",
        "label": "Arc completion",
        "fallback_keys": ["foreshadowing_resolution"],
    },
    {"key": "pacing_curve", "label": "Pacing curve"},
    {"key": "world_consistency", "label": "World consistency"},
    {"key": "overall_engagement", "label": "Overall engagement"},
]

PANELIST_LABELS = {
    "novelist": "Novelist",
    "dramatist": "Dramatist",
    "oral_reader": "Oral Reader",
}

PASSAGE_ID_RE = re.compile(r"\bch\d{2}-p\d{2}\b", re.I)


def load_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = load_json(path)
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def load_dialogue_audit() -> dict | None:
    return load_optional_json(EDIT_LOGS_DIR / "dialogue_audit.json")


def load_narration_audit() -> dict | None:
    return load_optional_json(EDIT_LOGS_DIR / "narration_audit.json")


def load_humanity_panel() -> dict | None:
    return load_optional_json(EDIT_LOGS_DIR / "humanity_panel.json")


def chapter_mention_pattern(ch: int) -> re.Pattern:
    return re.compile(rf"\b(?:Chapters?|Ch\.?)\s*0?{ch}\b", re.I)


def format_score(score: float | None) -> str:
    if score is None:
        return "?"
    if float(score).is_integer():
        return str(int(score))
    return f"{score:g}"


def coerce_score(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def short_quote(text: str, *, limit: int = 160) -> str:
    clean = " ".join(str(text).split()).strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "..."


def append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def fallback_tag(source_key: str, canonical_key: str) -> str:
    if source_key == canonical_key:
        return ""
    return f" | fallback from {source_key}"


def describe_dimension_key(raw_key: str, specs: list[dict]) -> str:
    if not raw_key:
        return "unknown"
    for spec in specs:
        if raw_key == spec["key"]:
            return spec["label"]
        if raw_key in spec.get("fallback_keys", []):
            return f"{spec['label']} (legacy {raw_key})"
    return raw_key.replace("_", " ")


def resolve_dimension_payload(data: dict, spec: dict) -> dict | None:
    for source_key in [spec["key"], *spec.get("fallback_keys", [])]:
        payload = data.get(source_key)
        if not isinstance(payload, dict):
            continue
        violations = [
            str(item).strip()
            for item in payload.get("violations", [])
            if str(item).strip()
        ] if isinstance(payload.get("violations"), list) else []
        return {
            "key": spec["key"],
            "label": spec["label"],
            "source_key": source_key,
            "score": coerce_score(payload.get("score")),
            "weakest_moment": str(
                payload.get("weakest_moment", payload.get("weakest_sentence", ""))
            ).strip(),
            "fix": str(payload.get("fix", "")).strip(),
            "note": str(payload.get("note", "")).strip(),
            "violations": violations,
        }
    return None


def collect_dimension_payloads(data: dict, specs: list[dict]) -> list[dict]:
    payloads: list[dict] = []
    for spec in specs:
        payload = resolve_dimension_payload(data, spec)
        if payload:
            payloads.append(payload)
    return payloads


def format_dimension_problem(payload: dict) -> str | None:
    detail = payload["weakest_moment"]
    if not detail and payload["violations"]:
        detail = "; ".join(payload["violations"][:2])
    if not detail:
        detail = payload["note"]
    if not detail:
        return None
    source_suffix = ""
    if payload["source_key"] != payload["key"]:
        source_suffix = f"; legacy {payload['source_key']}"
    return (
        f"**{payload['label']}** "
        f"({format_score(payload['score'])}/10{source_suffix}): {detail}"
    )


def format_dimension_change(payload: dict) -> str | None:
    source_suffix = fallback_tag(payload["source_key"], payload["key"])
    if payload["fix"]:
        return f"[{payload['label']}{source_suffix}] {payload['fix']}"
    if payload["key"] == "canon_compliance" and payload["violations"]:
        return (
            f"[{payload['label']}{source_suffix}] Resolve the flagged canon issues: "
            + "; ".join(payload["violations"][:2])
        )
    return None


def weak_dimension_payloads(data: dict, specs: list[dict], *, threshold: float = 7.0) -> list[dict]:
    payloads: list[dict] = []
    for payload in collect_dimension_payloads(data, specs):
        score = payload["score"]
        if score is not None and score <= threshold:
            payloads.append(payload)
    return payloads


def summarize_chapter_eval(ch_eval: dict) -> dict:
    problem_parts: list[str] = []
    keep_parts: list[str] = []
    change_items: list[str] = []

    overall = ch_eval.get("overall_score", "?")
    weakest_dim = describe_dimension_key(
        str(ch_eval.get("weakest_dimension", "")),
        CHAPTER_DIMENSION_SPECS,
    )
    problem_parts.append(
        f"Per-chapter eval score: **{overall}/10**. "
        f"Weakest dimension: **{weakest_dim}**."
    )

    for payload in weak_dimension_payloads(ch_eval, CHAPTER_DIMENSION_SPECS):
        problem_text = format_dimension_problem(payload)
        if problem_text:
            append_unique(problem_parts, problem_text)
        change_text = format_dimension_change(payload)
        if change_text:
            append_unique(change_items, change_text)

    for rev in ch_eval.get("top_3_revisions", []):
        append_unique(change_items, str(rev))

    ai_patterns = ch_eval.get("ai_patterns_detected", [])
    if ai_patterns:
        append_unique(problem_parts, "**AI patterns detected:**")
        for pattern in ai_patterns:
            append_unique(problem_parts, f"- {pattern}")

    strongest = ch_eval.get("three_strongest_sentences", [])
    if strongest:
        append_unique(keep_parts, "Strongest sentences (eval):")
        for sentence in strongest:
            append_unique(keep_parts, f'- "{sentence}"')

    weakest_sentences = ch_eval.get("three_weakest_sentences", [])
    if weakest_sentences:
        append_unique(problem_parts, "**Weakest sentences:**")
        for sentence in weakest_sentences:
            append_unique(problem_parts, f'- "{sentence}"')

    return {
        "problem_parts": problem_parts,
        "keep_parts": keep_parts,
        "change_items": change_items,
    }


def summarize_full_eval_for_chapter(
    full_eval: dict,
    ch: int,
    *,
    strongest_header: bool,
) -> dict:
    problem_parts: list[str] = []
    change_items: list[str] = []
    weakest_dim = describe_dimension_key(
        str(full_eval.get("weakest_dimension", "")),
        FULL_DIMENSION_SPECS,
    )
    novel_score = full_eval.get("novel_score", "?")
    if strongest_header:
        problem_parts.append(
            f"**Weakest chapter in the novel** (novel score: {novel_score}/10, "
            f"weakest dimension: {weakest_dim})."
        )
    elif full_eval.get("weakest_chapter") == ch:
        problem_parts.append(
            f"**This is the novel's weakest chapter** per full eval "
            f"(novel score: {novel_score}/10; weakest dimension: {weakest_dim})."
        )

    chapter_re = chapter_mention_pattern(ch)
    for payload in collect_dimension_payloads(full_eval, FULL_DIMENSION_SPECS):
        if payload["note"] and chapter_re.search(payload["note"]):
            source_suffix = ""
            if payload["source_key"] != payload["key"]:
                source_suffix = f"; legacy {payload['source_key']}"
            append_unique(
                problem_parts,
                f"**{payload['label']}** ({format_score(payload['score'])}/10{source_suffix}): "
                f"{payload['note']}",
            )

    top_suggestion = str(full_eval.get("top_suggestion", "")).strip()
    if top_suggestion:
        append_unique(change_items, f"[PRIORITY — full eval] {top_suggestion}")

    return {
        "problem_parts": problem_parts,
        "change_items": change_items,
    }


def build_passage_lookup(evidence_pack: dict | None) -> dict[str, dict]:
    if not evidence_pack:
        return {}
    lookup: dict[str, dict] = {}
    categories = evidence_pack.get("categories", {})
    if not isinstance(categories, dict):
        return lookup
    for passages in categories.values():
        if not isinstance(passages, list):
            continue
        for passage in passages:
            if not isinstance(passage, dict):
                continue
            passage_id = str(passage.get("id", "")).strip().lower()
            if passage_id:
                lookup[passage_id] = passage
    return lookup


def load_humanity_evidence_lookup(panel: dict | None) -> dict[str, dict]:
    if not panel:
        return {}
    candidates: list[Path] = []
    evidence_path = str(panel.get("evidence_path", "")).strip()
    if evidence_path:
        candidate = Path(evidence_path)
        candidates.append(candidate if candidate.is_absolute() else BASE_DIR / candidate)
    candidates.append(EVAL_LOGS_DIR / "evidence_pack.json")

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        evidence_pack = load_optional_json(candidate)
        if evidence_pack:
            return build_passage_lookup(evidence_pack)
    return {}


def chapter_for_passage_id(passage_id: str, passage_lookup: dict[str, dict]) -> int | None:
    normalized = str(passage_id).strip().lower()
    if not normalized:
        return None
    passage = passage_lookup.get(normalized)
    if isinstance(passage, dict):
        return int(passage.get("chapter", 0)) or None
    match = re.search(r"ch(\d+)-p\d+", normalized, re.I)
    if match:
        return int(match.group(1))
    return None


def note_mentions_chapter(note: str, ch: int, passage_lookup: dict[str, dict]) -> bool:
    if chapter_mention_pattern(ch).search(note):
        return True
    for match in PASSAGE_ID_RE.finditer(note):
        if chapter_for_passage_id(match.group(0), passage_lookup) == ch:
            return True
    return False


def passage_excerpt(passage_id: str, passage_lookup: dict[str, dict]) -> str:
    passage = passage_lookup.get(str(passage_id).strip().lower(), {})
    return short_quote(str(passage.get("text", "")), limit=140)


def summarize_dialogue_audit(ch: int, text: str, audit: dict | None) -> dict:
    problem_parts: list[str] = []
    change_items: list[str] = []
    if not audit:
        return {
            "problem_parts": problem_parts,
            "keep_parts": [],
            "change_items": change_items,
        }

    def chapter_records(key: str) -> list[dict]:
        records = audit.get(key, [])
        if not isinstance(records, list):
            return []
        return [record for record in records if isinstance(record, dict) and record.get("chapter") == ch]

    generic_lines = chapter_records("generic_lines")
    if generic_lines:
        line = short_quote(generic_lines[0].get("text", ""))
        append_unique(
            problem_parts,
            f'**Dialogue audit:** generic line flattening speaker identity in this chapter: "{line}"',
        )
        append_unique(
            change_items,
            "Push dialogue toward character-specific pressure, concealment, and concrete stakes instead of generic assent or explanation.",
        )

    theme_perfect_lines = chapter_records("theme_perfect_lines")
    if theme_perfect_lines:
        line = short_quote(theme_perfect_lines[0].get("text", ""))
        append_unique(
            problem_parts,
            f'**Dialogue audit — theme-perfect line:** "{line}"',
        )
        append_unique(
            change_items,
            "Break thesis-clean dialogue into wrong inference, evasion, or partial knowledge so speakers stop sounding like the novel's argument.",
        )

    domain_leaks = chapter_records("metaphor_domain_leakage")
    if domain_leaks:
        leak = domain_leaks[0]
        speaker = str(leak.get("speaker", "A speaker"))
        line = short_quote(leak.get("text", ""))
        other_domains = ", ".join(str(item) for item in leak.get("other_domains", []))
        append_unique(
            problem_parts,
            f'**Dialogue audit — metaphor leakage:** {speaker} borrows another character\'s domain '
            f"({other_domains}): \"{line}\"",
        )
        append_unique(
            change_items,
            "Keep each speaker inside their own metaphor and knowledge domain so the chapter's dialogue remains separable.",
        )

    ceiling_violations = chapter_records("cognitive_ceiling_violations")
    if ceiling_violations:
        violation = ceiling_violations[0]
        speaker = str(violation.get("speaker", "A speaker"))
        line = short_quote(violation.get("text", ""))
        append_unique(
            problem_parts,
            f'**Dialogue audit — cognitive ceiling:** {speaker} overreaches in abstraction: "{line}"',
        )
        append_unique(
            change_items,
            "Lower abstract dialogue until it matches the speaker's cognitive ceiling and lived vocabulary.",
        )

    overlap_records = audit.get("speaker_non_separability", [])
    if isinstance(overlap_records, list):
        for record in overlap_records:
            if not isinstance(record, dict):
                continue
            speakers = [str(speaker) for speaker in record.get("speakers", []) if str(speaker).strip()]
            if speakers and all(re.search(rf"\b{re.escape(speaker)}\b", text) for speaker in speakers):
                append_unique(
                    problem_parts,
                    f"**Dialogue audit — speaker overlap:** {', '.join(speakers)} "
                    f"share a {record.get('overlap', '?')} lexical overlap fingerprint.",
                )
                append_unique(
                    change_items,
                    "Separate overlapping speakers through diction, rhythm, and what each person refuses to say.",
                )
                break

    return {
        "problem_parts": problem_parts,
        "keep_parts": [],
        "change_items": change_items,
    }


def summarize_narration_audit(ch: int, audit: dict | None) -> dict:
    problem_parts: list[str] = []
    change_items: list[str] = []
    if not audit:
        return {
            "problem_parts": problem_parts,
            "keep_parts": [],
            "change_items": change_items,
        }

    examples = audit.get("room_entry_examples", [])
    if not isinstance(examples, list):
        examples = []
    chapter_examples = [
        example for example in examples
        if isinstance(example, dict) and example.get("chapter") == ch
    ]
    if not chapter_examples:
        return {
            "problem_parts": problem_parts,
            "keep_parts": [],
            "change_items": change_items,
        }

    habits: list[str] = []
    repeated_openings = audit.get("repeated_sentence_openings", [])
    if isinstance(repeated_openings, list) and repeated_openings:
        opening = repeated_openings[0]
        habits.append(f"repeated sentence openings ({opening.get('opening', '?')} x{opening.get('count', '?')})")
    repeated_ordering = audit.get("repeated_observation_ordering", [])
    if isinstance(repeated_ordering, list) and repeated_ordering:
        ordering = repeated_ordering[0]
        signature = " -> ".join(str(item) for item in ordering.get("signature", []))
        habits.append(f"repeated observation ordering ({signature} x{ordering.get('count', '?')})")
    repeated_intensifiers = audit.get("repeated_intensifiers", [])
    if isinstance(repeated_intensifiers, list) and repeated_intensifiers:
        token = repeated_intensifiers[0]
        habits.append(f"intensifier habit ({token.get('token', '?')} x{token.get('count', '?')})")

    descriptor = ""
    if habits:
        descriptor = " Manuscript-level habits: " + "; ".join(habits[:3]) + "."

    example_text = short_quote(chapter_examples[0].get("text", ""))
    append_unique(
        problem_parts,
        f'**Narration audit:** Chapter {ch} contains a flagged room-entry template: "{example_text}".{descriptor}',
    )
    append_unique(
        change_items,
        "Change how the scene enters: vary the sentence openings, sensory order, and pressure so formal enactment does not collapse into the same room-entry template.",
    )

    return {
        "problem_parts": problem_parts,
        "keep_parts": [],
        "change_items": change_items,
    }


def summarize_humanity_panel(ch: int, panel: dict | None) -> dict:
    problem_parts: list[str] = []
    keep_parts: list[str] = []
    change_items: list[str] = []
    if not panel:
        return {
            "problem_parts": problem_parts,
            "keep_parts": keep_parts,
            "change_items": change_items,
        }

    passage_lookup = load_humanity_evidence_lookup(panel)
    panelists = panel.get("panelists", {})
    if not isinstance(panelists, dict):
        panelists = {}

    for key, payload in panelists.items():
        if not isinstance(payload, dict):
            continue
        label = PANELIST_LABELS.get(key, str(key).replace("_", " ").title())
        strongest_passage_id = str(payload.get("strongest_passage_id", "")).strip()
        weakest_passage_id = str(payload.get("weakest_passage_id", "")).strip()
        strongest_chapter = chapter_for_passage_id(strongest_passage_id, passage_lookup)
        weakest_chapter = chapter_for_passage_id(weakest_passage_id, passage_lookup)

        if strongest_chapter == ch and strongest_passage_id:
            excerpt = passage_excerpt(strongest_passage_id, passage_lookup)
            if excerpt:
                append_unique(
                    keep_parts,
                    f'Humanity panel — {label} strongest passage: [{strongest_passage_id}] "{excerpt}"',
                )

        notes = payload.get("notes", [])
        if not isinstance(notes, list):
            notes = []
        matching_notes = [
            str(note).strip()
            for note in notes
            if isinstance(note, str) and note_mentions_chapter(note, ch, passage_lookup)
        ]
        issue = ""
        if weakest_chapter == ch:
            if key == "novelist":
                issue = str(payload.get("overdesigned", "")).strip()
            elif key == "dramatist":
                issue = str(payload.get("social_dramatic_failure", "")).strip()
            elif key == "oral_reader":
                issue = str(payload.get("oral_reading_issue", "")).strip()
        if not issue and matching_notes:
            issue = matching_notes[0]

        if issue:
            append_unique(problem_parts, f"**Humanity panel — {label}:** {issue}")
            if key == "novelist":
                append_unique(
                    change_items,
                    "Restore surplus life and let the scene carry more than the book's argument; reduce overdesigned thematic emphasis.",
                )
            elif key == "dramatist":
                append_unique(
                    change_items,
                    "Make the exchange a social event with concealment, status pressure, and wrong inference rather than clean information transfer.",
                )
            elif key == "oral_reader":
                append_unique(
                    change_items,
                    "Rewrite the aloud-failing passage for breath, torque, and mouth-feel until it survives oral reading.",
                )

    return {
        "problem_parts": problem_parts,
        "keep_parts": keep_parts,
        "change_items": change_items,
    }


def summarize_revision_audits(ch: int, text: str) -> dict:
    combined = {
        "problem_parts": [],
        "keep_parts": [],
        "change_items": [],
    }
    summaries = [
        summarize_dialogue_audit(ch, text, load_dialogue_audit()),
        summarize_narration_audit(ch, load_narration_audit()),
        summarize_humanity_panel(ch, load_humanity_panel()),
    ]
    for summary in summaries:
        for key in combined:
            for item in summary[key]:
                append_unique(combined[key], item)
    return combined


def extend_numbered_changes(
    change_parts: list[str],
    change_num: int,
    items: list[str],
) -> int:
    for item in items:
        change_parts.append(f"{change_num}. {item}")
        change_num += 1
    return change_num


# ---------------------------------------------------------------------------
# panel feedback extraction
# ---------------------------------------------------------------------------

def panel_mentions_for_chapter(panel: dict, ch: int) -> dict:
    """Extract all reader comments that mention this chapter."""
    readers = panel.get("readers", {})
    disagreements = panel.get("disagreements", [])

    mentions: dict[str, list[str]] = {
        "momentum_loss": [],
        "worst_scene": [],
        "cut_candidate": [],
        "best_scene": [],
        "thinnest_character": [],
        "missing_scene": [],
        "earned_ending": [],
    }

    # Use word-boundary regex so "Chapter 2" doesn't match "Chapter 21"
    ch_re = re.compile(
        rf"\b(?:Chapter|Ch\.?)\s*{ch}\b", re.I
    )

    for reader_name, reader_data in readers.items():
        for key in mentions:
            text = reader_data.get(key, "")
            if ch_re.search(text):
                mentions[key].append(f"[{reader_name}] {text}")

    # Also check disagreements for this chapter
    flagged_issues: list[str] = []
    for d in disagreements:
        if d.get("chapter") == ch:
            q = d.get("question", "")
            flagged = d.get("flagged_by", [])
            count = len(flagged)
            flagged_issues.append(
                f"{q}: flagged by {count}/4 readers ({', '.join(flagged)})"
            )

    return {
        "mentions": mentions,
        "flagged_issues": flagged_issues,
    }


# ---------------------------------------------------------------------------
# brief generators
# ---------------------------------------------------------------------------

def build_panel_brief(ch: int) -> str:
    panel = load_panel()
    if panel is None:
        sys.exit("ERROR: edit_logs/reader_panel.json not found")

    text = chapter_text(ch)
    title = chapter_title(text)
    wc = word_count(text)
    info = panel_mentions_for_chapter(panel, ch)
    mentions = info["mentions"]
    flagged = info["flagged_issues"]
    voice_rules = extract_voice_rules()

    # Determine brief type from dominant issue
    negative_keys = ["momentum_loss", "worst_scene", "cut_candidate"]
    neg_count = sum(len(mentions[k]) for k in negative_keys)
    if len(mentions["cut_candidate"]) > 0:
        brief_type = "COMPRESS"
    elif len(mentions["worst_scene"]) > 0:
        brief_type = "DRAMATIZE"
    elif len(mentions["momentum_loss"]) > 0:
        brief_type = "TIGHTEN"
    else:
        brief_type = "REVISE"

    # Build PROBLEM section
    problem_parts: list[str] = []
    if flagged:
        problem_parts.append(
            "Panel disagreement flags for this chapter:\n"
            + "\n".join(f"- {f}" for f in flagged)
        )
    for key in negative_keys:
        if mentions[key]:
            problem_parts.append(f"### {key.replace('_', ' ').title()}")
            for m in mentions[key]:
                # Truncate very long quotes to ~400 chars for readability
                if len(m) > 500:
                    m = m[:500] + "..."
                problem_parts.append(m)

    if not problem_parts:
        problem_parts.append(
            f"No specific negative feedback for Chapter {ch} from the reader panel. "
            "Consider cross-referencing with --eval or --cuts for targeted feedback."
        )

    # Build WHAT TO KEEP section
    keep_parts: list[str] = []
    if mentions["best_scene"]:
        for m in mentions["best_scene"]:
            if len(m) > 500:
                m = m[:500] + "..."
            keep_parts.append(m)
    # Check cuts file for tightest_passage
    cuts_data = load_cuts(ch)
    patch_directives = build_patch_directives_from_cuts(
        cuts_data,
        limit=6,
        allowed_types={"REDUNDANT", "OVER-EXPLAIN", "FAT", "TELL", "GENERIC"},
    )
    if cuts_data and cuts_data.get("tightest_passage"):
        keep_parts.append(
            f'Tightest passage (from adversarial edit): "{cuts_data["tightest_passage"]}"'
        )
    # Check per-chapter eval for strongest sentences
    ch_eval_path = latest_chapter_eval(ch)
    if ch_eval_path:
        ch_eval = load_json(ch_eval_path)
        strongest = ch_eval.get("three_strongest_sentences", [])
        if strongest:
            keep_parts.append("Strongest sentences (from eval):")
            for s in strongest:
                keep_parts.append(f'- "{s}"')

    if not keep_parts:
        keep_parts.append(
            f"(No specific 'best' mentions for Chapter {ch}. "
            "Review the chapter for its strongest passages before revising.)"
        )

    # Build WHAT TO CHANGE section
    change_parts: list[str] = []
    change_num = 1

    # From momentum_loss
    for m in mentions["momentum_loss"]:
        # Extract actionable suggestion if present
        change_parts.append(
            f"{change_num}. **Pacing**: Address momentum loss identified by panel — "
            "tighten or restructure the scenes that drag."
        )
        change_num += 1
        break  # one entry is enough

    # From worst_scene
    for m in mentions["worst_scene"]:
        # Try to extract the fix suggestion — look for "Fix:" or "The fix is"
        fix_match = re.search(
            r"(?:The fix(?:\s+is\s*\w*)?|Fix)\s*[:—]\s*(.+)",
            m, re.I | re.DOTALL
        )
        if fix_match:
            # Take up to ~300 chars of the fix suggestion
            raw_fix = fix_match.group(1).strip()
            fix_text = (raw_fix[:300] + "...") if len(raw_fix) > 300 else raw_fix
            fix_text = fix_text.rstrip(".")
        else:
            # Fall back to the full worst_scene comment, truncated
            raw = m.split("]", 1)[-1].strip() if "]" in m else m
            fix_text = (raw[:300] + "...") if len(raw) > 300 else raw
        change_parts.append(f"{change_num}. **Dramatize**: {fix_text}")
        change_num += 1
        break

    # From cut_candidate
    for m in mentions["cut_candidate"]:
        change_parts.append(
            f"{change_num}. **Compress**: Panel identifies this chapter as a cut candidate. "
            "Fold essential beats into fewer words; eliminate repeated exposition."
        )
        change_num += 1
        break

    # From thinnest_character
    if mentions["thinnest_character"]:
        change_parts.append(
            f"{change_num}. **Deepen character**: Panel flags thin characterization in this chapter. "
            "Add interiority, physical specificity, or a complicating moment."
        )
        change_num += 1

    # From missing_scene
    if mentions["missing_scene"]:
        change_parts.append(
            f"{change_num}. **Add missing beat**: Panel identifies a scene gap near this chapter."
        )
        for m in mentions["missing_scene"]:
            snippet = m[:300] + "..." if len(m) > 300 else m
            change_parts.append(f"   {snippet}")
        change_num += 1

    if not change_parts:
        change_parts.append(
            "No specific changes derived from panel. "
            "Consider combining with --eval or --cuts for concrete revision items."
        )

    # Determine word count target
    if brief_type == "COMPRESS":
        target_wc = int(wc * 0.55)
        target_note = f"~{target_wc} words (compress from current {wc})"
    elif brief_type == "DRAMATIZE":
        target_wc = wc  # restructure, not expand
        target_note = f"~{target_wc} words (restructure, roughly same length)"
    elif brief_type == "TIGHTEN":
        target_wc = int(wc * 0.85)
        target_note = f"~{target_wc} words (tighten from current {wc})"
    else:
        target_note = f"~{wc} words (current length, unless changes dictate otherwise)"

    # Assemble
    brief = f"# Revision Brief: Chapter {ch} — {title} ({brief_type})\n\n"
    brief += "## PROBLEM\n"
    brief += "\n\n".join(problem_parts) + "\n\n"
    brief += "## WHAT TO KEEP\n"
    brief += "\n".join(keep_parts) + "\n\n"
    brief += "## WHAT TO CHANGE\n"
    brief += "\n".join(change_parts) + "\n\n"
    brief += "## VOICE RULES\n"
    brief += "\n".join(f"- {r}" for r in voice_rules) + "\n\n"
    brief += "## TARGET\n"
    brief += target_note + "\n"

    return append_patch_directives_section(brief, patch_directives)


def build_eval_brief(ch: int) -> str:
    # Try per-chapter eval first, fall back to full eval
    ch_eval_path = latest_chapter_eval(ch)
    full_eval_path = latest_full_eval()

    if ch_eval_path is None and full_eval_path is None:
        sys.exit(f"ERROR: no eval logs found for chapter {ch}")

    text = chapter_text(ch)
    title = chapter_title(text)
    wc = word_count(text)
    voice_rules = extract_voice_rules()
    patch_directives: list[str] = []
    problem_parts: list[str] = []
    keep_parts: list[str] = []
    change_parts: list[str] = []
    change_num = 1

    ch_eval = load_json(ch_eval_path) if ch_eval_path else None
    full_eval = load_json(full_eval_path) if full_eval_path else None

    if ch_eval:
        ch_summary = summarize_chapter_eval(ch_eval)
        problem_parts.extend(ch_summary["problem_parts"])
        keep_parts.extend(ch_summary["keep_parts"])
        change_num = extend_numbered_changes(change_parts, change_num, ch_summary["change_items"])

    if full_eval:
        full_summary = summarize_full_eval_for_chapter(
            full_eval,
            ch,
            strongest_header=False,
        )
        for item in full_summary["problem_parts"]:
            append_unique(problem_parts, item)
        weakest_chapter = full_eval.get("weakest_chapter")
        if weakest_chapter == ch or ch_eval is None:
            change_num = extend_numbered_changes(change_parts, change_num, full_summary["change_items"])

    audit_summary = summarize_revision_audits(ch, text)
    for item in audit_summary["problem_parts"]:
        append_unique(problem_parts, item)
    for item in audit_summary["keep_parts"]:
        append_unique(keep_parts, item)
    change_num = extend_numbered_changes(change_parts, change_num, audit_summary["change_items"])

    # Tightest passage from cuts
    cuts_data = load_cuts(ch)
    if cuts_data and cuts_data.get("tightest_passage"):
        append_unique(
            keep_parts,
            f'Tightest passage (adversarial edit): "{cuts_data["tightest_passage"]}"',
        )
    patch_directives = build_patch_directives_from_cuts(
        cuts_data,
        limit=6,
        allowed_types={"REDUNDANT", "OVER-EXPLAIN", "FAT", "TELL", "GENERIC"},
    )

    if not keep_parts:
        keep_parts.append("(Review chapter for strongest passages before revising.)")

    if not change_parts:
        change_parts.append("(No specific revision items from eval. Check --panel or --cuts.)")

    # Determine type from eval
    if ch_eval:
        overall = ch_eval.get("overall_score", 10)
        if overall <= 5:
            brief_type = "REWRITE"
        elif overall <= 7:
            brief_type = "FIX"
        else:
            brief_type = "POLISH"
    else:
        brief_type = "FIX"

    target_note = f"~{wc} words (current length: {wc}; adjust based on revision scope)"

    brief = f"# Revision Brief: Chapter {ch} — {title} ({brief_type})\n\n"
    brief += "## PROBLEM\n"
    brief += "\n\n".join(problem_parts) + "\n\n"
    brief += "## WHAT TO KEEP\n"
    brief += "\n".join(keep_parts) + "\n\n"
    brief += "## WHAT TO CHANGE\n"
    brief += "\n".join(change_parts) + "\n\n"
    brief += "## VOICE RULES\n"
    brief += "\n".join(f"- {r}" for r in voice_rules) + "\n\n"
    brief += "## TARGET\n"
    brief += target_note + "\n"

    return append_patch_directives_section(brief, patch_directives)


def build_cuts_brief(ch: int) -> str:
    cuts_data = load_cuts(ch)
    if cuts_data is None:
        sys.exit(f"ERROR: edit_logs/ch{ch:02d}_cuts.json not found")

    text = chapter_text(ch)
    title = chapter_title(text)
    wc = word_count(text)
    voice_rules = extract_voice_rules()

    cuts = cuts_data.get("cuts", [])
    total_cuttable = cuts_data.get("total_cuttable_words", 0)
    tightest = cuts_data.get("tightest_passage", "")
    loosest = cuts_data.get("loosest_passage", "")
    fat_pct = cuts_data.get("overall_fat_percentage", 0)
    verdict = cuts_data.get("one_sentence_verdict", "")
    patch_directives = build_patch_directives_from_cuts(cuts_data, limit=12)

    # Categorize cuts by type
    cut_types: dict[str, list[dict]] = {}
    for c in cuts:
        t = c.get("type", "OTHER")
        cut_types.setdefault(t, []).append(c)

    # Determine dominant pattern
    type_counts = {t: len(cs) for t, cs in cut_types.items()}
    dominant = max(type_counts, key=type_counts.get) if type_counts else "MIXED"

    brief_type = "TIGHTEN"

    # PROBLEM
    problem_parts: list[str] = []
    problem_parts.append(
        f"Adversarial edit found **{total_cuttable} cuttable words** "
        f"({fat_pct}% fat) across {len(cuts)} passages."
    )
    if verdict:
        problem_parts.append(f"Verdict: {verdict}")

    problem_parts.append(f"\nDominant cut pattern: **{dominant}** ({type_counts.get(dominant, 0)} instances)")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        if t != dominant:
            problem_parts.append(f"- {t}: {count} instances")

    if loosest:
        problem_parts.append(f'\n**Loosest passage:**\n> {loosest}')

    # WHAT TO KEEP
    keep_parts: list[str] = []
    if tightest:
        keep_parts.append(f'**Tightest passage** (do not touch):\n> {tightest}')

    # Also pull strongest sentences from eval if available
    ch_eval_path = latest_chapter_eval(ch)
    if ch_eval_path:
        ch_eval = load_json(ch_eval_path)
        strongest = ch_eval.get("three_strongest_sentences", [])
        if strongest:
            keep_parts.append("\nStrongest sentences (from eval):")
            for s in strongest:
                keep_parts.append(f'- "{s}"')

    if not keep_parts:
        keep_parts.append("(Review chapter for strongest passages before revising.)")

    # WHAT TO CHANGE — specific numbered items from each cut
    change_parts: list[str] = []
    change_num = 1

    # Group by type for clarity
    for cut_type in ["REDUNDANT", "OVER-EXPLAIN", "FAT", "TELL", "GENERIC", "OTHER"]:
        type_cuts = cut_types.get(cut_type, [])
        if not type_cuts:
            continue
        change_parts.append(f"\n### {cut_type} ({len(type_cuts)} cuts)")
        for c in type_cuts:
            quote = c.get("quote", "")
            reason = c.get("reason", "")
            action = c.get("action", "CUT")
            rewrite = c.get("rewrite")

            # Truncate very long quotes
            if len(quote) > 200:
                quote = quote[:200] + "..."

            entry = f'{change_num}. `"{quote}"`\n'
            entry += f"   Reason: {reason}\n"
            if action == "REWRITE" and rewrite:
                entry += f'   → Rewrite as: "{rewrite}"'
            elif action == "CUT":
                entry += "   → Cut entirely"
            change_parts.append(entry)
            change_num += 1

    # Word count target
    target_wc = wc - total_cuttable
    target_note = (
        f"~{target_wc} words (cut ~{total_cuttable} from current {wc}). "
        f"Tighten {fat_pct}% fat without losing the chapter's strongest beats."
    )

    brief = f"# Revision Brief: Chapter {ch} — {title} ({brief_type})\n\n"
    brief += "## PROBLEM\n"
    brief += "\n".join(problem_parts) + "\n\n"
    brief += "## WHAT TO KEEP\n"
    brief += "\n".join(keep_parts) + "\n\n"
    brief += "## WHAT TO CHANGE\n"
    brief += "\n".join(change_parts) + "\n\n"
    brief += "## VOICE RULES\n"
    brief += "\n".join(f"- {r}" for r in voice_rules) + "\n\n"
    brief += "## TARGET\n"
    brief += target_note + "\n"

    return append_patch_directives_section(brief, patch_directives)


def build_auto_brief() -> tuple[int, str]:
    """Auto-detect weakest chapter and build a combined brief."""
    full_eval_path = latest_full_eval()
    if full_eval_path is None:
        sys.exit("ERROR: no *_full.json found in eval_logs/")

    full_eval = load_json(full_eval_path)
    ch = full_eval.get("weakest_chapter")
    if ch is None:
        sys.exit("ERROR: full eval does not contain 'weakest_chapter'")

    print(f"Auto-detected weakest chapter: {ch}", file=sys.stderr)
    print(f"  Source: {full_eval_path.name}", file=sys.stderr)

    text = chapter_text(ch)
    title = chapter_title(text)
    wc = word_count(text)
    voice_rules = extract_voice_rules()

    problem_parts: list[str] = []
    keep_parts: list[str] = []
    change_parts: list[str] = []
    patch_directives: list[str] = []
    change_num = 1

    full_summary = summarize_full_eval_for_chapter(
        full_eval,
        ch,
        strongest_header=True,
    )
    problem_parts.extend(full_summary["problem_parts"])

    # Per-chapter eval
    ch_eval_path = latest_chapter_eval(ch)
    ch_eval = load_json(ch_eval_path) if ch_eval_path else None
    if ch_eval:
        ch_summary = summarize_chapter_eval(ch_eval)
        for item in ch_summary["problem_parts"]:
            append_unique(problem_parts, item)
        for item in ch_summary["keep_parts"]:
            append_unique(keep_parts, item)
        change_num = extend_numbered_changes(change_parts, change_num, ch_summary["change_items"])

    audit_summary = summarize_revision_audits(ch, text)
    for item in audit_summary["problem_parts"]:
        append_unique(problem_parts, item)
    for item in audit_summary["keep_parts"]:
        append_unique(keep_parts, item)
    change_num = extend_numbered_changes(change_parts, change_num, audit_summary["change_items"])

    # Panel cross-reference
    panel = load_panel()
    if panel:
        info = panel_mentions_for_chapter(panel, ch)
        mentions = info["mentions"]
        flagged = info["flagged_issues"]
        if flagged:
            append_unique(problem_parts, "**Panel flags:**")
            for f in flagged:
                append_unique(problem_parts, f"- {f}")

        for key in ["worst_scene", "momentum_loss", "cut_candidate"]:
            if mentions[key]:
                append_unique(problem_parts, f"**Panel — {key.replace('_', ' ')}:**")
                for m in mentions[key]:
                    snippet = m[:400] + "..." if len(m) > 400 else m
                    append_unique(problem_parts, snippet)

        if mentions["best_scene"]:
            for m in mentions["best_scene"]:
                snippet = m[:400] + "..." if len(m) > 400 else m
                append_unique(keep_parts, f"Panel best scene mention: {snippet}")

    # Cuts data
    cuts_data = load_cuts(ch)
    if cuts_data:
        total_cuttable = cuts_data.get("total_cuttable_words", 0)
        fat_pct = cuts_data.get("overall_fat_percentage", 0)
        tightest = cuts_data.get("tightest_passage", "")
        verdict = cuts_data.get("one_sentence_verdict", "")
        patch_directives = build_patch_directives_from_cuts(
            cuts_data,
            limit=6,
            allowed_types={"REDUNDANT", "OVER-EXPLAIN", "FAT", "TELL", "GENERIC"},
        )

        if total_cuttable:
            append_unique(
                problem_parts,
                f"**Adversarial edit:** {total_cuttable} cuttable words ({fat_pct}% fat). "
                f"{verdict}",
            )
        if tightest:
            append_unique(keep_parts, f"Tightest passage (adversarial edit):\n> {tightest}")

        # Add top cuts as change items
        cuts_list = cuts_data.get("cuts", [])
        # Only include the most impactful — REDUNDANT and OVER-EXPLAIN
        priority_cuts = [c for c in cuts_list if c.get("type") in ("REDUNDANT", "OVER-EXPLAIN")]
        for c in priority_cuts[:5]:
            quote = c.get("quote", "")[:150]
            reason = c.get("reason", "")
            action = c.get("action", "CUT")
            rewrite = c.get("rewrite")
            entry = f'{change_num}. `"{quote}..."` — {reason}'
            if action == "REWRITE" and rewrite:
                entry += f'\n   → Rewrite as: "{rewrite}"'
            elif action == "CUT":
                entry += "\n   → Cut entirely"
            change_parts.append(entry)
            change_num += 1

    change_num = extend_numbered_changes(change_parts, change_num, full_summary["change_items"])

    if not keep_parts:
        keep_parts.append("(Review chapter for strongest passages before revising.)")
    if not change_parts:
        change_parts.append("(No specific changes auto-detected. Manual review recommended.)")

    # Determine brief type
    brief_type = "AUTO-FIX"

    target_note = f"~{wc} words (current: {wc}; adjust based on revision scope)"

    brief = f"# Revision Brief: Chapter {ch} — {title} ({brief_type})\n\n"
    brief += "## PROBLEM\n"
    brief += "\n\n".join(problem_parts) + "\n\n"
    brief += "## WHAT TO KEEP\n"
    brief += "\n".join(keep_parts) + "\n\n"
    brief += "## WHAT TO CHANGE\n"
    brief += "\n".join(change_parts) + "\n\n"
    brief += "## VOICE RULES\n"
    brief += "\n".join(f"- {r}" for r in voice_rules) + "\n\n"
    brief += "## TARGET\n"
    brief += target_note + "\n"

    return ch, append_patch_directives_section(brief, patch_directives)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Auto-generate revision briefs from feedback sources."
    )
    parser.add_argument("--panel", type=int, metavar="CH",
                        help="Generate brief from reader panel feedback for chapter CH")
    parser.add_argument("--eval", type=int, metavar="CH",
                        help="Generate brief from eval callouts for chapter CH")
    parser.add_argument("--cuts", type=int, metavar="CH",
                        help="Generate brief from adversarial cuts for chapter CH")
    parser.add_argument("--auto", action="store_true",
                        help="Auto-detect weakest chapter and generate combined brief")
    parser.add_argument(
        "--require-patch-directives",
        action="store_true",
        help="Fail if the generated brief does not contain an actionable patch-directives section.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print brief to stdout without saving")

    args = parser.parse_args()

    # Validate: exactly one mode
    modes = sum([
        args.panel is not None,
        args.eval is not None,
        args.cuts is not None,
        args.auto,
    ])
    if modes == 0:
        parser.print_help()
        sys.exit(1)
    if modes > 1:
        sys.exit("ERROR: specify exactly one of --panel, --eval, --cuts, --auto")

    # Generate
    if args.panel is not None:
        ch = args.panel
        brief_text = build_panel_brief(ch)
        suffix = "panel"
    elif args.eval is not None:
        ch = args.eval
        brief_text = build_eval_brief(ch)
        suffix = "eval"
    elif args.cuts is not None:
        ch = args.cuts
        brief_text = build_cuts_brief(ch)
        suffix = "cuts"
    else:  # --auto
        ch, brief_text = build_auto_brief()
        suffix = "auto"

    if args.require_patch_directives and not has_patch_directives(brief_text):
        sys.exit(
            "ERROR: generated brief is not patch-friendly; no actionable patch directives "
            "were available from the current evidence."
        )

    if args.dry_run:
        print(brief_text)
        return

    # Save
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BRIEFS_DIR / f"ch{ch:02d}_{suffix}.md"
    out_path.write_text(brief_text, encoding="utf-8")
    print(f"Saved: {out_path}", file=sys.stderr)
    print(f"Chapter: {ch}", file=sys.stderr)
    print(f"Type: {suffix}", file=sys.stderr)
    print(f"Brief length: {word_count(brief_text)} words", file=sys.stderr)


if __name__ == "__main__":
    main()
