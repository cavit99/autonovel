import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stateful_drafting import (
    build_new_mode_prompt,
    build_scene_options,
    build_story_state,
    detect_new_planning_mode,
    generate_scene_options,
    infer_focus_character,
    load_chapter_card,
    local_thread_window,
    normalize_scene_options,
    parse_perspective_markdown,
    resolve_mode,
)


class StatefulDraftingTests(unittest.TestCase):
    def test_parse_perspective_markdown_reads_lists_and_singletons(self):
        text = """# Perspective

## Obsessions
- sound before sight

## Blind Spots
- underestimates affection

## Sense of Humor
- pomposity that collapses under detail

## The Unbearable
- bureaucratic cruelty

## Self-Awareness
The narration revises itself when it gets too sure.

## Formal Signatures
- bureaucracy -> flatter diction
"""
        profile = parse_perspective_markdown(text)
        self.assertEqual(profile["obsessions"], ["sound before sight"])
        self.assertEqual(profile["blind_spots"], ["underestimates affection"])
        self.assertEqual(profile["self_awareness"], "The narration revises itself when it gets too sure.")

    def test_build_scene_options_returns_required_fields(self):
        chapter_card = {
            "number": 3,
            "goal": "Get proof from the steward",
            "pressure": "Public corridor with witnesses",
            "reversal": "The steward is protecting the wrong person",
            "aftermath": "Cass leaves more exposed than before",
            "irreversible_change": "Cass commits to the lie in public",
            "allowed_ambiguity": "Whether the steward is cruel or frightened",
            "scene_type": "confrontation",
            "scene_method": "dialogue_driven",
            "risk": "pov",
        }
        thread_window = [
            {"id": "letters", "type": "pressure", "description": "Guild letters are circulating", "required": True},
        ]
        options = build_scene_options(3, chapter_card, {"active_pressures": ["Guild letters are circulating"]}, thread_window, 4)
        self.assertEqual(len(options), 4)
        for option in options:
            for field in ("goal", "pressure", "social_imbalance", "wrong_inference", "surprise_slot", "residue"):
                self.assertIn(field, option)

    def test_normalize_scene_options_repairs_model_output_and_clamps_count(self):
        chapter_card = {
            "number": 2,
            "goal": "Get proof",
            "pressure": "Public corridor",
            "reversal": "The witness hedges",
            "aftermath": "Cass leaves exposed",
            "irreversible_change": "Cass commits to the lie",
            "allowed_ambiguity": "Whether the witness is afraid",
            "scene_type": "confrontation",
            "scene_method": "dialogue_driven",
            "risk": "pov",
        }
        fallback = build_scene_options(2, chapter_card, {"active_pressures": ["Guild scrutiny"]}, [], 3)
        payload = {
            "scene_options": [
                {
                    "goal": "Get proof from the porter",
                    "social_imbalance": "Porter has the better public footing",
                    "wrong_inference": "Cass mistakes pity for contempt",
                    "surprise_slot": "The porter quietly helps him",
                    "residue": "Cass leaves indebted",
                }
            ]
        }
        normalized = normalize_scene_options(payload, chapter_card, 3, fallback)
        self.assertEqual(len(normalized), 3)
        self.assertEqual(normalized[0]["goal"], "Get proof from the porter")
        self.assertEqual(normalized[0]["pressure"], "Public corridor")
        self.assertEqual(normalized[0]["scene_type"], "confrontation")

    def test_generate_scene_options_falls_back_without_api_key(self):
        chapter_card = {
            "number": 2,
            "goal": "Get proof",
            "pressure": "Public corridor",
            "reversal": "The witness hedges",
            "aftermath": "Cass leaves exposed",
            "irreversible_change": "Cass commits to the lie",
            "allowed_ambiguity": "Whether the witness is afraid",
            "scene_type": "confrontation",
            "scene_method": "dialogue_driven",
            "risk": "pov",
        }
        expected = build_scene_options(2, chapter_card, {"active_pressures": ["Guild scrutiny"]}, [], 3)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}, clear=False):
            options = generate_scene_options(2, chapter_card, {"active_pressures": ["Guild scrutiny"]}, [], 3)
        self.assertEqual(options, expected)

    def test_generate_scene_options_falls_back_on_malformed_model_output(self):
        chapter_card = {
            "number": 2,
            "goal": "Get proof",
            "pressure": "Public corridor",
            "reversal": "The witness hedges",
            "aftermath": "Cass leaves exposed",
            "irreversible_change": "Cass commits to the lie",
            "allowed_ambiguity": "Whether the witness is afraid",
            "scene_type": "confrontation",
            "scene_method": "dialogue_driven",
            "risk": "pov",
        }
        expected = build_scene_options(2, chapter_card, {"active_pressures": ["Guild scrutiny"]}, [], 3)
        options = generate_scene_options(
            2,
            chapter_card,
            {"active_pressures": ["Guild scrutiny"]},
            [],
            3,
            previous_prose="Cass leaves the room already committed.",
            mode="model",
            planner_call=lambda _prompt: "not json at all",
        )
        self.assertEqual(options, expected)

    def test_build_story_state_contains_required_shapes(self):
        state = build_story_state(
            2,
            {
                "goal": "Get proof",
                "pressure": "Room is public",
                "reversal": "The witness lies",
                "aftermath": "Cass doubles down",
                "irreversible_change": "Cass names a suspect aloud",
                "allowed_ambiguity": "Whether the witness is afraid",
            },
            None,
            "Cass said the wrong thing in public.",
            [{"type": "pressure", "description": "Guild scrutiny", "required": True}],
            {"Cass": {"cognitive_ceiling": {"abstraction_level": "medium"}}},
        )
        self.assertEqual(state["chapter"], 2)
        self.assertIn("world_clock", state)
        self.assertIn("knowledge_state", state)
        self.assertIn("minor_character_memory", state)
        self.assertIn("active_pressures", state)
        self.assertIn("Cass", state["knowledge_state"])

    def test_infer_focus_character_does_not_depend_on_engine_order(self):
        focus = infer_focus_character(
            {"goal": "Cass gets proof from the steward"},
            {"Bea": {"cognitive_ceiling": {}}, "Cass": {"cognitive_ceiling": {}}},
        )
        self.assertEqual(focus, "Cass")

    def test_build_story_state_prefers_accepted_prose_over_card_priors(self):
        state = build_story_state(
            3,
            {
                "focus_character": "Cass",
                "goal": "Get proof from the porter",
                "pressure": "Public corridor full of witnesses",
                "reversal": "The porter lies to Cass",
                "aftermath": "Cass decides he is alone",
                "irreversible_change": "Cass publicly accuses Orin",
                "allowed_ambiguity": "Whether Mara is loyal",
            },
            {
                "chapter": 2,
                "active_pressures": ["Old debt"],
                "minor_character_memory": {
                    "Toma": {"last_seen": 2, "remembers": ["Cass snapped at him once."]},
                },
            },
            (
                "Cass realized the ledger had been copied before dawn. "
                "He suspected Orin was moving the meeting to the bell tower. "
                "Cass mistook Mara's caution for betrayal. "
                "Cass told himself he could still control the room. "
                "Under the eyes of the waiting clerks, he had to answer before the bell. "
                "Lenne hovered by the door. "
                "Peta blocked the stair. "
                "Mara knew Cass had heard the bells. "
                "Cass left with the lie fixed in public."
            ),
            [
                {
                    "type": "pressure",
                    "description": "Waiting clerks are watching every answer",
                    "required": True,
                },
                {
                    "type": "pressure",
                    "description": "The bell tower meeting is moving",
                    "required": True,
                },
            ],
            {
                "Mara": {"cognitive_ceiling": {"abstraction_level": "high"}},
                "Cass": {"cognitive_ceiling": {"abstraction_level": "medium"}},
            },
        )
        cass_state = state["knowledge_state"]["Cass"]
        self.assertIn("the ledger had been copied before dawn", cass_state["knows"])
        self.assertIn("Orin was moving the meeting to the bell tower", cass_state["suspects"])
        self.assertIn("Mara's caution for betrayal", cass_state["misreads"])
        self.assertEqual(cass_state["self_story"], "he could still control the room")
        self.assertNotIn("The porter lies to Cass", cass_state["knows"])
        self.assertNotIn("Whether Mara is loyal", cass_state["misreads"])

        self.assertIn("Cass had heard the bells", state["knowledge_state"]["Mara"]["knows"])

        self.assertIn("Lenne", state["minor_character_memory"])
        self.assertIn("Peta", state["minor_character_memory"])
        self.assertNotIn("Mara", state["minor_character_memory"])
        self.assertEqual(state["minor_character_memory"]["Lenne"]["last_seen"], 3)
        self.assertIn("Toma", state["minor_character_memory"])

        self.assertIn("Old debt", state["active_pressures"])
        self.assertTrue(any("waiting clerks" in pressure.lower() for pressure in state["active_pressures"]))
        self.assertTrue(any("bell tower meeting" in pressure.lower() for pressure in state["active_pressures"]))
        self.assertNotIn("Public corridor full of witnesses", state["active_pressures"])
        self.assertIn("Cass left with the lie fixed in public.", state["world_clock"]["offstage_consequences"])
        self.assertNotIn("Cass publicly accuses Orin", state["world_clock"]["offstage_consequences"])

    def test_detect_new_mode_and_prompt_include_pr3_constraints(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "perspective.md").write_text(
                "# Perspective\n\n## Obsessions\n- sound before sight\n\n## Blind Spots\n- misses tenderness\n\n"
                "## Sense of Humor\n- pomp collapsing under detail\n\n## The Unbearable\n- public shame\n\n"
                "## Self-Awareness\nKnows he performs.\n\n## Formal Signatures\n- pressure -> shorter clauses\n"
            )
            (base / "voice.md").write_text("# Voice\n")
            (base / "character_engine.json").write_text(
                json.dumps(
                    {
                        "Cass": {
                            "wound": "",
                            "want": "",
                            "need": "",
                            "lie": "",
                            "unresolvable_contradictions": [],
                            "speech_sample": [],
                            "metaphor_domain": [],
                            "taboo_topics": [],
                            "default_dodge": "",
                            "stress_transform": {},
                            "cognitive_ceiling": {
                                "abstraction_level": "medium",
                                "reasoning_style": "fast but incomplete",
                                "failure_mode": "skips steps",
                            },
                        }
                    },
                    indent=2,
                )
            )
            (base / "chapter_cards.md").write_text(
                "# Chapter Cards\n\n## Ch 01: Signals\ngoal: Get proof\npressure: Public corridor\n"
                "reversal: The witness hedges\naftermath: Cass leaves exposed\n"
                "irreversible_change: Cass commits to the lie\nallowed_ambiguity: Whether the witness is afraid\n"
                "time_span: One afternoon\nscene_density: high\nscene_type: confrontation\n"
                "scene_method: dialogue_driven\nrisk: pov\n"
            )
            (base / "thread_registry.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "letters",
                            "description": "Guild letters are circulating",
                            "type": "pressure",
                            "first_seen": 1,
                            "payoff": 0,
                            "required": True,
                        }
                    ],
                    indent=2,
                )
            )
            (base / "world.md").write_text("# World\n")
            (base / "canon.md").write_text("# Canon\n")
            scene_dir = base / "scene_options"
            scene_dir.mkdir(parents=True)
            (scene_dir / "ch_01.json").write_text(
                json.dumps(
                    [
                        {
                            "option": 1,
                            "goal": "Get proof",
                            "pressure": "Public corridor",
                            "social_imbalance": "Student under scrutiny",
                            "wrong_inference": "Cass thinks he is being accused",
                            "surprise_slot": "Witness is covering for him",
                            "residue": "They leave more entangled than before",
                        }
                    ],
                    indent=2,
                )
            )

            self.assertTrue(detect_new_planning_mode(base, 1))
            self.assertEqual(resolve_mode(base, 1, "auto"), "new")

            prompt = build_new_mode_prompt(base, 1)
            self.assertIn("Blind spots are active constraints", prompt)
            self.assertIn("Humor is part of the mind", prompt)
            self.assertIn("cognitive ceiling", prompt)
            self.assertIn("Preserve the chapter card's irreversible change", prompt)
            self.assertIn("LOCAL THREAD WINDOW", prompt)
            self.assertEqual(load_chapter_card(base, 1)["title"], "Signals")

    def test_local_thread_window_prefers_required_pressure_threads(self):
        window = local_thread_window(
            [
                {"id": "echo", "description": "Coin motif", "type": "echo", "first_seen": 1, "payoff": 0, "required": False},
                {"id": "pressure", "description": "Guild scrutiny", "type": "pressure", "first_seen": 2, "payoff": 0, "required": True},
            ],
            2,
        )
        self.assertEqual(window[0]["id"], "pressure")

    def test_local_thread_window_excludes_future_threads(self):
        window = local_thread_window(
            [
                {"id": "current", "description": "Current thread", "type": "plot", "first_seen": 2, "payoff": 0, "required": True},
                {"id": "future", "description": "Future thread", "type": "plot", "first_seen": 3, "payoff": 0, "required": True},
            ],
            2,
        )
        self.assertEqual([thread["id"] for thread in window], ["current"])


if __name__ == "__main__":
    unittest.main()
