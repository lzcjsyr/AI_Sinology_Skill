from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.workspace_contract import inspect_project, list_projects


class WorkspaceContractTests(unittest.TestCase):
    def test_inspect_project_reports_next_stage_from_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = Path(tmpdir)
            project = outputs / "demo"
            project.mkdir()
            (project / "1_research_proposal.md").write_text("ok\n", encoding="utf-8")
            (project / "2_final_corpus.yaml").write_text("piece_count: 0\nrecords: []\n", encoding="utf-8")

            status = inspect_project(outputs, "demo")

        self.assertEqual(status.highest_completed_stage, 2)
        self.assertEqual(status.next_stage, 3)
        self.assertFalse(status.has_progress_file)
        self.assertEqual(status.stages[2].status, "missing")

    def test_stage_five_accepts_markdown_manuscript(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = Path(tmpdir)
            project = outputs / "demo"
            project.mkdir()
            for name in (
                "project_progress.yaml",
                "1_research_proposal.md",
                "2_final_corpus.yaml",
                "3_outline_matrix.yaml",
                "4_first_draft.md",
                "5_final_manuscript.md",
            ):
                (project / name).write_text("ok\n", encoding="utf-8")

            status = inspect_project(outputs, "demo")

        self.assertEqual(status.highest_completed_stage, 5)
        self.assertIsNone(status.next_stage)
        self.assertTrue(status.has_progress_file)
        self.assertEqual(status.stages[4].status, "complete")

    def test_list_projects_ignores_hidden_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = Path(tmpdir)
            (outputs / "a-project").mkdir()
            (outputs / ".hidden").mkdir()

            projects = list_projects(outputs)

        self.assertEqual(projects, ["a-project"])


if __name__ == "__main__":
    unittest.main()
