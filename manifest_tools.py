#!/usr/bin/env python3
"""Shared manifest and consistency helpers for the orchestrator."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from evidence_tools import compute_sha256, load_json
from planning_split import parse_arc_outline, parse_chapter_cards

BASE_DIR = Path(__file__).resolve().parent
CHAPTERS_DIR = BASE_DIR / "chapters"
EVAL_LOG_DIR = BASE_DIR / "eval_logs"
EDIT_LOG_DIR = BASE_DIR / "edit_logs"
MANIFEST_PATH = BASE_DIR / "manifest.json"

MANIFEST_VERSION = 1

FILE_KEYS = {
    "seed": Path("seed.txt"),
    "world": Path("world.md"),
    "characters": Path("characters.md"),
    "character_engine": Path("character_engine.json"),
    "perspective": Path("perspective.md"),
    "voice": Path("voice.md"),
    "voice_discovery": Path("voice_discovery.json"),
    "arc_outline": Path("arc_outline.md"),
    "chapter_cards": Path("chapter_cards.md"),
    "thread_registry": Path("thread_registry.json"),
    "canon": Path("canon.md"),
    "outline": Path("outline.md"),
    "arc_summary": Path("arc_summary.md"),
    "manuscript": Path("manuscript.md"),
    "state": Path("state.json"),
    "reviews": Path("reviews.md"),
    "voice_fingerprint": Path("edit_logs/voice_fingerprint.json"),
    "reader_panel": Path("edit_logs/reader_panel.json"),
    "humanity_panel": Path("edit_logs/humanity_panel.json"),
    "dialogue_audit": Path("edit_logs/dialogue_audit.json"),
    "narration_audit": Path("edit_logs/narration_audit.json"),
    "evidence_pack": Path("eval_logs/evidence_pack.json"),
}

PHASE_REQUIREMENTS = {
    "foundation": [
        "seed",
        "world",
        "characters",
        "character_engine",
        "perspective",
        "voice",
        "arc_outline",
        "chapter_cards",
        "thread_registry",
        "canon",
    ],
    "drafting": [
        "world",
        "characters",
        "character_engine",
        "perspective",
        "voice",
        "arc_outline",
        "chapter_cards",
        "thread_registry",
        "canon",
    ],
    "revision": [
        "chapter_cards",
        "thread_registry",
        "reader_panel",
        "humanity_panel",
        "dialogue_audit",
        "narration_audit",
        "evidence_pack",
    ],
    "review": [
        "reviews",
    ],
    "export": [
        "outline",
        "arc_summary",
        "manuscript",
    ],
}


def safe_load_json(path: Path, default: Any) -> Any:
    try:
        return load_json(path)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def relative_path(path: Path, base_dir: Path = BASE_DIR) -> str:
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def chapter_paths(base_dir: Path = BASE_DIR) -> list[Path]:
    return sorted((base_dir / "chapters").glob("ch_*.md"))


def chapter_numbers(base_dir: Path = BASE_DIR) -> list[int]:
    numbers: list[int] = []
    for path in chapter_paths(base_dir):
        match = re.search(r"ch_(\d+)\.md$", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return numbers


def chapter_word_count(base_dir: Path = BASE_DIR) -> int:
    return sum(len(path.read_text(encoding="utf-8").split()) for path in chapter_paths(base_dir))


def manuscript_text(base_dir: Path = BASE_DIR) -> str:
    parts = [path.read_text(encoding="utf-8").strip() for path in chapter_paths(base_dir)]
    parts = [part for part in parts if part]
    return "\n\n".join(parts)


def planned_chapter_count(base_dir: Path = BASE_DIR) -> int:
    chapter_cards_path = base_dir / "chapter_cards.md"
    if chapter_cards_path.exists():
        cards = parse_chapter_cards(chapter_cards_path.read_text(encoding="utf-8"))
        if cards:
            return len(cards)

    state_path = base_dir / "state.json"
    state = safe_load_json(state_path, {})
    if isinstance(state, dict):
        total = state.get("chapters_total")
        if isinstance(total, int) and total > 0:
            return total

    outline_path = base_dir / "outline.md"
    if outline_path.exists():
        matches = re.findall(r"^###\s*Ch(?:apter)?\s*(\d+)", outline_path.read_text(encoding="utf-8"), re.MULTILINE)
        if matches:
            return max(int(item) for item in matches)

    return len(chapter_paths(base_dir))


def risk_chapters(base_dir: Path = BASE_DIR) -> list[int]:
    chapter_cards_path = base_dir / "chapter_cards.md"
    risks: set[int] = set()
    if chapter_cards_path.exists():
        for card in parse_chapter_cards(chapter_cards_path.read_text(encoding="utf-8")):
            if str(card.get("risk", "none")).strip().lower() != "none":
                risks.add(int(card.get("number", 0)))

    arc_path = base_dir / "arc_outline.md"
    if arc_path.exists():
        arc = parse_arc_outline(arc_path.read_text(encoding="utf-8"))
        for chapter in arc.get("candidate_risk_chapters", []):
            try:
                risks.add(int(chapter))
            except (TypeError, ValueError):
                continue

    return sorted(chapter for chapter in risks if chapter > 0)


def derive_title(base_dir: Path = BASE_DIR) -> str:
    manifest = safe_load_json(base_dir / "manifest.json", {})
    if isinstance(manifest, dict) and manifest.get("title"):
        return str(manifest["title"])

    arc_path = base_dir / "arc_outline.md"
    if arc_path.exists():
        arc = parse_arc_outline(arc_path.read_text(encoding="utf-8"))
        title = str(arc.get("title", "")).strip()
        if title:
            return title

    for candidate in (base_dir / "outline.md", base_dir / "chapters" / "ch_01.md"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped.removeprefix("# ").strip()
    return ""


def files_index(base_dir: Path = BASE_DIR) -> dict[str, str]:
    files: dict[str, str] = {}
    for key, rel in FILE_KEYS.items():
        path = base_dir / rel
        if path.exists():
            files[key] = relative_path(path, base_dir)

    scene_options = sorted((base_dir / "scene_options").glob("ch_*.json"))
    if scene_options:
        files["scene_options_dir"] = relative_path(base_dir / "scene_options", base_dir)
        files["scene_options_latest"] = relative_path(scene_options[-1], base_dir)

    story_states = sorted((base_dir / "state" / "story_state").glob("ch_*.json"))
    if story_states:
        files["story_state_dir"] = relative_path(base_dir / "state" / "story_state", base_dir)
        files["story_state_latest"] = relative_path(story_states[-1], base_dir)

    variants = sorted((base_dir / "chapters" / "variants").glob("ch_*_variant_*.md"))
    if variants:
        files["variants_dir"] = relative_path(base_dir / "chapters" / "variants", base_dir)
        files["variant_latest"] = relative_path(variants[-1], base_dir)

    chapter_files = chapter_paths(base_dir)
    if chapter_files:
        files["chapters_dir"] = relative_path(base_dir / "chapters", base_dir)
        files["chapter_first"] = relative_path(chapter_files[0], base_dir)
        files["chapter_latest"] = relative_path(chapter_files[-1], base_dir)

    return files


def hash_index(base_dir: Path = BASE_DIR, files: dict[str, str] | None = None) -> dict[str, str]:
    files = files or files_index(base_dir)
    hashes: dict[str, str] = {}
    for key, rel in files.items():
        if key.endswith("_dir"):
            continue
        path = base_dir / rel
        if path.exists() and path.is_file():
            hashes[key] = compute_sha256(path.read_text(encoding="utf-8"))
    return hashes


def evidence_pack_info(base_dir: Path = BASE_DIR) -> dict[str, str]:
    evidence_path = base_dir / "eval_logs" / "evidence_pack.json"
    if not evidence_path.exists():
        return {
            "path": "",
            "sha256": "",
            "manuscript_hash": "",
            "generated_at": "",
        }

    payload = safe_load_json(evidence_path, {})
    generated_from = payload.get("generated_from", {}) if isinstance(payload, dict) else {}
    return {
        "path": relative_path(evidence_path, base_dir),
        "sha256": compute_sha256(evidence_path.read_text(encoding="utf-8")),
        "manuscript_hash": str(generated_from.get("manuscript_sha256", "")),
        "generated_at": str(payload.get("generated_at", "")),
    }


def current_models() -> dict[str, str]:
    judge = os.environ.get("AUTONOVEL_JUDGE_MODEL", "claude-opus-4-6")
    writer = os.environ.get("AUTONOVEL_WRITER_MODEL", "claude-sonnet-4-6")
    smell = os.environ.get("AUTONOVEL_SMELL_MODEL", judge)
    review = os.environ.get("AUTONOVEL_REVIEW_MODEL", "claude-opus-4-6")
    full_rewrite = os.environ.get("AUTONOVEL_FULL_REWRITE_MODEL", writer)
    return {
        "writer": writer,
        "judge": judge,
        "smell": smell,
        "review": review,
        "full_rewrite": full_rewrite,
    }


def build_manifest_payload(base_dir: Path = BASE_DIR, *, phase: str | None = None, chapter: int | None = None) -> dict[str, Any]:
    files = files_index(base_dir)
    chapter_count = len(chapter_paths(base_dir))
    payload = {
        "manifest_version": MANIFEST_VERSION,
        "title": derive_title(base_dir),
        "phase": phase or str(safe_load_json(base_dir / "state.json", {}).get("phase", "foundation")),
        "chapter_count": chapter_count,
        "planned_chapter_count": planned_chapter_count(base_dir),
        "word_count": chapter_word_count(base_dir),
        "risk_chapters": risk_chapters(base_dir),
        "current_chapter": chapter,
        "files": files,
        "hashes": hash_index(base_dir, files),
        "models": current_models(),
        "evidence_pack": evidence_pack_info(base_dir),
        "generated_at": datetime.now().isoformat(),
    }
    return payload


def save_manifest(payload: dict[str, Any], path: Path = MANIFEST_PATH) -> Path:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return safe_load_json(path, {})


def missing_required_artifacts(manifest: dict[str, Any], phase: str, chapter: int | None = None) -> list[str]:
    files = manifest.get("files", {})
    missing = [key for key in PHASE_REQUIREMENTS.get(phase, []) if key not in files]
    if phase == "drafting" and chapter is not None:
        chapter_rel = f"chapters/ch_{chapter:02d}.md"
        if chapter_rel not in files.values():
            missing.append(f"chapter_{chapter:02d}")
        scene_option_rel = f"scene_options/ch_{chapter:02d}.json"
        if scene_option_rel not in files.values():
            missing.append(f"scene_options_{chapter:02d}")
        if chapter > 1:
            state_rel = f"state/story_state/ch_{chapter - 1:02d}.json"
            if state_rel not in files.values():
                missing.append(f"story_state_{chapter - 1:02d}")
    return missing


def outline_card_count(base_dir: Path = BASE_DIR) -> int:
    outline_path = base_dir / "outline.md"
    if not outline_path.exists():
        return 0
    matches = re.findall(r"^###\s*Ch(?:apter)?\s*(\d+)", outline_path.read_text(encoding="utf-8"), re.MULTILINE)
    return len(matches)


def outline_titles(base_dir: Path = BASE_DIR) -> dict[int, str]:
    outline_path = base_dir / "outline.md"
    if not outline_path.exists():
        return {}
    titles: dict[int, str] = {}
    pattern = re.compile(r"^###\s*Ch(?:apter)?\s*(\d+)\s*:\s*(.+)$", re.MULTILINE)
    for match in pattern.finditer(outline_path.read_text(encoding="utf-8")):
        titles[int(match.group(1))] = match.group(2).strip()
    return titles


def collect_consistency_issues(
    base_dir: Path = BASE_DIR,
    manifest: dict[str, Any] | None = None,
    *,
    phase: str | None = None,
    chapter: int | None = None,
) -> list[str]:
    manifest = manifest or load_manifest(base_dir / "manifest.json")
    issues: list[str] = []
    active_phase = phase or str(manifest.get("phase", "foundation"))

    chapter_count = len(chapter_paths(base_dir))
    if manifest.get("chapter_count") != chapter_count:
        issues.append(
            f"manifest chapter_count={manifest.get('chapter_count')} does not match chapter files={chapter_count}"
        )

    word_count = chapter_word_count(base_dir)
    if manifest.get("word_count") != word_count:
        issues.append(
            f"manifest word_count={manifest.get('word_count')} does not match chapter word count={word_count}"
        )

    planned_count = planned_chapter_count(base_dir)
    if manifest.get("planned_chapter_count") != planned_count:
        issues.append(
            "manifest planned_chapter_count does not match chapter cards/outline derived total"
        )

    missing = missing_required_artifacts(manifest, active_phase, chapter=chapter)
    if missing:
        issues.append(f"missing required artifacts for phase {active_phase}: {', '.join(missing)}")

    evidence = manifest.get("evidence_pack", {}) if isinstance(manifest.get("evidence_pack"), dict) else {}
    current_manuscript_hash = compute_sha256(manuscript_text(base_dir))
    evidence_path = str(evidence.get("path", "")).strip()
    if evidence_path:
        if evidence.get("manuscript_hash") != current_manuscript_hash:
            issues.append("evidence pack manuscript hash does not match current manuscript")
    elif active_phase in {"revision", "review", "export"}:
        issues.append(f"phase {active_phase} requires an evidence pack but manifest has none")

    cards_path = base_dir / "chapter_cards.md"
    if active_phase != "export" and cards_path.exists() and (base_dir / "outline.md").exists():
        cards = parse_chapter_cards(cards_path.read_text(encoding="utf-8"))
        if outline_card_count(base_dir) != len(cards):
            issues.append("outline.md chapter count diverges from chapter_cards.md")
        else:
            titles = outline_titles(base_dir)
            for card in cards:
                number = int(card.get("number", 0))
                outline_title = titles.get(number, "").strip()
                if outline_title and outline_title != str(card.get("title", "")).strip():
                    issues.append(f"outline.md title for chapter {number} diverges from chapter_cards.md")
                    break

    if active_phase != "export" and (base_dir / "thread_registry.json").exists() and (base_dir / "outline.md").exists():
        outline_text = (base_dir / "outline.md").read_text(encoding="utf-8")
        if "Foreshadowing Ledger" not in outline_text and "FORESHADOWING LEDGER" not in outline_text:
            issues.append("outline.md is missing a foreshadowing ledger while thread_registry.json exists")

    return issues
