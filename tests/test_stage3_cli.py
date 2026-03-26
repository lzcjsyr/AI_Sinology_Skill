from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runtime.stage3.cli import main


class Stage3CliTests(unittest.TestCase):
    def test_cli_targets_mode_reads_default_dotenv_for_model_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outputs_root = root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "2b_scholarship_map.yaml").write_text(
                'research_question: "明代祈雨与国家礼制"\n'
                "stage3_handoff:\n"
                "  target_themes:\n"
                '    - theme: "祈雨"\n',
                encoding="utf-8",
            )
            (root / ".env").write_text("VOLCENGINE_API_KEY=dotenv-key\n", encoding="utf-8")

            kanripo_root = root / "kanripo_repos"
            repo_dir = kanripo_root / "KR3j0160"
            repo_dir.mkdir(parents=True)
            (repo_dir / "KR3j0160_000.txt").write_text(
                "#+TITLE: 测试\n正文内容\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with (
                patch("runtime.stage3.cli.Path.cwd", return_value=root),
                patch(
                    "sys.argv",
                    [
                        "stage3-cli",
                        "--outputs",
                        str(outputs_root),
                        "--project",
                        "demo",
                        "--kanripo-root",
                        str(kanripo_root),
                        "--targets",
                        "KR3j0160",
                        "--no-write",
                        "--json",
                    ],
                ),
                patch("sys.stdout", stdout),
            ):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(Path(payload["workspace_root"]).resolve(), root.resolve())
        self.assertEqual(payload["theme_source"], "stage2_handoff")
        self.assertEqual(payload["analysis_targets"], ["KR3j0160"])
        self.assertEqual(payload["corpus_overview"]["text_char_count"], 4)
        self.assertTrue(all(slot["has_api_key"] for slot in payload["model_slots"]))


if __name__ == "__main__":
    unittest.main()
