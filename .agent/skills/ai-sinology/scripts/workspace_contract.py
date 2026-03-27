from __future__ import annotations

# Shared workspace-contract loader and stage inspector used by the
# ai-sinology helper scripts.

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_CONTRACT_ASSET = SKILL_ROOT / "assets" / "workspace-contract.json"


@dataclass(frozen=True)
class StageDefinition:
    index: int
    name: str
    required_all: tuple[str, ...] = ()
    required_any: tuple[str, ...] = ()
    required_nonempty_dirs: tuple[str, ...] = ()
    recommended: tuple[str, ...] = ()


@dataclass(frozen=True)
class StageSnapshot:
    index: int
    name: str
    status: str
    present_files: tuple[str, ...]
    missing_required: tuple[str, ...]
    missing_recommended: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return self.status == "complete"


@dataclass(frozen=True)
class ProjectStatus:
    project_name: str
    project_dir: Path
    progress_file: Path
    has_progress_file: bool
    stages: tuple[StageSnapshot, ...]
    highest_completed_stage: int
    next_stage: int | None


@lru_cache(maxsize=1)
def workspace_contract_payload() -> dict[str, object]:
    return json.loads(WORKSPACE_CONTRACT_ASSET.read_text(encoding="utf-8"))


def project_progress_filename() -> str:
    payload = workspace_contract_payload()
    return str(payload["project_progress_file"])


@lru_cache(maxsize=1)
def stage_definitions() -> tuple[StageDefinition, ...]:
    payload = workspace_contract_payload()
    definitions: list[StageDefinition] = []
    for raw_stage in payload["stages"]:
        definitions.append(
            StageDefinition(
                index=int(raw_stage["index"]),
                name=str(raw_stage["name"]),
                required_all=tuple(raw_stage.get("required_all", [])),
                required_any=tuple(raw_stage.get("required_any", [])),
                required_nonempty_dirs=tuple(raw_stage.get("required_nonempty_dirs", [])),
                recommended=tuple(raw_stage.get("recommended", [])),
            )
        )
    definitions.sort(key=lambda item: item.index)
    return tuple(definitions)


def list_projects(outputs_root: str | Path) -> list[str]:
    root = Path(outputs_root).expanduser().resolve()
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))


def _existing(project_dir: Path, names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if (project_dir / name).exists())


def _has_visible_material(path: Path) -> bool:
    if not path.is_dir():
        return False
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        relative_parts = item.relative_to(path).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        if item.name in {".gitkeep", ".DS_Store"}:
            continue
        return True
    return False


def _existing_nonempty_dirs(project_dir: Path, names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if _has_visible_material(project_dir / name))


def _nonempty_dir_requirement_label(path: str) -> str:
    return f"{path}（目录内需至少有 1 份人工导入材料）"


def inspect_stage(project_dir: Path, definition: StageDefinition) -> StageSnapshot:
    present_required_all = _existing(project_dir, definition.required_all)
    present_required_any = _existing(project_dir, definition.required_any)
    present_required_nonempty_dirs = _existing_nonempty_dirs(project_dir, definition.required_nonempty_dirs)
    present_recommended = _existing(project_dir, definition.recommended)

    missing_required = tuple(name for name in definition.required_all if name not in present_required_all)
    missing_required = missing_required + tuple(
        _nonempty_dir_requirement_label(name)
        for name in definition.required_nonempty_dirs
        if name not in present_required_nonempty_dirs
    )
    any_satisfied = not definition.required_any or bool(present_required_any)
    if definition.required_any and not present_required_any:
        missing_required = missing_required + definition.required_any

    complete = not missing_required and any_satisfied
    present_files = tuple(
        dict.fromkeys(
            present_required_all
            + present_required_any
            + present_required_nonempty_dirs
            + present_recommended
        )
    )
    if complete:
        status = "complete"
    elif present_files:
        status = "partial"
    else:
        status = "missing"

    missing_recommended = tuple(name for name in definition.recommended if name not in present_recommended)
    return StageSnapshot(
        index=definition.index,
        name=definition.name,
        status=status,
        present_files=present_files,
        missing_required=missing_required,
        missing_recommended=missing_recommended,
    )


def inspect_project(outputs_root: str | Path, project_name: str) -> ProjectStatus:
    root = Path(outputs_root).expanduser().resolve()
    project_dir = root / project_name
    progress_file = project_dir / project_progress_filename()
    stages = tuple(inspect_stage(project_dir, stage) for stage in stage_definitions())

    highest_completed_stage = 0
    for stage in stages:
        if stage.is_complete and stage.index == highest_completed_stage + 1:
            highest_completed_stage = stage.index
        else:
            break

    next_stage = None if highest_completed_stage == len(stages) else highest_completed_stage + 1
    return ProjectStatus(
        project_name=project_name,
        project_dir=project_dir,
        progress_file=progress_file,
        has_progress_file=progress_file.exists(),
        stages=stages,
        highest_completed_stage=highest_completed_stage,
        next_stage=next_stage,
    )
