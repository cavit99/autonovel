# Master Orchestrator Prompt

```text
Use the shared repo context above.

You are the orchestration agent for a stacked 7-PR refactor of NousResearch/autonovel.

Goal:
Implement a redesign that:
- creates a governing narrative mind,
- adds contradiction-rich character engines with cognitive ceilings,
- replaces beat-execution planning with arc/chapter-card/scene-option planning,
- consolidates per-chapter story state,
- replaces full-chapter rewrites with patch revision,
- replaces summary-based novel judging with evidence-pack judging,
- adds dialogue and narration audits,
- adds risk chapters plus variant selection,
- adds manifest plus consistency gate,
- updates the orchestrator only after the building blocks exist.

Important:
- PR1 through PR5 should be mostly additive and backward-compatible.
- PR6 is the orchestration flip.
- PR7 is docs and export alignment.
- Do not introduce `scene_fingerprint.py` in this stack.
- Do not remove `review.py`.
- Do not require new env vars until PR5 or PR6; when introduced, they must have sensible defaults.

PR stack:
1. PR1 governing mind
2. PR2 planning split
3. PR3 stateful drafting
4. PR4 patch revision
5. PR5 evidence eval
6. PR6 orchestrator manifest
7. PR7 docs export

For each PR:
- create or modify only the files in scope,
- preserve old entry points where required,
- add minimal smoke tests for pure or local code,
- provide a concise handoff note for the next PR.

Do not implement all PRs at once.
Wait for approval after each PR prompt or run.
```
