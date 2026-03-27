from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.stage2.env_check import api_smoke_test, static_checks


class Stage2EnvCheckTests(unittest.TestCase):
    def test_static_checks_reports_runtime_readiness_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            kanripo_root = root / "kanripo"
            (kanripo_root / "KR-Catalog" / "KR").mkdir(parents=True)
            (kanripo_root / "KR3j0160").mkdir()

            checks = static_checks(
                kanripo_root,
                env_file=None,
            )

        self.assertEqual(checks["kanripo_root"], str(kanripo_root.resolve()))
        self.assertTrue(checks["has_kanripo_root"])
        self.assertTrue(checks["has_kanripo_catalog"])
        self.assertEqual(checks["scope_dir_count"], 1)
        self.assertIn("llm1", checks["slots"])

    def test_api_smoke_test_returns_normalized_result(self) -> None:
        fake_response = {
            "choices": [
                {
                    "message": {
                        "content": '{"ok":true}',
                    }
                }
            ],
            "usage": {"total_tokens": 7},
        }
        fake_module = types.SimpleNamespace(completion=lambda **kwargs: fake_response)

        with patch("runtime.stage2.env_check.merged_env", return_value={"VOLCENGINE_API_KEY": "test-key"}):
            with patch.dict("sys.modules", {"litellm": fake_module}):
                result = api_smoke_test("llm1")

        self.assertEqual(result["slot"], "llm1")
        self.assertEqual(result["provider"], "volcengine")
        self.assertEqual(result["content"], '{"ok":true}')
        self.assertEqual(result["usage"], {"total_tokens": 7})


if __name__ == "__main__":
    unittest.main()
