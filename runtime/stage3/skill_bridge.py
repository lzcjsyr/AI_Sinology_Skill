from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


def _load_workspace_contract_module():
    skill_script = (
        Path(__file__).resolve().parent.parent.parent
        / ".agent"
        / "skills"
        / "ai-sinology"
        / "scripts"
        / "workspace_contract.py"
    )
    spec = spec_from_file_location("ai_sinology_workspace_contract", skill_script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 Skill 工作区契约脚本: {skill_script}")
    sys.path.insert(0, str(skill_script.parent))
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if sys.path and sys.path[0] == str(skill_script.parent):
            sys.path.pop(0)
    return module


_MODULE = _load_workspace_contract_module()

ProjectStatus = _MODULE.ProjectStatus
StageDefinition = _MODULE.StageDefinition
StageSnapshot = _MODULE.StageSnapshot
inspect_project = _MODULE.inspect_project
inspect_stage = _MODULE.inspect_stage
list_projects = _MODULE.list_projects
project_progress_filename = _MODULE.project_progress_filename
stage_definitions = _MODULE.stage_definitions
workspace_contract_payload = _MODULE.workspace_contract_payload
