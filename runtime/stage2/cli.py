from __future__ import annotations

import argparse
import json
from pathlib import Path

from runtime.workspace_contract import inspect_project, list_projects

from .catalog import list_available_scope_options
from .session import (
    ProposalContext,
    ThemeItem,
    build_stage2_manifest,
    load_proposal_context,
    resolve_scope_selection,
    split_csv,
    write_stage2_manifest,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="交互式生成阶段二任务配置，并写入 outputs/<project>/2_stage2_manifest.json。")
    parser.add_argument("--outputs", default="outputs", help="项目输出目录，默认是 ./outputs。")
    parser.add_argument("--project", help="输出目录下的项目名。")
    parser.add_argument(
        "--kanripo-root",
        default="data/kanripo_repos",
        help="Kanripo 根目录，默认是 ./data/kanripo_repos。",
    )
    parser.add_argument(
        "--source",
        choices=("stage1", "manual"),
        help="分析主题来源：stage1=读取 1_research_proposal.md，manual=手工输入。",
    )
    parser.add_argument("--themes", help="手工输入分析主题，逗号分隔。")
    parser.add_argument("--scopes", help="阶段二 scope family，逗号分隔，如 KR1a,KR3j。")
    parser.add_argument("--repos", help="精确 repo 目录，逗号分隔，如 KR3j0160,KR3j0161。")
    parser.add_argument("--env-file", help="可选 .env 文件路径，用于写入模型槽位摘要。")
    parser.add_argument("--interactive", action="store_true", help="即使传参完整，也强制进入交互模式。")
    parser.add_argument("--no-write", action="store_true", help="只预览 manifest，不写文件。")
    parser.add_argument("--json", action="store_true", help="输出 JSON。")
    return parser


def _format_theme(item: ThemeItem) -> str:
    if item.description:
        return f"{item.theme} | {item.description}"
    return item.theme


def _prompt(message: str, *, default: str | None = None, allow_empty: bool = False) -> str:
    prompt = message
    if default:
        prompt += f" [{default}]"
    prompt += ": "
    while True:
        value = input(prompt).strip()
        if value:
            return value
        if default is not None:
            return default
        if allow_empty:
            return ""
        print("输入不能为空，请重试。")


def _prompt_menu(title: str, options: list[tuple[str, str]]) -> str:
    print()
    print(title)
    for key, label in options:
        print(f"  {key}. {label}")
    valid = {key for key, _ in options}
    while True:
        value = input("请选择编号: ").strip()
        if value in valid:
            return value
        print(f"无效输入，可选值: {', '.join(sorted(valid))}")


def _prompt_index_selection(items: list[str], *, allow_all: bool = True) -> list[int]:
    for index, item in enumerate(items, start=1):
        print(f"  {index}. {item}")
    hint = "输入编号，逗号分隔"
    if allow_all:
        hint += "；直接回车表示全选"
    hint += ": "
    while True:
        raw_value = input(hint).strip()
        if not raw_value and allow_all:
            return list(range(1, len(items) + 1))

        result: list[int] = []
        invalid = False
        for token in split_csv(raw_value):
            if not token.isdigit():
                invalid = True
                break
            index = int(token)
            if index < 1 or index > len(items):
                invalid = True
                break
            if index not in result:
                result.append(index)
        if result and not invalid:
            return result
        print("编号无效，请重试。")


def _pick_project(outputs_root: Path) -> str:
    projects = list_projects(outputs_root)
    if not projects:
        raise SystemExit("outputs/ 下没有项目。请先通过 Skill 创建项目并生成阶段一产物。")

    rows: list[str] = []
    for project_name in projects:
        status = inspect_project(outputs_root, project_name)
        proposal_ready = "有 proposal" if status.stages[0].status != "missing" else "无 proposal"
        rows.append(
            f"{project_name} | 下一阶段={status.next_stage} | 已完成到阶段={status.highest_completed_stage} | {proposal_ready}"
        )

    print()
    print("可用项目:")
    indexes = _prompt_index_selection(rows, allow_all=False)
    return projects[indexes[0] - 1]


def _choose_theme_source(proposal_context: ProposalContext | None) -> tuple[str, list[ThemeItem]]:
    if proposal_context and proposal_context.target_themes:
        choice = _prompt_menu(
            "请选择阶段二分析主题来源",
            [
                ("1", "使用阶段一 1_research_proposal.md 中的 target_themes"),
                ("2", "手工输入本次阶段二要分析的主题"),
            ],
        )
        if choice == "1":
            print()
            print("proposal 中检测到以下主题:")
            selected_indexes = _prompt_index_selection(
                [_format_theme(item) for item in proposal_context.target_themes]
            )
            return (
                "stage1",
                [proposal_context.target_themes[index - 1] for index in selected_indexes],
            )

    raw_themes = _prompt("请输入要分析的主题，逗号分隔")
    return (
        "manual",
        [ThemeItem(theme=item) for item in split_csv(raw_themes)],
    )


def _prompt_scope_inputs(kanripo_root: Path) -> tuple[list[str], list[str]]:
    options = list_available_scope_options(kanripo_root)
    if options:
        print()
        print("Kanripo scope family 示例:")
        for option in options[:12]:
            print(f"  - {option.code}: {option.display_label}")
        if len(options) > 12:
            print("  - ... 可继续手工输入更多 scope family。")

    print()
    print("至少提供一种检索目标：scope family 或精确 repo 目录。")
    while True:
        raw_scopes = _prompt("输入 scope family，逗号分隔；没有可直接回车", allow_empty=True)
        raw_repos = _prompt("输入精确 repo 目录，逗号分隔；没有可直接回车", allow_empty=True)
        scopes = split_csv(raw_scopes)
        repos = split_csv(raw_repos)
        if scopes or repos:
            return scopes, repos
        print("至少输入一个 scope family 或 repo 目录。")


def _resolve_project_context(outputs_root: Path, project_name: str) -> tuple[Path, ProposalContext | None]:
    project_dir = outputs_root / project_name
    if not project_dir.exists():
        raise SystemExit(f"项目不存在: {project_dir}")
    return project_dir, load_proposal_context(project_dir)


def _non_interactive_payload(args: argparse.Namespace, outputs_root: Path) -> dict[str, object]:
    if not args.project:
        raise SystemExit("非交互模式必须提供 --project。")

    project_dir, proposal_context = _resolve_project_context(outputs_root, args.project)

    if args.themes and args.source == "stage1":
        raise SystemExit("--source stage1 与 --themes 不能同时使用。")

    if args.themes:
        theme_source = "manual"
        target_themes = [ThemeItem(theme=item) for item in split_csv(args.themes)]
    elif args.source == "manual":
        raise SystemExit("--source manual 时必须同时提供 --themes。")
    else:
        if not proposal_context or not proposal_context.target_themes:
            raise SystemExit("当前项目缺少可读取的阶段一 target_themes，请改用 --themes 手工输入。")
        theme_source = "stage1"
        target_themes = list(proposal_context.target_themes)

    scope_selection = resolve_scope_selection(
        args.kanripo_root,
        scope_families=split_csv(args.scopes),
        repo_dirs=split_csv(args.repos),
    )
    if not scope_selection.scope_families and not scope_selection.repo_dirs:
        raise SystemExit("至少提供 --scopes 或 --repos 其中之一。")
    if not scope_selection.is_valid:
        raise SystemExit(
            "存在无效输入: "
            f"missing_scope_families={list(scope_selection.missing_scope_families)} "
            f"missing_repo_dirs={list(scope_selection.missing_repo_dirs)}"
        )

    manifest = build_stage2_manifest(
        workspace_root=Path.cwd(),
        outputs_root=outputs_root,
        project_name=args.project,
        kanripo_root=args.kanripo_root,
        theme_source=theme_source,
        target_themes=target_themes,
        scope_selection=scope_selection,
        proposal_context=proposal_context,
        dotenv_path=args.env_file,
    )
    return {
        "manifest": manifest,
        "project_dir": project_dir,
    }


def _interactive_payload(args: argparse.Namespace, outputs_root: Path) -> dict[str, object]:
    kanripo_root = Path(_prompt("Kanripo 根目录", default=args.kanripo_root)).expanduser().resolve()
    if not kanripo_root.exists():
        raise SystemExit(f"Kanripo 根目录不存在: {kanripo_root}")

    project_name = args.project or _pick_project(outputs_root)
    project_dir, proposal_context = _resolve_project_context(outputs_root, project_name)

    theme_source, target_themes = _choose_theme_source(proposal_context)
    if not target_themes:
        raise SystemExit("没有可用的分析主题。")

    raw_scopes, raw_repos = _prompt_scope_inputs(kanripo_root)
    scope_selection = resolve_scope_selection(
        kanripo_root,
        scope_families=raw_scopes,
        repo_dirs=raw_repos,
    )
    if not scope_selection.is_valid:
        print()
        if scope_selection.missing_scope_families:
            print(f"无效 scope family: {', '.join(scope_selection.missing_scope_families)}")
        if scope_selection.missing_repo_dirs:
            print(f"无效 repo 目录: {', '.join(scope_selection.missing_repo_dirs)}")
        raise SystemExit("阶段二 manifest 未写入，请修正后重试。")

    manifest = build_stage2_manifest(
        workspace_root=Path.cwd(),
        outputs_root=outputs_root,
        project_name=project_name,
        kanripo_root=kanripo_root,
        theme_source=theme_source,
        target_themes=target_themes,
        scope_selection=scope_selection,
        proposal_context=proposal_context,
        dotenv_path=args.env_file,
    )
    return {
        "manifest": manifest,
        "project_dir": project_dir,
    }


def _should_use_interactive(args: argparse.Namespace) -> bool:
    if args.interactive:
        return True
    if not args.project:
        return True
    if not args.scopes and not args.repos:
        return True
    if not args.source and not args.themes:
        return True
    return False


def _emit_summary(manifest: dict[str, object], *, manifest_output_path: Path | None, as_json: bool) -> None:
    payload = dict(manifest)
    payload["manifest_path"] = str(manifest_output_path) if manifest_output_path else ""

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print()
    print(f"项目: {payload['project_name']}")
    print(f"主题来源: {payload['theme_source']}")
    print("分析主题:")
    for item in payload["target_themes"]:
        print(f"  - {item['theme']}")
    print(f"scope family: {', '.join(payload['scope_families']) or '(空)'}")
    print(f"repo 目录: {', '.join(payload['repo_dirs']) or '(空)'}")
    if manifest_output_path:
        print(f"manifest 已写入: {manifest_output_path}")
    else:
        print("manifest 仅预览，未写入文件。")


def main() -> int:
    args = build_parser().parse_args()
    outputs_root = Path(args.outputs).expanduser().resolve()
    if not outputs_root.exists():
        raise SystemExit(f"outputs 根目录不存在: {outputs_root}")

    if _should_use_interactive(args):
        payload = _interactive_payload(args, outputs_root)
    else:
        payload = _non_interactive_payload(args, outputs_root)

    manifest = payload["manifest"]
    project_dir = payload["project_dir"]

    path: Path | None = None
    if not args.no_write:
        path = write_stage2_manifest(project_dir, manifest)

    _emit_summary(manifest, manifest_output_path=path, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
