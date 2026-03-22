#!/usr/bin/env python3
"""Shared path helpers for the evolving repo layout."""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PLANNING_DIRNAME = "planning"
PLANNING_DIR = BASE_DIR / PLANNING_DIRNAME

SEED_FILENAME = "seed.md"
LEGACY_ROOT_SEED_FILENAME = "seed.md"
LEGACY_SEED_TXT_FILENAME = "seed.txt"

PLANNING_FILES = {
    "world": "world.md",
    "characters": "characters.md",
    "character_engine": "character_engine.json",
    "perspective": "perspective.md",
    "voice": "voice.md",
    "voice_discovery": "voice_discovery.json",
    "arc_outline": "arc_outline.md",
    "chapter_cards": "chapter_cards.md",
    "thread_registry": "thread_registry.json",
    "canon": "canon.md",
    "outline": "outline.md",
}


def planning_dir(base_dir: Path = BASE_DIR) -> Path:
    return base_dir / PLANNING_DIRNAME


def ensure_planning_dir(base_dir: Path = BASE_DIR) -> Path:
    path = planning_dir(base_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_parent_dir(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def seed_path(base_dir: Path = BASE_DIR) -> Path:
    return planning_dir(base_dir) / SEED_FILENAME


def legacy_root_seed_path(base_dir: Path = BASE_DIR) -> Path:
    return base_dir / LEGACY_ROOT_SEED_FILENAME


def legacy_seed_txt_path(base_dir: Path = BASE_DIR) -> Path:
    return base_dir / LEGACY_SEED_TXT_FILENAME


def seed_contract_error(base_dir: Path = BASE_DIR) -> str:
    path = seed_path(base_dir)
    legacy_root = legacy_root_seed_path(base_dir)
    legacy_txt = legacy_seed_txt_path(base_dir)
    relative_target = path.relative_to(base_dir)
    if legacy_root.exists():
        return (
            f"required file not found: {path}. "
            f"root seed.md is deprecated; move it to {relative_target}."
        )
    if legacy_txt.exists():
        return (
            f"required file not found: {path}. "
            f"seed.txt is no longer read automatically; copy or rename it to {relative_target} when you are ready to migrate."
        )
    return f"required file not found: {path}"


def require_seed_path(base_dir: Path = BASE_DIR) -> Path:
    path = seed_path(base_dir)
    if path.exists():
        return path
    legacy_root = legacy_root_seed_path(base_dir)
    if legacy_root.exists():
        return legacy_root
    raise FileNotFoundError(seed_contract_error(base_dir))


def readable_seed_path(base_dir: Path = BASE_DIR) -> Path:
    path = seed_path(base_dir)
    if path.exists():
        return path
    legacy_root = legacy_root_seed_path(base_dir)
    if legacy_root.exists():
        return legacy_root
    return path


def planning_artifact_path(name: str, base_dir: Path = BASE_DIR) -> Path:
    filename = PLANNING_FILES.get(name, name)
    return planning_dir(base_dir) / filename


def legacy_planning_artifact_path(name: str, base_dir: Path = BASE_DIR) -> Path:
    filename = PLANNING_FILES.get(name, name)
    return base_dir / filename


def readable_planning_artifact_path(name: str, base_dir: Path = BASE_DIR) -> Path:
    current = planning_artifact_path(name, base_dir)
    if current.exists():
        return current
    legacy = legacy_planning_artifact_path(name, base_dir)
    if legacy.exists():
        return legacy
    return current


def planning_artifact_paths(base_dir: Path = BASE_DIR) -> dict[str, Path]:
    return {key: planning_artifact_path(key, base_dir) for key in PLANNING_FILES}


def legacy_planning_artifact_paths(base_dir: Path = BASE_DIR) -> dict[str, Path]:
    return {key: legacy_planning_artifact_path(key, base_dir) for key in PLANNING_FILES}


def all_planning_artifact_candidates(base_dir: Path = BASE_DIR) -> list[Path]:
    seen: set[Path] = set()
    paths: list[Path] = []
    for key in PLANNING_FILES:
        for path in (
            planning_artifact_path(key, base_dir),
            legacy_planning_artifact_path(key, base_dir),
        ):
            if path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


def migrate_planning_artifacts(base_dir: Path = BASE_DIR) -> list[tuple[Path, Path]]:
    ensure_planning_dir(base_dir)
    moved: list[tuple[Path, Path]] = []
    for key in PLANNING_FILES:
        legacy = legacy_planning_artifact_path(key, base_dir)
        target = planning_artifact_path(key, base_dir)
        if legacy.exists() and not target.exists():
            ensure_parent_dir(target)
            legacy.replace(target)
            moved.append((legacy, target))
    return moved
