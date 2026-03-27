from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import sys
import tempfile
import unittest
from pathlib import Path


def _load_init_project_module():
    script_path = (
        Path(__file__).resolve().parent.parent
        / ".agent"
        / "skills"
        / "ai-sinology"
        / "scripts"
        / "init_project.py"
    )
    spec = spec_from_file_location("test_ai_sinology_init_project", script_path)
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


_MODULE = _load_init_project_module()


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
