# autonovel

Agent operating instructions for the repo in its current state.

This file reflects the runtime after the PR6 orchestrator flip and PR7 export
alignment.

## Required Reading

Before writing or evaluating anything, read:

- `voice.md`
- `CRAFT.md`
- `ANTI-SLOP.md`
- `perspective.md` when it exists
- `chapter_cards.md`
- `thread_registry.json`
- the accepted chapter files relevant to the change

## Current Artifact Stack

```text
Layer 8: manifest.json            -- runtime snapshot, counts, hashes, risk chapters
Layer 7: voice.md                 -- style guardrails plus discovered voice
Layer 6: perspective.md           -- governing consciousness
Layer 5: world.md                 -- world, history, institutions, rules
Layer 4: characters.md            -- human-readable character registry
Layer 4b: character_engine.json   -- structured contradictions and ceilings
Layer 3: arc_outline.md           -- irreversible turns, reveals, pressure, risks
Layer 2: chapter_cards.md         -- chapter-by-chapter structural cards
Layer 2b: thread_registry.json    -- plot / pressure / echo / texture
Layer 1b: scene_options/ch_XX.json -- scene choices for a chapter
Layer 1a: state/story_state/*.json -- evolving accepted-story state
Layer 1: chapters/ch_XX.md        -- accepted prose
Cross-cutting: canon.md           -- hard facts
Compatibility: outline.md         -- legacy/export outline
Compatibility: arc_summary.md     -- legacy/export arc summary
```

Source of truth:

- accepted chapters
- `arc_outline.md`
- `chapter_cards.md`
- `thread_registry.json`
- `manifest.json`

Compatibility artifacts:

- `outline.md`
- `arc_summary.md`

## Automated Pipeline Truth

The active phase order is:

1. `foundation`
2. `drafting`
3. `revision`
4. `review`
5. `export`

Do not describe `run_pipeline.py` as legacy-only. The orchestrator now drives
the new architecture, including manifest updates, consistency gates,
evidence-backed revision, and a separate review phase.

## Foundation Rules

When building manually, the current sequence is:

1. `gen_world.py > world.md`
2. `gen_characters.py --emit-engine > characters.md`
3. `gen_perspective.py`
4. `discover_voice.py --trials 8`
5. `gen_arc.py`
6. `gen_chapter_cards.py`
7. `gen_thread_registry.py`
8. `gen_outline_part2.py`
9. `gen_canon.py > canon.md`
10. `build_manifest.py --phase foundation`
11. `consistency_gate.py --phase foundation`

Important:

- `discover_voice.py` is the voice discovery mechanism
- `voice_fingerprint.py` is telemetry, not the source of voice
- `gen_outline.py` and `gen_outline_part2.py` are compatibility wrappers
- `outline.md` is not the planning source of truth

## Drafting Rules

For chapter `N`:

1. ensure the previous accepted chapter, if any, has a story state file:
   `advance_state.py --chapter N-1`
2. generate `scene_options/ch_NN.json` with `plan_scene.py N --variants 4`
3. draft with `draft_chapter.py N --mode auto`
4. evaluate the chapter
5. for risky, critical, or weak chapters, consider `draft_variant.py` and
   `compare_variants.py`
6. if accepted, write `state/story_state/ch_NN.json` with
   `advance_state.py --chapter N`
7. refresh manifest and gate for the accepted chapter

`draft_chapter.py --mode auto`:

- uses the new planning path when governing perspective, character engine,
  planning split, scene options, and prior story state exist
- otherwise falls back to the legacy outline prompt

`draft_chapter.py --mode new` requires:

- `perspective.md`
- `voice.md`
- `character_engine.json`
- `chapter_cards.md`
- `thread_registry.json`
- `world.md`
- `canon.md`
- relevant `scene_options` and prior `story_state`

New-mode context order:

1. `perspective.md`
2. `voice.md`
3. `character_engine.json`
4. `state/story_state/ch_{n-1}.json`
5. current chapter card
6. `scene_options/ch_XX.json`
7. local thread window
8. `world.md`
9. `canon.md`

New-mode writing principles:

- governing perspective is a hard constraint
- blind spots are active, not decorative
- humor belongs to the consciousness
- characters think and speak within their ceiling
- preserve the chapter card's irreversible change
- choose the most alive scene option, not the most obedient one
- optional non-plot threads may be deferred, migrated, or dropped

## Planning Rules

`arc_outline.md` should contain only:

- irreversible turns
- major reveals
- pressure escalations
- candidate risk chapters

`thread_registry.json` should distinguish:

- `plot`
- `pressure`
- `echo`
- `texture`

Do not assume every thread must pay off. `echo` and `texture` threads may
persist for surplus life rather than plot closure.

## Revision, Review, And Export

Current revision loop:

- `adversarial_edit.py`
- `dialogue_audit.py`
- `narration_audit.py`
- `assemble_evidence_pack.py`
- `reader_panel.py --evidence`
- `humanity_panel.py --evidence`
- `gen_brief.py --auto --require-patch-directives`
- `patch_revision.py`
- `apply_edits.py`
- `evaluate.py --full --evidence`
- `build_manifest.py --phase revision`
- `consistency_gate.py --phase revision`

Important distinctions:

- revision is evidence-backed; summary-led full eval is not the primary loop
- `review.py` is the final full-manuscript review phase after revision
- patch revision depends on actionable directives; prose-only briefs are not
  safe deterministic patch inputs

Review phase:

- `review.py --output reviews.md`
- `review.py --parse`
- `build_manifest.py --phase review`
- `consistency_gate.py --phase review`

Export phase:

- `build_outline.py`
- `build_arc_summary.py`
- `typeset/build_tex.py`
- `build_manifest.py --phase export`
- `consistency_gate.py --phase export`

`build_outline.py` and `build_arc_summary.py` rebuild compatibility artifacts
from accepted prose plus the current planning stack and manifest metadata.

## Propagation Rules

When a file changes, check the downstream artifacts that depend on it:

- `perspective.md` -> review `voice.md`, chapter cards, scene planning, and
  new-mode prompts
- `world.md` -> review `canon.md`, chapter cards, and accepted prose
- `characters.md` / `character_engine.json` -> review dialogue, behavior, and
  story state
- `arc_outline.md` -> review `chapter_cards.md`, risk chapter assumptions, and
  manifest risk output
- `chapter_cards.md` -> review scene options, accepted prose, variants, and
  story-state assumptions
- `thread_registry.json` -> review scene options, local thread windows,
  compatibility outline output, and export summaries
- accepted prose -> update story state, evidence pack, export summaries, and
  manifest counts as needed

## Evaluation Rules

Current evaluator reality:

- evidence-pack evaluation is active in revision
- `dialogue_audit.py` and `narration_audit.py` are active audit tools
- `humanity_panel.py` is part of the evidence-backed revision loop
- `review.py` remains the final full-manuscript reviewer
- legacy no-arg `reader_panel.py` still exists for compatibility, but it is not
  the primary revision path

## Rules

- Prefer the planning split and accepted prose over `outline.md`.
- Treat `outline.md` and `arc_summary.md` as compatibility outputs.
- Keep canonical state deterministic in shape.
- Keep scene planning imaginative, but normalize saved outputs.
- Preserve legacy compatibility where it does not distort current source of
  truth.
