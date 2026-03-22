#!/usr/bin/env python3
"""
evaluate.py -- Novel evaluation harness.

Usage:
  python evaluate.py --phase=foundation    # Score planning docs only
  python evaluate.py --chapter=5           # Score a single chapter
  python evaluate.py --full                # Score the entire novel

Output: structured scores to stdout + eval_logs/<timestamp>.json

This file is READ-ONLY during autonomous runs. The human edits it
to tune what "good" means. The agent treats it as a black box.
"""

import argparse
import json
import os
import sys
import glob
import re
from datetime import datetime
from pathlib import Path

# --- Configuration ---
BASE_DIR = Path(__file__).parent

# Load .env file if present
try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for bare Python test runners
    def load_dotenv(*_args, **_kwargs):
        return False
load_dotenv(BASE_DIR / ".env")

from anthropic_api import message_text_from_response
from evidence_tools import load_json, render_evidence_pack
from project_paths import readable_planning_artifact_path

# Judge uses Opus 4.6 (harsh, critical). Writer uses Sonnet 4.6 (fast, long context).
# Intentionally different to avoid self-congratulation.
JUDGE_MODEL = os.environ.get("AUTONOVEL_JUDGE_MODEL", "claude-opus-4-6")
SMELL_MODEL = os.environ.get("AUTONOVEL_SMELL_MODEL", JUDGE_MODEL)
AUTONOVEL_DIALOGUE_MODEL = os.environ.get("AUTONOVEL_DIALOGUE_MODEL", SMELL_MODEL)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_BASE_URL = os.environ.get("AUTONOVEL_API_BASE_URL", "https://api.anthropic.com")

# Beta header to unlock 1M context window on both Opus 4.6 and Sonnet 4.6
ANTHROPIC_BETA = "context-1m-2025-08-07"
CHAPTERS_DIR = BASE_DIR / "chapters"
EVAL_LOG_DIR = BASE_DIR / "eval_logs"
EVAL_LOG_DIR.mkdir(exist_ok=True)
FULL_EVIDENCE_MAX_TOKENS = 12000
SUMMARY_MODE_FULL_WARNING = (
    "WARNING: --full without --evidence uses degraded summary-mode judging. "
    "Prefer --full --evidence <eval_logs/evidence_pack.json> for normalized full-novel evaluation."
)


# ---- Mechanical Slop Detection (no LLM needed) ----

TIER1_BANNED = [
    "delve", "utilize", "leverage", "facilitate", "elucidate",
    "embark", "endeavor", "encompass", "multifaceted", "tapestry",
    "paradigm", "synergy", "synergize", "holistic", "catalyze",
    "catalyst", "juxtapose", "myriad", "plethora",
]

TIER2_SUSPICIOUS = [
    "robust", "comprehensive", "seamless", "seamlessly", "cutting-edge",
    "innovative", "streamline", "empower", "foster", "enhance", "elevate",
    "optimize", "pivotal", "intricate", "profound", "resonate",
    "underscore", "harness", "cultivate", "bolster", "galvanize",
    "cornerstone", "game-changer", "scalable",
]

TIER3_FILLER = [
    r"it'?s worth noting that",
    r"it'?s important to note that",
    r"^importantly,?\s",
    r"^notably,?\s",
    r"^interestingly,?\s",
    r"let'?s dive into",
    r"let'?s explore",
    r"as we can see",
    r"^furthermore,?\s",
    r"^moreover,?\s",
    r"^additionally,?\s",
    r"in today'?s .*(fast-paced|digital|modern)",
    r"at the end of the day",
    r"it goes without saying",
    r"when it comes to",
    r"one might argue that",
    r"not just .+, but",
]

TRANSITION_OPENERS = [
    "however", "furthermore", "additionally", "moreover",
    "nevertheless", "consequently", "nonetheless", "similarly",
]

# Fiction-specific AI tells (prose clichés that betray machine origin)
FICTION_AI_TELLS = [
    r"a sense of \w+",
    r"couldn'?t help but feel",
    r"the weight of \w+",
    r"the air was thick with",
    r"eyes widened",
    r"a wave of \w+ washed over",
    r"a pang of \w+",
    r"heart pounded in (?:his|her|their) chest",
    r"(?:raven|dark|golden|silver) (?:hair|tresses) (?:spilled|cascaded|tumbled|fell)",
    r"piercing (?:blue|green|gray|grey|dark) eyes",
    r"a knowing (?:smile|grin|look|glance)",
    r"(?:he|she|they) felt a (?:surge|rush|wave|pang|flicker) of",
    r"the silence (?:was|hung|stretched|grew) (?:heavy|thick|oppressive|deafening)",
    r"let out a breath (?:he|she|they) didn'?t (?:know|realize)",
    r"something (?:dark|ancient|primal|unnamed) stirred",
]

# Structural AI tics -- rhetorical formulas that betray AI composition
STRUCTURAL_AI_TICS = [
    r"(?:I'm|I am) not (?:saying|asking|suggesting) .{3,40}(?:I'm|I am) (?:saying|asking|suggesting)",  # "I'm not saying X. I'm saying Y"
    r"(?:which|that) means either .{3,40} or ",  # "which means either X, or Y"
    r"[Tt]here'?s a (?:difference|distinction)\.",  # formula capper
    r"[Tt]hose are (?:different|not the same) things\.",  # formula capper
    r"[Nn]ot (?:just|merely|simply) .{3,40}, but ",  # "not just X, but Y"
    r"[Nn]ot (?:from|by|because of) .{3,40}, but (?:from|by|because)",  # "not from X, but from Y" in narration
]

# Show-don't-tell detectors: emotion TELLING patterns
TELLING_PATTERNS = [
    r"\b(?:he|she|they|I|we|[A-Z]\w+) (?:felt|was|seemed|looked|appeared) (?:angry|sad|happy|scared|nervous|excited|jealous|guilty|anxious|lonely|desperate|furious|terrified|elated|miserable|hopeful|confused|relieved|horrified|disgusted|ashamed|proud|bitter|defeated|triumphant)\b",
    r"\b(?:angrily|sadly|happily|nervously|excitedly|desperately|furiously|anxiously|guiltily|bitterly|wearily|miserably)\b",
]


def slop_score(text):
    """
    Mechanical slop detection. Returns a dict with:
      - tier1_hits: list of (word, count)
      - tier2_hits: list of (word, count)
      - tier3_hits: list of (pattern, count)
      - em_dash_density: em dashes per 1000 words
      - sentence_length_cv: coefficient of variation (higher = more human)
      - transition_opener_ratio: fraction of paragraphs starting with transitions
      - slop_penalty: 0-10 deduction (0 = clean, 10 = pure slop)
    """
    words = text.lower().split()
    word_count = len(words) or 1

    # Tier 1
    tier1_hits = []
    for w in TIER1_BANNED:
        c = sum(1 for token in words if token.strip(".,;:!?\"'()") == w)
        if c > 0:
            tier1_hits.append((w, c))

    # Tier 2 -- count per paragraph, flag clusters
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    tier2_hits = []
    tier2_cluster_count = 0
    for w in TIER2_SUSPICIOUS:
        c = sum(1 for token in words if token.strip(".,;:!?\"'()") == w)
        if c > 0:
            tier2_hits.append((w, c))
    for para in paragraphs:
        para_lower = para.lower()
        hits_in_para = sum(1 for w in TIER2_SUSPICIOUS if w in para_lower)
        if hits_in_para >= 3:
            tier2_cluster_count += 1

    # Tier 3
    tier3_hits = []
    for pattern in TIER3_FILLER:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        if matches:
            tier3_hits.append((pattern, len(matches)))

    # Em dash density
    em_dashes = text.count("—") + text.count("--")
    em_dash_density = (em_dashes / word_count) * 1000

    # Sentence length variation (coefficient of variation)
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip().split()) > 2]
    if len(sentences) > 2:
        lengths = [len(s.split()) for s in sentences]
        mean_len = sum(lengths) / len(lengths)
        variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
        std_len = variance ** 0.5
        sentence_length_cv = std_len / mean_len if mean_len > 0 else 0
    else:
        sentence_length_cv = 0.5  # not enough data, assume OK

    # Transition opener ratio
    transition_starts = 0
    for para in paragraphs:
        first_word = para.split()[0].lower().strip(".,;:!?\"'()") if para.split() else ""
        if first_word in TRANSITION_OPENERS:
            transition_starts += 1
    transition_ratio = transition_starts / len(paragraphs) if paragraphs else 0

    # Fiction AI tells
    fiction_tells = []
    for pattern in FICTION_AI_TELLS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            fiction_tells.append((pattern[:40], len(matches)))
    fiction_tell_count = sum(c for _, c in fiction_tells)

    # Show-don't-tell violations
    telling_count = 0
    for pattern in TELLING_PATTERNS:
        telling_count += len(re.findall(pattern, text, re.IGNORECASE))

    # Structural AI tics (rhetorical formulas)
    structural_tics = []
    for pattern in STRUCTURAL_AI_TICS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            structural_tics.append((pattern[:40], len(matches)))
    structural_tic_count = sum(c for _, c in structural_tics)

    # Composite penalty (0 = clean, 10 = disaster)
    penalty = 0.0
    penalty += min(len(tier1_hits) * 1.5, 4.0)       # tier1: up to 4 pts
    penalty += min(tier2_cluster_count * 1.0, 2.0)    # tier2 clusters: up to 2 pts
    penalty += min(sum(c for _, c in tier3_hits) * 0.3, 2.0)  # tier3: up to 2 pts
    if em_dash_density > 15:
        penalty += min((em_dash_density - 15) * 0.3, 1.0)  # em dashes: up to 1 pt (threshold raised for voice)
    if sentence_length_cv < 0.3:
        penalty += 1.0  # uniform sentence length: 1 pt
    if transition_ratio > 0.3:
        penalty += min(transition_ratio * 2, 1.0)  # transition abuse: up to 1 pt
    penalty += min(fiction_tell_count * 0.3, 2.0)     # fiction AI tells: up to 2 pts
    penalty += min(telling_count * 0.2, 1.5)          # show-don't-tell: up to 1.5 pts
    penalty += min(structural_tic_count * 0.5, 2.0)   # structural AI tics: up to 2 pts

    penalty = min(penalty, 10.0)

    return {
        "tier1_hits": tier1_hits,
        "tier2_hits": tier2_hits,
        "tier2_clusters": tier2_cluster_count,
        "tier3_hits": tier3_hits,
        "fiction_ai_tells": fiction_tells,
        "structural_ai_tics": structural_tics,
        "telling_violations": telling_count,
        "em_dash_density": round(em_dash_density, 2),
        "sentence_length_cv": round(sentence_length_cv, 3),
        "transition_opener_ratio": round(transition_ratio, 3),
        "slop_penalty": round(penalty, 2),
    }


def load_file(path):
    """Load a text file, return empty string if missing."""
    try:
        return Path(path).read_text()
    except FileNotFoundError:
        return ""


def load_layer_files():
    """Load all planning layer files."""
    return {
        "voice": load_file(readable_planning_artifact_path("voice", BASE_DIR)),
        "world": load_file(readable_planning_artifact_path("world", BASE_DIR)),
        "characters": load_file(readable_planning_artifact_path("characters", BASE_DIR)),
        "outline": load_file(readable_planning_artifact_path("outline", BASE_DIR)),
        "canon": load_file(readable_planning_artifact_path("canon", BASE_DIR)),
    }


def load_extended_layer_files():
    layers = load_layer_files()
    layers.update(
        {
            "perspective": load_file(readable_planning_artifact_path("perspective", BASE_DIR)),
            "character_engine": load_file(readable_planning_artifact_path("character_engine", BASE_DIR)),
            "chapter_cards": load_file(readable_planning_artifact_path("chapter_cards", BASE_DIR)),
            "thread_registry": load_file(readable_planning_artifact_path("thread_registry", BASE_DIR)),
        }
    )
    return layers


def load_chapter(n):
    """Load a single chapter file."""
    return load_file(CHAPTERS_DIR / f"ch_{n:02d}.md")


def load_all_chapters():
    """Load all chapter files in order."""
    chapters = {}
    for f in sorted(glob.glob(str(CHAPTERS_DIR / "ch_*.md"))):
        num = int(re.search(r'ch_(\d+)', f).group(1))
        chapters[num] = Path(f).read_text()
    return chapters


def extract_chapter_reference(chapter_num: int, layers: dict[str, str]) -> str:
    chapter_cards = layers.get("chapter_cards", "")
    if chapter_cards.strip():
        pattern = rf"##\s*Ch\s*{chapter_num}\b.*?(?=##\s*Ch\s*\d+|$)"
        match = re.search(pattern, chapter_cards, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(0)

    outline = layers.get("outline", "")
    if outline.strip():
        pattern = rf"###\s*Ch(?:apter)?\s*{chapter_num}\b.*?(?=###\s*Ch(?:apter)?\s*\d+|##\s*Act|##\s*Foreshadowing|$)"
        match = re.search(pattern, outline, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(0)
    return "(chapter plan reference not found)"


def call_judge(prompt, max_tokens=2000):
    """Call the Anthropic judge LLM and return its response text."""
    import httpx

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": ANTHROPIC_BETA,
        "content-type": "application/json",
    }
    payload = {
        "model": JUDGE_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "system": "You are a literary critic and novel editor. "
                  "You evaluate fiction with precision. Always respond with valid JSON. "
                  "No markdown fences, no preamble -- just the JSON object.",
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }

    resp = httpx.post(
        f"{API_BASE_URL}/v1/messages",
        headers=headers,
        json=payload,
        timeout=180,
    )
    return message_text_from_response(resp, context="evaluate judge request")


def parse_json_response(text):
    """Extract JSON from a response that might have markdown fences or trailing text."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```\w*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
    # Find the outermost JSON object
    start = text.find('{')
    if start == -1:
        raise ValueError("No JSON object found in response")
    # Walk forward to find the matching closing brace
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == '\\' and in_string:
            escape = True
            continue
        if c == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i+1], strict=False)
    # Fallback: try loading as-is, with strict=False to handle control chars
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        # Last resort: fix common issues (literal newlines in strings)
        fixed = re.sub(r'(?<!\\)\n', '\\n', text)
        return json.loads(fixed, strict=False)


# --- Foundation Evaluation ---

FOUNDATION_PROMPT = """Evaluate these fantasy novel planning documents.

SCORING CALIBRATION (read this before scoring anything):

  9-10: Could not improve this with a month of focused editorial work.
        Published-novel quality. You can name the specific published
        novel it competes with. Reserve 10 for work that SURPRISES you.
  7-8:  Strong. A skilled author could draft from this document with
        minimal invention. Gaps exist but are minor and enumerable.
  5-6:  Functional but thin. A writer would need to invent significant
        material on the fly. Major gaps or generic choices.
  3-4:  Sketchy. More questions than answers. Would require heavy
        supplementation before drafting.
  1-2:  Placeholder or stub. Not usable for drafting.
  0:    Empty or missing.

  A score of 8+ requires ZERO major gaps. A score of 9+ requires
  that you genuinely struggled to find flaws. Err toward lower scores.

MANDATORY: For EVERY dimension, before scoring, you must identify:
  (a) The single biggest GAP or WEAKNESS in that area
  (b) A specific, actionable improvement that would raise the score
  If you cannot find a gap, explain why you believe one doesn't exist.

VOICE DEFINITION:
{voice}

WORLD BIBLE:
{world}

CHARACTER REGISTRY:
{characters}

OUTLINE:
{outline}

CANON (established facts):
{canon}

CROSS-CHECKS (perform these before scoring):
1. Check all example dialogue lines against ANTI-SLOP patterns:
   - Look for structural formulas repeated across characters
     ("not X, but Y" / "either X, or Y" / "there's a difference")
   - Check for AI rhetorical tics disguised as character voice
   - Deduct from character_distinctiveness if multiple characters
     share the same sentence structures
2. Check for missing NEGATIVE SPACE -- what's absent?
   - Are there gaps in the magic system that would block a specific
     plot scene? (e.g., can the protagonist's core ability affect written documents?
     What happens during the climax -- what rule resolves it?)
   - Are there characters needed for the plot who don't exist?
   - Are there scenes the outline demands that the world can't support?
3. Check for CONVENIENT GAPS vs DELIBERATE MYSTERY:
   - Convenient: "the details are unclear" where specifics are needed
   - Deliberate: withholding information from the READER while the
     AUTHOR knows the answer. If the planning docs dodge a question
     that a writer would need answered to draft a scene, that's a gap,
     not an iceberg.
4. Check the canon for INTERNAL CONTRADICTIONS:
   - Cross-reference dates, ages, and timelines
   - Check if character abilities match magic system rules
   - Look for factual conflicts between documents

Score these dimensions (gap + improvement required for each):

LORE & WORLDBUILDING:
- magic_system: Hard rules with COSTS and LIMITATIONS per Sanderson's
  Second Law. Could a writer resolve the CLIMACTIC CONFLICT using only
  rules already established? Are costs plot-driving, not decorative?
  Are there at least 3 societal implications explored with specificity?
  Is the system TESTABLE -- could you write a courtroom scene, a
  contract negotiation, and a magical confrontation without inventing
  new rules?
- world_history: Timeline of events creating PRESENT-DAY tensions.
  Each historical event should map to a current faction conflict or
  character motivation. Decorative history (cool but plot-irrelevant)
  counts against the score, not for it.
- geography_and_culture: Locations distinct with sensory signatures.
  Cultures with specific customs that GENERATE CONFLICT. Economy that
  creates class tension. Check: could two different scenes set in two
  different locations feel meaningfully different based on what's here?
- lore_interconnection: Does changing one element force changes in
  at least two others? Test by mentally removing the magic system --
  does the political structure collapse? Does the class system change?
  If elements are modular/detachable, score low.
- iceberg_depth: Implied depth vs stated depth. But CHECK: does the
  author actually know the answers to the mysteries, or are they
  handwaving? If a planning doc says "the answer will be revealed"
  without specifying WHAT the answer is, that's a gap wearing an
  iceberg costume.

CHARACTER:
- character_depth: Wound/want/need/lie chains that are CAUSALLY LINKED
  (not just thematically associated). The lie must logically follow
  from the wound. The want must be the wrong solution to the lie.
  The need must directly oppose the want. Check each chain for
  logical gaps. Also check: are ANY characters missing wound/want/need
  chains who probably need them?
- character_distinctiveness: Remove all dialogue tags from the example
  lines. Can you identify the speaker from sentence structure alone?
  Check for REPEATED STRUCTURAL FORMULAS across characters (e.g.,
  multiple characters using "X. Not Y." or balanced antithesis).
  Check that metaphor domains don't overlap. Check that speech
  patterns reflect character background (a 14-year-old should not
  sound like a 60-year-old merchant).
- character_secrets: Each major character's secret should be something
  that, if revealed, changes the plot's trajectory. Vague secrets
  ("he knows more than he says") score lower than specific ones
  ("he knows the harmonic means X, which would invalidate Y").

STRUCTURE:
- outline_completeness: Chapters with beats, POV, emotional arc,
  try-fail cycle type. Save the Cat beats at correct % marks.
  Score 0 if empty. Score 5+ only if act structure exists.
- foreshadowing_balance: Every planted thread has a planned payoff.
  Score 0 if ledger is empty regardless of implicit threads in
  other documents -- foreshadowing must be TRACKED to count.

CRAFT:
- internal_consistency: Actively hunt for contradictions. Cross-ref
  dates, ages, character counts, named locations. Flag any case
  where documents disagree. A single major contradiction caps this
  at 6. Three or more caps at 4.
- voice_clarity: Voice definition must be specific and ACTIONABLE.
  Exemplar passages must demonstrate the voice. Anti-exemplars must
  define boundaries. Check exemplar dialogue for AI slop patterns.
  A voice doc that is beautiful but contains slop in its own examples
  is undermined -- deduct.
- canon_coverage: Facts logged, sourced, and sufficient to catch
  contradictions. Check: if a writer introduced a NEW fact in
  chapter 5, could they verify it against the canon? Is the canon
  granular enough? Are there known facts from other docs that
  AREN'T in the canon?

Respond with JSON:
{{
  "magic_system": {{"score": N, "gap": "biggest weakness", "fix": "specific improvement", "note": "..."}},
  "world_history": {{"score": N, "gap": "...", "fix": "...", "note": "..."}},
  "geography_and_culture": {{"score": N, "gap": "...", "fix": "...", "note": "..."}},
  "lore_interconnection": {{"score": N, "gap": "...", "fix": "...", "note": "..."}},
  "iceberg_depth": {{"score": N, "gap": "...", "fix": "...", "note": "..."}},
  "character_depth": {{"score": N, "gap": "...", "fix": "...", "note": "..."}},
  "character_distinctiveness": {{"score": N, "gap": "...", "fix": "...", "note": "..."}},
  "character_secrets": {{"score": N, "gap": "...", "fix": "...", "note": "..."}},
  "outline_completeness": {{"score": N, "gap": "...", "fix": "...", "note": "..."}},
  "foreshadowing_balance": {{"score": N, "gap": "...", "fix": "...", "note": "..."}},
  "internal_consistency": {{"score": N, "gap": "...", "fix": "...", "note": "..."}},
  "voice_clarity": {{"score": N, "gap": "...", "fix": "...", "note": "..."}},
  "canon_coverage": {{"score": N, "gap": "...", "fix": "...", "note": "..."}},
  "slop_in_planning_docs": {{"found": ["list any AI slop patterns found in exemplar dialogue, voice examples, or character descriptions"], "note": "..."}},
  "contradictions_found": ["list any factual contradictions between documents"],
  "overall_score": N,
  "lore_score": N,
  "weakest_dimension": "...",
  "top_3_improvements": ["ranked list of the 3 highest-leverage improvements"]
}}

WEIGHTING: lore/worldbuilding 40%, character 30%, structure 20%, craft 10%.
A novel with thin worldbuilding but a complete outline is WORSE than deep
worldbuilding with an incomplete outline.

FINAL CHECK: If your overall_score is above 7, re-read your gap lists.
If any gap describes a problem that would force a writer to stop and
invent something during drafting, your score is too high. Revise down.
"""


def evaluate_foundation():
    layers = load_layer_files()
    prompt = FOUNDATION_PROMPT.format(**layers)
    raw = call_judge(prompt, max_tokens=16000)
    return parse_json_response(raw)


# --- Chapter Evaluation ---

CHAPTER_PROMPT = """Evaluate this fantasy novel chapter against the planning docs.

SCORING CALIBRATION:
  9-10: Among the best chapters you've read in published fantasy. Name
        a specific published chapter it competes with, or don't give 9+.
  7-8:  Strong, publishable with editorial polish. Specific flaws exist
        but don't break the reading experience.
  5-6:  Functional but flat. A competent draft that needs substantial revision.
        Generic where it should be specific. Safe where it should risk.
  3-4:  Significant problems. Voice breaks, beats missed, prose generic.
  1-2:  Not usable. Rewrite from scratch.

  The MEDIAN score for a competent AI-generated chapter should be 6.
  A 7 means it does something a generic AI draft wouldn't.
  An 8 means a human editor would keep it with minor notes.
  Most dimensions should score 6-7. Reserve 8+ for genuine excellence.

MANDATORY: For each dimension, you must identify:
  (a) The single WEAKEST MOMENT -- quote the specific sentence or passage
  (b) What would make it better -- a concrete revision, not a vague note
  If every sentence is perfect, you're not reading carefully enough.

VOICE DEFINITION:
{voice}

WORLD BIBLE (summary):
{world}

CHARACTER REGISTRY:
{characters}

CANON (established hard facts -- violations are bugs):
{canon}

CHAPTER OUTLINE ENTRY:
{chapter_outline}

PREVIOUS CHAPTER (last 1500 words):
{prev_chapter_tail}

THE CHAPTER TO EVALUATE:
{chapter_text}

CROSS-CHECKS (perform before scoring):
1. QUOTE TEST: Find the 3 best sentences and 3 weakest sentences.
   If you can't find 3 weak ones, lower your standards -- every
   chapter has weak moments. Look for: generic phrasing where
   specificity was possible, rhythmic monotony in any paragraph,
   metaphors that don't come from the character's experience,
   emotional moments that tell instead of show, transitions that
   summarize instead of dramatize.
2. DIALOGUE REALISM: Read all dialogue aloud (mentally). Does it
   sound like speech or like written prose? Do characters say things
   a 14-year-old / 60-year-old / etc. would actually say?
3. SCENE VS SUMMARY: How much of the chapter is in-scene (moment
   by moment, with dialogue and action) vs summary (narrator
   compressing time)? Chapters heavy on summary score lower on
   engagement regardless of prose quality.
4. AI PATTERN CHECK: Look for these common AI writing patterns:
   - Every paragraph the same length
   - Observations always in threes (X, Y, and Z)
   - Emotional beats that arrive on schedule rather than surprising
   - Characters who never say the wrong thing or talk past each other
   - Description that catalogs instead of selecting (listing 5 sensory
     details when 2 specific ones would be sharper)
   - Internal monologue explaining what the scene already showed
5. EARNED VS GIVEN: Is tension earned through scene work or handed to
   the reader through the narrator's assertions? Is mystery maintained
   through genuine withholding or through the character conveniently
   not thinking about things they'd think about?

Score these dimensions:

- voice_adherence: Does the prose match voice.md Part 2? Check: sentence
  rhythm variation, vocabulary wells, body-before-emotion principle,
  the specific tone described. Quote the strongest voice moment AND
  the weakest. Does ANY passage sound like generic fantasy prose that
  could appear in any novel? If yes, score 7 max.

- beat_coverage: Did it hit every beat from the outline? Were beats
  dramatized or merely mentioned? A beat that's summarized in a sentence
  instead of lived in a scene counts as half-hit. Score reflects
  QUALITY of beat execution, not just presence.

- character_voice: Remove all dialogue tags mentally. Can you tell who's
  speaking? Do characters ever sound alike? Does dialogue read as speech
  or as written prose? Does the primary viewpoint character sound age-
  and background-specific, or like "young protagonist"? Does anyone say something surprising -- not
  just the right thing, but a REAL thing? Characters who never stumble,
  hesitate, or say something slightly wrong are AI-pattern characters.

- plants_seeded: Were foreshadowing elements placed naturally? A plant
  that's obvious is worse than a plant that's invisible. Score based on
  HOW WELL they're integrated, not just whether they're present.

- prose_quality: Sentence variety (measure: do 3+ consecutive sentences
  start the same way?). Specificity (concrete nouns > abstract).
  Metaphors from the viewpoint character's experience, not from a thesaurus. Show-don't-tell
  at emotional peaks. QUOTE the weakest sentence and explain why. Also
  check for: repeated phrases, leaned-on constructions, paragraphs that
  could be cut without loss.

- continuity: Does it follow logically from the previous chapter? Emotional
  continuity as well as plot continuity. Does the character's state of
  mind track?

- canon_compliance: Check ALL facts against canon. List violations.
  One major violation caps score at 6. Check: character names, locations,
  magic system rules, timeline, established events, physical descriptions.

- lore_integration: Does the world do WORK in this chapter, or is it
  set dressing? A scene that could happen in any fantasy city with
  find-and-replace on proper nouns scores 5 max.

- engagement: Would a reader turn the page? Where does tension come from --
  plot, character, mystery, prose? Is there a moment that SURPRISES?
  Predictable excellence is still predictable. Score 8+ only if the
  chapter does something unexpected.

Respond with JSON:
{{
  "voice_adherence": {{"score": N, "weakest_moment": "quote the specific weak passage", "fix": "how to improve it", "note": "..."}},
  "beat_coverage": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "character_voice": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "plants_seeded": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "prose_quality": {{"score": N, "weakest_sentence": "quote it", "fix": "rewrite suggestion", "strongest_sentence": "quote it", "note": "..."}},
  "continuity": {{"score": N, "note": "..."}},
  "canon_compliance": {{"score": N, "violations": ["list any found"], "note": "..."}},
  "lore_integration": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "engagement": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "three_weakest_sentences": ["quote 1", "quote 2", "quote 3"],
  "three_strongest_sentences": ["quote 1", "quote 2", "quote 3"],
  "ai_patterns_detected": ["list any AI writing patterns found"],
  "overall_score": N,
  "weakest_dimension": "...",
  "top_3_revisions": ["specific, actionable revision 1", "revision 2", "revision 3"],
  "new_canon_entries": ["any new facts established in this chapter"]
}}

FINAL CHECK: If your overall_score is above 7, re-read your weakest_moment
quotes. If any of them describe a problem that an editor would flag, your
score is too high. The median AI chapter is a 6. An 8 is exceptional. A 9
is rare. A 10 does not exist for a first draft.
"""


CHAPTER_PROMPT_V2 = """Evaluate this fantasy novel chapter against the planning docs and governing perspective.

GOVERNING PERSPECTIVE:
{perspective}

VOICE DEFINITION:
{voice}

CHARACTER REGISTRY:
{characters}

CHARACTER ENGINE:
{character_engine}

WORLD BIBLE:
{world}

CANON:
{canon}

THREAD REGISTRY WINDOW:
{thread_registry}

CHAPTER PLAN REFERENCE:
{chapter_reference}

PREVIOUS CHAPTER (tail):
{prev_chapter_tail}

CHAPTER TO EVALUATE:
{chapter_text}

Score the chapter on these dimensions. For every scored dimension, give:
- score
- weakest_moment
- fix
- note

Primary chapter dimensions:
- baseline_voice
- perspective_distinctiveness
- character_truthfulness
- dialogue_separability
- formal_enactment
- surplus_life
- scene_method_freshness
- humor_signature
- prose_quality
- continuity
- canon_compliance
- lore_integration
- engagement

Compatibility dimensions for existing tools:
- voice_adherence
- beat_coverage
- character_voice
- plants_seeded

Definitions:
- baseline_voice: does the chapter still sound like the established book?
- perspective_distinctiveness: does the chapter feel perceived by a specific mind with blind spots?
- character_truthfulness: do people behave from contradiction, pressure, concealment, and cognitive ceiling?
- dialogue_separability: can speakers be distinguished and do they sound socially alive rather than theme-perfect?
- formal_enactment: does prose shape change when content changes? obsession scenes, unbearable scenes, bureaucracy, bodily stress should not all read the same
- surplus_life: are there details serving the world and scene rather than only the argument?
- scene_method_freshness: does the scene arrive through a vivid method rather than obedient beat execution?
- humor_signature: does any humor feel native to the governing consciousness?
- beat_coverage: how well does the chapter honor its current plan reference without becoming mechanical?
- plants_seeded: are threads and plants integrated naturally rather than telegraphed?

AI-pattern checks:
- generic abstract dialogue
- repeated sentence openings
- metaphor domains that do not belong to the viewpoint or speaker
- theme-perfect lines
- explanation after the scene already showed the point

Return JSON:
{{
  "baseline_voice": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "perspective_distinctiveness": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "character_truthfulness": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "dialogue_separability": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "formal_enactment": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "surplus_life": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "scene_method_freshness": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "humor_signature": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "prose_quality": {{"score": N, "weakest_sentence": "...", "fix": "...", "strongest_sentence": "...", "note": "..."}},
  "continuity": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "canon_compliance": {{"score": N, "violations": ["..."], "note": "..."}},
  "lore_integration": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "engagement": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "voice_adherence": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "beat_coverage": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "character_voice": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "plants_seeded": {{"score": N, "weakest_moment": "...", "fix": "...", "note": "..."}},
  "three_weakest_sentences": ["quote 1", "quote 2", "quote 3"],
  "three_strongest_sentences": ["quote 1", "quote 2", "quote 3"],
  "ai_patterns_detected": ["list any AI writing patterns found"],
  "overall_score": N,
  "weakest_dimension": "...",
  "top_3_revisions": ["specific revision 1", "specific revision 2", "specific revision 3"],
  "new_canon_entries": ["any new facts established in this chapter"]
  {risk_schema}
}}
"""


FULL_NOVEL_EVIDENCE_PROMPT = """Evaluate this fantasy novel holistically from planning docs plus an evidence pack of real passages.

VOICE:
{voice}

PERSPECTIVE:
{perspective}

WORLD:
{world}

CHARACTERS:
{characters}

CANON:
{canon}

THREAD REGISTRY:
{thread_registry}

EVIDENCE PACK:
{evidence}

Score these novel-level dimensions:
- arc_completion
- pacing_curve
- perspective_continuity
- formal_variety
- temporal_variety
- theme_pressure
- surplus_life
- human_texture
- over_determinedness_penalty
- world_consistency
- overall_engagement

Compatibility dimensions for existing tooling:
- theme_coherence
- foreshadowing_resolution
- voice_consistency

Rules:
- Do not hard-cap theme coherence.
- If theme pressure is high and surplus life is low, apply an over_determinedness_penalty and explain why.
- Tie major claims to the evidence pack's real passages and chapter numbers.
- Name the weakest chapter if the evidence supports one.

Return JSON:
{{
  "arc_completion": {{"score": N, "note": "..."}},
  "pacing_curve": {{"score": N, "note": "..."}},
  "perspective_continuity": {{"score": N, "note": "..."}},
  "formal_variety": {{"score": N, "note": "..."}},
  "temporal_variety": {{"score": N, "note": "..."}},
  "theme_pressure": {{"score": N, "note": "..."}},
  "surplus_life": {{"score": N, "note": "..."}},
  "human_texture": {{"score": N, "note": "..."}},
  "over_determinedness_penalty": {{"score": N, "note": "..."}},
  "world_consistency": {{"score": N, "note": "..."}},
  "overall_engagement": {{"score": N, "note": "..."}},
  "theme_coherence": {{"score": N, "note": "..."}},
  "foreshadowing_resolution": {{"score": N, "note": "..."}},
  "voice_consistency": {{"score": N, "note": "..."}},
  "novel_score": N,
  "weakest_dimension": "...",
  "weakest_chapter": N,
  "top_suggestion": "..."
}}
"""


def build_risk_schema(include_risk: bool) -> str:
    if not include_risk:
        return ""
    return ',\n  "risk_assessment": {"interestingness": N, "necessity": N, "coherence_floor": N, "note": "..."}'


def ensure_dimension(
    result: dict,
    target_key: str,
    source_key: str,
    *,
    default_note: str,
) -> None:
    if target_key in result:
        return
    source = result.get(source_key)
    if isinstance(source, dict):
        result[target_key] = {
            "score": source.get("score", 0),
            "weakest_moment": source.get("weakest_moment", source.get("weakest_sentence", "")),
            "fix": source.get("fix", ""),
            "note": source.get("note", default_note),
        }
        return
    result[target_key] = {"score": 0, "weakest_moment": "", "fix": "", "note": default_note}


def normalize_chapter_result(result: dict, include_risk: bool) -> dict:
    ensure_dimension(result, "voice_adherence", "baseline_voice", default_note="compatibility alias for baseline_voice")
    ensure_dimension(result, "character_voice", "dialogue_separability", default_note="compatibility alias for dialogue_separability")
    ensure_dimension(result, "beat_coverage", "scene_method_freshness", default_note="compatibility alias for scene_method_freshness")
    ensure_dimension(result, "plants_seeded", "lore_integration", default_note="compatibility alias for lore_integration")
    result.setdefault("three_weakest_sentences", [])
    result.setdefault("three_strongest_sentences", [])
    result.setdefault("ai_patterns_detected", [])
    result.setdefault("top_3_revisions", [])
    result.setdefault("new_canon_entries", [])
    result.setdefault("weakest_dimension", "unknown")
    if include_risk and "risk_assessment" not in result:
        result["risk_assessment"] = {
            "interestingness": result.get("engagement", {}).get("score", 0),
            "necessity": result.get("scene_method_freshness", {}).get("score", 0),
            "coherence_floor": result.get("continuity", {}).get("score", 0),
            "note": "Fallback risk rubric derived from chapter dimensions.",
        }
    return result


def evaluate_chapter(chapter_num, *, include_risk: bool = False):
    layers = load_extended_layer_files()
    chapter_text = load_chapter(chapter_num)
    if not chapter_text.strip():
        return {"error": f"Chapter {chapter_num} is empty or missing",
                "overall_score": 0.0}

    prev_text = load_chapter(chapter_num - 1) if chapter_num > 1 else "(first chapter)"
    prev_tail = prev_text[-3000:] if len(prev_text) > 3000 else prev_text

    prompt = CHAPTER_PROMPT_V2.format(
        perspective=layers["perspective"][:3000],
        voice=layers["voice"],
        world=layers["world"][:4000],
        characters=layers["characters"],
        character_engine=layers["character_engine"][:6000],
        canon=layers["canon"],
        thread_registry=layers["thread_registry"][:3000],
        chapter_reference=extract_chapter_reference(chapter_num, layers),
        prev_chapter_tail=prev_tail,
        chapter_text=chapter_text,
        risk_schema=build_risk_schema(include_risk),
    )
    raw = call_judge(prompt, max_tokens=8000)
    result = normalize_chapter_result(parse_json_response(raw), include_risk)

    # Mechanical slop check -- adjusts score independently of judge
    slop = slop_score(chapter_text)
    result["slop"] = slop
    if "overall_score" in result:
        adjusted = max(0, result["overall_score"] - slop["slop_penalty"])
        result["raw_judge_score"] = result["overall_score"]
        result["overall_score"] = round(adjusted, 2)

    return result


# --- Full Novel Evaluation ---

FULL_NOVEL_PROMPT = """Evaluate this complete fantasy novel holistically.
You have the planning docs and ALL chapter summaries with their individual scores.

VOICE DEFINITION:
{voice}

WORLD BIBLE:
{world_summary}

CHARACTER REGISTRY:
{characters}

OUTLINE + FORESHADOWING LEDGER:
{outline}

CHAPTER SUMMARIES AND SCORES:
{chapter_summaries}

Score these novel-level dimensions 0-10:
- arc_completion: Do character arcs resolve satisfyingly?
- pacing_curve: Does tension build properly across the book?
- theme_coherence: Are themes explored consistently?
- foreshadowing_resolution: Are all planted threads harvested?
- world_consistency: Any lore contradictions across chapters?
- voice_consistency: Is the voice steady throughout?
- overall_engagement: Is this a compelling read start to finish?

Respond with JSON:
{{
  "arc_completion": {{"score": N, "note": "..."}},
  "pacing_curve": {{"score": N, "note": "..."}},
  "theme_coherence": {{"score": N, "note": "..."}},
  "foreshadowing_resolution": {{"score": N, "note": "..."}},
  "world_consistency": {{"score": N, "note": "..."}},
  "voice_consistency": {{"score": N, "note": "..."}},
  "overall_engagement": {{"score": N, "note": "..."}},
  "novel_score": N,
  "weakest_dimension": "...",
  "weakest_chapter": N,
  "top_suggestion": "..."
}}
"""


def normalize_full_result(result: dict) -> dict:
    if "theme_coherence" not in result and "theme_pressure" in result:
        result["theme_coherence"] = {
            "score": result["theme_pressure"].get("score", 0),
            "note": "compatibility alias for theme_pressure",
        }
    if "foreshadowing_resolution" not in result and "arc_completion" in result:
        result["foreshadowing_resolution"] = {
            "score": result["arc_completion"].get("score", 0),
            "note": "compatibility alias for arc_completion",
        }
    if "voice_consistency" not in result and "perspective_continuity" in result:
        result["voice_consistency"] = {
            "score": result["perspective_continuity"].get("score", 0),
            "note": "compatibility alias for perspective_continuity",
        }
    result.setdefault("weakest_dimension", "unknown")
    result.setdefault("weakest_chapter", 0)
    result.setdefault("top_suggestion", "")
    return result


def evaluate_full(evidence_path: str | None = None):
    if evidence_path:
        layers = load_extended_layer_files()
        evidence_pack = load_json(Path(evidence_path))
        prompt = FULL_NOVEL_EVIDENCE_PROMPT.format(
            voice=layers["voice"][:3000],
            perspective=layers["perspective"][:2500],
            world=layers["world"][:2500],
            characters=layers["characters"][:3000],
            canon=layers["canon"][:2500],
            thread_registry=layers["thread_registry"][:2500],
            evidence=render_evidence_pack(evidence_pack),
        )
        raw = call_judge(prompt, max_tokens=FULL_EVIDENCE_MAX_TOKENS)
        result = normalize_full_result(parse_json_response(raw))
        result.setdefault("evaluation_mode", "evidence")
        return result

    print(SUMMARY_MODE_FULL_WARNING, file=sys.stderr)
    layers = load_layer_files()
    chapters = load_all_chapters()

    if not chapters:
        return normalize_full_result(
            {
                "error": "No chapters found",
                "novel_score": 0.0,
                "warning": SUMMARY_MODE_FULL_WARNING,
                "evaluation_mode": "summary_fallback",
            }
        )

    # Build chapter summaries (first/last 500 chars of each)
    summaries = []
    for num in sorted(chapters.keys()):
        text = chapters[num]
        word_count = len(text.split())
        head = text[:500]
        tail = text[-500:] if len(text) > 500 else ""
        summaries.append(
            f"Chapter {num} ({word_count} words):\n"
            f"  Opening: {head}...\n"
            f"  Closing: ...{tail}\n"
        )

    prompt = FULL_NOVEL_PROMPT.format(
        voice=layers["voice"],
        world_summary=layers["world"][:3000],
        characters=layers["characters"],
        outline=layers["outline"],
        chapter_summaries="\n".join(summaries),
    )
    raw = call_judge(prompt)
    result = normalize_full_result(parse_json_response(raw))
    result.setdefault("warning", SUMMARY_MODE_FULL_WARNING)
    result.setdefault("evaluation_mode", "summary_fallback")
    return result


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Evaluate the novel")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--phase", choices=["foundation"],
                       help="Evaluate planning documents")
    group.add_argument("--chapter", type=int,
                       help="Evaluate a specific chapter number")
    group.add_argument("--full", action="store_true",
                       help="Evaluate the entire novel")
    parser.add_argument(
        "--evidence",
        help="Optional evidence-pack JSON path. Used by --full and accepted for forward compatibility elsewhere.",
    )
    parser.add_argument(
        "--risk",
        action="store_true",
        help="Use the risk-chapter rubric when evaluating a chapter.",
    )
    args = parser.parse_args()

    if args.phase == "foundation":
        result = evaluate_foundation()
        score_key = "overall_score"
    elif args.chapter is not None:
        result = evaluate_chapter(args.chapter, include_risk=args.risk)
        score_key = "overall_score"
    elif args.full:
        result = evaluate_full(args.evidence)
        score_key = "novel_score"

    # Print structured output
    print("---")
    if score_key in result:
        print(f"{score_key}: {result[score_key]}")
    for key, val in result.items():
        if key == score_key:
            continue
        if isinstance(val, dict):
            print(f"{key}: {val.get('score', 'N/A')} -- {val.get('note', '')}")
        else:
            print(f"{key}: {val}")

    # Save full eval log
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = args.phase or (f"ch{args.chapter:02d}" if args.chapter else "full")
    log_path = EVAL_LOG_DIR / f"{timestamp}_{mode}.json"
    with open(log_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\neval_log: {log_path}")


if __name__ == "__main__":
    main()
