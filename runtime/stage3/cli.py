"""提供 Stage3 外部入口，负责确认调研范围并写入 manifest / session。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .catalog import measure_corpus_overview, resolve_analysis_targets
from .session import (
    Stage3Context,
    analysis_targets_from_session,
    build_stage3_manifest,
    ensure_stage3_workspace,
    load_stage3_context,
    load_stage3_session,
    save_stage3_session,
    stage3_session_path,
    stage3_workspace_dir,
    summarize_retrieval_progress,
    update_stage3_session_checkpoint,
    write_stage3_manifest,
)
from .skill_bridge import inspect_project, list_projects


DEFAULT_KANRIPO_ROOT = "data/kanripo_repos"
DEFAULT_ENV_FILE = ".env"
SKILL_REFERENCES_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / ".agent"
    / "skills"
    / "ai-sinology"
    / "references"
)
STAGE3_GUIDE_PATH = SKILL_REFERENCES_DIR / "stage3-handoff.md"
WORKSPACE_CONTRACT_PATH = SKILL_REFERENCES_DIR / "workspace-contract.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="确认阶段三调研范围，统计正文规模，并写入 outputs/<project>/3_stage3_manifest.json。"
    )
    parser.add_argument("--outputs", default="outputs", help="项目输出目录，默认是 ./outputs。")
    parser.add_argument("--project", help="输出目录下的项目名。")
    parser.add_argument(
        "--kanripo-root",
        default=DEFAULT_KANRIPO_ROOT,
        help="Kanripo 根目录，默认是 ./data/kanripo_repos。",
    )
    parser.add_argument(
        "--targets",
        help="直接指定 analysis_targets，支持 KR1a / KR1a0001，逗号或空格分隔。",
    )
    parser.add_argument(
        "--env-file",
        help="可选 .env 文件路径；默认读取当前工作目录下的 .env，并写入模型槽位摘要。",
    )
    parser.add_argument("--no-write", action="store_true", help="只预览 manifest，不写文件。")
    parser.add_argument(
        "--checkpoint-action",
        choices=("start", "checkpoint", "pause", "complete", "reset"),
        help="直接更新 outputs/<project>/_stage3/session.json 中的检索断点，不重新进入配置流程。",
    )
    parser.add_argument("--checkpoint-target", help="断点操作对应的当前检索目标，如 KR1a 或 KR1a0157。")
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


def _prompt(message: str, *, default: str | None = None) -> str:
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
        print("输入不能为空，请重试。")


def _confirm(message: str, *, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        value = input(message + suffix).strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("请输入 y 或 n。")


def _pick_project(outputs_root: Path) -> str:
    projects = list_projects(outputs_root)
    if not projects:
        raise SystemExit("outputs/ 下没有项目。请先通过 Skill 创建项目并完成阶段二产物。")

    print()
    print("可用项目:")
    for index, project_name in enumerate(projects, start=1):
        status = inspect_project(outputs_root, project_name)
        print(
            f"  {index}. {project_name}"
            f" | 下一阶段={status.next_stage}"
            f" | 已完成到阶段={status.highest_completed_stage}"
        )

    valid_indexes = {str(index): project for index, project in enumerate(projects, start=1)}
    while True:
        selected = input("请选择项目编号: ").strip()
        if selected in valid_indexes:
            return valid_indexes[selected]
        print(f"无效输入，可选值: {', '.join(valid_indexes.keys())}")


def _resolve_project(outputs_root: Path, project_name: str) -> tuple[Path, Stage3Context]:
    project_dir = outputs_root / project_name
    if not project_dir.exists():
        raise SystemExit(f"项目不存在: {project_dir}")

    stage3_context = load_stage3_context(project_dir)
    if stage3_context is None:
        raise SystemExit(f"缺少阶段二交接文件: {project_dir / '2b_scholarship_map.yaml'}")
    if not stage3_context.target_themes:
        raise SystemExit("stage3_handoff.target_themes 为空，无法启动阶段三。")
    return project_dir, stage3_context


def _resolved_env_file(raw_env_file: str | None) -> str:
    return raw_env_file or DEFAULT_ENV_FILE


def _print_intro(project_dir: Path, stage3_context: Stage3Context, kanripo_root: Path) -> None:
    print()
    print("阶段三将直接读取 stage2 handoff，不再提供交互清单。")
    print("请先阅读 guide 或底层契约，确认本次要覆盖的 Kanripo 范围后，再输入 analysis_targets。")
    print(f"guide: {STAGE3_GUIDE_PATH}")
    print(f"底层契约: {WORKSPACE_CONTRACT_PATH}")
    print(f"项目目录: {project_dir}")
    print(f"Kanripo 根目录: {kanripo_root}")
    print(f"研究问题: {stage3_context.research_question or '(未填写)'}")
    print("阶段二 handoff 主题:")
    for item in stage3_context.target_themes:
        if item.description:
            print(f"  - {item.theme} | {item.description}")
        else:
            print(f"  - {item.theme}")


def _print_selection_errors(issues: tuple[Any, ...]) -> None:
    print()
    print("输入有误，请修正以下目标后重新输入：")
    for issue in issues:
        print(f"  - {issue.token}: {issue.detail}")


def _print_corpus_overview(overview: Any) -> None:
    print()
    print("调研范围统计（正文字符数仅供预估工作量使用）:")
    for item in overview.targets:
        level_label = "类目" if item.level == "family" else "目录"
        print(
            f"  - {item.token} [{level_label}]"
            f" | 目录 {item.repo_dir_count}"
            f" | 文本 {item.text_file_count}"
            f" | 正文约 {item.text_char_count} 字"
        )
    print(
        f"合计 | 目录 {overview.repo_dir_count}"
        f" | 文本 {overview.text_file_count}"
        f" | 正文约 {overview.text_char_count} 字"
    )


def _prompt_analysis_targets(kanripo_root: Path, *, default_targets: list[str] | None = None) -> tuple[list[str], dict[str, object]]:
    default_value = " ".join(default_targets or []) or None
    while True:
        raw_targets = _prompt(
            "请输入调研范围（支持 KR1a / KR1a0001，逗号或空格分隔）",
            default=default_value,
        )
        selection = resolve_analysis_targets(kanripo_root, raw_input=raw_targets)
        if not selection.tokens:
            print("至少输入一个调研范围。")
            continue
        if selection.issues:
            _print_selection_errors(selection.issues)
            continue

        overview = measure_corpus_overview(kanripo_root, selection)
        _print_corpus_overview(overview)
        if _confirm("确认以上调研范围无误，并开始阶段三研究吗？", default=True):
            return list(selection.analysis_targets), overview.as_dict()
        default_value = " ".join(selection.analysis_targets)


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


def _handle_checkpoint_command(args: argparse.Namespace, outputs_root: Path) -> int:
    if not args.project:
        raise SystemExit("checkpoint 模式必须提供 --project。")

    project_dir, _ = _resolve_project(outputs_root, args.project)
    ensure_stage3_workspace(project_dir)

    if args.show_checkpoint:
        payload = _session_snapshot_payload(project_dir, load_stage3_session(project_dir))
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


def _build_session_payload(
    *,
    project_dir: Path,
    stage3_context: Any,
    kanripo_root: Path,
    analysis_targets: list[str],
    manifest_output_path: Path | None,
) -> dict[str, Any]:
    return {
        "session_version": 3,
        "status": "configured",
        "project_name": project_dir.name,
        "project_dir": str(project_dir),
        "stage3_workspace_dir": str(stage3_workspace_dir(project_dir)),
        "manifest_path": str(manifest_output_path) if manifest_output_path else "",
        "workspace_manifest_path": str(stage3_workspace_dir(project_dir) / "manifest.json"),
        "scholarship_map_path": str(stage3_context.scholarship_map_path),
        "proposal_path": str(stage3_context.proposal_path) if stage3_context.proposal_path else "",
        "journal_path": str(stage3_context.journal_path) if stage3_context.journal_path else "",
        "research_question": stage3_context.research_question,
        "idea": stage3_context.research_question,
        "theme_source": "stage2_handoff",
        "target_themes": [
            {"theme": item.theme, "description": item.description}
            for item in stage3_context.target_themes
        ],
        "kanripo_root": str(kanripo_root),
        "analysis_targets": analysis_targets,
    }


def _emit_summary(
    manifest: dict[str, Any],
    *,
    manifest_output_path: Path | None,
    session_output_path: Path | None,
    as_json: bool,
) -> None:
    payload = dict(manifest)
    payload["manifest_path"] = str(manifest_output_path) if manifest_output_path else ""
    payload["session_path"] = str(session_output_path) if session_output_path else ""

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print()
    print(f"项目: {payload['project_name']}")
    print(f"analysis_targets: {', '.join(payload['analysis_targets'])}")
    print(
        f"预估正文规模: {payload['corpus_overview']['text_char_count']} 字"
        f" | 文本 {payload['corpus_overview']['text_file_count']}"
        f" | 目录 {payload['corpus_overview']['repo_dir_count']}"
    )
    print(f"阶段三工作目录: {payload['stage3_workspace_dir']}")
    if session_output_path:
        print(f"会话文件: {session_output_path}")
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

    project_name = args.project or _pick_project(outputs_root)
    project_dir, stage3_context = _resolve_project(outputs_root, project_name)
    ensure_stage3_workspace(project_dir)

    resumed_session = load_stage3_session(project_dir)
    if resumed_session:
        print()
        print(f"检测到已有阶段三会话: {stage3_session_path(project_dir)}")
        print(summarize_retrieval_progress(resumed_session.get("retrieval_progress")))

    kanripo_root = Path(args.kanripo_root).expanduser().resolve()
    if not kanripo_root.exists():
        raise SystemExit(f"Kanripo 根目录不存在: {kanripo_root}")

    if not args.json:
        _print_intro(project_dir, stage3_context, kanripo_root)

    if args.targets:
        selection = resolve_analysis_targets(kanripo_root, raw_input=args.targets)
        if not selection.tokens:
            raise SystemExit("至少输入一个调研范围。")
        if selection.issues:
            details = "; ".join(f"{item.token}: {item.detail}" for item in selection.issues)
            raise SystemExit(f"调研范围无效: {details}")
        analysis_targets = list(selection.analysis_targets)
        corpus_overview = measure_corpus_overview(kanripo_root, selection).as_dict()
        if not args.json:
            _print_corpus_overview(measure_corpus_overview(kanripo_root, selection))
    else:
        analysis_targets, corpus_overview = _prompt_analysis_targets(
            kanripo_root,
            default_targets=analysis_targets_from_session(resumed_session),
        )

    manifest = build_stage3_manifest(
        workspace_root=Path.cwd(),
        outputs_root=outputs_root,
        project_name=project_name,
        kanripo_root=kanripo_root,
        analysis_targets=analysis_targets,
        corpus_overview=corpus_overview,
        stage3_context=stage3_context,
        dotenv_path=_resolved_env_file(args.env_file),
    )

    manifest_output_path: Path | None = None
    session_output_path: Path | None = None
    if not args.no_write:
        manifest_output_path = write_stage3_manifest(project_dir, manifest)
        session_output_path = save_stage3_session(
            project_dir,
            _build_session_payload(
                project_dir=project_dir,
                stage3_context=stage3_context,
                kanripo_root=kanripo_root,
                analysis_targets=analysis_targets,
                manifest_output_path=manifest_output_path,
            ),
        )

    _emit_summary(
        manifest,
        manifest_output_path=manifest_output_path,
        session_output_path=session_output_path,
        as_json=args.json,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
