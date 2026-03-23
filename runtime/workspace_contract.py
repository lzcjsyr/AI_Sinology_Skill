from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_PROGRESS_FILE = "project_progress.yaml"


@dataclass(frozen=True)
class StageDefinition:
    index: int
    name: str
    required_all: tuple[str, ...] = ()
    required_any: tuple[str, ...] = ()
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


STAGES: tuple[StageDefinition, ...] = (
    StageDefinition(
        index=1,
        name="选题与构思",
        required_all=("1_research_proposal.md",),
    ),
    StageDefinition(
        index=2,
        name="外部史料总库",
        required_all=("2_final_corpus.yaml",),
        recommended=("2_stage2_manifest.json",),
    ),
    StageDefinition(
        index=3,
        name="论纲构建",
        required_all=("3_outline_matrix.yaml",),
    ),
    StageDefinition(
        index=4,
        name="初稿写作",
        required_all=("4_first_draft.md",),
    ),
    StageDefinition(
        index=5,
        name="润色与终稿",
        required_any=("5_final_manuscript.md", "5_final_manuscript.docx"),
        recommended=("5_revision_checklist.md",),
    ),
)


def list_projects(outputs_root: str | Path) -> list[str]:
    root = Path(outputs_root).expanduser().resolve()
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))


def _existing(project_dir: Path, names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if (project_dir / name).exists())


def inspect_stage(project_dir: Path, definition: StageDefinition) -> StageSnapshot:
    present_required_all = _existing(project_dir, definition.required_all)
    present_required_any = _existing(project_dir, definition.required_any)
    present_recommended = _existing(project_dir, definition.recommended)

    missing_required = tuple(name for name in definition.required_all if name not in present_required_all)
    any_satisfied = not definition.required_any or bool(present_required_any)
    if definition.required_any and not present_required_any:
        missing_required = missing_required + definition.required_any

    complete = not missing_required and any_satisfied
    present_files = tuple(
        dict.fromkeys(
            present_required_all + present_required_any + present_recommended
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
    progress_file = project_dir / PROJECT_PROGRESS_FILE
    stages = tuple(inspect_stage(project_dir, stage) for stage in STAGES)

    highest_completed_stage = 0
    for stage in stages:
        if stage.is_complete and stage.index == highest_completed_stage + 1:
            highest_completed_stage = stage.index
        else:
            break

    next_stage = None if highest_completed_stage == len(STAGES) else highest_completed_stage + 1
    return ProjectStatus(
        project_name=project_name,
        project_dir=project_dir,
        progress_file=progress_file,
        has_progress_file=progress_file.exists(),
        stages=stages,
        highest_completed_stage=highest_completed_stage,
        next_stage=next_stage,
    )
