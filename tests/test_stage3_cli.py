from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from runtime.stage3.cli import _non_interactive_payload


class Stage3CliTests(unittest.TestCase):
    def test_non_interactive_payload_reads_default_dotenv_for_model_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            outputs_root = root / "outputs"
            project_dir = outputs_root / "demo"
            project_dir.mkdir(parents=True)
            (project_dir / "1_research_proposal.md").write_text(
                "---\n"
                'idea: "明代祈雨与国家礼制"\n'
                "target_themes:\n"
                '  - theme: "祈雨"\n'
                "---\n",
                encoding="utf-8",
            )
            (root / ".env").write_text("VOLCENGINE_API_KEY=dotenv-key\n", encoding="utf-8")

            kanripo_root = root / "kanripo_repos"
            catalog_root = kanripo_root / "KR-Catalog" / "KR"
            catalog_root.mkdir(parents=True)
            (catalog_root / "KR3.txt").write_text(
                "* KR3 子部\n"
                "** [[file:KR3j.txt][術數類]]\n",
                encoding="utf-8",
            )
            (kanripo_root / "KR3j0160").mkdir()

            args = SimpleNamespace(
                project="demo",
                kanripo_root=str(kanripo_root),
                themes=None,
                source="stage1",
                scopes=None,
                repos="KR3j0160",
                env_file=None,
            )

            with patch("runtime.stage3.cli.Path.cwd", return_value=root):
                payload = _non_interactive_payload(args, outputs_root)

        self.assertEqual(Path(payload["manifest"]["workspace_root"]).resolve(), root.resolve())
        self.assertTrue(all(slot["has_api_key"] for slot in payload["manifest"]["model_slots"]))


if __name__ == "__main__":
    unittest.main()
