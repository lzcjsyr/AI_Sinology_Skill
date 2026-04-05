from __future__ import annotations

# Recompute project_progress.yaml from the current workspace contents so
# the stage tracker stays aligned with the actual files on disk.

import argparse
from datetime import datetime
from pathlib import Path

from workspace_contract import inspect_project, project_progress_filename, stage_definitions


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def next_action_for_stage(stage_snapshot, stage_name: str) -> str:
    if stage_snapshot.missing_required:
        return f"推进阶段{stage_snapshot.index}: {stage_name}，补齐 {'、'.join(stage_snapshot.missing_required)}"
    return f"推进阶段{stage_snapshot.index}: {stage_name}"


def render_list(items: list[str]) -> list[str]:
    if not items:
        return [" []"]
    lines = [""]
    lines.extend(f"  - {yaml_quote(item)}" for item in items)
    return lines


def render_progress_yaml(*, status, workspace_root: Path, notes: str) -> str:
    definitions = {stage.index: stage.name for stage in stage_definitions()}
    snapshots = {stage.index: stage for stage in status.stages}
    current_stage = status.next_stage or status.highest_completed_stage or 1
    current_stage_name = definitions.get(current_stage, definitions[max(definitions)])
    if status.next_stage is None:
        next_action = "项目已完成，进入人工复核或导出环节"
    else:
        next_action = next_action_for_stage(snapshots[status.next_stage], definitions[status.next_stage])

    available_files = sorted(
        path.name for path in status.project_dir.iterdir() if path.is_file() and not path.name.startswith(".")
    )
    completed_stages = [f"{stage.index}:{stage.name}" for stage in status.stages if stage.is_complete]

    lines = [
        f"project_name: {yaml_quote(status.project_name)}",
        f"workspace_root: {yaml_quote(str(workspace_root))}",
        f"project_root: {yaml_quote(str(status.project_dir))}",
        f"current_stage: {current_stage}",
        f"current_stage_name: {yaml_quote(current_stage_name)}",
        "completed_stages:" + render_list(completed_stages)[0],
    ]
    lines.extend(render_list(completed_stages)[1:])
    lines.append("available_files:" + render_list(available_files)[0])
    lines.extend(render_list(available_files)[1:])
    lines.append(f"next_action: {yaml_quote(next_action)}")
    lines.append(f"last_updated: {yaml_quote(datetime.now().astimezone().isoformat(timespec='seconds'))}")
    lines.append(f"notes: {yaml_quote(notes)}")
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="根据当前工作区文件同步 project_progress.yaml。")
    parser.add_argument("project", help="项目名。")
    parser.add_argument("--outputs", default="outputs", help="项目输出目录，默认是 ./outputs。")
    parser.add_argument("--notes", default="", help="覆盖写入进度文件的备注。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    outputs_root = Path(args.outputs).expanduser().resolve()
    status = inspect_project(outputs_root, args.project)
    status.project_dir.mkdir(parents=True, exist_ok=True)

    progress_path = status.project_dir / project_progress_filename()
    payload = render_progress_yaml(
        status=status,
        workspace_root=outputs_root.parent,
        notes=args.notes,
    )
    progress_path.write_text(payload, encoding="utf-8")
    print(f"已同步进度文件: {progress_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
