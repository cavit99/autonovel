# PR4 Prompt

```text
Use the shared repo context above.

PR title: PR4 — Patch revision and roughness preservation
Branch: pr/04-patch-revision
Base: pr/03-stateful-drafting

Objective:
Introduce patch-based revision and local roughness preservation without flipping the active pipeline yet.

Deliverables:
1. Add `patch_revision.py`
2. Add `apply_edits.py`
3. Add `roughness_guard.py`
4. Modify `gen_revision.py` to support modes:
   - `--mode full`
   - `--mode patch`
5. Keep `gen_revision.py` default behaviour unchanged for now
6. Optionally make `apply_cuts.py` a wrapper or partial wrapper to `apply_edits.py` in cut-only mode, but do not break current CLI

`patch_revision.py` requirements:
- consume a revision brief
- propose span-level edits:
  - cut
  - replace
  - move
  - insert
- preserve untouched text byte-for-byte where possible

`roughness_guard.py` requirements:
- identify and lock top 3 to 5 strongest lines or passages
- protect speaker-specific awkwardness
- protect odd but alive syntax
- allow revision to target cited defects without globally smoothing voice

Constraints:
- Do not change `run_pipeline.py` yet
- Do not flip the default revision path yet
- Keep old `gen_revision.py` CLI valid
- No docs PR yet

Acceptance checks:
- `uv run python patch_revision.py --help`
- `uv run python apply_edits.py --help`
- `uv run python roughness_guard.py --help`
- `uv run python gen_revision.py 5 briefs/example.md --mode patch`
- `uv run python gen_revision.py 5 briefs/example.md --mode full`
- unchanged spans remain unchanged in patch mode on a local fixture

Implementation notes:
- Define a simple JSON edit schema
- Build patch application as deterministic local logic when possible
- Keep patch revision composable with future dialogue and narration audits

Return at the end:
- changed files
- commands run
- smoke tests run
- edit schema summary
- risks or follow-up for PR5
```
