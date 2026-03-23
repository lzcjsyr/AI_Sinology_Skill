from __future__ import annotations

import argparse
import json
from pathlib import Path

from .workspace_contract import inspect_project, list_projects


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查 skill 工作区中的项目进度。")
    parser.add_argument("project", nargs="?", help="单个项目名。")
    parser.add_argument("--outputs", default="outputs", help="项目输出目录，默认是 ./outputs。")
    parser.add_argument("--all", action="store_true", help="显示全部项目。")
    parser.add_argument("--json", action="store_true", help="输出 JSON。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    outputs_root = Path(args.outputs).expanduser().resolve()

    if args.project:
        project_names = [args.project]
    else:
        project_names = list_projects(outputs_root)

    if not project_names:
        print("outputs/ 下没有项目。")
        return 0

    payload = []
    for project_name in project_names:
        status = inspect_project(outputs_root, project_name)
        payload.append(
            {
                "project_name": status.project_name,
                "project_dir": str(status.project_dir),
                "progress_file": str(status.progress_file),
                "has_progress_file": status.has_progress_file,
                "highest_completed_stage": status.highest_completed_stage,
                "next_stage": status.next_stage,
                "stages": [
                    {
                        "stage_index": stage.index,
                        "stage_name": stage.name,
                        "status": stage.status,
                        "present_files": list(stage.present_files),
                        "missing_required": list(stage.missing_required),
                        "missing_recommended": list(stage.missing_recommended),
                    }
                    for stage in status.stages
                ],
            }
        )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for project in payload:
            print(
                f"{project['project_name']}: 下一阶段={project['next_stage']} "
                f"顺序完成到阶段={project['highest_completed_stage']}"
            )
            print(
                f"  进度文件: {'存在' if project['has_progress_file'] else '缺失'} "
                f"| {project['progress_file']}"
            )
            for stage in project["stages"]:
                print(
                    f"  阶段{stage['stage_index']} {stage['stage_name']}: {stage['status']}"
                    + (f" | present={','.join(stage['present_files'])}" if stage["present_files"] else "")
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
