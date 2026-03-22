# Shared Repo Context

Use this block as the prefix for every PR prompt and for the master orchestration prompt.

```text
You are working in the original master branch of NousResearch/autonovel.

Current repo facts you must respect:
- run_pipeline.py currently orchestrates foundation as:
  gen_world.py -> gen_characters.py -> gen_outline.py -> gen_outline_part2.py -> gen_canon.py -> voice_fingerprint.py
- program.md still describes chapter drafting as loading:
  voice.md + world.md + characters.md + this chapter's outline entry + previous chapter tail + next chapter outline
- draft_chapter.py explicitly tells the writer to:
  "hit every beat in the outline" and "Plant ALL foreshadowing elements"
- revision currently runs apply_cuts.py, then reader_panel.py, then gen_revision.py
- gen_revision.py rewrites the FULL chapter
- evaluate.py --full judges the novel from planning docs + chapter summaries
- reader_panel.py judges the novel "in summary form" and hard-codes 72,422 words across 24 chapters
- program.md already wants voice discovery via five trial passages in different registers
- gen_outline_part2.py is still story-specific and brittle
- repo metadata disagree about the Bells chapter count, so new manifest/consistency work is justified

Global migration principles:
1. Do not break the current CLI before PR6 unless the PR explicitly says to.
2. Prefer wrappers and compatibility layers over deletions.
3. Additive changes first; orchestration flip later.
4. No networked tests. Add lightweight unit/smoke tests only for pure logic and local file orchestration.
5. Do not touch art/audiobook/typesetting unless the PR explicitly says to.
6. Stop at the PR boundary. Do not spill into the next PR.
7. At the end of the PR, output:
   - changed files
   - commands run
   - tests/smoke checks run
   - open risks / next-PR handoff
```
