from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from runtime.stage2.io_utils import load_skill_script

_MODULE = load_skill_script("test_ai_sinology_init_project", "init_project.py")


class InitProjectTests(unittest.TestCase):
    def test_init_project_creates_stage2_and_stage3b_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outputs = Path(tmpdir) / "outputs"
            argv = [
                "init_project.py",
                "demo",
                "--outputs",
                str(outputs),
            ]
            previous = sys.argv
            try:
                sys.argv = argv
                exit_code = _MODULE.main()
            finally:
                sys.argv = previous

            project = outputs / "demo"
            progress_exists = (project / "project_progress.yaml").exists()
            stage2_dir_exists = (project / "_stage2").is_dir()
            papers_dir_exists = (project / "_stage3b" / "papers").is_dir()

        self.assertEqual(exit_code, 0)
        self.assertTrue(progress_exists)
        self.assertTrue(stage2_dir_exists)
        self.assertTrue(papers_dir_exists)


if __name__ == "__main__":
    unittest.main()
