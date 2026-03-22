# PR5 Prompt

```text
Use the shared repo context above.

PR title: PR5 — Evidence-pack evaluation, dialogue audit, narration audit
Branch: pr/05-evidence-eval
Base: pr/04-patch-revision

Objective:
Replace summary-only judging with prose-level evidence packs and add the audits that detect sameness in dialogue and narration. Keep backward compatibility for existing reader and eval entry points until PR6.

Deliverables:
1. Add `assemble_evidence_pack.py`
2. Add `dialogue_audit.py`
3. Add `narration_audit.py`
4. Add `humanity_panel.py`
5. Modify `reader_panel.py` to support:
   - legacy no-arg summary mode
   - new `--evidence` mode using raw passages
6. Modify `evaluate.py` to support:
   - new chapter-level dimensions
   - new `--full --evidence` mode
   - risk-chapter rubric
7. Introduce new model env vars, but with safe fallbacks:
   - `AUTONOVEL_JUDGE_MODEL`
   - `AUTONOVEL_SMELL_MODEL`
   - `AUTONOVEL_DIALOGUE_MODEL`
8. Augment `review.py` prompts and parsing without removing its full-manuscript role

New chapter-level dimensions:
- `baseline_voice`
- `perspective_distinctiveness`
- `character_truthfulness`
- `dialogue_separability`
- `formal_enactment`
- `surplus_life`
- `scene_method_freshness`
- `humor_signature`

Required evaluator changes:
- split old `voice_adherence` into `baseline_voice` plus `formal_enactment`
- replace any `character_arc` emphasis with `character_truthfulness`

New full-novel dimensions:
- `arc_completion`
- `pacing_curve`
- `perspective_continuity`
- `formal_variety`
- `temporal_variety`
- `theme_pressure`
- `surplus_life`
- `human_texture`
- `over_determinedness_penalty`
- `world_consistency`
- `overall_engagement`

Important evaluation rule:
- do not hard-cap theme coherence
- instead apply an over-determinedness penalty when theme pressure is high and surplus life is low

`dialogue_audit.py` should flag:
- generic lines
- speaker non-separability
- theme-perfect lines
- metaphor-domain leakage
- cognitive ceiling violations

`narration_audit.py` should flag:
- repeated room-entry templates
- repeated metaphor structures
- repeated sentence-openers
- repeated observation ordering
- repeated intensifiers or conceptual habits

`humanity_panel.py` should include:
- The Novelist
- The Dramatist
- The Oral Reader

Risk-chapter rubric should evaluate:
- `interestingness`
- `necessity`
- `coherence_floor`

`review.py` additions:
- ask where the novel feels overdesigned or too fully on-theme
- ask where the governing perspective is strongest and weakest
- ask where characters sound too aware of the novel's argument
- ask whether risk chapters are interesting or merely defective
- ask where formal enactment fails
- preserve `review.py` as the final full-manuscript reviewer rather than converting it to evidence-pack mode

Constraints:
- Keep old `evaluate.py --full` working if no evidence pack is supplied
- Keep old `reader_panel.py` no-arg mode working until PR6
- No `run_pipeline.py` rewiring yet
- No networked tests

Acceptance checks:
- `uv run python assemble_evidence_pack.py --help`
- `uv run python dialogue_audit.py --help`
- `uv run python narration_audit.py --help`
- `uv run python humanity_panel.py --help`
- `uv run python reader_panel.py --help`
- `uv run python evaluate.py --help`
- `uv run python review.py --help`
- `reader_panel.py` works in both legacy and evidence modes
- `evaluate.py` works in both legacy full mode and evidence full mode
- audits can run against local chapter fixtures without network when using pure extraction paths

Implementation notes:
- Make evidence packs JSON, not markdown
- Every major panel claim should be tied to raw passages in evidence mode
- Keep model selection overrideable via env vars

Return at the end:
- changed files
- commands run
- smoke tests run
- new evaluator dimensions
- risks or follow-up for PR6
```
