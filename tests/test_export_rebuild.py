import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from export_rebuild import render_arc_summary_text, render_outline_text


def write_chapter(path: Path, title: str, body: str) -> None:
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")


class ExportRebuildTests(unittest.TestCase):
    def test_outline_rebuild_uses_live_counts_and_current_artifacts(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (root / "chapters").mkdir()
            write_chapter(
                root / "chapters" / "ch_01.md",
                "First Bell",
                "Cass hears the hidden note in the bell tower.\n\nHe leaves with the question still ringing.",
            )
            write_chapter(
                root / "chapters" / "ch_02.md",
                "Second Bell",
                "Perin refuses the easy answer.\n\nCass decides the bell has been asking consent all along.",
            )
            (planning / "arc_outline.md").write_text(
                "# Arc Outline\n\n"
                "**Working title:** Bells\n\n"
                "## Irreversible Turns\n"
                "### Act I\n"
                "- Cass hears the forbidden interval.\n\n"
                "## Major Reveals\n"
                "- The bell hides a legal question.\n\n"
                "## Pressure Escalations\n"
                "- The family can no longer pretend the contract is ordinary.\n\n"
                "## Candidate Risk Chapters\n"
                "2\n",
                encoding="utf-8",
            )
            (planning / "chapter_cards.md").write_text(
                "# Chapter Cards\n\n"
                "## Ch 01: Signals\n"
                "goal: Learn why the bell hurts\n"
                "pressure: The household treats the pain as disobedience\n"
                "reversal: Cass realizes the bell is speaking\n"
                "aftermath: He hides what he heard\n"
                "irreversible_change: Cass can no longer believe the bell is neutral\n"
                "allowed_ambiguity: Whether the note is memory or law\n"
                "time_span: One afternoon\n"
                "scene_density: high\n"
                "scene_type: revelation\n"
                "scene_method: close_interiority\n"
                "risk: none\n\n"
                "## Ch 02: Refusal\n"
                "goal: Test whether Perin hears the same thing\n"
                "pressure: Perin needs the contract to remain real\n"
                "reversal: The brothers recognize the question in the bell\n"
                "aftermath: They stop trusting the city record\n"
                "irreversible_change: Perin becomes part of the secret\n"
                "allowed_ambiguity: Whether consent can be recovered\n"
                "time_span: One night\n"
                "scene_density: medium\n"
                "scene_type: confrontation\n"
                "scene_method: dialogue_driven\n"
                "risk: formal\n",
                encoding="utf-8",
            )
            (planning / "thread_registry.json").write_text(
                "[\n"
                '  {"id": "consent", "description": "The bell asks for consent", "type": "plot", "first_seen": 1, "reinforced": [2], "payoff": 2, "required": true},\n'
                '  {"id": "shame", "description": "Cass hides the pain", "type": "pressure", "first_seen": 1, "reinforced": [], "payoff": 0, "required": false}\n'
                "]\n",
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                "{\n"
                '  "title": "Old Bells",\n'
                '  "phase": "review",\n'
                '  "chapter_count": 99,\n'
                '  "planned_chapter_count": 99,\n'
                '  "word_count": 9999,\n'
                '  "risk_chapters": [99]\n'
                "}\n",
                encoding="utf-8",
            )

            outline = render_outline_text(root)

        self.assertIn("# Bells", outline)
        self.assertIn("accepted chapters: 2 / planned chapters: 2", outline)
        self.assertIn("### Ch 1: First Bell", outline)
        self.assertIn("### Ch 2: Second Bell", outline)
        self.assertIn("Cass hears the hidden note in the bell tower.", outline)
        self.assertIn("payoff=Ch 02", outline)
        self.assertIn("| consent | The bell asks for consent | plot | Ch 01 | Ch 02 | Ch 02 | yes | paid-off |", outline)

    def test_arc_summary_rebuild_uses_accepted_prose_and_thread_registry(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (root / "chapters").mkdir()
            write_chapter(
                root / "chapters" / "ch_01.md",
                "Glass Choir",
                "The choir glass rattles when the contract is sung.\n\nCass thinks the answer is trapped in the metal.",
            )
            (planning / "arc_outline.md").write_text(
                "# Arc Outline\n\n"
                "**Working title:** Glass Choir\n\n"
                "## Irreversible Turns\n"
                "### Act I\n"
                "- Cass hears the contract answer back.\n\n"
                "## Major Reveals\n"
                "- Binding law depends on consent.\n\n"
                "## Pressure Escalations\n"
                "- His family risks exposure.\n\n"
                "## Candidate Risk Chapters\n"
                "1\n",
                encoding="utf-8",
            )
            (planning / "chapter_cards.md").write_text(
                "# Chapter Cards\n\n"
                "## Ch 01: Glass Choir\n"
                "goal: Understand the sound inside the contract\n"
                "pressure: Adults insist the pain is imagination\n"
                "reversal: The bell answers with a question\n"
                "aftermath: Cass keeps the knowledge private\n"
                "irreversible_change: He knows the law can speak back\n"
                "allowed_ambiguity: Whether the answer wants him\n"
                "time_span: One morning\n"
                "scene_density: high\n"
                "scene_type: revelation\n"
                "scene_method: close_interiority\n"
                "risk: formal\n",
                encoding="utf-8",
            )
            (planning / "thread_registry.json").write_text(
                "[\n"
                '  {"id": "answer", "description": "The bell answers the contract", "type": "plot", "first_seen": 1, "reinforced": [], "payoff": 0, "required": true}\n'
                "]\n",
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                "{\n"
                '  "title": "Glass Choir",\n'
                '  "phase": "export",\n'
                '  "chapter_count": 1,\n'
                '  "planned_chapter_count": 1,\n'
                '  "word_count": 18,\n'
                '  "risk_chapters": [1]\n'
                "}\n",
                encoding="utf-8",
            )
            (root / "state.json").write_text('{"phase": "export"}\n', encoding="utf-8")

            summary = render_arc_summary_text(root)

        self.assertIn("# Glass Choir", summary)
        self.assertIn("Current phase: export. Accepted chapters: 1 / planned chapters: 1.", summary)
        self.assertIn("Thread counts by type: plot=1", summary)
        self.assertIn("### Ch 1: Glass Choir", summary)
        self.assertIn("The choir glass rattles when the contract is sung.", summary)
        self.assertIn("plants=The bell answers the contract | type=plot", summary)

    def test_outline_rebuild_prefers_live_phase_over_stale_manifest_phase(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (root / "chapters").mkdir()
            (planning / "arc_outline.md").write_text(
                "# Arc Outline\n\n**Working title:** Bells\n",
                encoding="utf-8",
            )
            (planning / "chapter_cards.md").write_text(
                "# Chapter Cards\n\n"
                "## Ch 01: One\n"
                "goal: Test\n"
                "pressure: Pressure\n"
                "reversal: Reversal\n"
                "aftermath: Aftermath\n"
                "irreversible_change: Change\n"
                "allowed_ambiguity: Maybe\n"
                "time_span: One night\n"
                "scene_density: medium\n"
                "scene_type: quiet\n"
                "scene_method: close_interiority\n"
                "risk: none\n",
                encoding="utf-8",
            )
            (planning / "thread_registry.json").write_text("[]\n", encoding="utf-8")
            (root / "manifest.json").write_text(
                "{\n"
                '  "title": "Bells",\n'
                '  "phase": "review",\n'
                '  "chapter_count": 0,\n'
                '  "planned_chapter_count": 1,\n'
                '  "word_count": 0,\n'
                '  "risk_chapters": []\n'
                "}\n",
                encoding="utf-8",
            )
            (root / "state.json").write_text('{"phase": "export"}\n', encoding="utf-8")

            outline = render_outline_text(root)

        self.assertIn("- Phase: export | accepted chapters: 0 / planned chapters: 1 | accepted words: 0", outline)
        self.assertIn("- Manifest source used for export metadata: live-snapshot", outline)


if __name__ == "__main__":
    unittest.main()
