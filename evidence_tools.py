#!/usr/bin/env python3
"""Shared helpers for evidence-pack evaluation and local audit tooling."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
CHAPTERS_DIR = BASE_DIR / "chapters"
EVAL_LOG_DIR = BASE_DIR / "eval_logs"
EDIT_LOG_DIR = BASE_DIR / "edit_logs"

QUOTE_RE = re.compile(r'["“](.+?)["”]', re.DOTALL)
SENTENCE_RE = re.compile(r"[^.!?]+[.!?]?")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for",
    "from", "had", "has", "have", "he", "her", "him", "his", "i", "in", "is",
    "it", "its", "me", "my", "of", "on", "or", "she", "that", "the", "their",
    "them", "there", "they", "this", "to", "was", "were", "with", "you", "your",
}

CONFLICT_KEYWORDS = {
    "accused", "anger", "argued", "attack", "broke", "cut", "demanded", "feared",
    "fight", "fought", "grief", "lied", "lie", "no", "refused", "shouted",
    "struck", "threat", "warned", "won't", "wouldn't",
}

QUIET_KEYWORDS = {
    "breathed", "drifted", "listened", "paused", "sat", "settled", "stared",
    "stood", "waited", "watched",
}

ABSTRACT_TERMS = {
    "argument", "balance", "destiny", "ethics", "history", "justice", "mercy",
    "order", "power", "principle", "system", "theory", "truth",
}

THEME_WORDS = {
    "consent", "destiny", "duty", "freedom", "history", "inheritance", "justice",
    "law", "memory", "order", "power", "responsibility", "truth",
}

INTENSIFIERS = {
    "almost", "barely", "especially", "just", "nearly", "really", "rather",
    "so", "specific", "suddenly", "too", "very",
}

SENSORY_DOMAINS = {
    "smell": {"smell", "scent", "odor", "reek", "perfume", "stink"},
    "sound": {"hear", "heard", "listen", "listened", "ring", "rang", "sound", "voice"},
    "sight": {"glow", "look", "looked", "light", "saw", "seen", "shadow"},
    "touch": {"cold", "heat", "rough", "touch", "touched", "warm"},
    "emotion": {"afraid", "angry", "grief", "hope", "nervous", "shame"},
}


def compute_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_chapters(chapters_dir: Path = CHAPTERS_DIR) -> dict[int, str]:
    chapters: dict[int, str] = {}
    for path in sorted(chapters_dir.glob("ch_*.md")):
        match = re.search(r"ch_(\d+)\.md$", path.name)
        if not match:
            continue
        chapters[int(match.group(1))] = path.read_text(encoding="utf-8")
    return chapters


def load_character_engine(path: Path | None = None) -> dict[str, Any]:
    engine_path = path or (BASE_DIR / "character_engine.json")
    if not engine_path.exists():
        return {}
    try:
        return load_json(engine_path)
    except json.JSONDecodeError:
        return {}


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def split_passages(text: str, min_words: int = 45) -> list[str]:
    passages: list[str] = []
    buffer: list[str] = []
    words = 0

    for paragraph in [part.strip() for part in text.split("\n\n") if part.strip()]:
        buffer.append(paragraph)
        words += len(paragraph.split())
        if words >= min_words:
            passages.append("\n\n".join(buffer))
            buffer = []
            words = 0

    if buffer:
        if passages and len(" ".join(buffer).split()) < min_words // 2:
            passages[-1] = passages[-1] + "\n\n" + "\n\n".join(buffer)
        else:
            passages.append("\n\n".join(buffer))

    return passages


def sentence_starters(text: str, width: int = 2) -> list[str]:
    starters: list[str] = []
    for raw in SENTENCE_RE.findall(text):
        tokens = tokenize(raw)
        if not tokens:
            continue
        starters.append(" ".join(tokens[:width]))
    return starters


def repeated_bigram_score(tokens: list[str]) -> int:
    if len(tokens) < 4:
        return 0
    bigrams = [" ".join(tokens[index:index + 2]) for index in range(len(tokens) - 1)]
    counts = Counter(bigrams)
    return sum(count - 1 for count in counts.values() if count > 1)


def motif_density(tokens: list[str]) -> int:
    counts = Counter(token for token in tokens if token not in STOPWORDS and len(token) > 4)
    return sum(count for count in counts.values() if count >= 3)


def exposition_score(text: str, tokens: list[str]) -> float:
    lower = text.lower()
    signals = sum(lower.count(needle) for needle in (
        "because", "had been", "had always", "remembered", "explained",
        "history of", "knew that", "was supposed to",
    ))
    abstract_hits = sum(1 for token in tokens if token in ABSTRACT_TERMS)
    return signals + abstract_hits * 0.5


def quiet_score(text: str, tokens: list[str], dialogue_ratio: float) -> float:
    lower = text.lower()
    quiet_hits = sum(1 for token in tokens if token in QUIET_KEYWORDS)
    return quiet_hits + (1.2 if dialogue_ratio < 0.12 else 0.0) + lower.count("silence") * 0.5


def conflict_score(text: str, tokens: list[str], question_count: int) -> float:
    lower = text.lower()
    hits = sum(1 for token in tokens if token in CONFLICT_KEYWORDS)
    negations = lower.count("not ") + lower.count("never ")
    return hits + question_count * 0.5 + negations * 0.2 + lower.count("!") * 0.5


def passage_features(text: str) -> dict[str, float]:
    tokens = tokenize(text)
    word_count = len(tokens)
    quote_chars = sum(len(match.group(0)) for match in QUOTE_RE.finditer(text))
    dialogue_ratio = quote_chars / max(1, len(text))
    starters = sentence_starters(text)
    repeated_starters = Counter(starters)
    starter_repetition = sum(count - 1 for count in repeated_starters.values() if count > 1)
    question_count = text.count("?")
    repetition = starter_repetition + repeated_bigram_score(tokens)
    return {
        "word_count": word_count,
        "dialogue_ratio": round(dialogue_ratio, 3),
        "question_count": question_count,
        "conflict_score": round(conflict_score(text, tokens, question_count), 3),
        "quiet_score": round(quiet_score(text, tokens, dialogue_ratio), 3),
        "exposition_score": round(exposition_score(text, tokens), 3),
        "repetition_score": repetition,
        "motif_score": motif_density(tokens),
    }


def build_passage_records(chapters: dict[int, str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for chapter_num, text in chapters.items():
        passages = split_passages(text)
        for index, passage in enumerate(passages, start=1):
            features = passage_features(passage)
            records.append(
                {
                    "id": f"ch{chapter_num:02d}-p{index:02d}",
                    "chapter": chapter_num,
                    "passage_index": index,
                    "text": passage,
                    **features,
                }
            )
    return records


def select_unique_passages(
    passages: list[dict[str, Any]],
    *,
    key: str,
    count: int,
    reverse: bool = True,
    predicate: Any = None,
) -> list[dict[str, Any]]:
    filtered = [passage for passage in passages if predicate(passage)] if predicate else list(passages)
    filtered.sort(key=lambda item: (item.get(key, 0), item["chapter"], item["passage_index"]), reverse=reverse)

    chosen: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for passage in filtered:
        if passage["id"] in seen_ids:
            continue
        chosen.append(passage)
        seen_ids.add(passage["id"])
        if len(chosen) >= count:
            break
    return chosen


def latest_chapter_scores(eval_log_dir: Path | None = EVAL_LOG_DIR) -> dict[int, float]:
    if eval_log_dir is None:
        return {}
    scores: dict[int, tuple[str, float]] = {}
    for path in sorted(eval_log_dir.glob("*_ch*.json")):
        match = re.search(r"_ch(\d+)\.json$", path.name)
        if not match:
            continue
        chapter = int(match.group(1))
        try:
            data = load_json(path)
        except json.JSONDecodeError:
            continue
        if "overall_score" not in data:
            continue
        scores[chapter] = (path.name, float(data["overall_score"]))
    return {chapter: score for chapter, (_name, score) in scores.items()}


def late_weak_passages(
    passages: list[dict[str, Any]],
    chapter_scores: dict[int, float],
    total_chapters: int,
    count: int = 3,
) -> list[dict[str, Any]]:
    if not passages:
        return []
    late_threshold = max(1, (total_chapters + 1) // 2)
    ranked_chapters = sorted(
        (
            (chapter, chapter_scores.get(chapter, 10.0))
            for chapter in {passage["chapter"] for passage in passages}
            if chapter >= late_threshold
        ),
        key=lambda item: (item[1], item[0]),
    )
    chosen: list[dict[str, Any]] = []
    for chapter, _score in ranked_chapters:
        for passage in passages:
            if passage["chapter"] == chapter:
                chosen.append(passage)
                break
        if len(chosen) >= count:
            break
    return chosen


def build_evidence_pack(
    chapters: dict[int, str] | None = None,
    *,
    eval_log_dir: Path | None = EVAL_LOG_DIR,
) -> dict[str, Any]:
    chapters = chapters or load_all_chapters()
    passages = build_passage_records(chapters)
    chapter_scores = latest_chapter_scores(eval_log_dir)
    total_words = sum(len(text.split()) for text in chapters.values())
    manuscript = "\n\n".join(chapters[num] for num in sorted(chapters))
    opening_passages = []
    for chapter in sorted(chapters)[:3]:
        for passage in passages:
            if passage["chapter"] == chapter:
                opening_passages.append(passage)
                break

    pack = {
        "generated_from": {
            "chapter_count": len(chapters),
            "word_count": total_words,
            "manuscript_sha256": compute_sha256(manuscript),
        },
        "chapter_scores": chapter_scores,
        "categories": {
            "openings": opening_passages,
            "confrontations": select_unique_passages(
                passages,
                key="conflict_score",
                count=3,
                predicate=lambda item: item["dialogue_ratio"] > 0.08,
            ),
            "quiet_scenes": select_unique_passages(
                passages,
                key="quiet_score",
                count=3,
                predicate=lambda item: item["conflict_score"] < 2.5,
            ),
            "exposition_heavy": select_unique_passages(passages, key="exposition_score", count=3),
            "dialogue_heavy": select_unique_passages(passages, key="dialogue_ratio", count=3),
            "suspected_repetitive": select_unique_passages(passages, key="repetition_score", count=3),
            "motif_dense": select_unique_passages(passages, key="motif_score", count=3),
            "late_weak_chapters": late_weak_passages(passages, chapter_scores, len(chapters), count=3),
        },
    }

    return pack


def render_passage(passage: dict[str, Any]) -> str:
    return (
        f"[{passage['id']}] Chapter {passage['chapter']} "
        f"(passage {passage['passage_index']}, {passage['word_count']} words)\n"
        f"{passage['text']}"
    )


def render_evidence_pack(pack: dict[str, Any]) -> str:
    lines = [
        f"Evidence pack for {pack['generated_from']['chapter_count']} chapters / "
        f"{pack['generated_from']['word_count']} words.",
        "",
    ]
    for category, passages in pack.get("categories", {}).items():
        lines.append(f"## {category}")
        if not passages:
            lines.append("(none)")
            lines.append("")
            continue
        for passage in passages:
            lines.append(render_passage(passage))
            lines.append("")
    return "\n".join(lines).strip()


def extract_dialogue_records(
    text: str,
    *,
    chapter: int,
    known_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    attribution_verbs = "said|asked|replied|answered|murmured|shouted|whispered|snapped"
    known_names = known_names or set()

    for index, match in enumerate(QUOTE_RE.finditer(text), start=1):
        line = normalize_whitespace(match.group(1))
        if not line:
            continue
        before = text[max(0, match.start() - 80):match.start()]
        after = text[match.end():match.end() + 80]
        speaker = "Unknown"

        after_match = re.search(
            rf"^\s*[,—-]*\s*([A-Z][A-Za-z]+)\s+(?:{attribution_verbs})\b",
            after,
        )
        if after_match:
            speaker = after_match.group(1)
        else:
            after_match = re.search(
                rf"^\s*[,—-]*\s*(?:{attribution_verbs})\s+([A-Z][A-Za-z]+)\b",
                after,
            )
            if after_match:
                speaker = after_match.group(1)
            else:
                before_match = re.search(
                    rf"([A-Z][A-Za-z]+)\s+(?:{attribution_verbs})\s*[,—-]*\s*$",
                    before,
                )
                if before_match:
                    speaker = before_match.group(1)
                else:
                    for name in known_names:
                        if re.search(rf"\b{name}\b", before[-40:] + after[:40]):
                            speaker = name
                            break

        records.append(
            {
                "id": f"ch{chapter:02d}-d{index:02d}",
                "chapter": chapter,
                "speaker": speaker,
                "text": line,
                "word_count": len(line.split()),
            }
        )
    return records


def generic_dialogue(line: str) -> bool:
    tokens = tokenize(line)
    if not tokens:
        return False
    stopword_ratio = sum(1 for token in tokens if token in STOPWORDS) / len(tokens)
    return len(tokens) <= 6 or stopword_ratio > 0.7


def theme_perfect_dialogue(line: str) -> bool:
    lower = line.lower()
    if re.search(r"\bnot\b.+\bbut\b", lower):
        return True
    return sum(1 for token in tokenize(line) if token in THEME_WORDS) >= 2


def speaker_similarity(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {}
    for record in records:
        if record["speaker"] == "Unknown":
            continue
        grouped.setdefault(record["speaker"], []).append(record["text"])

    flagged: list[dict[str, Any]] = []
    speakers = sorted(grouped)
    for index, speaker in enumerate(speakers):
        tokens_a = {token for token in tokenize(" ".join(grouped[speaker])) if token not in STOPWORDS}
        if not tokens_a:
            continue
        for other in speakers[index + 1:]:
            tokens_b = {token for token in tokenize(" ".join(grouped[other])) if token not in STOPWORDS}
            if not tokens_b:
                continue
            overlap = len(tokens_a & tokens_b) / max(1, len(tokens_a | tokens_b))
            if overlap >= 0.45:
                flagged.append({"speakers": [speaker, other], "overlap": round(overlap, 3)})
    return flagged


def speaker_domain_leaks(
    record: dict[str, Any],
    character_engine: dict[str, Any],
) -> list[str]:
    speaker = record["speaker"]
    if speaker not in character_engine:
        return []
    line_tokens = set(tokenize(record["text"]))
    own_domains = {
        normalize_whitespace(domain).lower()
        for domain in character_engine[speaker].get("metaphor_domain", [])
    }
    leaks: list[str] = []
    for other_name, payload in character_engine.items():
        if other_name == speaker:
            continue
        for domain in payload.get("metaphor_domain", []):
            domain_token = normalize_whitespace(str(domain)).lower()
            if domain_token and domain_token in line_tokens and domain_token not in own_domains:
                leaks.append(other_name)
    return sorted(set(leaks))


def cognitive_ceiling_violation(
    record: dict[str, Any],
    character_engine: dict[str, Any],
) -> bool:
    speaker = record["speaker"]
    if speaker not in character_engine:
        return False
    ceiling = character_engine[speaker].get("cognitive_ceiling", {})
    level = str(ceiling.get("abstraction_level", "")).lower()
    tokens = tokenize(record["text"])
    abstract_hits = sum(1 for token in tokens if token in ABSTRACT_TERMS)
    if level == "low":
        return abstract_hits >= 2 or ";" in record["text"]
    if level == "medium":
        return abstract_hits >= 4
    return False


def strip_dialogue(text: str) -> str:
    return QUOTE_RE.sub("", text)


def extract_narration_sentences(chapters: dict[int, str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for chapter, text in chapters.items():
        narration = strip_dialogue(text)
        for index, sentence in enumerate(SENTENCE_RE.findall(narration), start=1):
            cleaned = normalize_whitespace(sentence)
            if len(cleaned.split()) < 4:
                continue
            records.append(
                {
                    "id": f"ch{chapter:02d}-n{index:02d}",
                    "chapter": chapter,
                    "text": cleaned,
                }
            )
    return records


def observation_signature(paragraph: str) -> tuple[str, ...]:
    tokens = tokenize(paragraph)
    order: list[str] = []
    for label, keywords in SENSORY_DOMAINS.items():
        positions = [index for index, token in enumerate(tokens) if token in keywords]
        if positions:
            order.append((min(positions), label))
    order.sort()
    return tuple(label for _pos, label in order)


def room_entry_signature(paragraph: str) -> bool:
    lower = paragraph.lower()
    return bool(re.search(r"\b(?:entered|stepped into|walked into|came into)\b", lower))
