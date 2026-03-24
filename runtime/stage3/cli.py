from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .catalog import list_available_scope_options
from .session import (
    ProposalContext,
    ThemeItem,
    analysis_targets_from_session,
    build_stage3_manifest,
    ensure_stage3_workspace,
    load_proposal_context,
    load_stage3_session,
    normalize_stage3_session,
    resolve_scope_selection,
    save_stage3_session,
    split_csv,
    stage3_session_path,
    stage3_workspace_dir,
    stage3_workspace_manifest_path,
    summarize_retrieval_progress,
    update_stage3_session_checkpoint,
    write_stage3_manifest,
)
from .skill_bridge import inspect_project, list_projects


DEFAULT_KANRIPO_ROOT = "data/kanripo_repos"
DEFAULT_ENV_FILE = ".env"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="交互式生成阶段三任务配置；会先选择项目，创建 outputs/<project>/_stage3/ 工作目录，并写入 outputs/<project>/3_stage3_manifest.json。"
    )
    parser.add_argument("--outputs", default="outputs", help="项目输出目录，默认是 ./outputs。")
    parser.add_argument("--project", help="输出目录下的项目名。")
    parser.add_argument(
        "--kanripo-root",
        default=DEFAULT_KANRIPO_ROOT,
        help="Kanripo 根目录，默认是 ./data/kanripo_repos。",
    )
    parser.add_argument(
        "--source",
        choices=("stage1", "manual"),
        help="分析主题来源：stage1=读取 1_research_proposal.md，manual=手工输入。",
    )
    parser.add_argument("--themes", help="手工输入分析主题，逗号分隔。")
    parser.add_argument("--scopes", help="阶段三 scope family，逗号分隔，如 KR1a,KR3j。")
    parser.add_argument("--repos", help="精确 repo 目录，逗号分隔，如 KR3j0160,KR3j0161。")
    parser.add_argument(
        "--env-file",
        help="可选 .env 文件路径；默认读取当前工作目录下的 .env，并将结果写入模型槽位摘要。",
    )
    parser.add_argument("--interactive", action="store_true", help="即使传参完整，也强制进入交互模式。")
    parser.add_argument("--no-write", action="store_true", help="只预览 manifest，不写文件。")
    parser.add_argument(
        "--checkpoint-action",
        choices=("start", "checkpoint", "pause", "complete", "reset"),
        help="直接更新 outputs/<project>/_stage3/session.json 中的检索断点，不重新进入配置流程。",
    )
    parser.add_argument("--checkpoint-target", help="断点操作对应的当前检索目标，如 KR3j 或 KR3j0160。")
    parser.add_argument("--checkpoint-cursor", help="当前检索游标或批次标记。")
    parser.add_argument("--checkpoint-piece-id", help="最近一次确认的 piece_id。")
    parser.add_argument(
        "--checkpoint-piece-delta",
        type=int,
        default=0,
        help="本次操作新增确认的史料条数，默认 0。",
    )
    parser.add_argument("--checkpoint-note", help="覆盖保存本次断点备注。")
    parser.add_argument("--show-checkpoint", action="store_true", help="仅展示当前断点摘要，不写入新配置。")
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


def _prompt_menu(title: str, options: list[tuple[str, str]], *, default: str | None = None) -> str:
    print()
    print(title)
    for key, label in options:
        print(f"  {key}. {label}")
    valid = {key for key, _ in options}
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"请选择编号{suffix}: ").strip()
        if not value and default in valid:
            return default
        if value in valid:
            return value
        print(f"无效输入，可选值: {', '.join(sorted(valid))}")


def _prompt_index_selection(
    items: list[str],
    *,
    allow_all: bool = True,
    default: list[int] | None = None,
) -> list[int]:
    for index, item in enumerate(items, start=1):
        print(f"  {index}. {item}")
    hint = "输入编号，逗号分隔"
    if allow_all:
        hint += "；直接回车表示全选"
    elif default:
        hint += f"；直接回车沿用 {','.join(str(item) for item in default)}"
    hint += ": "
    while True:
        raw_value = input(hint).strip()
        if not raw_value and allow_all:
            return list(range(1, len(items) + 1))
        if not raw_value and default:
            return default

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


def _theme_items_from_payload(payload: object) -> list[ThemeItem]:
    if not isinstance(payload, list):
        return []
    items: list[ThemeItem] = []
    for raw in payload:
        if isinstance(raw, dict):
            theme = str(raw.get("theme") or "").strip()
            description = str(raw.get("description") or "").strip()
        else:
            theme = str(raw).strip()
            description = ""
        if theme:
            items.append(ThemeItem(theme=theme, description=description))
    return items


def _theme_names(items: list[ThemeItem]) -> list[str]:
    return [item.theme for item in items]


def _theme_payload(items: list[ThemeItem]) -> list[dict[str, str]]:
    return [{"theme": item.theme, "description": item.description} for item in items]


def _default_theme_indexes(options: tuple[ThemeItem, ...], existing: list[ThemeItem]) -> list[int]:
    if not existing:
        return []
    existing_names = set(_theme_names(existing))
    return [index for index, item in enumerate(options, start=1) if item.theme in existing_names]


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


def _choose_theme_source(
    proposal_context: ProposalContext | None,
    *,
    default_source: str | None = None,
    default_themes: list[ThemeItem] | None = None,
) -> tuple[str, list[ThemeItem]]:
    if proposal_context and proposal_context.target_themes:
        menu_default = "1" if default_source == "stage1" else "2"
        choice = _prompt_menu(
            "请选择阶段三分析主题来源",
            [
                ("1", "使用阶段一 1_research_proposal.md 中的 target_themes"),
                ("2", "手工输入本次阶段三要分析的主题"),
            ],
            default=menu_default,
        )
        if choice == "1":
            print()
            print("proposal 中检测到以下主题:")
            selected_indexes = _prompt_index_selection(
                [_format_theme(item) for item in proposal_context.target_themes],
                default=_default_theme_indexes(proposal_context.target_themes, default_themes or []) or None,
            )
            return (
                "stage1",
                [proposal_context.target_themes[index - 1] for index in selected_indexes],
            )

    raw_themes = _prompt(
        "请输入要分析的主题，逗号分隔",
        default=",".join(_theme_names(default_themes or [])) or None,
    )
    return (
        "manual",
        [ThemeItem(theme=item) for item in split_csv(raw_themes)],
    )


def _prompt_scope_inputs(
    kanripo_root: Path,
    *,
    default_scopes: list[str] | None = None,
    default_repos: list[str] | None = None,
) -> tuple[list[str], list[str]]:
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
        raw_scopes = _prompt(
            "输入 scope family，逗号分隔；没有可直接回车",
            default=",".join(default_scopes or []) or None,
            allow_empty=True,
        )
        raw_repos = _prompt(
            "输入精确 repo 目录，逗号分隔；没有可直接回车",
            default=",".join(default_repos or []) or None,
            allow_empty=True,
        )
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


def _base_session_payload(project_dir: Path, proposal_context: ProposalContext | None) -> dict[str, Any]:
    return {
        "session_version": 2,
        "status": "project_selected",
        "project_name": project_dir.name,
        "project_dir": str(project_dir),
        "stage3_workspace_dir": str(stage3_workspace_dir(project_dir)),
        "proposal_path": str(proposal_context.proposal_path) if proposal_context else "",
        "idea": proposal_context.idea if proposal_context else "",
    }


def _manifest_session_fields(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "kanripo_root": Path(str(manifest["kanripo_root"])),
        "theme_source": str(manifest["theme_source"]),
        "target_themes": _theme_items_from_payload(manifest["target_themes"]),
        "scope_families": [str(item) for item in manifest["scope_families"]],
        "repo_dirs": [str(item) for item in manifest["repo_dirs"]],
    }


def _runtime_payload(
    *,
    manifest: dict[str, Any],
    project_dir: Path,
    stage3_dir: Path,
    session_data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "manifest": manifest,
        "project_dir": project_dir,
        "stage3_dir": stage3_dir,
        "session_data": session_data,
    }


def _resolved_env_file(raw_env_file: str | None) -> str:
    return raw_env_file or DEFAULT_ENV_FILE


def _session_snapshot_payload(project_dir: Path, session_data: dict[str, Any]) -> dict[str, Any]:
    progress = session_data.get("retrieval_progress")
    return {
        "project_name": project_dir.name,
        "project_dir": str(project_dir),
        "stage3_workspace_dir": str(stage3_workspace_dir(project_dir)),
        "analysis_targets": analysis_targets_from_session(session_data),
        "retrieval_progress": progress or {},
        "summary": summarize_retrieval_progress(progress),
        "session_path": str(stage3_session_path(project_dir)),
    }


def _save_progress(
    project_dir: Path,
    *,
    session_data: dict[str, Any],
    status: str,
    kanripo_root: Path | None = None,
    theme_source: str | None = None,
    target_themes: list[ThemeItem] | None = None,
    scope_families: list[str] | None = None,
    repo_dirs: list[str] | None = None,
    manifest_output_path: Path | None = None,
) -> Path:
    payload = dict(session_data)
    payload["status"] = status
    optional_fields = {
        "kanripo_root": str(kanripo_root) if kanripo_root is not None else None,
        "theme_source": theme_source,
        "target_themes": _theme_payload(target_themes) if target_themes is not None else None,
        "scope_families": list(scope_families) if scope_families is not None else None,
        "repo_dirs": list(repo_dirs) if repo_dirs is not None else None,
    }
    payload.update({key: value for key, value in optional_fields.items() if value is not None})
    if manifest_output_path is not None:
        payload["manifest_path"] = str(manifest_output_path)
        payload["workspace_manifest_path"] = str(stage3_workspace_manifest_path(project_dir))
    payload = normalize_stage3_session(payload)
    return save_stage3_session(project_dir, payload)


def _checkpoint_summary_payload(project_dir: Path) -> dict[str, Any]:
    session_data = load_stage3_session(project_dir)
    return _session_snapshot_payload(project_dir, session_data)


def _handle_checkpoint_command(args: argparse.Namespace, outputs_root: Path) -> int:
    if not args.project:
        raise SystemExit("checkpoint 模式必须提供 --project。")

    project_dir, _ = _resolve_project_context(outputs_root, args.project)
    ensure_stage3_workspace(project_dir)

    if args.show_checkpoint:
        payload = _checkpoint_summary_payload(project_dir)
    else:
        try:
            session_data = update_stage3_session_checkpoint(
                project_dir,
                action=str(args.checkpoint_action),
                target=args.checkpoint_target,
                cursor=args.checkpoint_cursor,
                piece_id=args.checkpoint_piece_id,
                note=args.checkpoint_note,
                completed_piece_delta=args.checkpoint_piece_delta,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        payload = _session_snapshot_payload(project_dir, session_data)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print()
    print(f"项目: {payload['project_name']}")
    print(payload["summary"])
    if payload["analysis_targets"]:
        print(f"analysis_targets: {', '.join(payload['analysis_targets'])}")
    print(f"会话文件: {payload['session_path']}")
    return 0


def _non_interactive_payload(args: argparse.Namespace, outputs_root: Path) -> dict[str, Any]:
    if not args.project:
        raise SystemExit("非交互模式必须提供 --project。")

    project_dir, proposal_context = _resolve_project_context(outputs_root, args.project)
    stage3_dir = ensure_stage3_workspace(project_dir)
    session_data = _base_session_payload(project_dir, proposal_context)

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

    manifest = build_stage3_manifest(
        workspace_root=Path.cwd(),
        outputs_root=outputs_root,
        project_name=args.project,
        kanripo_root=args.kanripo_root,
        theme_source=theme_source,
        target_themes=target_themes,
        scope_selection=scope_selection,
        proposal_context=proposal_context,
        dotenv_path=_resolved_env_file(args.env_file),
    )
    return _runtime_payload(
        manifest=manifest,
        project_dir=project_dir,
        stage3_dir=stage3_dir,
        session_data=session_data,
    )


def _interactive_payload(args: argparse.Namespace, outputs_root: Path) -> dict[str, Any]:
    project_name = args.project or _pick_project(outputs_root)
    project_dir, proposal_context = _resolve_project_context(outputs_root, project_name)
    stage3_dir = ensure_stage3_workspace(project_dir)
    resumed = load_stage3_session(project_dir)
    session_data = _base_session_payload(project_dir, proposal_context)
    session_data.update(resumed)
    _save_progress(project_dir, session_data=session_data, status="project_selected")

    if resumed:
        print()
        print(f"检测到已有阶段三工作目录，将沿用上次配置作为默认值: {stage3_dir}")
        print(summarize_retrieval_progress(resumed.get("retrieval_progress")))

    kanripo_default = args.kanripo_root if args.kanripo_root != DEFAULT_KANRIPO_ROOT else str(
        session_data.get("kanripo_root") or DEFAULT_KANRIPO_ROOT
    )
    kanripo_root = Path(_prompt("Kanripo 根目录", default=kanripo_default)).expanduser().resolve()
    if not kanripo_root.exists():
        raise SystemExit(f"Kanripo 根目录不存在: {kanripo_root}")
    _save_progress(project_dir, session_data=session_data, status="project_selected", kanripo_root=kanripo_root)

    theme_source, target_themes = _choose_theme_source(
        proposal_context,
        default_source=str(session_data.get("theme_source") or ""),
        default_themes=_theme_items_from_payload(session_data.get("target_themes")),
    )
    if not target_themes:
        raise SystemExit("没有可用的分析主题。")
    _save_progress(
        project_dir,
        session_data=session_data,
        status="themes_selected",
        kanripo_root=kanripo_root,
        theme_source=theme_source,
        target_themes=target_themes,
    )

    raw_scopes, raw_repos = _prompt_scope_inputs(
        kanripo_root,
        default_scopes=[str(item) for item in session_data.get("scope_families", []) if str(item)],
        default_repos=[str(item) for item in session_data.get("repo_dirs", []) if str(item)],
    )
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
        raise SystemExit("阶段三 manifest 未写入，请修正后重试。")
    _save_progress(
        project_dir,
        session_data=session_data,
        status="scopes_selected",
        kanripo_root=kanripo_root,
        theme_source=theme_source,
        target_themes=target_themes,
        scope_families=list(scope_selection.scope_families),
        repo_dirs=list(scope_selection.repo_dirs),
    )

    manifest = build_stage3_manifest(
        workspace_root=Path.cwd(),
        outputs_root=outputs_root,
        project_name=project_name,
        kanripo_root=kanripo_root,
        theme_source=theme_source,
        target_themes=target_themes,
        scope_selection=scope_selection,
        proposal_context=proposal_context,
        dotenv_path=_resolved_env_file(args.env_file),
    )
    return _runtime_payload(
        manifest=manifest,
        project_dir=project_dir,
        stage3_dir=stage3_dir,
        session_data=session_data,
    )


def _should_use_interactive(args: argparse.Namespace) -> bool:
    return bool(
        args.interactive
        or not args.project
        or (not args.scopes and not args.repos)
        or (not args.source and not args.themes)
    )


def _emit_summary(
    manifest: dict[str, Any],
    *,
    manifest_output_path: Path | None,
    stage3_dir: Path,
    session_output_path: Path | None,
    retrieval_progress: dict[str, Any] | None,
    as_json: bool,
) -> None:
    payload = dict(manifest)
    payload["manifest_path"] = str(manifest_output_path) if manifest_output_path else ""
    payload["stage3_workspace_dir"] = str(stage3_dir)
    payload["session_path"] = str(session_output_path) if session_output_path else ""
    payload["retrieval_progress"] = retrieval_progress or {}

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
    print(f"阶段三工作目录: {stage3_dir}")
    print(summarize_retrieval_progress(retrieval_progress))
    if session_output_path:
        print(f"续跑会话文件: {session_output_path}")
    if manifest_output_path:
        print(f"manifest 已写入: {manifest_output_path}")
    else:
        print("manifest 仅预览，未写入文件。")


def main() -> int:
    args = build_parser().parse_args()
    outputs_root = Path(args.outputs).expanduser().resolve()
    if not outputs_root.exists():
        raise SystemExit(f"outputs 根目录不存在: {outputs_root}")

    if args.show_checkpoint or args.checkpoint_action:
        return _handle_checkpoint_command(args, outputs_root)

    payload = (
        _interactive_payload(args, outputs_root)
        if _should_use_interactive(args)
        else _non_interactive_payload(args, outputs_root)
    )

    manifest = payload["manifest"]
    project_dir = payload["project_dir"]
    stage3_dir = payload["stage3_dir"]
    session_data = payload["session_data"]

    manifest_output_path: Path | None = None
    session_output_path: Path | None = None
    if not args.no_write:
        manifest_output_path = write_stage3_manifest(project_dir, manifest)
        manifest_session_fields = _manifest_session_fields(manifest)
        session_output_path = _save_progress(
            project_dir,
            session_data=session_data,
            status="configured",
            kanripo_root=manifest_session_fields["kanripo_root"],
            theme_source=manifest_session_fields["theme_source"],
            target_themes=manifest_session_fields["target_themes"],
            scope_families=manifest_session_fields["scope_families"],
            repo_dirs=manifest_session_fields["repo_dirs"],
            manifest_output_path=manifest_output_path,
        )

    summary_session = (
        load_stage3_session(project_dir)
        if session_output_path
        else normalize_stage3_session({**session_data, **_manifest_session_fields(manifest)})
    )
    _emit_summary(
        manifest,
        manifest_output_path=manifest_output_path,
        stage3_dir=stage3_dir,
        session_output_path=session_output_path,
        retrieval_progress=summary_session.get("retrieval_progress"),
        as_json=args.json,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
