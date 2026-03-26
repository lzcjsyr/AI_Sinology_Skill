from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.stage3.catalog import measure_corpus_overview, resolve_analysis_targets, split_target_tokens
from runtime.stage3.session import (
    ThemeItem,
    build_stage3_manifest,
    load_stage3_context,
    load_stage3_session,
    reconcile_retrieval_progress,
    save_stage3_session,
    stage3_session_path,
    stage3_workspace_manifest_path,
    update_retrieval_progress,
    update_stage3_session_checkpoint,
    write_stage3_manifest,
)


class Stage3SessionTests(unittest.TestCase):
    def test_load_stage3_context_reads_stage2_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "2b_scholarship_map.yaml").write_text(
                'research_question: "明代祈雨与国家礼制"\n'
                "stage3_handoff:\n"
                "  target_themes:\n"
                '    - theme: "祈雨"\n'
                '      description: "礼制中的祈雨实践"\n'
                '    - theme: "灾异"\n',
                encoding="utf-8",
            )
            (project_dir / "1_research_proposal.md").write_text("正文\n", encoding="utf-8")
            (project_dir / "1_journal_targeting.md").write_text("目标期刊：《中国语文》\n", encoding="utf-8")

            context = load_stage3_context(project_dir)

        assert context is not None
        self.assertEqual(context.research_question, "明代祈雨与国家礼制")
        self.assertEqual(
            list(context.target_themes),
            [
                ThemeItem(theme="祈雨", description="礼制中的祈雨实践"),
                ThemeItem(theme="灾异", description=""),
            ],
        )

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
        self.assertEqual(overview.targets[0].text_char_count, 16)

    def test_build_stage3_manifest_keeps_project_and_analysis_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            outputs_root = workspace_root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "2b_scholarship_map.yaml").write_text(
                'research_question: "明代祈雨与国家礼制"\n'
                "stage3_handoff:\n"
                "  target_themes:\n"
                '    - theme: "祈雨"\n',
                encoding="utf-8",
            )
            stage3_context = load_stage3_context(project_dir)

            manifest = build_stage3_manifest(
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
                stage3_context=stage3_context,
                env_values={},
            )

        assert stage3_context is not None
        self.assertEqual(manifest["project_name"], "demo")
        self.assertEqual(manifest["theme_source"], "stage2_handoff")
        self.assertEqual(manifest["target_themes"][0]["theme"], "祈雨")
        self.assertEqual(manifest["research_question"], "明代祈雨与国家礼制")
        self.assertEqual(manifest["analysis_targets"], ["KR1a", "KR3j0160"])
        self.assertEqual(manifest["corpus_overview"]["text_char_count"], 12345)
        self.assertEqual(len(manifest["model_slots"]), 3)
        self.assertTrue(manifest["stage3_session_path"].endswith("/_stage3/session.json"))
        self.assertTrue(manifest["stage3_workspace_manifest_path"].endswith("/_stage3/manifest.json"))

    def test_stage3_workspace_persists_session_and_manifest_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "demo"
            project_dir.mkdir()

            save_stage3_session(
                project_dir,
                {
                    "status": "configured",
                    "project_name": "demo",
                    "analysis_targets": ["KR3j0160"],
                },
            )
            root_manifest = write_stage3_manifest(
                project_dir,
                {
                    "project_name": "demo",
                    "analysis_targets": ["KR3j0160"],
                },
            )
            loaded_session = load_stage3_session(project_dir)

            self.assertTrue(root_manifest.exists())
            self.assertTrue(stage3_workspace_manifest_path(project_dir).exists())
            self.assertTrue(stage3_session_path(project_dir).exists())
            self.assertEqual(loaded_session["status"], "configured")
            self.assertEqual(loaded_session["analysis_targets"], ["KR3j0160"])
            self.assertEqual(loaded_session["retrieval_progress"]["pending_targets"], ["KR3j0160"])

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

    def test_update_stage3_session_checkpoint_persists_resume_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "demo"
            project_dir.mkdir()

            save_stage3_session(
                project_dir,
                {
                    "status": "configured",
                    "project_name": "demo",
                    "analysis_targets": ["KR3j", "KR3j0160"],
                },
            )

            update_stage3_session_checkpoint(project_dir, action="start", target="KR3j0160")
            update_stage3_session_checkpoint(
                project_dir,
                action="checkpoint",
                cursor="offset=120",
                piece_id="pb:KR3j0160_010-2b",
                completed_piece_delta=5,
                note="已检索到第 120 条",
            )

            loaded_session = load_stage3_session(project_dir)

        self.assertEqual(loaded_session["analysis_targets"], ["KR3j", "KR3j0160"])
        self.assertEqual(loaded_session["retrieval_progress"]["current_target"], "KR3j0160")
        self.assertEqual(loaded_session["retrieval_progress"]["current_cursor"], "offset=120")
        self.assertEqual(loaded_session["retrieval_progress"]["last_piece_id"], "pb:KR3j0160_010-2b")
        self.assertEqual(loaded_session["retrieval_progress"]["completed_piece_count"], 5)
        self.assertEqual(loaded_session["retrieval_progress"]["notes"], "已检索到第 120 条")


if __name__ == "__main__":
    unittest.main()
