from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.stage2.session import (
    ThemeItem,
    build_stage2_manifest,
    load_proposal_context,
    resolve_scope_selection,
)


class Stage2SessionTests(unittest.TestCase):
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

    def test_build_stage2_manifest_keeps_project_and_selection_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_root = Path(tmpdir)
            outputs_root = workspace_root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)

            manifest = build_stage2_manifest(
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


if __name__ == "__main__":
    unittest.main()
