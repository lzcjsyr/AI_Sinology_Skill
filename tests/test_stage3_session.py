from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.stage3.session import (
    ThemeItem,
    build_stage3_manifest,
    load_stage3_session,
    load_proposal_context,
    reconcile_retrieval_progress,
    resolve_scope_selection,
    save_stage3_session,
    stage3_session_path,
    stage3_workspace_manifest_path,
    update_retrieval_progress,
    update_stage3_session_checkpoint,
    write_stage3_manifest,
)


class Stage3SessionTests(unittest.TestCase):
    def test_load_proposal_context_reads_machine_front_matter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "1_research_proposal.md").write_text(
                "---\n"
                'idea: "明代祈雨与国家礼制"\n'
                "target_themes:\n"
                '  - theme: "祈雨"\n'
                '    description: "礼制中的祈雨实践"\n'
                '  - theme: "灾异"\n'
                "---\n"
                "\n"
                "正文\n",
                encoding="utf-8",
            )

            context = load_proposal_context(project_dir)

        assert context is not None
        self.assertEqual(context.idea, "明代祈雨与国家礼制")
        self.assertEqual(
            list(context.target_themes),
            [
                ThemeItem(theme="祈雨", description="礼制中的祈雨实践"),
                ThemeItem(theme="灾异", description=""),
            ],
        )

    def test_load_proposal_context_accepts_plain_theme_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            (project_dir / "1_research_proposal.md").write_text(
                "---\n"
                "target_themes:\n"
                "  - 祈雨\n"
                '  - "灾异"\n'
                "---\n",
                encoding="utf-8",
            )

            context = load_proposal_context(project_dir)

        assert context is not None
        self.assertEqual(
            [item.theme for item in context.target_themes],
            ["祈雨", "灾异"],
        )

    def test_resolve_scope_selection_validates_families_and_repo_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            kanripo_root = Path(tmpdir)
            catalog_root = kanripo_root / "KR-Catalog" / "KR"
            catalog_root.mkdir(parents=True)
            (catalog_root / "KR3.txt").write_text(
                "* KR3 子部\n"
                "** [[file:KR3j.txt][術數類]]\n",
                encoding="utf-8",
            )
            (kanripo_root / "KR3j0160").mkdir()

            result = resolve_scope_selection(
                kanripo_root,
                scope_families=["kr3j", "KR1a"],
                repo_dirs=["kr3j0160", "KR3j9999"],
            )

        self.assertEqual(result.scope_families, ("KR3j",))
        self.assertEqual(result.repo_dirs, ("KR3j0160",))
        self.assertEqual(result.missing_scope_families, ("KR1a",))
        self.assertEqual(result.missing_repo_dirs, ("KR3j9999",))

    def test_build_stage3_manifest_keeps_project_and_selection_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            outputs_root = workspace_root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)

            manifest = build_stage3_manifest(
                workspace_root=workspace_root,
                outputs_root=outputs_root,
                project_name="demo",
                kanripo_root=workspace_root / "data" / "kanripo_repos",
                theme_source="manual",
                target_themes=[ThemeItem(theme="祈雨")],
                scope_selection=resolve_scope_selection(
                    workspace_root / "missing",
                    scope_families=[],
                    repo_dirs=[],
                ),
                proposal_context=None,
                env_values={},
            )

        self.assertEqual(manifest["project_name"], "demo")
        self.assertEqual(manifest["theme_source"], "manual")
        self.assertEqual(manifest["target_themes"][0]["theme"], "祈雨")
        self.assertEqual(manifest["scope_families"], [])
        self.assertEqual(manifest["repo_dirs"], [])
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
                    "status": "themes_selected",
                    "project_name": "demo",
                    "repo_dirs": ["KR3j0160"],
                },
            )
            root_manifest = write_stage3_manifest(
                project_dir,
                {
                    "project_name": "demo",
                    "repo_dirs": ["KR3j0160"],
                },
            )
            loaded_session = load_stage3_session(project_dir)

            self.assertTrue(root_manifest.exists())
            self.assertTrue(stage3_workspace_manifest_path(project_dir).exists())
            self.assertTrue(stage3_session_path(project_dir).exists())
            self.assertEqual(loaded_session["status"], "themes_selected")
            self.assertEqual(loaded_session["repo_dirs"], ["KR3j0160"])
            self.assertEqual(loaded_session["analysis_targets"], ["KR3j0160"])
            self.assertEqual(loaded_session["retrieval_progress"]["pending_targets"], ["KR3j0160"])

    def test_reconcile_retrieval_progress_upgrades_legacy_payload(self) -> None:
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
                    "scope_families": ["KR3j"],
                    "repo_dirs": ["KR3j0160"],
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
