# WORKFLOW

Practical guide to using the repo as it exists on this branch.

## Setup

```bash
uv sync
cp .env.example .env
```

Minimum required env:

- `ANTHROPIC_API_KEY`

Common optional env:

- `AUTONOVEL_WRITER_MODEL`
- `AUTONOVEL_JUDGE_MODEL`
- `AUTONOVEL_SMELL_MODEL`
- `AUTONOVEL_DIALOGUE_MODEL`
- `AUTONOVEL_REVIEW_MODEL`
- `AUTONOVEL_SCENE_PLANNER_MODEL`
- `FAL_KEY`
- `ELEVENLABS_API_KEY`

For a story branch, prefer a short-lived branch such as:

```bash
git switch -c experiment/my-novel
```

## Option A: Run The Automated Pipeline

This is the main runtime now.

```bash
uv run python run_pipeline.py --help
```

Start from scratch:

```bash
uv run python run_pipeline.py --from-scratch
uv run python run_pipeline.py --approve-bootstrap
```

Resume from the current `state.json`:

```bash
uv run python run_pipeline.py
```

Useful phase-limited runs:

```bash
uv run python run_pipeline.py --phase foundation
uv run python run_pipeline.py --phase foundation --approve-bootstrap
uv run python run_pipeline.py --phase drafting
uv run python run_pipeline.py --phase revision --max-cycles 4
uv run python run_pipeline.py --phase review
uv run python run_pipeline.py --phase export
```

Current orchestrator order:

1. `foundation`
2. `drafting`
3. `revision`
4. `review`
5. `export`

What each phase does:

- `foundation`: bootstrap generation for world, characters, perspective, voice,
  and canon; then pause for explicit human approval; after approval, iterative
  structural planning for arc, chapter cards, thread registry, legacy outline
  refresh, manifest, gate, voice telemetry, and foundation eval
- `drafting`: `advance_state.py`, `plan_scene.py --variants 4`,
  `draft_chapter.py --mode auto`, chapter eval, optional variants for risk or
  weak chapters, manifest, gate
- `revision`: adversarial edit pass, dialogue and narration audits, evidence
  pack assembly, evidence panels, patch revision when a patch-friendly brief is
  available, full evidence-backed eval, manifest, gate
- `review`: `review.py --output reviews.md`, `review.py --parse`, manifest,
  gate
- `export`: rebuild `planning/outline.md` and `arc_summary.md`, assemble
  `manuscript.md`, optional LaTeX/PDF build, manifest, gate

Important runtime detail:

- `gen_world.py`, `gen_characters.py`, and `gen_canon.py` still emit markdown
  to stdout in direct manual use, but `run_pipeline.py` already captures them
  into `planning/world.md`, `planning/characters.md`, and
  `planning/canon.md`

## Option B: Run Targeted Steps Manually

Use this when you want to intervene in a single phase without running the full
orchestrator.

### Foundation

Bootstrap first:

```bash
uv run python seed.py

uv run python gen_world.py > planning/world.md
uv run python gen_characters.py --emit-engine > planning/characters.md
uv run python gen_perspective.py
uv run python discover_voice.py --trials 8
uv run python gen_canon.py > planning/canon.md
```

Review these before proceeding:

- `planning/world.md`
- `planning/characters.md`
- `planning/perspective.md`
- `planning/voice.md`
- `planning/canon.md`

Then continue with structural planning:

```bash
uv run python gen_arc.py
uv run python gen_chapter_cards.py
uv run python gen_thread_registry.py
uv run python gen_outline_part2.py
uv run python build_manifest.py --phase foundation
uv run python consistency_gate.py --phase foundation
uv run python voice_fingerprint.py
uv run python evaluate.py --phase foundation
```

Source-of-truth planning files at the end of foundation:

- `planning/world.md`
- `planning/characters.md`
- `planning/perspective.md`
- `planning/voice.md`
- `planning/canon.md`
- `planning/arc_outline.md`
- `planning/chapter_cards.md`
- `planning/thread_registry.json`
- `manifest.json`

Compatibility file:

- `planning/outline.md`

### Drafting

The active chapter flow is:

1. plan the scene options
2. draft the chapter
3. evaluate or compare variants
4. accept the prose
5. advance state for the accepted chapter
6. refresh manifest and gate

Example:

```bash
# Chapter 1
uv run python plan_scene.py 1 --variants 4
uv run python draft_chapter.py 1 --mode auto
uv run python evaluate.py --chapter 1
uv run python advance_state.py --chapter 1
uv run python build_manifest.py --phase drafting --chapter 1
uv run python consistency_gate.py --phase drafting --chapter 1

# Chapter 2
uv run python plan_scene.py 2 --variants 4
uv run python draft_chapter.py 2 --mode auto
uv run python evaluate.py --chapter 2
uv run python advance_state.py --chapter 2
uv run python build_manifest.py --phase drafting --chapter 2
uv run python consistency_gate.py --phase drafting --chapter 2
```

Useful drafting flags:

```bash
uv run python draft_chapter.py 3 --mode auto --dry-run
uv run python draft_chapter.py 3 --mode new
uv run python draft_chapter.py 3 --mode legacy
uv run python plan_scene.py 3 --planner-mode deterministic
uv run python plan_scene.py 3 --planner-mode model
```

Variant workflow for risky or weak chapters:

```bash
uv run python draft_variant.py 3 --variants 3 --mode auto
uv run python compare_variants.py 3
uv run python evaluate.py --chapter 3 --risk
```

How `auto` works:

- `draft_chapter.py --mode auto` switches to the PR3+ path when
  `planning/perspective.md`, `planning/voice.md`,
  `planning/character_engine.json`, `planning/chapter_cards.md`,
  `planning/thread_registry.json`, `planning/world.md`,
  `planning/canon.md`, and the needed `scene_options` and prior
  `story_state` files exist
- otherwise it raises instead of silently falling back to legacy drafting

How `plan_scene.py` works:

- `--planner-mode auto` uses the model-backed planner when API config is
  present
- otherwise it falls back to deterministic scene-option generation

### Revision

The current revision path is no longer summary-led. It is evidence-backed and
patch-backed.

Revision cycle commands:

```bash
uv run python adversarial_edit.py all
uv run python dialogue_audit.py --all
uv run python narration_audit.py --all
uv run python assemble_evidence_pack.py --novel
uv run python reader_panel.py --evidence eval_logs/evidence_pack.json
uv run python humanity_panel.py --evidence eval_logs/evidence_pack.json
uv run python gen_brief.py --auto --require-patch-directives
uv run python evaluate.py --full --evidence eval_logs/evidence_pack.json
uv run python build_manifest.py --phase revision
uv run python consistency_gate.py --phase revision
```

Patch-revision commands:

```bash
uv run python roughness_guard.py 5
uv run python gen_brief.py --auto --require-patch-directives
uv run python patch_revision.py 5 briefs/ch05_auto.md --plan-only
uv run python apply_edits.py 5
uv run python assemble_evidence_pack.py --novel
uv run python evaluate.py --full --evidence eval_logs/evidence_pack.json
```

Patch-planning note:

- deterministic fallback is reliable for explicit patch directives and the
  quote-based cut or rewrite items that `gen_brief.py` can emit today
- prose-only briefs are not safely auto-converted into local span edits, so
  patch mode should fail clearly unless a model planner is available

### Review

Keep review separate from revision:

```bash
uv run python review.py --output reviews.md
uv run python review.py --parse
uv run python build_manifest.py --phase review
uv run python consistency_gate.py --phase review
```

`review.py` is the final full-manuscript reviewer. Evidence evaluation informs
revision; it does not replace the dedicated review phase.

### Export

```bash
uv run python build_outline.py
uv run python build_arc_summary.py
uv run python typeset/build_tex.py
tectonic typeset/novel.tex
uv run python build_manifest.py --phase export
uv run python consistency_gate.py --phase export
```

`build_outline.py` and `build_arc_summary.py` now rebuild from accepted
chapters plus:

- `planning/arc_outline.md`
- `planning/chapter_cards.md`
- `planning/thread_registry.json`
- `manifest.json`

They are compatibility and export helpers, not primary planning generators.

## Source Of Truth

Treat these as the current story-state truth:

- accepted chapter files in `chapters/`
- `planning/arc_outline.md`
- `planning/chapter_cards.md`
- `planning/thread_registry.json`
- `scene_options/`
- `state/story_state/`
- `manifest.json`

Treat these as compatibility or presentation outputs:

- `planning/outline.md`
- `arc_summary.md`
- `manuscript.md`

## Migration Note

If you were used to the old flow:

- stop treating `planning/outline.md` as the only planning artifact
- stop treating summary-led full eval as the primary revision loop
- treat `review` as its own phase between `revision` and `export`
- use manifest and consistency checks as part of normal workflow, not as
  future work
