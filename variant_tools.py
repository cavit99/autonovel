#!/usr/bin/env python3
"""Shared helpers for drafting and comparing chapter variants."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from evidence_tools import passage_features
from evaluate import slop_score

BASE_DIR = Path(__file__).resolve().parent
CHAPTERS_DIR = BASE_DIR / "chapters"
VARIANTS_DIR = CHAPTERS_DIR / "variants"


def baseline_variant_path(chapter_num: int, base_dir: Path = BASE_DIR) -> Path:
    return base_dir / "chapters" / "variants" / f"ch_{chapter_num:02d}_baseline.md"


def variant_path(chapter_num: int, variant_index: int, base_dir: Path = BASE_DIR) -> Path:
    return base_dir / "chapters" / "variants" / f"ch_{chapter_num:02d}_variant_{variant_index:02d}.md"


def variant_metadata_path(chapter_num: int, base_dir: Path = BASE_DIR) -> Path:
    return base_dir / "edit_logs" / f"ch{chapter_num:02d}_variants.json"


def comparison_log_path(chapter_num: int, base_dir: Path = BASE_DIR) -> Path:
    return base_dir / "edit_logs" / f"ch{chapter_num:02d}_variant_compare.json"


def scene_options_for_prompt(base_dir: Path, chapter_num: int) -> list[dict[str, Any]]:
    path = base_dir / "scene_options" / f"ch_{chapter_num:02d}.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def load_variant_candidates(chapter_num: int, base_dir: Path = BASE_DIR) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    baseline = base_dir / "chapters" / f"ch_{chapter_num:02d}.md"
    baseline_copy = baseline_variant_path(chapter_num, base_dir)
    for label, path in (
        ("baseline", baseline_copy if baseline_copy.exists() else baseline),
    ):
        if path.exists():
            candidates.append(
                {
                    "id": label,
                    "path": path,
                    "text": path.read_text(encoding="utf-8"),
                }
            )

    for path in sorted((base_dir / "chapters" / "variants").glob(f"ch_{chapter_num:02d}_variant_*.md")):
        candidates.append({"id": path.stem.replace(f"ch_{chapter_num:02d}_", ""), "path": path, "text": path.read_text(encoding="utf-8")})
    return candidates


def variant_instruction(chapter_num: int, variant_index: int, total_variants: int, scene_options: list[dict[str, Any]]) -> str:
    if scene_options:
        option = scene_options[(variant_index - 1) % len(scene_options)]
        residue = str(option.get("residue", "")).strip()
        imbalance = str(option.get("social_imbalance", "")).strip()
        wrong_inference = str(option.get("wrong_inference", "")).strip()
        return (
            f"VARIANT {variant_index}/{total_variants} for Chapter {chapter_num}.\n"
            f"Prioritize scene option #{((variant_index - 1) % len(scene_options)) + 1}.\n"
            f"Lean into this social imbalance: {imbalance or '(none provided)'}.\n"
            f"Let this wrong inference matter: {wrong_inference or '(none provided)'}.\n"
            f"Make the chapter leave this residue: {residue or '(none provided)'}.\n"
            "Do not merely paraphrase another variant."
        )
    return (
        f"VARIANT {variant_index}/{total_variants} for Chapter {chapter_num}.\n"
        "Take a materially different path through the chapter while preserving the irreversible change.\n"
        "Vary the opening pressure, the social imbalance, or the residue so the alternatives are genuinely distinct."
    )


def deterministic_variant_record(candidate: dict[str, Any]) -> dict[str, Any]:
    text = candidate["text"]
    slop = slop_score(text)
    features = passage_features(text)
    dialogue_ratio = features["dialogue_ratio"]
    score = (
        12.0
        - float(slop["slop_penalty"])
        + min(features["word_count"] / 900.0, 2.0)
        + min(features["conflict_score"] / 4.0, 2.0)
        + (1.0 if 0.06 <= dialogue_ratio <= 0.45 else 0.0)
        + min(features["motif_score"] / 6.0, 1.0)
    )
    return {
        **candidate,
        "mechanical_score": round(score, 3),
        "slop_penalty": slop["slop_penalty"],
        "dialogue_ratio": dialogue_ratio,
        "word_count": features["word_count"],
    }


def pick_best_variant_deterministically(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    ranked = [deterministic_variant_record(candidate) for candidate in candidates]
    ranked.sort(
        key=lambda item: (
            item["mechanical_score"],
            -item["slop_penalty"],
            item["word_count"],
        ),
        reverse=True,
    )
    winner = ranked[0]
    return {
        "decision": "select",
        "winner": winner["id"],
        "winner_path": str(winner["path"]),
        "reason": (
            f"Deterministic fallback preferred {winner['id']} "
            f"(score {winner['mechanical_score']}, slop {winner['slop_penalty']})."
        ),
        "ranked": [
            {
                "id": item["id"],
                "path": str(item["path"]),
                "mechanical_score": item["mechanical_score"],
                "slop_penalty": item["slop_penalty"],
                "word_count": item["word_count"],
            }
            for item in ranked
        ],
    }


def parse_json_blob(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```\w*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("No JSON object found in compare output")
    return json.loads(cleaned[start:end + 1])


def variant_compare_model() -> str:
    return os.environ.get("AUTONOVEL_JUDGE_MODEL", "claude-opus-4-6")
