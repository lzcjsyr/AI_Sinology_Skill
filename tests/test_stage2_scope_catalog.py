from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.stage2.catalog import list_available_scope_dirs, list_available_scope_options


class Stage2ScopeCatalogTests(unittest.TestCase):
    def test_list_scope_options_reads_catalog_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            catalog = root / "KR-Catalog" / "KR"
            catalog.mkdir(parents=True)
            (catalog / "KR1.txt").write_text(
                "* KR1 經部\n** [[file:KR1a.txt][易類]]\n** [[file:KR1b.txt][書類]]\n",
                encoding="utf-8",
            )
            (root / "KR1a0001").mkdir()
            (root / "KR1b0002").mkdir()

            options = list_available_scope_options(root)
            dirs = list_available_scope_dirs(root)

        self.assertEqual([option.code for option in options], ["KR1a", "KR1b"])
        self.assertEqual(options[0].display_label, "經部 [易類]")
        self.assertEqual(dirs, ["KR1a0001", "KR1b0002"])

    def test_list_scope_options_falls_back_to_directories_without_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "KR3j0160").mkdir()

            options = list_available_scope_options(root)

        self.assertEqual(options[0].code, "KR3j0160")
        self.assertEqual(options[0].section, "未分类")


if __name__ == "__main__":
    unittest.main()
