# PR3 Prompt

```text
Use the shared repo context above.

PR title: PR3 — Stateful drafting and scene planning
Branch: pr/03-stateful-drafting
Base: pr/02-planning-split

Objective:
Add a single consolidated story-state updater and a scene-option planner, then teach `draft_chapter.py` to use the new mode when the new artifacts are present, while preserving legacy mode.

Deliverables:
1. Add `advance_state.py`
2. Add `state/story_state/ch_XX.json` artifact generation
3. Add `plan_scene.py`
4. Modify `draft_chapter.py` to support:
   - `perspective.md`
   - `character_engine.json`
   - `chapter_cards.md`
   - `thread_registry.json`
   - scene options
   - story state
   - `world.md`
   - `canon.md`
5. Preserve legacy draft mode if the new artifacts are absent

`state/story_state/ch_XX.json` should include:
- `world_clock`
- `knowledge_state`
- `minor_character_memory`
- `active_pressures`

`plan_scene.py` should:
- read chapter card plus previous state
- read the local relevant window from `thread_registry.json`
- generate 2 to 4 scene options
- include:
  - goal
  - pressure
  - social_imbalance
  - wrong_inference
  - surprise_slot
  - residue

`draft_chapter.py` changes:
- keep current CLI working
- if new artifacts exist, use new mode
- use this context order in new mode:
  1. `perspective.md`
  2. `voice.md`
  3. `character_engine.json`
  4. `state/story_state/ch_{n-1}.json`
  5. current chapter card
  6. `scene_options/ch_XX.json`
  7. local thread-registry window
  8. `world.md`
  9. `canon.md`
- enforce blind spots actively
- incorporate humor signature
- enforce cognitive ceilings in dialogue and thought
- preserve the chapter card's irreversible change
- choose the most alive path from `scene_options`
- allow non-plot threads to be deferred, migrated, or dropped unless explicitly marked required
- stop requiring all beats and all plants in new mode
- preserve legacy behaviour in legacy mode for compatibility

Constraints:
- Do not rewire `run_pipeline.py` yet
- Do not change evaluation yet
- Keep all new-mode checks additive
- No new network tests

Acceptance checks:
- `uv run python advance_state.py --help`
- `uv run python plan_scene.py --help`
- `uv run python draft_chapter.py --help`
- `draft_chapter.py` still runs in legacy mode with only `outline.md` present
- `draft_chapter.py` can run in new mode when chapter cards, scene options, and story state exist
- local fixtures show the new prompt path includes blind spots, humor, cognitive ceiling constraints, irreversible change preservation, and local thread-window context

Implementation notes:
- Avoid branching chaos by factoring prompt assembly into helper functions
- Keep old prompt assembly path intact as a fallback
- Prefer a clear `new planning mode detected` switch based on file existence or explicit flags

Return at the end:
- changed files
- commands run
- smoke tests run
- exact legacy/new-mode switch logic
- risks or follow-up for PR4
```
