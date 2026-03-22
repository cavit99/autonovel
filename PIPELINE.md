# AUTONOVEL PIPELINE

This document describes the runtime as it exists on the current branch.

## Current Phase Order

`run_pipeline.py` currently orchestrates five phases:

1. `foundation`
2. `drafting`
3. `revision`
4. `review`
5. `export`

This is the active runtime order. `review` is a separate phase. Export happens
after review, not during revision.

## Phase Details

### Phase 1: Foundation

Current execution order in `run_pipeline.py`:

```text
gen_world.py                      -> world.md
gen_characters.py --emit-engine   -> characters.md + character_engine.json
gen_perspective.py
discover_voice.py --trials 8      -> voice.md + voice_discovery.json
gen_arc.py                        -> arc_outline.md
gen_chapter_cards.py              -> chapter_cards.md
gen_thread_registry.py            -> thread_registry.json
gen_outline_part2.py              -> outline.md (compatibility)
gen_canon.py                      -> canon.md
build_manifest.py --phase foundation
consistency_gate.py --phase foundation
voice_fingerprint.py
evaluate.py --phase foundation
```

Notes:

- `gen_world.py`, `gen_characters.py`, and `gen_canon.py` still print markdown
  to stdout in direct manual use; the orchestrator captures that stdout into
  files
- `discover_voice.py` is the foundation-time voice discovery mechanism
- `voice_fingerprint.py` is prose telemetry, but it is still run during
  foundation in the current automated path
- `gen_outline_part2.py` is retained as the compatibility wrapper for
  `outline.md`

### Phase 2: Drafting

Per chapter, the orchestrator currently does this:

```text
advance_state.py --chapter N-1        (when N > 1)
plan_scene.py N --variants 4
draft_chapter.py N --mode auto
evaluate.py --chapter N               (or --risk for risk chapters)
optional variant pass:
  draft_variant.py N --variants 3 --mode auto
  compare_variants.py N
  evaluate.py --chapter N [--risk]
build_manifest.py --phase drafting --chapter N
consistency_gate.py --phase drafting --chapter N
```

Important drafting rules now active:

- `draft_chapter.py --mode auto` prefers the new path when governing
  perspective, character engine, planning split, scene options, and prior
  story state exist
- `plan_scene.py` is writer-backed when API config is available and falls back
  to deterministic planning otherwise
- risk chapters come from `chapter_cards.md` and `arc_outline.md`, then land in
  `manifest.json`
- critical, risky, or weak chapters may trigger a variant drafting pass

Active orchestrator thresholds:

- `FOUNDATION_THRESHOLD = 7.5`
- `CHAPTER_THRESHOLD = 6.0`
- `RISK_INTERESTINGNESS_FLOOR = 7.0`
- `RISK_COHERENCE_FLOOR = 5.0`
- `CRITICAL_SCENE_THRESHOLD = 6.3`
- `MAX_CHAPTER_ATTEMPTS = 5`
- `MIN_REVISION_CYCLES = 3`
- `MAX_REVISION_CYCLES = 6`

### Phase 3: Revision

Current execution order:

```text
adversarial_edit.py all
dialogue_audit.py --all
narration_audit.py --all
assemble_evidence_pack.py --novel
reader_panel.py --evidence eval_logs/evidence_pack.json
humanity_panel.py --evidence eval_logs/evidence_pack.json
gen_brief.py --auto --require-patch-directives
optional targeted patch pass:
  patch_revision.py CHAPTER BRIEF --plan-only
  apply_edits.py CHAPTER
  assemble_evidence_pack.py --novel   (refresh after patch)
evaluate.py --full --evidence eval_logs/evidence_pack.json
build_manifest.py --phase revision
consistency_gate.py --phase revision
```

Revision reality:

- the active loop is evidence-backed, not summary-led
- `dialogue_audit.py` and `narration_audit.py` are part of the normal revision
  cycle
- patch revision is wired into the automated path when `gen_brief.py` produces
  a patch-friendly brief
- `apply_edits.py` is the local patch application step
- full-manuscript review is not part of revision; it happens in the next phase

### Phase 4: Review

Current execution order:

```text
review.py --output reviews.md
review.py --parse
build_manifest.py --phase review
consistency_gate.py --phase review
```

This is the dedicated final full-manuscript review phase. It remains distinct
from evidence-mode evaluation.

### Phase 5: Export

Current execution order:

```text
build_outline.py
build_arc_summary.py
manuscript.md assembly
typeset/build_tex.py
tectonic typeset/novel.tex   (if available)
build_manifest.py --phase export
consistency_gate.py --phase export
```

Export helper behavior:

- `build_outline.py` rebuilds `outline.md` from accepted chapters plus
  `arc_outline.md`, `chapter_cards.md`, `thread_registry.json`, and
  `manifest.json`
- `build_arc_summary.py` rebuilds `arc_summary.md` from the same source-of-truth
  stack
- both helpers now avoid fixed chapter counts and stale story-specific
  assumptions

## Source Of Truth

### Foundation And Planning

- `seed.txt`
- `world.md`
- `characters.md`
- `character_engine.json`
- `perspective.md`
- `voice.md`
- `arc_outline.md`
- `chapter_cards.md`
- `thread_registry.json`
- `canon.md`

### Drafting And Accepted Prose

- `scene_options/ch_XX.json`
- `state/story_state/ch_XX.json`
- `chapters/ch_XX.md`

### Runtime State And Validation

- `manifest.json`
- `reviews.md`
- `eval_logs/evidence_pack.json`
- `edit_logs/dialogue_audit.json`
- `edit_logs/narration_audit.json`
- `edit_logs/reader_panel.json`
- `edit_logs/humanity_panel.json`

### Compatibility And Presentation

- `outline.md`
- `arc_summary.md`
- `manuscript.md`
- `state.json`
- `results.tsv`

`outline.md` is no longer the planning source of truth. It is a compatibility
and export artifact.

## New-Mode Draft Context

In new mode, `draft_chapter.py` assembles context in this order:

1. `perspective.md`
2. `voice.md`
3. `character_engine.json`
4. `state/story_state/ch_{n-1}.json`
5. current chapter card from `chapter_cards.md`
6. `scene_options/ch_XX.json`
7. local thread window from `thread_registry.json`
8. `world.md`
9. `canon.md`

New-mode behavior:

- blind spots are active constraints
- humor belongs to the governing consciousness, not generic narration
- cognitive ceilings constrain dialogue and reasoning
- the chapter card's irreversible change remains binding
- optional non-plot threads may be deferred or dropped
- scene choice comes from `scene_options`, not a rigid legacy beat march

Legacy outline mode still exists through `draft_chapter.py --mode legacy`.

## Planning Split

Current planning truth is split across:

- `arc_outline.md` for irreversible turns, major reveals, pressure
  escalations, and candidate risk chapters
- `chapter_cards.md` for chapter-level structural cards
- `thread_registry.json` for typed plot, pressure, echo, and texture threads

Current compatibility rule:

- `gen_outline.py` and `gen_outline_part2.py` keep `outline.md` alive for
  legacy consumers
- `build_outline.py` refreshes `outline.md` during export from current accepted
  prose plus the planning split

## Manifest And Consistency Gate

`build_manifest.py` writes the runtime snapshot used across phases:

- title
- phase
- accepted chapter count
- planned chapter count
- word count
- risk chapters
- files and hashes
- evidence-pack metadata
- configured model names

`consistency_gate.py` validates phase requirements and catches drift such as:

- missing required artifacts for the active phase
- manifest counts diverging from current chapter files
- evidence pack hash mismatch against the current manuscript
- planning and compatibility artifacts drifting out of sync

## Revision And Evaluation Notes

Important active constraints:

- evidence-pack evaluation is now part of the automated revision loop
- `reader_panel.py` still has a legacy no-arg compatibility mode, but that is
  not the primary review path
- `review.py` remains the final full-manuscript reviewer
- patch revision expects actionable directives; prose-only briefs are not safe
  deterministic patch inputs

## Environment Variables

Currently used by the codebase:

- `ANTHROPIC_API_KEY`
- `AUTONOVEL_API_BASE_URL`
- `AUTONOVEL_WRITER_MODEL`
- `AUTONOVEL_JUDGE_MODEL`
- `AUTONOVEL_SMELL_MODEL`
- `AUTONOVEL_DIALOGUE_MODEL`
- `AUTONOVEL_REVIEW_MODEL`
- `AUTONOVEL_SCENE_PLANNER_MODEL`
- `FAL_KEY`
- `ELEVENLABS_API_KEY`

## Migration Summary

If you are comparing this branch to the older outline-led flow:

- do not describe summary-led full eval as the primary revision loop
- do not describe `outline.md` as the planning source of truth
- do not collapse review into revision
- do describe risk chapters, variants, manifest generation, and consistency
  checks as active runtime behavior
