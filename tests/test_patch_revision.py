import unittest
from unittest.mock import patch

from patch_revision import generate_patch_plan
from revision_patching import (
    DeterministicPatchPlanError,
    apply_patch_edits,
    build_deterministic_patch_plan,
)
from roughness_guard import build_guard_report


class PatchRevisionTests(unittest.TestCase):
    def test_roughness_guard_locks_three_to_five_passages(self):
        text = (
            'He touched the latch as if it might hiss.\n\n'
            '"You can say it plain," Cass said. "Or you can keep scraping at it."\n\n'
            "The clerk smiled; then smiled again, thinner.\n\n"
            "Outside, a cartwheel barked over the stones and left the air feeling rung.\n\n"
            "He wrote the number twice. Then once more, smaller."
        )
        report = build_guard_report(text, 4)
        self.assertGreaterEqual(report["lock_count"], 3)
        self.assertLessEqual(report["lock_count"], 5)
        reasons = {item["reason"] for item in report["locked_spans"]}
        self.assertTrue({"speaker-specific awkwardness", "odd but alive syntax"} & reasons)

    def test_deterministic_patch_plan_supports_cut_replace_insert_and_move(self):
        source = (
            "Opening line.\n\n"
            "This sentence is redundant.\n\n"
            "Anchor sentence.\n\n"
            "Move me please.\n\n"
            "Closing line.\n"
        )
        brief = (
            '# Example Brief\n\n'
            '- replace: "Opening line." => "Sharper opening line."\n'
            '- cut: "This sentence is redundant."\n'
            '- insert after: "Anchor sentence." => "Inserted beat."\n'
            '- move before: "Move me please." "Anchor sentence."\n'
        )
        plan = build_deterministic_patch_plan(5, brief, source, locked_spans=[])
        self.assertEqual([edit["type"] for edit in plan["edits"]], ["replace", "cut", "insert", "move"])

        revised, applied = apply_patch_edits(source, plan["edits"], plan["locked_spans"])
        self.assertEqual(len(applied), 4)
        self.assertTrue(revised.startswith("Sharper opening line.\n\n"))
        self.assertNotIn("This sentence is redundant.", revised)
        self.assertLess(revised.index("Move me please."), revised.index("Anchor sentence."))
        self.assertIn("Anchor sentence.\n\nInserted beat.\n\n", revised)
        self.assertNotIn("\n\n\n\n", revised)
        self.assertNotIn("please.Anchor", revised)

    def test_apply_patch_edits_preserves_readable_boundaries_for_cut_and_move(self):
        source = "A.\n\nB.\n\nC.\n"
        edits = [
            {"id": "cut-mid", "type": "cut", "start": 4, "end": 6, "reason": ""},
        ]
        revised, _applied = apply_patch_edits(source, edits, locked_spans=[])
        self.assertEqual(revised, "A.\n\nC.\n")

        move_source = "A.\n\nC.\n\nB.\n"
        move_edits = [
            {"id": "move-b", "type": "move", "start": 8, "end": 10, "to": 4, "reason": ""},
        ]
        moved, _applied = apply_patch_edits(move_source, move_edits, locked_spans=[])
        self.assertEqual(moved, "A.\n\nB.\n\nC.\n")

    def test_apply_patch_edits_preserves_unmodified_prefix_and_suffix(self):
        source = "Prefix with two spaces.  \n\nreplace me\n\nSuffix stays exact.\n"
        edits = [{"id": "edit-1", "type": "replace", "start": 27, "end": 37, "text": "repair me", "reason": ""}]
        revised, _applied = apply_patch_edits(source, edits, locked_spans=[])
        self.assertEqual(revised[:27], source[:27])
        self.assertEqual(revised[-20:], source[-20:])
        self.assertIn("repair me", revised)

    def test_apply_patch_edits_rejects_locked_overlap(self):
        source = "Keep this strange line.\n\nCut me.\n"
        edits = [{"id": "edit-1", "type": "cut", "start": 0, "end": 22, "reason": ""}]
        locked = [{"start": 0, "end": 22, "reason": "odd but alive syntax", "excerpt": "Keep this strange line."}]
        with self.assertRaises(ValueError):
            apply_patch_edits(source, edits, locked)

    def test_generate_patch_plan_falls_back_when_model_output_is_invalid(self):
        source = "Anchor sentence.\n\nThis sentence is redundant.\n"
        brief = '- cut: "This sentence is redundant."'
        with patch("patch_revision.API_KEY", "stub"):
            plan = generate_patch_plan(
                5,
                brief,
                source,
                guard_report={"locked_spans": []},
                planner_mode="auto",
                planner_call=lambda _prompt: "not json",
            )
        self.assertEqual(plan["planner"], "deterministic")
        self.assertEqual(len(plan["edits"]), 1)
        self.assertEqual(plan["edits"][0]["type"], "cut")

    def test_deterministic_patch_plan_parses_current_cuts_brief_structure(self):
        source = "Opening line.\n\nThis sentence is redundant.\n"
        brief = (
            "# Revision Brief: Chapter 5 - Example (TIGHTEN)\n\n"
            "## PROBLEM\nStuff.\n\n"
            "## WHAT TO KEEP\nKeep it.\n\n"
            "## WHAT TO CHANGE\n"
            "### OVER-EXPLAIN (1 cuts)\n"
            '1. `"This sentence is redundant."`\n'
            "   Reason: repeats itself\n"
            "   → Cut entirely\n"
            '2. `"Opening line."`\n'
            "   Reason: too flat\n"
            '   → Rewrite as: "Sharper opening line."\n\n'
            "## VOICE RULES\n- Keep the bite.\n"
        )
        plan = build_deterministic_patch_plan(5, brief, source, locked_spans=[])
        self.assertEqual([edit["type"] for edit in plan["edits"]], ["cut", "replace"])

    def test_deterministic_patch_plan_fails_clearly_on_prose_only_brief(self):
        brief = (
            "# Revision Brief: Chapter 5 - Example (FIX)\n\n"
            "## WHAT TO CHANGE\n"
            "1. **Pacing**: Tighten the scene that drags.\n"
            "2. **Deepen character**: Add more interiority.\n"
        )
        with self.assertRaises(DeterministicPatchPlanError) as ctx:
            build_deterministic_patch_plan(5, brief, "Opening line.\n", locked_spans=[])
        self.assertIn("could not derive actionable edits", str(ctx.exception))

    def test_generate_patch_plan_raises_when_no_key_and_brief_is_prose_only(self):
        brief = (
            "# Revision Brief: Chapter 5 - Example (FIX)\n\n"
            "## WHAT TO CHANGE\n"
            "1. **Pacing**: Tighten the scene that drags.\n"
        )
        with patch("patch_revision.API_KEY", ""):
            with self.assertRaises(DeterministicPatchPlanError) as ctx:
                generate_patch_plan(5, brief, "Opening line.\n", guard_report={"locked_spans": []}, planner_mode="auto")
        self.assertIn("No patch planner API key is configured", str(ctx.exception))

    def test_generate_patch_plan_with_missing_source_returns_pending_directives(self):
        brief = (
            "# Example Revision Brief\n\n"
            "## Patch Directives\n"
            '- cut: "This sentence is redundant."\n'
        )
        plan = generate_patch_plan(5, brief, "", guard_report={"locked_spans": []}, planner_mode="auto")
        self.assertEqual(plan["planner"], "deterministic-pending")
        self.assertEqual(plan["edits"], [])
        self.assertEqual(plan["unresolved_directives"][0]["type"], "cut")


if __name__ == "__main__":
    unittest.main()
