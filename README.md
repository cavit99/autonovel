# autonovel

`autonovel` is a script-first fiction pipeline for generating, drafting,
revising, reviewing, and exporting a novel from a seed concept.

## Current Runtime

`run_pipeline.py` is the canonical automated path on this branch.

Current phase order:

1. `foundation`
2. `drafting`
3. `revision`
4. `review`
5. `export`

Current runtime features:

- governing perspective via `gen_perspective.py`
- voice discovery via `discover_voice.py`
- structured character constraints via `character_engine.json`
- planning split across `arc_outline.md`, `chapter_cards.md`, and
  `thread_registry.json`
- stateful drafting with `advance_state.py` and writer-backed `plan_scene.py`
- risk-chapter and critical-chapter variant drafting via `draft_variant.py`
  and `compare_variants.py`
- patch revision via `patch_revision.py` and `apply_edits.py`
- prose evaluation via evidence packs, `dialogue_audit.py`,
  `narration_audit.py`, `reader_panel.py --evidence`,
  `humanity_panel.py --evidence`, and `evaluate.py --full --evidence`
- manifest generation via `build_manifest.py` and validation via
  `consistency_gate.py`
- a separate final `review` phase before export

Important compatibility note:

- `outline.md` and `arc_summary.md` still exist, but they are now
  compatibility and export artifacts rebuilt from the current planning stack
  plus accepted chapters
- the planning source of truth is `arc_outline.md`, `chapter_cards.md`,
  `thread_registry.json`, accepted chapters, and `manifest.json`

## Quick Start

```bash
uv sync
cp .env.example .env
uv run python seed.py
```

If `seed.py` is not part of your workflow, write `seed.txt` directly.

To run the full automated pipeline from scratch:

```bash
uv run python run_pipeline.py --from-scratch
```

To resume from the current `state.json`:

```bash
uv run python run_pipeline.py
```

Useful phase-limited runs:

```bash
uv run python run_pipeline.py --phase foundation
uv run python run_pipeline.py --phase drafting
uv run python run_pipeline.py --phase revision --max-cycles 4
uv run python run_pipeline.py --phase review
uv run python run_pipeline.py --phase export
```

## Automated Pipeline Summary

### 1. Foundation

`run_pipeline.py` currently runs foundation in this order:

1. `gen_world.py` -> `world.md`
2. `gen_characters.py --emit-engine` -> `characters.md` plus
   `character_engine.json`
3. `gen_perspective.py`
4. `discover_voice.py --trials 8`
5. `gen_arc.py`
6. `gen_chapter_cards.py`
7. `gen_thread_registry.py`
8. `gen_outline_part2.py` for legacy outline compatibility
9. `gen_canon.py` -> `canon.md`
10. `build_manifest.py --phase foundation`
11. `consistency_gate.py --phase foundation`
12. `voice_fingerprint.py`
13. `evaluate.py --phase foundation`

The manual path still needs shell redirection for `gen_world.py`,
`gen_characters.py`, and `gen_canon.py`, but `run_pipeline.py` already captures
their stdout into the target files.

### 2. Drafting

For each chapter, the orchestrator currently does this:

1. `advance_state.py --chapter N-1` when `N > 1`
2. `plan_scene.py N --variants 4`
3. `draft_chapter.py N --mode auto`
4. `evaluate.py --chapter N`
5. optional variant pass for critical, risky, or weak chapters:
   `draft_variant.py`, `compare_variants.py`, then re-evaluate
6. `build_manifest.py --phase drafting --chapter N`
7. `consistency_gate.py --phase drafting --chapter N`

`draft_chapter.py --mode auto` prefers the PR3+ path when the governing
artifacts exist:

- `perspective.md`
- `voice.md`
- `character_engine.json`
- `chapter_cards.md`
- `thread_registry.json`
- `world.md`
- `canon.md`
- `scene_options/ch_NN.json`
- `state/story_state/ch_NN.json` for prior accepted chapters

### 3. Revision

The revision phase is patch-backed and evidence-backed:

1. `adversarial_edit.py all`
2. `dialogue_audit.py --all`
3. `narration_audit.py --all`
4. `assemble_evidence_pack.py --novel`
5. `reader_panel.py --evidence ...`
6. `humanity_panel.py --evidence ...`
7. `gen_brief.py --auto --require-patch-directives`
8. `patch_revision.py` and `apply_edits.py` for a targeted chapter when a
   patch-friendly brief is available
9. refresh the evidence pack if prose changed
10. `evaluate.py --full --evidence ...`
11. `build_manifest.py --phase revision`
12. `consistency_gate.py --phase revision`

### 4. Review

The full-manuscript review phase is separate from evidence evaluation:

```bash
uv run python review.py --output reviews.md
uv run python review.py --parse
```

The orchestrator then runs:

```bash
uv run python build_manifest.py --phase review
uv run python consistency_gate.py --phase review
```

### 5. Export

The export phase rebuilds compatibility artifacts from current source-of-truth
files, then assembles the manuscript and optional PDF:

```bash
uv run python build_outline.py
uv run python build_arc_summary.py
uv run python typeset/build_tex.py
tectonic typeset/novel.tex
uv run python build_manifest.py --phase export
uv run python consistency_gate.py --phase export
```

`build_outline.py` and `build_arc_summary.py` now derive from accepted
chapters, `arc_outline.md`, `chapter_cards.md`, `thread_registry.json`, and
`manifest.json`. They no longer rely on fixed chapter counts or legacy
story-specific assumptions.

## Manual Targeted Workflow

You can still run pieces of the pipeline directly.

Foundation:

```bash
uv run python gen_world.py > world.md
uv run python gen_characters.py --emit-engine > characters.md
uv run python gen_perspective.py
uv run python discover_voice.py --trials 8
uv run python gen_arc.py
uv run python gen_chapter_cards.py
uv run python gen_thread_registry.py
uv run python gen_canon.py > canon.md
uv run python gen_outline_part2.py
uv run python build_manifest.py --phase foundation
uv run python consistency_gate.py --phase foundation
```

Draft a chapter manually:

```bash
uv run python plan_scene.py 1 --variants 4
uv run python draft_chapter.py 1 --mode auto
uv run python evaluate.py --chapter 1
uv run python advance_state.py --chapter 1
uv run python build_manifest.py --phase drafting --chapter 1
uv run python consistency_gate.py --phase drafting --chapter 1
```

Patch revision:

```bash
uv run python roughness_guard.py 5
uv run python gen_brief.py --auto --require-patch-directives
uv run python patch_revision.py 5 briefs/ch05_auto.md --plan-only
uv run python apply_edits.py 5
```

Evidence evaluation:

```bash
uv run python assemble_evidence_pack.py --novel
uv run python dialogue_audit.py --all
uv run python narration_audit.py --all
uv run python reader_panel.py --evidence eval_logs/evidence_pack.json
uv run python humanity_panel.py --evidence eval_logs/evidence_pack.json
uv run python evaluate.py --full --evidence eval_logs/evidence_pack.json
uv run python review.py
```

## Source Of Truth Vs Compatibility

Current source-of-truth artifacts:

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
- `scene_options/ch_XX.json`
- `state/story_state/ch_XX.json`
- `chapters/ch_XX.md`
- `manifest.json`

Compatibility or export artifacts:

- `outline.md`
- `arc_summary.md`
- `manuscript.md`
- `reviews.md`
- `state.json`
- `results.tsv`

## Tool Map

Foundation and planning:

- `gen_world.py`
- `gen_characters.py --emit-engine`
- `gen_perspective.py`
- `discover_voice.py`
- `gen_arc.py`
- `gen_chapter_cards.py`
- `gen_thread_registry.py`
- `gen_canon.py`
- `gen_outline.py`
- `gen_outline_part2.py`

Drafting:

- `advance_state.py`
- `plan_scene.py`
- `draft_chapter.py`
- `draft_variant.py`
- `compare_variants.py`

Revision and evaluation:

- `adversarial_edit.py`
- `dialogue_audit.py`
- `narration_audit.py`
- `assemble_evidence_pack.py`
- `reader_panel.py`
- `humanity_panel.py`
- `evaluate.py`
- `gen_brief.py`
- `patch_revision.py`
- `apply_edits.py`
- `review.py`

Orchestration and export:

- `run_pipeline.py`
- `build_manifest.py`
- `consistency_gate.py`
- `build_outline.py`
- `build_arc_summary.py`
- `typeset/build_tex.py`

## Environment

Common env vars:

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

See `.env.example` for the starter template.

## Migration Note

If you were using the old outline-led flow:

- treat `outline.md` as a compatibility artifact, not the planning truth
- treat `arc_summary.md` as a compatibility/export summary, not the primary
  evaluation input
- use `review` as its own phase after revision, not as part of revision
- prefer `arc_outline.md`, `chapter_cards.md`, `thread_registry.json`,
  accepted chapters, and `manifest.json` when inspecting current story state

## Further Reading

- `WORKFLOW.md` for concrete command sequences
- `PIPELINE.md` for the technical phase-by-phase description
- `program.md` for agent-facing operating rules
