from __future__ import annotations

import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock
from unittest.mock import patch

from runtime.stage2.cli import WORKSPACE_ROOT, _resolve_runtime_path, main
from runtime.stage2.runner import Fragment, _build_batches, run_stage2_pipeline


class Stage2CliTests(unittest.TestCase):
    @staticmethod
    def _fake_chat_json(self, *, messages, max_tokens=4000, temperature=0.0):  # noqa: ANN001
        system_text = messages[0]["content"]
        user_text = messages[1]["content"]
        if "第三方学术仲裁助手" in system_text:
            return {"is_relevant": False, "reason": "以免误收，判为不保留"}, {"total_tokens": 10}

        piece_ids = re.findall(r"^###\s+(\S+)$", user_text, re.MULTILINE)
        theme_names = [item.strip() for item in re.findall(r"^T\d+:\s+([^\n|]+)", user_text, re.MULTILINE)]
        results = []
        for piece_id in piece_ids:
            matches = []
            for theme in theme_names:
                if self.slot == "llm1":
                    is_relevant = piece_id.endswith("1a")
                    reason = "出现冬雷题咏线索" if is_relevant else "仅一般叙写"
                elif self.slot == "llm2":
                    is_relevant = True
                    reason = "可能关联冬雷主题"
                else:
                    is_relevant = False
                    reason = "不应进入最终语料"
                matches.append(
                    {
                        "theme": theme,
                        "is_relevant": is_relevant,
                        "reason": reason,
                    }
                )
            results.append({"piece_id": piece_id, "matches": matches})
        return {"results": results}, {"total_tokens": 20}

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

    def test_build_batches_respects_300_char_limit(self) -> None:
        fragments = [
            Fragment(
                piece_id="pb:1",
                source_file="测试文献",
                original_text="甲" * 180,
                repo_dir="KR4c0001",
                text_file="KR4c0001_000.txt",
            ),
            Fragment(
                piece_id="pb:2",
                source_file="测试文献",
                original_text="乙" * 140,
                repo_dir="KR4c0001",
                text_file="KR4c0001_000.txt",
            ),
        ]

        batches = _build_batches(fragments)

        self.assertEqual(len(batches), 2)
        self.assertEqual(list(batches[0].piece_ids), ["pb:1"])
        self.assertEqual(list(batches[1].piece_ids), ["pb:2"])

    def test_cli_default_runtime_paths_resolve_from_workspace_root(self) -> None:
        self.assertEqual(
            _resolve_runtime_path("outputs", default_relative="outputs"),
            (WORKSPACE_ROOT / "outputs").resolve(),
        )
        self.assertEqual(
            _resolve_runtime_path("data/kanripo_repos", default_relative="data/kanripo_repos"),
            (WORKSPACE_ROOT / "data" / "kanripo_repos").resolve(),
        )

    def test_cli_supports_direct_script_execution(self) -> None:
        script_path = WORKSPACE_ROOT / "runtime" / "stage2" / "cli.py"
        result = subprocess.run(
            [sys.executable, str(script_path), "--help"],
            cwd=script_path.parent,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("确认阶段二调研范围", result.stdout)

    def test_cli_setup_only_prevents_default_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outputs_root = root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "1_research_proposal.md").write_text(
                "---\nidea: 冬雷诗题咏\nsettled_research_direction: 冬雷意象的诗学转化\nstage2_retrieval_themes:\n  - 唐宋冬雷题咏\n---\n正文\n",
                encoding="utf-8",
            )
            (project_dir / "1_journal_targeting.md").write_text("目标期刊：《中国语文》\n", encoding="utf-8")
            kanripo_root = root / "kanripo_repos"
            repo_dir = kanripo_root / "KR4c0001"
            repo_dir.mkdir(parents=True)
            (repo_dir / "KR4c0001_000.txt").write_text("#+TITLE: 测试\n正文内容\n", encoding="utf-8")

            with (
                patch("runtime.stage2.runner.OpenAICompatClient.chat_json", side_effect=AssertionError("should not run")),
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
                        "KR4c0001",
                        "--setup-only",
                    ],
                ),
            ):
                exit_code = main()

        self.assertEqual(exit_code, 0)
        self.assertFalse((project_dir / "2_primary_corpus.yaml").exists())

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
        self.assertEqual(Path(payload["workspace_root"]).resolve(), WORKSPACE_ROOT.resolve())
        self.assertEqual(payload["theme_source"], "stage1_proposal")
        self.assertEqual(payload["retrieval_theme_source"], "stage1_frontmatter")
        self.assertEqual(
            [item["theme"] for item in payload["retrieval_themes"]],
            ["明代祈雨礼制", "祈雨奏疏与诏令"],
        )
        self.assertEqual(payload["analysis_targets"], ["KR3j0160"])
        self.assertEqual(payload["corpus_overview"]["text_char_count"], 4)
        self.assertTrue(all(slot["has_api_key"] for slot in payload["model_slots"]))

    def test_cli_run_executes_dual_screening_and_arbitration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outputs_root = root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "1_research_proposal.md").write_text(
                "---\n"
                "idea: 冬雷诗题咏\n"
                "settled_research_direction: 冬雷意象的诗学转化\n"
                "stage2_retrieval_themes:\n"
                "  - 唐宋冬雷题咏\n"
                "---\n"
                "正文\n",
                encoding="utf-8",
            )
            (project_dir / "1_journal_targeting.md").write_text(
                "---\ntarget_journal: 中国语文\n---\n目标期刊：《中国语文》\n",
                encoding="utf-8",
            )
            (root / ".env").write_text("VOLCENGINE_API_KEY=test-key\n", encoding="utf-8")

            kanripo_root = root / "kanripo_repos"
            repo_dir = kanripo_root / "KR4c0001"
            repo_dir.mkdir(parents=True)
            (repo_dir / "KR4c0001_000.txt").write_text(
                "#+TITLE: 测试唐诗\n"
                "<pb:KR4c0001_000-1a>\n"
                "冬雷忽作，诗人惊而有咏。\n"
                "<pb:KR4c0001_000-1b>\n"
                "春风池馆，闲写花光。\n",
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with (
                patch("runtime.stage2.runner.OpenAICompatClient.chat_json", new=self._fake_chat_json),
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
                        "KR4c0001",
                    ],
                ),
                patch("sys.stdout", stdout),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            final_corpus = (project_dir / "2_primary_corpus.yaml").read_text(encoding="utf-8")
            self.assertIn("KR4c0001_000-1a", final_corpus)
            self.assertNotIn("KR4c0001_000-1b", final_corpus)
            self.assertTrue((project_dir / "_stage2" / "targets" / "KR4c0001" / "fragments.jsonl").exists())
            self.assertTrue((project_dir / "_stage2" / "targets" / "KR4c0001" / "llm1_screening.jsonl").exists())
            self.assertTrue((project_dir / "_stage2" / "targets" / "KR4c0001" / "llm2_screening.jsonl").exists())
            disputes_text = (project_dir / "_stage2" / "targets" / "KR4c0001" / "disputes.jsonl").read_text(encoding="utf-8")
            self.assertIn("KR4c0001_000-1b::唐宋冬雷题咏", disputes_text)
            self.assertTrue((project_dir / "_stage2" / "targets" / "KR4c0001" / "llm3_arbitration.jsonl").exists())
            session_text = (project_dir / "_stage2" / "session.json").read_text(encoding="utf-8")
            self.assertIn('"status": "completed"', session_text)
            self.assertIn('"current_target": ""', session_text)
            self.assertIn("[stage2] 开始执行", stdout.getvalue())
            self.assertIn("[stage2] KR4c0001 llm1 进度", stdout.getvalue())
            self.assertIn("[stage2] 完成目标 KR4c0001", stdout.getvalue())
            self.assertIn("阶段二执行完成", stdout.getvalue())

    def test_run_stage2_pipeline_reuses_completed_target_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outputs_root = root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "1_research_proposal.md").write_text(
                "---\nidea: 冬雷诗题咏\nsettled_research_direction: 冬雷意象的诗学转化\nstage2_retrieval_themes:\n  - 唐宋冬雷题咏\n---\n正文\n",
                encoding="utf-8",
            )
            (project_dir / "1_journal_targeting.md").write_text("目标期刊：《中国语文》\n", encoding="utf-8")
            (root / ".env").write_text("VOLCENGINE_API_KEY=test-key\n", encoding="utf-8")

            kanripo_root = root / "kanripo_repos"
            repo_dir = kanripo_root / "KR4c0001"
            repo_dir.mkdir(parents=True)
            (repo_dir / "KR4c0001_000.txt").write_text(
                "#+TITLE: 测试唐诗\n<pb:KR4c0001_000-1a>\n冬雷忽作，诗人惊而有咏。\n",
                encoding="utf-8",
            )

            with (
                patch("runtime.stage2.runner.OpenAICompatClient.chat_json", new=self._fake_chat_json),
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
                        "KR4c0001",
                        "--setup-only",
                    ],
                ),
            ):
                self.assertEqual(main(), 0)
                first_summary = run_stage2_pipeline(project_dir=project_dir, dotenv_path=root / ".env")

            with patch("runtime.stage2.runner.OpenAICompatClient.chat_json", side_effect=AssertionError("should not call model again")):
                summary = run_stage2_pipeline(project_dir=project_dir, dotenv_path=root / ".env")

            self.assertEqual(first_summary["piece_count"], 1)
            self.assertEqual(summary["piece_count"], 1)
            self.assertEqual(summary["record_count"], 1)

    def test_run_stage2_pipeline_resumes_from_partial_target_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outputs_root = root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "1_research_proposal.md").write_text(
                "---\nidea: 冬雷诗题咏\nsettled_research_direction: 冬雷意象的诗学转化\nstage2_retrieval_themes:\n  - 唐宋冬雷题咏\n---\n正文\n",
                encoding="utf-8",
            )
            (project_dir / "1_journal_targeting.md").write_text("目标期刊：《中国语文》\n", encoding="utf-8")
            (root / ".env").write_text("VOLCENGINE_API_KEY=test-key\n", encoding="utf-8")

            kanripo_root = root / "kanripo_repos"
            repo_dir = kanripo_root / "KR4c0001"
            repo_dir.mkdir(parents=True)
            (repo_dir / "KR4c0001_000.txt").write_text(
                "#+TITLE: 测试唐诗\n<pb:KR4c0001_000-1a>\n冬雷忽作，诗人惊而有咏。\n",
                encoding="utf-8",
            )

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
                        "KR4c0001",
                        "--setup-only",
                    ],
                ),
            ):
                self.assertEqual(main(), 0)

            def flaky_chat_json(self, *, messages, max_tokens=4000, temperature=0.0):  # noqa: ANN001
                if self.slot == "llm2":
                    raise RuntimeError("simulated interruption")
                return Stage2CliTests._fake_chat_json(self, messages=messages, max_tokens=max_tokens, temperature=temperature)

            with patch("runtime.stage2.runner.OpenAICompatClient.chat_json", new=flaky_chat_json):
                with self.assertRaises(RuntimeError):
                    run_stage2_pipeline(project_dir=project_dir, dotenv_path=root / ".env")

            run_state_path = project_dir / "_stage2" / "targets" / "KR4c0001" / "run_state.json"
            failed_state = json.loads(run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(failed_state["phase"], "failed")
            self.assertEqual(failed_state["llm1_completed_batches"], 1)
            self.assertIn("simulated interruption", failed_state["last_error"])

            stdout = io.StringIO()
            with (
                patch("runtime.stage2.runner.OpenAICompatClient.chat_json", new=self._fake_chat_json),
                patch("sys.stdout", stdout),
            ):
                summary = run_stage2_pipeline(
                    project_dir=project_dir,
                    dotenv_path=root / ".env",
                    progress_callback=Mock(side_effect=lambda event: print(event["event"], file=stdout)),
                )

            completed_state = json.loads(run_state_path.read_text(encoding="utf-8"))
            self.assertEqual(completed_state["phase"], "completed")
            self.assertTrue(completed_state["is_completed"])
            self.assertEqual(summary["piece_count"], 1)
            self.assertIn("target_resumed", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
