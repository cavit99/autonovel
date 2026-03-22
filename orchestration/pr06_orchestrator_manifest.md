# PR6 Prompt

```text
Use the shared repo context above.

PR title: PR6 — Orchestrator flip, manifest, consistency gate, variants
Branch: pr/06-orchestrator-manifest
Base: pr/05-evidence-eval

Objective:
Turn the new architecture on in `run_pipeline.py`, add a manifest as single source of truth, add consistency gating, and add chapter variant comparison for critical or risk chapters.

Deliverables:
1. Add `manifest.json` template and `build_manifest.py`
2. Add `consistency_gate.py`
3. Add `draft_variant.py`
4. Add `compare_variants.py`
5. Update `run_pipeline.py` to use the new flow
6. Flip the default revision path in the pipeline to patch mode
7. Use evidence-pack reader and eval in the pipeline
8. Keep wrappers for old entry points

`run_pipeline.py` target flow:
- foundation:
  `gen_world.py`
  `gen_characters.py --emit-engine`
  `gen_perspective.py`
  `discover_voice.py --trials 8`
  `gen_arc.py`
  `gen_chapter_cards.py`
  `gen_thread_registry.py`
  `gen_canon.py`
  `build_manifest.py`
  `consistency_gate.py`
  `voice_fingerprint.py`
  `evaluate.py --phase foundation`

- drafting:
  `advance_state.py`
  `plan_scene.py`
  `draft_chapter.py`
  `evaluate.py --chapter`
  if critical, risk, or weak -> `draft_variant.py` plus `compare_variants.py` plus re-evaluate
  `build_manifest.py`
  `consistency_gate.py`

- revision:
  `adversarial_edit.py`
  `dialogue_audit.py`
  `narration_audit.py`
  `assemble_evidence_pack.py`
  `reader_panel.py --evidence`
  `humanity_panel.py --evidence`
  `gen_brief.py --auto`
  `patch_revision.py`
  `apply_edits.py`
  `evaluate.py --chapter`
  `evaluate.py --full --evidence`
  `build_manifest.py`
  `consistency_gate.py`

- review:
  `review.py`
  `review.py --parse`
  `build_manifest.py`
  `consistency_gate.py`

- export:
  `build_outline.py`
  `build_arc_summary.py`
  `build_manifest.py`
  `consistency_gate.py`

Manifest requirements:
- title
- phase
- chapter_count
- word_count
- risk_chapters
- files
- hashes
- model configuration
- evidence pack hash and path

Consistency gate requirements:
- chapter count agrees with files
- word count matches manuscript
- evidence pack matches current manuscript hash
- required artifacts exist for current phase
- wrappers and source-of-truth files are not silently diverging

Variant flow:
- use `draft_variant.py` and `compare_variants.py` on:
  - critical chapters
  - risk chapters
  - chapters scoring below 6.3 after first pass

Threshold policy:
- keep normal `CHAPTER_THRESHOLD = 6.0`
- add `RISK_INTERESTINGNESS_FLOOR = 7.0`
- add `RISK_COHERENCE_FLOOR = 5.0`
- preserve `MAX_CHAPTER_ATTEMPTS = 5` unless there is a compelling compatibility reason to change it
- preserve `MIN_REVISION_CYCLES = 3`, `MAX_REVISION_CYCLES = 6`, and plateau logic unless the new architecture makes a direct carry-forward impossible

Revision policy:
- patch revision is now the default path
- full-chapter rewrite should require explicit escalation rather than happen by default
- every revision cycle should include the smell or humanity audit path, not just writer-family scoring

Constraints:
- Preserve old CLI entry points where possible
- Do not remove `review.py`
- Do not rewrite docs yet beyond help strings if strictly necessary
- Keep art, audiobook, and export side systems untouched except manifest and consistency integration

Acceptance checks:
- `uv run python build_manifest.py --help`
- `uv run python consistency_gate.py --help`
- `uv run python draft_variant.py --help`
- `uv run python compare_variants.py --help`
- `uv run python run_pipeline.py --help`
- `run_pipeline.py` imports and resolves all new tools
- dry local smoke path for foundation and one drafting pass with mocked or no-network calls where feasible
- `consistency_gate.py` fails on intentionally inconsistent local fixture

Implementation notes:
- This is the PR that flips defaults
- Preserve wrappers and compatibility paths added earlier
- Keep orchestration readable; do not hide the phase flow
- `voice_fingerprint.py` remains QA telemetry, not the discovery mechanism

Return at the end:
- changed files
- commands run
- smoke tests run
- final pipeline phase order
- risks or follow-up for PR7
```
