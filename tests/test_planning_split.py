import json
import io
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import gen_arc
import gen_chapter_cards
import gen_outline
import gen_outline_part2
import gen_thread_registry

from planning_split import (
    CHAPTER_CARD_FIELDS,
    derive_thread_registry_from_outline,
    derive_chapter_cards_from_outline,
    extract_json_object,
    normalize_chapter_cards,
    normalize_thread_registry,
    parse_arc_outline,
    parse_chapter_cards,
    render_chapter_cards,
    render_legacy_outline,
)


class PlanningSplitTests(unittest.TestCase):
    def run_wrapper(self, module, args: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = module.main(args)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def write_planning_artifacts(self, base_dir: Path) -> tuple[Path, Path, Path]:
        arc_path = base_dir / "arc_outline.md"
        arc_path.write_text(
            """# Arc Outline

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
        )
        cards_path = base_dir / "chapter_cards.md"
        cards_path.write_text(
            """# Chapter Cards

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
        )
        threads_path = base_dir / "thread_registry.json"
        threads = normalize_thread_registry(
            [{"id": "proof", "description": "Need proof", "type": "plot", "first_seen": 1, "payoff": 5}]
        )
        threads_path.write_text(json.dumps(threads, indent=2) + "\n")
        return arc_path, cards_path, threads_path

    def snapshot_paths(self, *paths: Path) -> dict[Path, tuple[str, int]]:
        return {path: (path.read_text(), path.stat().st_mtime_ns) for path in paths}

    def test_normalize_chapter_cards_fills_required_fields(self):
        cards = normalize_chapter_cards([{"number": 2, "title": "Signals", "goal": "Get answers"}])
        card = cards[0]
        self.assertEqual(card["number"], 2)
        self.assertEqual(card["title"], "Signals")
        for field in CHAPTER_CARD_FIELDS:
            self.assertIn(field, card)

    def test_extract_json_object_rejects_missing_json_cleanly(self):
        with self.assertRaisesRegex(ValueError, "No JSON object found in response"):
            extract_json_object("No structured payload was returned.")

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
focus_character: Cass
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
        self.assertEqual(cards[0]["focus_character"], "Cass")
        self.assertEqual(cards[0]["scene_density"], "high")
        self.assertEqual(cards[0]["scene_type"], "confrontation")
        self.assertEqual(cards[0]["scene_method"], "dialogue_driven")
        self.assertEqual(cards[0]["risk"], "pov")

    def test_parse_chapter_cards_accepts_focus_alias(self):
        text = """# Chapter Cards

## Ch 01: Signals
pov_character: Cass
goal: Get proof
"""
        cards = parse_chapter_cards(text)
        self.assertEqual(cards[0]["focus_character"], "Cass")

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
| bells_question | Bells question | Ch 2 | Ch 8, Ch 12 | Ch 22 | echo |
"""
        threads = derive_thread_registry_from_outline(legacy)
        self.assertEqual(threads[0]["id"], "bells_question")
        self.assertEqual(threads[0]["type"], "echo")
        self.assertEqual(threads[0]["planted"], 2)
        self.assertEqual(threads[0]["payoff"], 22)

    def test_derive_thread_registry_from_rendered_legacy_outline_preserves_thread_types(self):
        arc = {"title": "Signals", "acts": [], "major_reveals": [], "pressure_escalations": []}
        cards = normalize_chapter_cards([{"number": 1, "title": "Signals", "goal": "Find proof"}])
        threads = normalize_thread_registry(
            [
                {"id": "coin_echo", "description": "Coin echo", "type": "echo", "first_seen": 2, "payoff": 9},
                {"id": "street_grit", "description": "Street grit", "type": "texture", "first_seen": 3, "payoff": 11},
            ]
        )

        rendered = render_legacy_outline("Signals", arc, cards, threads)
        imported_threads = derive_thread_registry_from_outline(rendered)

        self.assertEqual(
            [(thread["id"], thread["type"]) for thread in imported_threads],
            [("coin_echo", "echo"), ("street_grit", "texture")],
        )

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

    def test_generate_arc_warns_when_falling_back(self):
        fallback_arc = {"title": "Signals", "acts": [], "major_reveals": [], "pressure_escalations": [], "candidate_risk_chapters": [4]}
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            seed_path = Path(tmpdir) / "seed.md"
            seed_path.write_text("stub", encoding="utf-8")
            output_path = Path(tmpdir) / "arc_outline.md"
            with (
                mock.patch.object(gen_arc, "API_KEY", "test-key"),
                mock.patch.object(gen_arc, "require_seed_path", return_value=seed_path),
                mock.patch.object(gen_arc, "read_required", return_value="stub"),
                mock.patch.object(gen_arc, "call_writer", side_effect=RuntimeError("writer failed")),
                mock.patch.object(gen_arc, "derive_arc", return_value=fallback_arc),
                redirect_stderr(stderr),
            ):
                arc = gen_arc.generate_arc(output_path=output_path)

        self.assertEqual(arc, fallback_arc)
        self.assertIn("WARNING: gen_arc.py falling back to derived arc outline: writer failed", stderr.getvalue())

    def test_generate_chapter_cards_warns_when_falling_back(self):
        fallback_cards = normalize_chapter_cards([{"number": 1, "title": "Signals"}])
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            seed_path = Path(tmpdir) / "seed.md"
            seed_path.write_text("stub", encoding="utf-8")
            output_path = Path(tmpdir) / "chapter_cards.md"
            with (
                mock.patch.object(gen_chapter_cards, "API_KEY", "test-key"),
                mock.patch.object(gen_chapter_cards, "require_seed_path", return_value=seed_path),
                mock.patch.object(gen_chapter_cards, "read_required", return_value="stub"),
                mock.patch.object(gen_chapter_cards, "call_writer", side_effect=RuntimeError("writer failed")),
                mock.patch.object(gen_chapter_cards, "derive_cards", return_value=fallback_cards),
                redirect_stderr(stderr),
            ):
                cards = gen_chapter_cards.generate_chapter_cards(output_path=output_path)

        self.assertEqual(cards, fallback_cards)
        self.assertIn(
            "WARNING: gen_chapter_cards.py falling back to derived chapter cards: writer failed",
            stderr.getvalue(),
        )

    def test_generate_thread_registry_warns_when_falling_back(self):
        fallback_threads = normalize_thread_registry(
            [{"id": "proof", "description": "Need proof", "type": "plot", "first_seen": 1, "payoff": 5}]
        )
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            planning = base_dir / "planning"
            planning.mkdir()
            (planning / "arc_outline.md").write_text("# Arc Outline\n", encoding="utf-8")
            (planning / "chapter_cards.md").write_text("# Chapter Cards\n", encoding="utf-8")
            (planning / "outline.md").write_text("# Outline\n", encoding="utf-8")
            output_path = planning / "thread_registry.json"
            with (
                mock.patch.object(gen_thread_registry, "BASE_DIR", base_dir),
                mock.patch.object(gen_thread_registry, "API_KEY", "test-key"),
                mock.patch.object(gen_thread_registry, "call_writer", side_effect=RuntimeError("writer failed")),
                mock.patch.object(gen_thread_registry, "derive_threads", return_value=fallback_threads),
                redirect_stderr(stderr),
            ):
                threads = gen_thread_registry.generate_thread_registry(output_path=output_path)

        self.assertEqual(threads, fallback_threads)
        self.assertIn(
            "WARNING: gen_thread_registry.py falling back to derived thread registry: writer failed",
            stderr.getvalue(),
        )

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

    def test_empty_legacy_render_does_not_invent_placeholder_chapter_blocks(self):
        rendered = render_legacy_outline(
            "Outline",
            {"title": "Outline", "acts": [], "major_reveals": [], "pressure_escalations": []},
            [],
            [],
        )
        self.assertIn("## Chapters", rendered)
        self.assertIn("<!-- Chapter cards have not been generated yet. -->", rendered)
        self.assertNotIn("### Ch 1:", rendered)

    def test_thread_registry_json_round_trip_shape(self):
        threads = normalize_thread_registry([{"id": "echo", "description": "Coin", "type": "echo"}])
        blob = json.dumps(threads)
        self.assertEqual(json.loads(blob)[0]["type"], "echo")

    def test_gen_outline_wrapper_default_mode_is_read_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            arc_path, cards_path, threads_path = self.write_planning_artifacts(base_dir)
            output_path = base_dir / "outline.md"
            before = self.snapshot_paths(arc_path, cards_path, threads_path)

            with (
                mock.patch.object(gen_outline, "generate_arc", side_effect=AssertionError("generate_arc called")),
                mock.patch.object(
                    gen_outline, "generate_chapter_cards", side_effect=AssertionError("generate_chapter_cards called")
                ),
                mock.patch.object(
                    gen_outline, "generate_thread_registry", side_effect=AssertionError("generate_thread_registry called")
                ),
            ):
                exit_code, _, _ = self.run_wrapper(
                    gen_outline,
                    [
                        "--output",
                        str(output_path),
                        "--arc-output",
                        str(arc_path),
                        "--cards-output",
                        str(cards_path),
                        "--threads-output",
                        str(threads_path),
                    ],
                )

            self.assertEqual(exit_code, 0)
            rendered = output_path.read_text()
            self.assertIn("### Ch 1: Signals", rendered)
            self.assertIn("| proof | Need proof |", rendered)
            for path, (contents, mtime_ns) in before.items():
                self.assertEqual(path.read_text(), contents)
                self.assertEqual(path.stat().st_mtime_ns, mtime_ns)

    def test_gen_outline_wrapper_requires_existing_artifacts_without_refresh(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            output_path = base_dir / "outline.md"
            arc_path = base_dir / "arc_outline.md"
            cards_path = base_dir / "chapter_cards.md"
            threads_path = base_dir / "thread_registry.json"

            exit_code, _, stderr = self.run_wrapper(
                gen_outline,
                [
                    "--output",
                    str(output_path),
                    "--arc-output",
                    str(arc_path),
                    "--cards-output",
                    str(cards_path),
                    "--threads-output",
                    str(threads_path),
                ],
            )

            self.assertEqual(exit_code, 1)
            self.assertIn("read-only by default", stderr)
            self.assertIn("--refresh-new-planning", stderr)
            self.assertIn(str(arc_path), stderr)
            self.assertIn(str(cards_path), stderr)
            self.assertIn(str(threads_path), stderr)

    def test_gen_outline_wrapper_refresh_flag_regenerates_planning_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            arc_path, cards_path, threads_path = self.write_planning_artifacts(base_dir)
            output_path = base_dir / "outline.md"

            refreshed_arc = {
                "title": "Refreshed Signals",
                "acts": [{"name": "Act 1", "irreversible_turns": ["Cass burns the ledger bridge"]}],
                "major_reveals": ["The ledger was bait"],
                "pressure_escalations": ["The guild seals the archives"],
                "candidate_risk_chapters": [3],
            }
            refreshed_cards = normalize_chapter_cards([{"number": 3, "title": "Aftershock", "goal": "Survive fallout"}])
            refreshed_threads = normalize_thread_registry(
                [{"id": "bait", "description": "Ledger bait", "type": "plot", "first_seen": 3, "payoff": 7}]
            )

            def fake_generate_arc(*, output_path: Path) -> dict[str, object]:
                output_path.write_text("arc refreshed\n")
                return refreshed_arc

            def fake_generate_cards(*, output_path: Path) -> list[dict[str, object]]:
                output_path.write_text("cards refreshed\n")
                return refreshed_cards

            def fake_generate_threads(*, output_path: Path) -> list[dict[str, object]]:
                output_path.write_text(json.dumps(refreshed_threads, indent=2) + "\n")
                return refreshed_threads

            with (
                mock.patch.object(gen_outline, "generate_arc", side_effect=fake_generate_arc) as arc_mock,
                mock.patch.object(gen_outline, "generate_chapter_cards", side_effect=fake_generate_cards) as cards_mock,
                mock.patch.object(
                    gen_outline, "generate_thread_registry", side_effect=fake_generate_threads
                ) as threads_mock,
            ):
                exit_code, _, _ = self.run_wrapper(
                    gen_outline,
                    [
                        "--refresh-new-planning",
                        "--output",
                        str(output_path),
                        "--arc-output",
                        str(arc_path),
                        "--cards-output",
                        str(cards_path),
                        "--threads-output",
                        str(threads_path),
                    ],
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(arc_mock.call_count, 1)
            self.assertEqual(cards_mock.call_count, 1)
            self.assertEqual(threads_mock.call_count, 1)
            self.assertEqual(arc_path.read_text(), "arc refreshed\n")
            self.assertEqual(cards_path.read_text(), "cards refreshed\n")
            self.assertIn("Ledger bait", threads_path.read_text())
            rendered = output_path.read_text()
            self.assertIn("# Refreshed Signals", rendered)
            self.assertIn("### Ch 3: Aftershock", rendered)
            self.assertIn("| bait | Ledger bait |", rendered)

    def test_gen_outline_part2_default_mode_is_read_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            arc_path, cards_path, threads_path = self.write_planning_artifacts(base_dir)
            output_path = base_dir / "outline.md"
            before = self.snapshot_paths(arc_path, cards_path, threads_path)

            with mock.patch.object(
                gen_outline_part2, "generate_thread_registry", side_effect=AssertionError("generate_thread_registry called")
            ):
                exit_code, _, _ = self.run_wrapper(
                    gen_outline_part2,
                    [
                        "--output",
                        str(output_path),
                        "--arc-output",
                        str(arc_path),
                        "--cards-output",
                        str(cards_path),
                        "--threads-output",
                        str(threads_path),
                    ],
                )

            self.assertEqual(exit_code, 0)
            rendered = output_path.read_text()
            self.assertIn("### Ch 1: Signals", rendered)
            self.assertIn("| proof | Need proof |", rendered)
            for path, (contents, mtime_ns) in before.items():
                self.assertEqual(path.read_text(), contents)
                self.assertEqual(path.stat().st_mtime_ns, mtime_ns)

    def test_gen_outline_part2_refresh_flag_regenerates_thread_registry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            arc_path, cards_path, threads_path = self.write_planning_artifacts(base_dir)
            output_path = base_dir / "outline.md"
            before = self.snapshot_paths(arc_path, cards_path)
            refreshed_threads = normalize_thread_registry(
                [{"id": "echo", "description": "Bell echo", "type": "echo", "first_seen": 2, "payoff": 6}]
            )

            def fake_generate_threads(*, output_path: Path) -> list[dict[str, object]]:
                output_path.write_text(json.dumps(refreshed_threads, indent=2) + "\n")
                return refreshed_threads

            with mock.patch.object(
                gen_outline_part2, "generate_thread_registry", side_effect=fake_generate_threads
            ) as threads_mock:
                exit_code, _, _ = self.run_wrapper(
                    gen_outline_part2,
                    [
                        "--refresh-new-planning",
                        "--output",
                        str(output_path),
                        "--arc-output",
                        str(arc_path),
                        "--cards-output",
                        str(cards_path),
                        "--threads-output",
                        str(threads_path),
                    ],
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(threads_mock.call_count, 1)
            self.assertIn("Bell echo", threads_path.read_text())
            for path, (contents, mtime_ns) in before.items():
                self.assertEqual(path.read_text(), contents)
                self.assertEqual(path.stat().st_mtime_ns, mtime_ns)
            self.assertIn("| echo | Bell echo |", output_path.read_text())


if __name__ == "__main__":
    unittest.main()
