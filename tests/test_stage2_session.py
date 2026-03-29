from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.stage2.catalog import measure_corpus_overview, resolve_analysis_targets, split_target_tokens
from runtime.stage2.session import (
    ThemeItem,
    build_stage2_timing_estimate,
    build_stage2_manifest,
    load_stage2_context,
    load_stage2_manifest,
    manifest_path,
    reconcile_retrieval_progress,
    update_retrieval_progress,
    update_stage2_manifest_checkpoint,
    write_stage2_manifest,
)


class Stage2SessionTests(unittest.TestCase):
    def test_build_stage2_timing_estimate_uses_targeted_screening_ratios_without_arbitration(self) -> None:
        timing = build_stage2_timing_estimate(
            corpus_overview={
                "targets": [
                    {
                        "token": "KR1a",
                        "batch_count": 1000,
                        "fragment_count": 2400,
                    }
                ]
            },
            theme_count=7,
            model_slots=[
                {"slot": "llm1", "max_concurrency": 10},
                {"slot": "llm2", "max_concurrency": 10},
                {"slot": "llm3", "max_concurrency": 10},
            ],
            request_seconds=20,
        )

        self.assertEqual(timing["targeted_batch_count_lower"], 10)
        self.assertEqual(timing["targeted_batch_count_upper"], 50)
        self.assertEqual(timing["lower_bound_seconds"], 4040)
        self.assertEqual(timing["upper_bound_seconds"], 4200)

    def test_load_stage2_context_reads_stage1_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "1_research_proposal.md").write_text(
                "---\nidea: 明代祈雨\nsettled_research_direction: 明代祈雨与国家礼制\n---\n正文\n",
                encoding="utf-8",
            )
            (project_dir / "1_journal_targeting.md").write_text(
                "---\nidea: 明代祈雨\nsettled_research_direction: 明代祈雨与国家礼制\n---\n目标期刊：《中国语文》\n",
                encoding="utf-8",
            )

            context = load_stage2_context(project_dir)

        assert context is not None
        self.assertEqual(context.research_question, "明代祈雨与国家礼制")
        self.assertEqual(context.retrieval_theme_source, "stage1_inference")
        self.assertEqual(
            list(context.target_themes),
            [
                ThemeItem(theme="明代祈雨与国家礼制", description="基于阶段一初步想法与研究方向提炼的初始主题。"),
                ThemeItem(theme="明代祈雨", description="基于阶段一初步想法与研究方向提炼的初始主题。"),
            ],
        )
        self.assertEqual(context.retrieval_themes, context.target_themes)

    def test_load_stage2_context_prefers_explicit_stage2_retrieval_themes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "1_research_proposal.md").write_text(
                "---\n"
                "idea: 明代祈雨\n"
                "settled_research_direction: 明代祈雨与国家礼制\n"
                "stage2_retrieval_themes:\n"
                "  - 明代祈雨礼制\n"
                "  - 中央与地方祈雨文书\n"
                "---\n"
                "正文\n",
                encoding="utf-8",
            )
            (project_dir / "1_journal_targeting.md").write_text(
                "---\n"
                "retrieval_themes:\n"
                "  - 国家礼制与期刊问题意识\n"
                "---\n"
                "目标期刊：《中国语文》\n",
                encoding="utf-8",
            )

            context = load_stage2_context(project_dir)

        assert context is not None
        self.assertEqual(context.retrieval_theme_source, "stage1_frontmatter")
        self.assertEqual(
            list(context.retrieval_themes),
            [
                ThemeItem(theme="明代祈雨礼制", description="阶段一明确给出的阶段二检索主题。"),
                ThemeItem(theme="中央与地方祈雨文书", description="阶段一明确给出的阶段二检索主题。"),
                ThemeItem(theme="国家礼制与期刊问题意识", description="阶段一明确给出的阶段二检索主题。"),
            ],
        )
        self.assertEqual(context.retrieval_themes, context.target_themes)

    def test_split_target_tokens_accepts_commas_and_spaces(self) -> None:
        self.assertEqual(
            split_target_tokens(" KR1a，KR1a0001  KR3j0160 "),
            ["KR1a", "KR1a0001", "KR3j0160"],
        )

    def test_resolve_analysis_targets_reports_invalid_and_overlap_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            kanripo_root = Path(tmpdir)
            (kanripo_root / "KR1a0001").mkdir(parents=True)
            (kanripo_root / "KR1a0002").mkdir()
            (kanripo_root / "KR3j0160").mkdir()

            selection = resolve_analysis_targets(
                kanripo_root,
                raw_input="KR1a KR1a0001 KR3j9999 bad-token",
            )

        self.assertEqual(selection.analysis_targets, ("KR1a", "KR1a0001"))
        self.assertEqual(
            [(item.token, item.detail) for item in selection.issues],
            [
                ("KR3j9999", "该目录不存在。"),
                ("bad-token", "格式不合法；仅支持 KR1a 或 KR1a0001。"),
                ("KR1a0001", "范围重复，已经被 KR1a 覆盖。"),
            ],
        )

    def test_measure_corpus_overview_counts_plain_text_chars(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            kanripo_root = Path(tmpdir)
            repo_dir = kanripo_root / "KR1a0001"
            repo_dir.mkdir(parents=True)
            (repo_dir / "KR1a0001_000.txt").write_text(
                "#+TITLE: 测试\n"
                "<pb:KR1a0001_000-1a>¶\n"
                "天地玄黄 宇宙洪荒¶\n"
                "<pb:KR1a0001_000-1b>¶\n"
                "日月盈昃 辰宿列张¶\n",
                encoding="utf-8",
            )

            selection = resolve_analysis_targets(kanripo_root, raw_input="KR1a0001")
            overview = measure_corpus_overview(kanripo_root, selection)

        self.assertTrue(selection.is_valid)
        self.assertEqual(overview.repo_dir_count, 1)
        self.assertEqual(overview.text_file_count, 1)
        self.assertEqual(overview.text_char_count, 16)
        self.assertEqual(overview.fragment_count, 2)
        self.assertEqual(overview.batch_count, 1)
        self.assertEqual(overview.targets[0].text_char_count, 16)
        self.assertEqual(overview.targets[0].fragment_count, 2)
        self.assertEqual(overview.targets[0].batch_count, 1)

    def test_build_stage2_manifest_keeps_project_and_analysis_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            outputs_root = workspace_root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "1_research_proposal.md").write_text(
                "---\nidea: 明代祈雨\nsettled_research_direction: 明代祈雨与国家礼制\n---\n正文\n",
                encoding="utf-8",
            )
            (project_dir / "1_journal_targeting.md").write_text("目标期刊：《中国语文》\n", encoding="utf-8")
            stage2_context = load_stage2_context(project_dir)

            manifest = build_stage2_manifest(
                workspace_root=workspace_root,
                outputs_root=outputs_root,
                project_name="demo",
                kanripo_root=workspace_root / "data" / "kanripo_repos",
                analysis_targets=["KR1a", "KR3j0160"],
                corpus_overview={
                    "repo_dir_count": 2,
                    "text_file_count": 10,
                    "text_char_count": 12345,
                    "targets": [],
                },
                stage2_context=stage2_context,
                env_values={},
            )

        assert stage2_context is not None
        self.assertEqual(manifest["project_name"], "demo")
        self.assertEqual(manifest["theme_source"], "stage1_proposal")
        self.assertEqual(manifest["retrieval_theme_source"], "stage1_inference")
        self.assertEqual(manifest["retrieval_themes"][0]["theme"], "明代祈雨与国家礼制")
        self.assertEqual(manifest["target_themes"][0]["theme"], "明代祈雨与国家礼制")
        self.assertEqual(manifest["research_question"], "明代祈雨与国家礼制")
        self.assertEqual(manifest["analysis_targets"], ["KR1a", "KR3j0160"])
        self.assertEqual(manifest["corpus_overview"]["text_char_count"], 12345)
        self.assertEqual(len(manifest["model_slots"]), 3)
        self.assertEqual(manifest["timing_estimate"]["theme_count"], 2)
        self.assertGreaterEqual(manifest["timing_estimate"]["upper_bound_seconds"], manifest["timing_estimate"]["lower_bound_seconds"])
        self.assertTrue(manifest["stage2_manifest_path"].endswith("/_stage2/2_stage2_manifest.json"))

    def test_build_stage2_manifest_does_not_leak_process_env_when_env_values_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            outputs_root = workspace_root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "1_research_proposal.md").write_text(
                "---\nidea: 明代祈雨\nsettled_research_direction: 明代祈雨与国家礼制\n---\n正文\n",
                encoding="utf-8",
            )
            (project_dir / "1_journal_targeting.md").write_text("目标期刊：《中国语文》\n", encoding="utf-8")
            stage2_context = load_stage2_context(project_dir)

            with patch.dict("os.environ", {"VOLCENGINE_API_KEY": "from-os"}, clear=False):
                manifest = build_stage2_manifest(
                    workspace_root=workspace_root,
                    outputs_root=outputs_root,
                    project_name="demo",
                    kanripo_root=workspace_root / "data" / "kanripo_repos",
                    analysis_targets=["KR1a"],
                    corpus_overview={
                        "repo_dir_count": 1,
                        "text_file_count": 1,
                        "text_char_count": 100,
                        "targets": [],
                    },
                    stage2_context=stage2_context,
                    env_values={},
                )

        assert stage2_context is not None
        self.assertTrue(all(not slot["has_api_key"] for slot in manifest["model_slots"]))

    def test_stage2_workspace_persists_manifest_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "demo"
            project_dir.mkdir()

            root_manifest = write_stage2_manifest(
                project_dir,
                {
                    "project_name": "demo",
                    "status": "configured",
                    "analysis_targets": ["KR3j0160"],
                },
            )
            loaded_manifest = load_stage2_manifest(project_dir)

            self.assertTrue(root_manifest.exists())
            self.assertEqual(root_manifest, manifest_path(project_dir))
            self.assertEqual(loaded_manifest["status"], "configured")
            self.assertEqual(loaded_manifest["analysis_targets"], ["KR3j0160"])
            self.assertEqual(loaded_manifest["retrieval_progress"]["pending_targets"], ["KR3j0160"])
            self.assertEqual(loaded_manifest["project_name"], "demo")

    def test_reconcile_retrieval_progress_tracks_targets(self) -> None:
        progress = reconcile_retrieval_progress(
            ["KR3j", "KR3j0160"],
            progress={
                "completed_targets": ["kr3j"],
                "current_target": "KR3j0160",
                "current_cursor": "offset=200",
                "last_piece_id": "pb:KR3j0160_001-1a",
                "completed_piece_count": 12,
            },
        )

        self.assertEqual(progress["status"], "running")
        self.assertEqual(progress["completed_targets"], ["KR3j"])
        self.assertEqual(progress["current_target"], "KR3j0160")
        self.assertEqual(progress["pending_targets"], [])
        self.assertEqual(progress["completed_piece_count"], 12)

    def test_update_retrieval_progress_tracks_checkpoint_and_completion(self) -> None:
        analysis_targets = ["KR3j", "KR3j0160"]

        progress = update_retrieval_progress(
            analysis_targets,
            action="start",
            target="kr3j",
        )
        self.assertEqual(progress["status"], "running")
        self.assertEqual(progress["current_target"], "KR3j")
        self.assertEqual(progress["run_count"], 1)

        progress = update_retrieval_progress(
            analysis_targets,
            progress=progress,
            action="checkpoint",
            cursor="offset=50",
            piece_id="pb:KR3j0001_001-1a",
            completed_piece_delta=3,
        )
        self.assertEqual(progress["current_cursor"], "offset=50")
        self.assertEqual(progress["last_piece_id"], "pb:KR3j0001_001-1a")
        self.assertEqual(progress["completed_piece_count"], 3)

        progress = update_retrieval_progress(
            analysis_targets,
            progress=progress,
            action="complete",
            target="KR3j",
        )
        self.assertEqual(progress["status"], "paused")
        self.assertEqual(progress["completed_targets"], ["KR3j"])
        self.assertEqual(progress["pending_targets"], ["KR3j0160"])

    def test_update_stage2_manifest_checkpoint_persists_resume_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "demo"
            project_dir.mkdir()

            write_stage2_manifest(
                project_dir,
                {
                    "status": "configured",
                    "analysis_targets": ["KR3j", "KR3j0160"],
                },
            )

            update_stage2_manifest_checkpoint(project_dir, action="start", target="KR3j0160")
            update_stage2_manifest_checkpoint(
                project_dir,
                action="checkpoint",
                cursor="offset=120",
                piece_id="pb:KR3j0160_010-2b",
                completed_piece_delta=5,
                note="已检索到第 120 条",
            )

            loaded_manifest = load_stage2_manifest(project_dir)

        self.assertEqual(loaded_manifest["analysis_targets"], ["KR3j", "KR3j0160"])
        self.assertEqual(loaded_manifest["retrieval_progress"]["current_target"], "KR3j0160")
        self.assertEqual(loaded_manifest["retrieval_progress"]["current_cursor"], "offset=120")
        self.assertEqual(loaded_manifest["retrieval_progress"]["last_piece_id"], "pb:KR3j0160_010-2b")
        self.assertEqual(loaded_manifest["retrieval_progress"]["completed_piece_count"], 5)
        self.assertEqual(loaded_manifest["retrieval_progress"]["notes"], "已检索到第 120 条")


if __name__ == "__main__":
    unittest.main()
