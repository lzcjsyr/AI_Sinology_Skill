from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from runtime.stage2.cli import main


class Stage2CliTests(unittest.TestCase):
    def test_cli_requires_both_stage1_files_before_stage2(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outputs_root = root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "1_research_proposal.md").write_text(
                "---\nidea: 明代祈雨\nsettled_research_direction: 明代祈雨与国家礼制\n---\n正文\n",
                encoding="utf-8",
            )

            kanripo_root = root / "kanripo_repos"
            kanripo_root.mkdir()

            with (
                patch(
                    "sys.argv",
                    [
                        "stage2-cli",
                        "--outputs",
                        str(outputs_root),
                        "--project",
                        "demo",
                        "--kanripo-root",
                        str(kanripo_root),
                        "--targets",
                        "KR3j0160",
                        "--json",
                    ],
                ),
                self.assertRaises(SystemExit) as ctx,
            ):
                main()

        self.assertIn("阶段一尚未完成", str(ctx.exception))
        self.assertIn("1_journal_targeting.md", str(ctx.exception))

    def test_cli_targets_mode_reads_default_dotenv_for_model_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outputs_root = root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "1_research_proposal.md").write_text(
                "---\n"
                "idea: 明代祈雨\n"
                "settled_research_direction: 明代祈雨与国家礼制\n"
                "stage2_retrieval_themes:\n"
                "  - 明代祈雨礼制\n"
                "  - 祈雨奏疏与诏令\n"
                "---\n"
                "正文\n",
                encoding="utf-8",
            )
            (project_dir / "1_journal_targeting.md").write_text(
                "---\ntarget_journal: 中国语文\n---\n目标期刊：《中国语文》\n",
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
                patch("runtime.stage2.cli.Path.cwd", return_value=root),
                patch(
                    "sys.argv",
                    [
                        "stage2-cli",
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
        self.assertEqual(payload["theme_source"], "stage1_proposal")
        self.assertEqual(payload["retrieval_theme_source"], "stage1_frontmatter")
        self.assertEqual(
            [item["theme"] for item in payload["retrieval_themes"]],
            ["明代祈雨礼制", "祈雨奏疏与诏令"],
        )
        self.assertEqual(payload["analysis_targets"], ["KR3j0160"])
        self.assertEqual(payload["corpus_overview"]["text_char_count"], 4)
        self.assertTrue(all(slot["has_api_key"] for slot in payload["model_slots"]))


if __name__ == "__main__":
    unittest.main()
