import json
import re
import unittest

from planning_split import (
    CHAPTER_CARD_FIELDS,
    derive_thread_registry_from_outline,
    derive_chapter_cards_from_outline,
    normalize_chapter_cards,
    normalize_thread_registry,
    parse_arc_outline,
    parse_chapter_cards,
    render_chapter_cards,
    render_legacy_outline,
)


class PlanningSplitTests(unittest.TestCase):
    def test_normalize_chapter_cards_fills_required_fields(self):
        cards = normalize_chapter_cards([{"number": 2, "title": "Signals", "goal": "Get answers"}])
        card = cards[0]
        self.assertEqual(card["number"], 2)
        self.assertEqual(card["title"], "Signals")
        for field in CHAPTER_CARD_FIELDS:
            self.assertIn(field, card)

    def test_render_chapter_cards_produces_template_when_empty(self):
        rendered = render_chapter_cards([])
        self.assertIn("# Chapter Cards", rendered)
        self.assertIn("## Ch 01", rendered)

    def test_parse_arc_outline_reads_new_source_of_truth_file(self):
        text = """# Arc Outline

**Working title:** Signals

## Irreversible Turns
### Act 1
- Cass lies to get in

## Major Reveals
- The ledger is forged

## Pressure Escalations
- The guild begins checking records

## Candidate Risk Chapters
Ch 4, Ch 9
"""
        arc = parse_arc_outline(text)
        self.assertEqual(arc["title"], "Signals")
        self.assertEqual(arc["acts"][0]["name"], "Act 1")
        self.assertEqual(arc["major_reveals"], ["The ledger is forged"])
        self.assertEqual(arc["candidate_risk_chapters"], [4, 9])

    def test_normalize_chapter_cards_enforces_enums(self):
        cards = normalize_chapter_cards(
            [
                {
                    "number": 1,
                    "title": "Signals",
                    "scene_density": "LOUD",
                    "scene_type": "mystery",
                    "scene_method": "voiceover",
                    "risk": "wild",
                }
            ]
        )
        card = cards[0]
        self.assertEqual(card["scene_density"], "medium")
        self.assertEqual(card["scene_type"], "investigation")
        self.assertEqual(card["scene_method"], "close_interiority")
        self.assertEqual(card["risk"], "none")

    def test_parse_chapter_cards_reads_new_source_of_truth_file(self):
        text = """# Chapter Cards

## Ch 01: Signals
goal: Get proof
pressure: The hallway is public
reversal: The witness refuses
aftermath: Cass doubles down
irreversible_change: He commits to the lie
allowed_ambiguity: Whether the witness is afraid or complicit
time_span: One afternoon
scene_density: high
scene_type: confrontation
scene_method: dialogue_driven
risk: pov
"""
        cards = parse_chapter_cards(text)
        self.assertEqual(cards[0]["title"], "Signals")
        self.assertEqual(cards[0]["scene_density"], "high")
        self.assertEqual(cards[0]["scene_type"], "confrontation")
        self.assertEqual(cards[0]["scene_method"], "dialogue_driven")
        self.assertEqual(cards[0]["risk"], "pov")

    def test_parse_chapter_cards_ignores_empty_template_card(self):
        rendered = render_chapter_cards([])
        cards = parse_chapter_cards(rendered)
        self.assertEqual(cards, [])

    def test_derive_thread_registry_from_outline_parses_legacy_table(self):
        legacy = """
# Outline

## Foreshadowing Ledger
| ID | Thread | Planted | Reinforced | Payoff | Type |
|----|--------|---------|------------|--------|------|
| bells_question | Bells question | Ch 2 | Ch 8, Ch 12 | Ch 22 | plot |
"""
        threads = derive_thread_registry_from_outline(legacy)
        self.assertEqual(threads[0]["id"], "bells_question")
        self.assertEqual(threads[0]["type"], "plot")
        self.assertEqual(threads[0]["planted"], 2)
        self.assertEqual(threads[0]["payoff"], 22)

    def test_render_legacy_outline_includes_cards_and_threads(self):
        arc = {"title": "Signals", "acts": [], "major_reveals": [], "pressure_escalations": []}
        cards = normalize_chapter_cards([{"number": 1, "title": "Signals", "goal": "Find proof"}])
        threads = normalize_thread_registry(
            [{"id": "proof", "description": "Need proof", "type": "plot", "first_seen": 1, "payoff": 5}]
        )
        rendered = render_legacy_outline("Signals", arc, cards, threads)
        self.assertIn("### Ch 1: Signals", rendered)
        self.assertIn("## Foreshadowing Ledger", rendered)
        self.assertIn("| proof | Need proof |", rendered)

    def test_rendered_legacy_outline_stays_parseable_for_current_extractor(self):
        arc = {"title": "Signals", "acts": [], "major_reveals": [], "pressure_escalations": []}
        cards = normalize_chapter_cards(
            [
                {"number": 1, "title": "Signals", "goal": "Find proof"},
                {"number": 2, "title": "Echoes", "goal": "Test the clue"},
            ]
        )
        rendered = render_legacy_outline("Signals", arc, cards, [])
        self.assertIn("### Ch 1: Signals", rendered)
        self.assertIn("### Ch 2: Echoes", rendered)
        self.assertIn("## Foreshadowing Ledger", rendered)

    def test_derive_chapter_cards_from_legacy_outline_keeps_heading_title(self):
        legacy = """# Outline

## Act 1

### Ch 1: First Signal
- BEATS:
  1. Cass arrives at the corridor.
  2. He lies about the ledger.
- PLANTS: (foreshadowing seeded here)
  - bell clue (payoff: Ch 9)
- HARVESTS: (foreshadowing paid off here)
- EMOTIONAL ARC: anxious -> committed
- STATUS: unwritten
"""
        cards = derive_chapter_cards_from_outline(legacy)
        self.assertEqual(cards[0]["title"], "First Signal")
        self.assertEqual(cards[0]["goal"], "Cass arrives at the corridor.")

    def test_first_beat_ignores_section_labels(self):
        legacy = """# Outline

## Act 1

### Ch 1: First Signal
- BEATS:
  1. Cass arrives.
"""
        cards = derive_chapter_cards_from_outline(legacy)
        self.assertEqual(cards[0]["goal"], "Cass arrives.")

    def test_empty_legacy_render_includes_real_chapter_blocks(self):
        rendered = render_legacy_outline(
            "Outline",
            {"title": "Outline", "acts": [], "major_reveals": [], "pressure_escalations": []},
            [],
            [],
        )
        match = re.search(r"### Ch 1:.*?(?=### Ch 2:|## Foreshadowing|$)", rendered, re.DOTALL)
        self.assertIsNotNone(match)
        self.assertIn("- BEATS:", match.group(0))
        self.assertIn("1. Placeholder beat for Chapter 1.", match.group(0))

    def test_thread_registry_json_round_trip_shape(self):
        threads = normalize_thread_registry([{"id": "echo", "description": "Coin", "type": "echo"}])
        blob = json.dumps(threads)
        self.assertEqual(json.loads(blob)[0]["type"], "echo")


if __name__ == "__main__":
    unittest.main()
