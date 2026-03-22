# PR2 Prompt

```text
Use the shared repo context above.

PR title: PR2 — Planning split with compatibility wrappers
Branch: pr/02-planning-split
Base: pr/01-governing-mind

Objective:
Replace the monolithic outline and foreshadowing model with arc plus chapter cards plus thread registry, while preserving legacy outline entry points for the current pipeline.

Deliverables:
1. Add `gen_arc.py` -> writes `arc_outline.md`
2. Add `gen_chapter_cards.py` -> writes `chapter_cards.md`
3. Add `gen_thread_registry.py` -> writes `thread_registry.json`
4. Convert `gen_outline.py` into a compatibility wrapper
5. Convert `gen_outline_part2.py` into a compatibility wrapper
6. Preserve legacy `outline.md` output for old `draft_chapter.py` consumers

`arc_outline.md` should capture only:
- irreversible turns
- major reveals
- pressure escalations
- candidate risk chapters

Required `chapter_cards.md` fields:
- goal
- pressure
- reversal
- aftermath
- irreversible_change
- allowed_ambiguity
- time_span
- scene_density
- scene_type
- scene_method
- risk

Expected enum values:
- `scene_density`: `high`, `medium`, `low`
- `scene_type`: `investigation`, `confrontation`, `revelation`, `quiet`, `crisis`, `preparation`, `aftermath`, `digression`
- `scene_method`: `close_interiority`, `observed_action`, `dialogue_driven`, `environmental`, `epistolary`, `panoramic`, `fragmented`
- `risk`: `none`, `formal`, `pov`, `document`, `temporal`

Required thread types:
- plot
- pressure
- echo
- texture

Compatibility requirements:
- Running `gen_outline.py` should still produce `outline.md` in a form the old pipeline can consume
- Running `gen_outline_part2.py` should still preserve or reconstruct a legacy foreshadowing section if needed
- The new files should be the source of truth for the wrappers, not vice versa
- Eliminate `/tmp/outline_output.md` and story-specific continuation assumptions from the active `gen_outline_part2.py` code path
- Keep the rendered legacy `outline.md` parseable by the current `draft_chapter.py` chapter extractor

Constraints:
- Do not modify `draft_chapter.py` yet
- Do not modify `run_pipeline.py` yet
- No docs PR yet
- Keep wrappers explicit and clearly commented as transitional

Acceptance checks:
- `uv run python gen_arc.py --help`
- `uv run python gen_chapter_cards.py --help`
- `uv run python gen_thread_registry.py --help`
- `uv run python gen_outline.py`
- `uv run python gen_outline_part2.py`
- `outline.md` still exists after wrapper execution
- `chapter_cards.md` and `thread_registry.json` are generated and well-formed

Implementation notes:
- The legacy outline can be rendered from chapter cards
- The legacy foreshadowing ledger can be rendered from `thread_registry.json`
- Use clear comments like `compatibility wrapper for legacy pipeline`
- Build schema validators for chapter cards and thread registry

Return at the end:
- changed files
- commands run
- smoke tests run
- exact compatibility assumptions
- risks or follow-up for PR3
```
