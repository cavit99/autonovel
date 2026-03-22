import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_paths import migrate_planning_artifacts, require_seed_path, seed_path


class ProjectPathsTests(unittest.TestCase):
    def test_migrate_planning_artifacts_moves_root_docs_into_planning(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "world.md").write_text("# World\n", encoding="utf-8")
            (root / "outline.md").write_text("# Outline\n", encoding="utf-8")
            (root / "seed.txt").write_text("Legacy seed\n", encoding="utf-8")

            moved = migrate_planning_artifacts(root)

            self.assertEqual(
                {(src.name, dest.relative_to(root).as_posix()) for src, dest in moved},
                {
                    ("outline.md", "planning/outline.md"),
                    ("world.md", "planning/world.md"),
                },
            )
            self.assertFalse((root / "world.md").exists())
            self.assertFalse((root / "outline.md").exists())
            self.assertTrue((root / "planning" / "world.md").exists())
            self.assertTrue((root / "planning" / "outline.md").exists())
            self.assertTrue((root / "seed.txt").exists())

    def test_require_seed_path_mentions_seed_md_contract(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "seed.txt").write_text("Legacy seed\n", encoding="utf-8")

            with self.assertRaises(FileNotFoundError) as ctx:
                require_seed_path(root)

        self.assertIn("seed.md", str(ctx.exception))
        self.assertIn("seed.txt is no longer read automatically", str(ctx.exception))

    def test_require_seed_path_prefers_planning_seed_md_and_falls_back_to_root_seed_md(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            planning = root / "planning"
            planning.mkdir()
            (root / "seed.md").write_text("root seed\n", encoding="utf-8")

            self.assertEqual(require_seed_path(root), root / "seed.md")

            (planning / "seed.md").write_text("planning seed\n", encoding="utf-8")

            self.assertEqual(require_seed_path(root), planning / "seed.md")
            self.assertEqual(seed_path(root), planning / "seed.md")


if __name__ == "__main__":
    unittest.main()
