# Stacked PR Orchestration

This directory packages the approved migration plan into dispatchable prompt files.

## Files

- `shared_repo_context.md`
- `master_orchestrator_prompt.md`
- `pr01_governing_mind.md`
- `pr02_planning_split.md`
- `pr03_stateful_drafting.md`
- `pr04_patch_revision.md`
- `pr05_evidence_eval.md`
- `pr06_orchestrator_manifest.md`
- `pr07_docs_export.md`

## Branch Order

Dispatch the stack in this order:

1. `pr/01-governing-mind`
2. `pr/02-planning-split`
3. `pr/03-stateful-drafting`
4. `pr/04-patch-revision`
5. `pr/05-evidence-eval`
6. `pr/06-orchestrator-manifest`
7. `pr/07-docs-export`

## Dispatch Flow

For each PR:

1. Create the branch named in the PR prompt from its stated base branch.
2. Prepend the full contents of `shared_repo_context.md`.
3. Append the contents of the relevant `prXX_*.md` file.
4. Send that combined prompt to the implementing agent.
5. Wait for the exact `PR COMPLETE` handoff block before reviewing or moving on.
6. Merge or restack, then dispatch the next PR against the new base.

Use `master_orchestrator_prompt.md` for the coordinating agent only. Use the PR files for the implementation agents.

## Suggested Terminal Sequence

```bash
# coordinator context
cat orchestration/shared_repo_context.md orchestration/master_orchestrator_prompt.md

# PR1
git checkout -b pr/01-governing-mind
cat orchestration/shared_repo_context.md orchestration/pr01_governing_mind.md

# PR2
git checkout -b pr/02-planning-split pr/01-governing-mind
cat orchestration/shared_repo_context.md orchestration/pr02_planning_split.md
```

Repeat the same pattern through PR7.

## Review Gate

Do not dispatch the next PR until the prior one reports:

```text
PR COMPLETE

Changed files:
- ...

Commands run:
- ...

Smoke tests:
- ...

What remains deliberately untouched:
- ...

Known risks / follow-up for next PR:
- ...
```

## Notes

- PR1 through PR5 are intended to be mostly additive and backward-compatible.
- PR6 is the orchestrator flip.
- PR7 aligns docs and export helpers with the new runtime.
- Keep `review.py` throughout the stack.
- Do not spill work across PR boundaries.
