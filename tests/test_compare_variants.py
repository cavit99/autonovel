import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *args, **kwargs: False
sys.modules.setdefault("dotenv", dotenv_stub)

import compare_variants


class CompareVariantsTests(unittest.TestCase):
    def test_call_judge_uses_automatic_prompt_caching(self):
        captured = {}

        class FakeResponse:
            def json(self):
                return {"content": [{"text": '{"winner":"baseline","decision":"select","reason":"ok"}'}]}

            def raise_for_status(self):
                return None

        class FakeHttpx:
            @staticmethod
            def post(url, headers=None, json=None, timeout=None):
                captured["url"] = url
                captured["headers"] = headers
                captured["json"] = json
                captured["timeout"] = timeout
                return FakeResponse()

        with mock.patch.dict("sys.modules", {"httpx": FakeHttpx}):
            result = compare_variants.call_judge("compare these candidates")

        self.assertEqual(result["winner"], "baseline")
        self.assertEqual(captured["json"]["cache_control"], {"type": "ephemeral", "ttl": "5m"})

    def test_main_uses_deterministic_winner_id_when_winner_path_string_differs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            candidate_path = base_dir / "chapters" / "variants" / "ch_01_variant_01.md"
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_text("Variant text.\n", encoding="utf-8")
            applied_path = base_dir / "chapters" / "ch_01.md"
            log_path = base_dir / "edit_logs" / "ch01_variant_compare.json"
            candidates = [
                {"id": "baseline", "path": base_dir / "chapters" / "ch_01.md", "text": "Baseline draft."},
                {"id": "variant_01", "path": candidate_path, "text": "Variant draft."},
            ]
            deterministic_result = {
                "decision": "select",
                "winner": "variant_01",
                "winner_path": "chapters/variants/./ch_01_variant_01.md",
                "reason": "Deterministic fallback preferred variant_01.",
            }

            with (
                mock.patch.object(compare_variants, "API_KEY", ""),
                mock.patch.object(compare_variants, "load_variant_candidates", return_value=candidates),
                mock.patch.object(
                    compare_variants,
                    "pick_best_variant_deterministically",
                    return_value=deterministic_result,
                ),
                mock.patch.object(compare_variants, "apply_winner", return_value=applied_path) as apply_mock,
                mock.patch.object(compare_variants, "comparison_log_path", return_value=log_path),
                mock.patch.object(
                    compare_variants.sys,
                    "argv",
                    ["compare_variants.py", "1", "--base-dir", str(base_dir)],
                ),
                redirect_stdout(io.StringIO()),
            ):
                compare_variants.main()

            apply_mock.assert_called_once_with(1, candidate_path, base_dir)
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["winner"], "variant_01")
            self.assertEqual(payload["winner_path"], str(candidate_path))
            self.assertEqual(payload["applied_path"], str(applied_path))

    def test_main_uses_fallback_winner_id_after_unknown_model_winner(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            candidate_path = base_dir / "chapters" / "variants" / "ch_01_variant_01.md"
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_text("Variant text.\n", encoding="utf-8")
            applied_path = base_dir / "chapters" / "ch_01.md"
            log_path = base_dir / "edit_logs" / "ch01_variant_compare.json"
            candidates = [
                {"id": "baseline", "path": base_dir / "chapters" / "ch_01.md", "text": "Baseline draft."},
                {"id": "variant_01", "path": candidate_path, "text": "Variant draft."},
            ]
            model_result = {"decision": "select", "winner": "missing", "reason": "No usable answer."}
            deterministic_result = {
                "decision": "select",
                "winner": "variant_01",
                "winner_path": "./chapters/variants/ch_01_variant_01.md",
                "reason": "Deterministic fallback preferred variant_01.",
            }

            with (
                mock.patch.object(compare_variants, "API_KEY", "test-key"),
                mock.patch.object(compare_variants, "call_judge", return_value=model_result),
                mock.patch.object(compare_variants, "load_variant_candidates", return_value=candidates),
                mock.patch.object(
                    compare_variants,
                    "pick_best_variant_deterministically",
                    return_value=deterministic_result,
                ),
                mock.patch.object(compare_variants, "apply_winner", return_value=applied_path) as apply_mock,
                mock.patch.object(compare_variants, "comparison_log_path", return_value=log_path),
                mock.patch.object(
                    compare_variants.sys,
                    "argv",
                    ["compare_variants.py", "1", "--base-dir", str(base_dir)],
                ),
                redirect_stdout(io.StringIO()),
            ):
                compare_variants.main()

            apply_mock.assert_called_once_with(1, candidate_path, base_dir)
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["winner"], "variant_01")
            self.assertEqual(payload["winner_path"], str(candidate_path))
            self.assertEqual(
                payload["notes"],
                ["Model compare returned an unknown winner id; used deterministic fallback."],
            )


if __name__ == "__main__":
    unittest.main()
