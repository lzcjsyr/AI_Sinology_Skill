from __future__ import annotations

# Initialize a project workspace under outputs/<project>/ and create
# the first project_progress.yaml snapshot used by later stages.

import argparse
from datetime import datetime
from pathlib import Path

from workspace_contract import project_progress_filename, stage_definitions


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def next_action_for_stage(stage) -> str:
    required = list(stage.required_all)
    if required:
        return f"完成阶段{stage.index}必选文件: {'、'.join(required)}"
    if stage.required_any:
        return f"完成阶段{stage.index}任一必选文件: {'、'.join(stage.required_any)}"
    return f"推进阶段{stage.index}: {stage.name}"


def render_progress_yaml(
    *,
    project_name: str,
    workspace_root: Path,
    project_root: Path,
    notes: str = "",
) -> str:
    first_stage = stage_definitions()[0]
    lines = [
        f"project_name: {yaml_quote(project_name)}",
        f"workspace_root: {yaml_quote(str(workspace_root))}",
        f"project_root: {yaml_quote(str(project_root))}",
        f"current_stage: {first_stage.index}",
        f"current_stage_name: {yaml_quote(first_stage.name)}",
        "completed_stages: []",
        "available_files: []",
        f"next_action: {yaml_quote(next_action_for_stage(first_stage))}",
        f"last_updated: {yaml_quote(datetime.now().astimezone().isoformat(timespec='seconds'))}",
        f"notes: {yaml_quote(notes)}",
        "",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="为 ai-sinology Skill 初始化 outputs/<project>/ 工作目录。")
    parser.add_argument("project", help="项目名。")
    parser.add_argument("--outputs", default="outputs", help="项目输出目录，默认是 ./outputs。")
    parser.add_argument("--notes", default="", help="初始化时写入 project_progress.yaml 的备注。")
    parser.add_argument("--force", action="store_true", help="已存在时覆盖 project_progress.yaml。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    outputs_root = Path(args.outputs).expanduser().resolve()
    outputs_root.mkdir(parents=True, exist_ok=True)

    project_dir = outputs_root / args.project
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "_stage2a" / "papers").mkdir(parents=True, exist_ok=True)

    progress_path = project_dir / project_progress_filename()
    if progress_path.exists() and not args.force:
        print(f"已存在进度文件，未覆盖: {progress_path}")
        return 0

    payload = render_progress_yaml(
        project_name=args.project,
        workspace_root=outputs_root.parent,
        project_root=project_dir,
        notes=args.notes,
    )
    progress_path.write_text(payload, encoding="utf-8")
    print(f"已初始化项目目录: {project_dir}")
    print(f"已写入进度文件: {progress_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
