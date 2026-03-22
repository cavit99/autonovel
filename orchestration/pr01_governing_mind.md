# PR1 Prompt

```text
Use the shared repo context above.

PR title: PR1 — Governing mind foundation
Branch: pr/01-governing-mind
Base: master

Objective:
Add the novel-mind layer without changing the active pipeline yet.

Deliverables:
1. Add `gen_perspective.py`
2. Add `perspective.md` generation
3. Extend `gen_characters.py` with an optional `--emit-engine` mode
4. Add `character_engine.json` output
5. Add `discover_voice.py` implementing actual trial-passage discovery
6. Keep existing `gen_characters.py` behaviour backward-compatible when `--emit-engine` is not used
7. Do not wire `run_pipeline.py` yet
8. Do not rewrite docs except minimal inline usage/help text

Required output shapes:

`perspective.md`
- Obsessions
- Blind Spots
- Sense of Humor
- The Unbearable
- Self-Awareness
- Formal Signatures

`character_engine.json` per major character:
- wound
- want
- need
- lie
- unresolvable_contradictions
- speech_sample
- metaphor_domain
- taboo_topics
- default_dodge
- stress_transform
- cognitive_ceiling:
  - abstraction_level
  - reasoning_style
  - failure_mode

`discover_voice.py` requirements:
- generate 5 to 8 trial passages in distinct registers
- evaluate quality
- evaluate distinctiveness
- evaluate fit to `perspective.md`
- choose top 2 and run pairwise compare
- write the chosen voice into `voice.md` Part 2 or a clearly documented compatible artifact

Constraints:
- No `run_pipeline.py` wiring yet
- No `evaluate.py` changes yet
- No drafting prompt changes yet
- No network tests
- Add lightweight tests or smoke-testable helper functions where possible

Acceptance checks:
- `uv run python gen_perspective.py --help`
- `uv run python gen_characters.py --help`
- `uv run python gen_characters.py --emit-engine` on local fixtures or existing files
- `uv run python discover_voice.py --help`
- `character_engine.json` is valid JSON and includes `cognitive_ceiling`
- `perspective.md` is generated with all six required sections

Implementation notes:
- Keep file locations simple: root-level artifacts are acceptable for now
- Build pure helper functions for schema shaping so they can be locally tested without network calls
- If `discover_voice.py` needs a metadata artifact, write something like `voice_discovery.json`

Return at the end:
- changed files
- commands run
- smoke tests run
- risks or follow-up for PR2
```
