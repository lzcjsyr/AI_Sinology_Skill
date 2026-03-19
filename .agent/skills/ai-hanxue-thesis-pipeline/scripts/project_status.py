#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from repo_helpers import ensure_workspace_on_syspath, find_workspace_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="汇总 outputs/ 下项目的阶段状态。")
    parser.add_argument("project", nargs="?", help="要检查的单个项目名。")
    parser.add_argument("--workspace", help="仓库根目录，默认自动探测。")
    parser.add_argument("--all", action="store_true", help="检查全部项目。")
    parser.add_argument("--json", action="store_true", help="输出 JSON，而不是纯文本。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workspace_root = find_workspace_root(args.workspace)
    ensure_workspace_on_syspath(workspace_root)

    from core.state_manager import StateManager

    state_manager = StateManager(workspace_root / "outputs")

    if args.project:
        project_names = [args.project]
    else:
        project_names = state_manager.list_projects()

    if not project_names:
        print("outputs/ 下没有项目。")
        return 0

    payload = []
    for project_name in project_names:
        progress = state_manager.infer_stage_progress(project_name)
        payload.append(
            {
                "project_name": project_name,
                "next_stage": state_manager.suggest_next_stage(progress),
                "highest_completed_stage": state_manager.highest_completed_stage(progress),
                "stages": [
                    {
                        "stage_index": item.stage_index,
                        "stage_name": item.stage_name,
                        "status": item.status,
                        "status_label": item.status_label,
                    }
                    for item in progress
                ],
            }
        )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for project in payload:
            print(
                f"{project['project_name']}: 下一阶段={project['next_stage']} "
                f"最高已完成阶段={project['highest_completed_stage']}"
            )
            for stage in project["stages"]:
                print(f"  阶段{stage['stage_index']}: {stage['status_label']} | {stage['stage_name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
