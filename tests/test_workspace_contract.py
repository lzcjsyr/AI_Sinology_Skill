from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import sys
import tempfile
import unittest
from pathlib import Path


def _load_workspace_contract_module():
    script_path = (
        Path(__file__).resolve().parent.parent
        / ".agent"
        / "skills"
        / "ai-sinology"
        / "scripts"
        / "workspace_contract.py"
    )
    spec = spec_from_file_location("test_ai_sinology_workspace_contract", script_path)
    assert spec is not None and spec.loader is not None
    sys.path.insert(0, str(script_path.parent))
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if sys.path and sys.path[0] == str(script_path.parent):
            sys.path.pop(0)
    return module


_MODULE = _load_workspace_contract_module()
inspect_project = _MODULE.inspect_project
list_projects = _MODULE.list_projects


class WorkspaceContractTests(unittest.TestCase):
    def test_inspect_project_advances_to_stage_three_after_primary_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = Path(tmpdir)
            project = outputs / "demo"
            project.mkdir()
            (project / "1_journal_targeting.md").write_text("ok\n", encoding="utf-8")
            (project / "1_research_proposal.md").write_text("ok\n", encoding="utf-8")
            (project / "2_scholarship_map.yaml").write_text("research_question: \"x\"\n", encoding="utf-8")

            status = inspect_project(outputs, "demo")

        self.assertEqual(status.highest_completed_stage, 2)
        self.assertEqual(status.next_stage, 3)
        self.assertFalse(status.has_progress_file)
        self.assertEqual(status.stages[2].status, "missing")

    def test_stage_six_accepts_markdown_manuscript(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = Path(tmpdir)
            project = outputs / "demo"
            project.mkdir()
            for name in (
                "project_progress.yaml",
                "1_journal_targeting.md",
                "1_research_proposal.md",
                "2_scholarship_map.yaml",
                "3_final_corpus.yaml",
                "4_outline_matrix.yaml",
                "4_argument_audit.md",
                "5_first_draft.md",
                "6_final_manuscript.md",
                "6_abstract_keywords.md",
                "6_title_options.md",
                "6_anonymous_submission_checklist.md",
                "6_claim_boundary.md",
            ):
                (project / name).write_text("ok\n", encoding="utf-8")

            status = inspect_project(outputs, "demo")

        self.assertEqual(status.highest_completed_stage, 6)
        self.assertIsNone(status.next_stage)
        self.assertTrue(status.has_progress_file)
        self.assertEqual(status.stages[5].status, "complete")

    def test_list_projects_ignores_hidden_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = Path(tmpdir)
            (outputs / "a-project").mkdir()
            (outputs / ".hidden").mkdir()

            projects = list_projects(outputs)

        self.assertEqual(projects, ["a-project"])


if __name__ == "__main__":
    unittest.main()
