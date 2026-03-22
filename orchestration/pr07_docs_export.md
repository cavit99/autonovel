# PR7 Prompt

```text
Use the shared repo context above.

PR title: PR7 — Docs and export alignment
Branch: pr/07-docs-export
Base: pr/06-orchestrator-manifest

Objective:
Make the documentation, export helpers, and reconstruction tools match the new runtime. Remove stale assumptions and hard-coded metadata where appropriate.

Deliverables:
1. Update `README.md`
2. Update `WORKFLOW.md`
3. Update `program.md`
4. Update `PIPELINE.md`
5. Update `build_outline.py` to rebuild or export the new planning artifacts coherently
6. Update `build_arc_summary.py` to use current source-of-truth artifacts
7. Ensure no stale hard-coded novel length or chapter count language remains in active prompts or docs
8. Document new env vars and CLI commands

Docs must describe:
- governing perspective and character engine
- arc plus chapter cards plus thread registry
- `advance_state.py`
- `patch_revision.py` and `apply_edits.py`
- evidence-pack evaluation
- dialogue plus narration audits
- risk chapters plus variants
- manifest plus consistency gate
- orchestrator phase order

`build_outline.py` and `build_arc_summary.py` requirements:
- work from accepted chapters plus current source-of-truth artifacts
- do not silently rely on old outline assumptions
- produce outputs that reflect the novel as-written and the new planning structure

Constraints:
- Do not redesign the code again here
- Only make code changes required to align export and rebuild helpers with the new architecture
- Keep the PR focused on documentation and reconstruction or export

Acceptance checks:
- `README` and `WORKFLOW` command examples are valid
- no stale hard-coded `72,422 words / 24 chapters` style text remains in active evaluation or panel paths
- `uv run python build_outline.py --help`
- `uv run python build_arc_summary.py --help`
- docs reflect the actual `run_pipeline.py` order from PR6

Implementation notes:
- Be explicit about compatibility wrappers and what is now source-of-truth
- Include a short migration note for users coming from the old flow

Return at the end:
- changed files
- commands run
- smoke tests run
- final documentation summary
```
