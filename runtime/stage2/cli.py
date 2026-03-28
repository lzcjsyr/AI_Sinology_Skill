"""提供阶段二外部入口，负责确认调研范围并写入 manifest / session。"""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
    if str(WORKSPACE_ROOT) not in sys.path:
        sys.path.insert(0, str(WORKSPACE_ROOT))
    from runtime.stage2.catalog import measure_corpus_overview, resolve_analysis_targets
    from runtime.stage2.runner import run_stage2_pipeline
    from runtime.stage2.session import (
        Stage2Context,
        analysis_targets_from_session,
        build_stage2_timing_estimate,
        build_stage2_manifest,
        ensure_stage2_workspace,
        load_stage2_context,
        load_stage2_session,
        save_stage2_session,
        slot_summaries,
        stage2_session_path,
        stage2_workspace_dir,
        summarize_retrieval_progress,
        update_stage2_session_checkpoint,
        write_stage2_manifest,
    )
else:
    WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
    from .catalog import measure_corpus_overview, resolve_analysis_targets
    from .runner import run_stage2_pipeline
    from .session import (
        Stage2Context,
        analysis_targets_from_session,
        build_stage2_timing_estimate,
        build_stage2_manifest,
        ensure_stage2_workspace,
        load_stage2_context,
        load_stage2_session,
        save_stage2_session,
        slot_summaries,
        stage2_session_path,
        stage2_workspace_dir,
        summarize_retrieval_progress,
        update_stage2_session_checkpoint,
        write_stage2_manifest,
    )

DEFAULT_KANRIPO_ROOT = "data/kanripo_repos"
DEFAULT_ENV_FILE = ".env"
STAGE2_GUIDE_PATH = Path(__file__).resolve().parent / "docs" / "kanripo_family_guide.md"
WORKSPACE_CONTRACT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / ".agent"
    / "skills"
    / "ai-sinology"
    / "references"
    / "workspace-contract.md"
)


def _load_workspace_contract_module():
    skill_script = (
        WORKSPACE_ROOT
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


_WORKSPACE_CONTRACT_MODULE = _load_workspace_contract_module()
inspect_project = _WORKSPACE_CONTRACT_MODULE.inspect_project
list_projects = _WORKSPACE_CONTRACT_MODULE.list_projects


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="确认阶段二调研范围，统计正文规模，并写入 outputs/<project>/_stage2/2_stage2_manifest.json。"
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
    parser.add_argument("--run", action="store_true", help="显式要求在配置后执行阶段二筛读。")
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="只完成阶段二配置，不启动实际筛读。",
    )
    parser.add_argument(
        "--max-fragments",
        type=int,
        help="执行模式下最多读取多少个分页 fragment；默认不限。",
    )
    parser.add_argument("--llm1-workers", type=int, help="覆盖 llm1 并发数；默认使用运行时配置。")
    parser.add_argument("--llm2-workers", type=int, help="覆盖 llm2 并发数；默认使用运行时配置。")
    parser.add_argument("--llm3-workers", type=int, help="覆盖 llm3 并发数；默认使用运行时配置。")
    parser.add_argument("--force-rerun", action="store_true", help="忽略已缓存的 target 产物并重跑。")
    parser.add_argument(
        "--checkpoint-action",
        choices=("start", "checkpoint", "pause", "complete", "reset"),
        help="直接更新 outputs/<project>/_stage2/session.json 中的检索断点，不重新进入配置流程。",
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
        raise SystemExit("outputs/ 下没有项目。请先通过 Skill 创建项目并完成阶段一产物。")

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


def _resolve_project(outputs_root: Path, project_name: str) -> tuple[Path, Stage2Context]:
    project_dir = outputs_root / project_name
    if not project_dir.exists():
        raise SystemExit(f"项目不存在: {project_dir}")

    project_status = inspect_project(outputs_root, project_name)
    stage1_snapshot = project_status.stages[0]
    if not stage1_snapshot.is_complete:
        missing = "、".join(stage1_snapshot.missing_required) or "1_journal_targeting.md、1_research_proposal.md"
        raise SystemExit(f"阶段一尚未完成，缺少必选文件: {missing}")

    stage2_context = load_stage2_context(project_dir)
    if stage2_context is None:
        raise SystemExit(f"缺少阶段一输入文件: {project_dir / '1_research_proposal.md'}")
    if not stage2_context.target_themes:
        raise SystemExit("阶段一尚未形成可用的研究问题或主题，无法启动阶段二。")
    return project_dir, stage2_context


def _resolved_env_file(raw_env_file: str | None) -> str:
    if raw_env_file:
        return raw_env_file
    return str(WORKSPACE_ROOT / DEFAULT_ENV_FILE)


def _resolve_runtime_path(raw_value: str, *, default_relative: str) -> Path:
    candidate = Path(raw_value if raw_value else default_relative).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    if raw_value and raw_value != default_relative:
        return candidate.resolve()
    return (WORKSPACE_ROOT / default_relative).resolve()


def _print_intro(project_dir: Path, stage2_context: Stage2Context, kanripo_root: Path) -> None:
    print()
    print("阶段二将直接读取阶段一文件，不再要求额外 handoff。")
    print("请先阅读 guide 或底层契约，确认本次要覆盖的 Kanripo 范围后，再输入 analysis_targets。")
    print(f"guide: {STAGE2_GUIDE_PATH}")
    print(f"底层契约: {WORKSPACE_CONTRACT_PATH}")
    print(f"项目目录: {project_dir}")
    print(f"Kanripo 根目录: {kanripo_root}")
    print(f"研究问题: {stage2_context.research_question or '(未填写)'}")
    print(
        "阶段一检索主题:"
        if stage2_context.retrieval_theme_source == "stage1_frontmatter"
        else "阶段一提炼主题:"
    )
    for item in stage2_context.retrieval_themes:
        if item.description:
            print(f"  - {item.theme} | {item.description}")
        else:
            print(f"  - {item.theme}")


def _print_selection_errors(issues: tuple[Any, ...]) -> None:
    print()
    print("输入有误，请修正以下目标后重新输入：")
    for issue in issues:
        print(f"  - {issue.token}: {issue.detail}")


def _format_int(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _format_duration(seconds: object) -> str:
    try:
        total_seconds = max(0, int(seconds))
    except (TypeError, ValueError):
        return str(seconds)

    if total_seconds < 60:
        return f"{_format_int(total_seconds)} 秒"

    total_minutes, remaining_seconds = divmod(total_seconds, 60)
    if total_minutes < 60:
        if remaining_seconds:
            return f"{_format_int(total_minutes)} 分 {_format_int(remaining_seconds)} 秒"
        return f"{_format_int(total_minutes)} 分"

    total_hours, remaining_minutes = divmod(total_minutes, 60)
    if total_hours < 24:
        if remaining_minutes:
            return f"{_format_int(total_hours)} 小时 {_format_int(remaining_minutes)} 分"
        return f"{_format_int(total_hours)} 小时"

    total_days, remaining_hours = divmod(total_hours, 24)
    if remaining_hours:
        return f"{_format_int(total_days)} 天 {_format_int(remaining_hours)} 小时"
    return f"{_format_int(total_days)} 天"


def _print_timing_estimate(timing_estimate: dict[str, Any] | None) -> None:
    if not timing_estimate:
        return
    print(
        f"估时 | 主题 {_format_int(timing_estimate.get('theme_count', 0))}"
        f" | 片段 {_format_int(timing_estimate.get('fragment_count', 0))}"
        f" | 批次 {_format_int(timing_estimate.get('batch_count', 0))}"
        f" | 预估耗时 {_format_duration(timing_estimate.get('lower_bound_seconds', 0))}"
        f" - {_format_duration(timing_estimate.get('upper_bound_seconds', 0))}"
        f"（按单次请求 {_format_int(timing_estimate.get('request_seconds', 0))} 秒）"
    )


def _print_corpus_overview(overview: Any, timing_estimate: dict[str, Any] | None = None) -> None:
    print()
    print("调研范围统计（正文字符数仅供预估工作量使用）:")
    for item in overview.targets:
        level_label = "类目" if item.level == "family" else "目录"
        print(
            f"  - {item.token} [{level_label}]"
            f" | 目录 {_format_int(item.repo_dir_count)}"
            f" | 文本 {_format_int(item.text_file_count)}"
            f" | 正文约 {_format_int(item.text_char_count)} 字"
        )
    print(
        f"合计 | 目录 {_format_int(overview.repo_dir_count)}"
        f" | 文本 {_format_int(overview.text_file_count)}"
        f" | 正文约 {_format_int(overview.text_char_count)} 字"
    )
    _print_timing_estimate(timing_estimate)


def _prompt_analysis_targets(
    kanripo_root: Path,
    *,
    default_targets: list[str] | None = None,
    theme_count: int,
    model_slots: list[dict[str, Any]],
) -> tuple[list[str], dict[str, object], dict[str, Any]]:
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
        timing_estimate = build_stage2_timing_estimate(
            corpus_overview=overview.as_dict(),
            theme_count=theme_count,
            model_slots=model_slots,
        )
        _print_corpus_overview(overview, timing_estimate)
        if _confirm("确认以上调研范围无误，并开始阶段二研究吗？", default=True):
            return list(selection.analysis_targets), overview.as_dict(), timing_estimate
        default_value = " ".join(selection.analysis_targets)


def _session_snapshot_payload(project_dir: Path, session_data: dict[str, Any]) -> dict[str, Any]:
    progress = session_data.get("retrieval_progress")
    return {
        "project_name": project_dir.name,
        "project_dir": str(project_dir),
        "stage2_workspace_dir": str(stage2_workspace_dir(project_dir)),
        "analysis_targets": analysis_targets_from_session(session_data),
        "retrieval_progress": progress or {},
        "summary": summarize_retrieval_progress(progress),
        "session_path": str(stage2_session_path(project_dir)),
    }


def _handle_checkpoint_command(args: argparse.Namespace, outputs_root: Path) -> int:
    if not args.project:
        raise SystemExit("checkpoint 模式必须提供 --project。")

    project_dir, _ = _resolve_project(outputs_root, args.project)
    ensure_stage2_workspace(project_dir)

    if args.show_checkpoint:
        payload = _session_snapshot_payload(project_dir, load_stage2_session(project_dir))
    else:
        try:
            session_data = update_stage2_session_checkpoint(
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
    stage2_context: Stage2Context,
    kanripo_root: Path,
    analysis_targets: list[str],
    manifest_output_path: Path | None,
) -> dict[str, Any]:
    return {
        "session_version": 2,
        "status": "configured",
        "project_name": project_dir.name,
        "project_dir": str(project_dir),
        "stage2_workspace_dir": str(stage2_workspace_dir(project_dir)),
        "manifest_path": str(manifest_output_path) if manifest_output_path else "",
        "workspace_manifest_path": str(manifest_output_path) if manifest_output_path else "",
        "proposal_path": str(stage2_context.proposal_path),
        "journal_path": str(stage2_context.journal_path) if stage2_context.journal_path else "",
        "research_question": stage2_context.research_question,
        "idea": stage2_context.idea,
        "theme_source": "stage1_proposal",
        "retrieval_theme_source": stage2_context.retrieval_theme_source,
        "retrieval_themes": [
            {"theme": item.theme, "description": item.description}
            for item in stage2_context.retrieval_themes
        ],
        "target_themes": [
            {"theme": item.theme, "description": item.description}
            for item in stage2_context.target_themes
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
        f"预估正文规模: {_format_int(payload['corpus_overview']['text_char_count'])} 字"
        f" | 文本 {_format_int(payload['corpus_overview']['text_file_count'])}"
        f" | 目录 {_format_int(payload['corpus_overview']['repo_dir_count'])}"
    )
    _print_timing_estimate(payload.get("timing_estimate"))
    print(f"阶段二工作目录: {payload['stage2_workspace_dir']}")
    if session_output_path:
        print(f"会话文件: {session_output_path}")
    if manifest_output_path:
        print(f"manifest 已写入: {manifest_output_path}")
    else:
        print("manifest 仅预览，未写入文件。")


def _emit_run_summary(summary: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print()
    print("阶段二执行完成:")
    print(f"项目: {summary['project_name']}")
    print(f"analysis_targets: {', '.join(summary['analysis_targets'])}")
    print(f"最终保留: {summary['piece_count']} 个 piece_id / {summary['record_count']} 条记录")
    for item in summary.get("targets") or []:
        print(
            f"  - {item['target']}"
            f" | fragments {item['fragment_count']}"
            f" | batches {item['batch_count']}"
            f" | candidate_pairs {item.get('candidate_pair_count', 0)}"
            f" | consensus {item['consensus_count']}"
            f" | disputes {item['dispute_count']}"
            f" | final {item['final_record_count']}"
        )


def _build_progress_printer(*, as_json: bool):
    stream = sys.stderr if as_json else sys.stdout

    def emit(event: dict[str, Any]) -> None:
        event_name = str(event.get("event") or "").strip()
        if not event_name:
            return

        if event_name == "pipeline_started":
            line = (
                f"[stage2] 开始执行 | 项目={event['project_name']}"
                f" | 目标数={event['target_count']}"
                f" | analysis_targets={', '.join(event.get('analysis_targets') or [])}"
            )
        elif event_name == "target_started":
            line = f"[stage2] 开始目标 {event['target']} | repo_dirs={event['repo_dir_count']}"
        elif event_name == "target_resumed":
            line = f"[stage2] 恢复目标 {event['target']} | {event['summary']}"
        elif event_name == "target_reused":
            line = f"[stage2] 复用缓存 {event['target']} | final_records={event['final_record_count']}"
        elif event_name == "fragments_ready":
            line = f"[stage2] {event['target']} 切片完成 | fragments={event['fragment_count']}"
        elif event_name == "batches_ready":
            line = f"[stage2] {event['target']} 批次就绪 | batches={event['batch_count']}"
        elif event_name == "candidate_pairs_ready":
            line = f"[stage2] {event['target']} 候选主题就绪 | pairs={event['candidate_pair_count']}"
        elif event_name == "slot_resume":
            stage = str(event.get("stage") or "targeted")
            stage_label = "粗筛" if stage == "coarse" else "精筛"
            line = f"[stage2] {event['target']} {event['slot']} {stage_label}复用缓存 | {event['completed']}/{event['total']}"
        elif event_name == "slot_progress":
            stage = str(event.get("stage") or "targeted")
            if stage == "coarse":
                line = (
                    f"[stage2] {event['target']} {event['slot']} 粗筛进度"
                    f" | {event['completed']}/{event['total']}"
                    f" | 当前批次={event['batch_id']}"
                )
            else:
                line = (
                    f"[stage2] {event['target']} {event['slot']} 精筛进度"
                    f" | {event['completed']}/{event['total']}"
                    f" | 当前批次={event['batch_id']}"
                    f" | 当前主题={event['theme']}"
                )
        elif event_name == "slot_waiting":
            stage = str(event.get("stage") or "targeted")
            stage_label = "粗筛" if stage == "coarse" else "精筛"
            line = (
                f"[stage2] {event['target']} {event['slot']} {stage_label}等待中"
                f" | 已完成={event['completed']}/{event['total']}"
                f" | in_flight={event['in_flight']}"
            )
        elif event_name == "consensus_ready":
            line = (
                f"[stage2] {event['target']} 双模型比对完成"
                f" | candidate_pairs={event.get('candidate_pair_count', 0)}"
                f" | consensus={event['consensus_count']}"
                f" | disputes={event['dispute_count']}"
            )
        elif event_name == "arbitration_resume":
            line = f"[stage2] {event['target']} llm3 复用缓存 | {event['completed']}/{event['total']}"
        elif event_name == "arbitration_progress":
            line = (
                f"[stage2] {event['target']} llm3 仲裁进度"
                f" | {event['completed']}/{event['total']}"
                f" | 当前={event['piece_id']}"
            )
        elif event_name == "arbitration_waiting":
            line = (
                f"[stage2] {event['target']} llm3 仲裁等待中"
                f" | 已完成={event['completed']}/{event['total']}"
                f" | in_flight={event['in_flight']}"
            )
        elif event_name == "target_completed":
            line = (
                f"[stage2] 完成目标 {event['target']}"
                f" | final_records={event['final_record_count']}"
                f" | final_pieces={event['final_piece_count']}"
            )
        elif event_name == "pipeline_completed":
            line = (
                f"[stage2] 全部完成 | 项目={event['project_name']}"
                f" | piece_count={event['piece_count']}"
                f" | record_count={event['record_count']}"
            )
        elif event_name == "pipeline_failed":
            line = f"[stage2] 执行失败 | 项目={event['project_name']} | error={event['error']}"
        else:
            line = f"[stage2] {json.dumps(event, ensure_ascii=False)}"

        print(line, file=stream, flush=True)

    return emit


def _should_run_stage2(args: argparse.Namespace) -> bool:
    if args.no_write or args.setup_only:
        return False
    if args.run:
        return True
    if args.json:
        return False
    return True


def main() -> int:
    args = build_parser().parse_args()
    outputs_root = _resolve_runtime_path(args.outputs, default_relative="outputs")
    if not outputs_root.exists():
        raise SystemExit(f"outputs 根目录不存在: {outputs_root}")

    if args.show_checkpoint or args.checkpoint_action:
        return _handle_checkpoint_command(args, outputs_root)
    if args.run and args.no_write:
        raise SystemExit("--run 不能与 --no-write 同时使用。")
    if args.run and args.setup_only:
        raise SystemExit("--run 不能与 --setup-only 同时使用。")

    project_name = args.project or _pick_project(outputs_root)
    project_dir, stage2_context = _resolve_project(outputs_root, project_name)
    ensure_stage2_workspace(project_dir)

    resumed_session = load_stage2_session(project_dir)
    if resumed_session:
        print()
        print(f"检测到已有阶段二会话: {stage2_session_path(project_dir)}")
        print(summarize_retrieval_progress(resumed_session.get("retrieval_progress")))

    kanripo_root = _resolve_runtime_path(args.kanripo_root, default_relative=DEFAULT_KANRIPO_ROOT)
    if not kanripo_root.exists():
        raise SystemExit(f"Kanripo 根目录不存在: {kanripo_root}")

    if not args.json:
        _print_intro(project_dir, stage2_context, kanripo_root)

    resolved_env_file = _resolved_env_file(args.env_file)
    model_slots = slot_summaries(dotenv_path=resolved_env_file)
    theme_count = len(stage2_context.target_themes)

    if args.targets:
        selection = resolve_analysis_targets(kanripo_root, raw_input=args.targets)
        if not selection.tokens:
            raise SystemExit("至少输入一个调研范围。")
        if selection.issues:
            details = "; ".join(f"{item.token}: {item.detail}" for item in selection.issues)
            raise SystemExit(f"调研范围无效: {details}")
        analysis_targets = list(selection.analysis_targets)
        overview = measure_corpus_overview(kanripo_root, selection)
        corpus_overview = overview.as_dict()
        timing_estimate = build_stage2_timing_estimate(
            corpus_overview=corpus_overview,
            theme_count=theme_count,
            model_slots=model_slots,
        )
        if not args.json:
            _print_corpus_overview(overview, timing_estimate)
    else:
        analysis_targets, corpus_overview, timing_estimate = _prompt_analysis_targets(
            kanripo_root,
            default_targets=analysis_targets_from_session(resumed_session),
            theme_count=theme_count,
            model_slots=model_slots,
        )

    manifest = build_stage2_manifest(
        workspace_root=WORKSPACE_ROOT,
        outputs_root=outputs_root,
        project_name=project_name,
        kanripo_root=kanripo_root,
        analysis_targets=analysis_targets,
        corpus_overview=corpus_overview,
        stage2_context=stage2_context,
        dotenv_path=resolved_env_file,
        model_slots=model_slots,
        timing_estimate=timing_estimate,
    )

    manifest_output_path: Path | None = None
    session_output_path: Path | None = None
    if not args.no_write:
        manifest_output_path = write_stage2_manifest(project_dir, manifest)
        session_output_path = save_stage2_session(
            project_dir,
            _build_session_payload(
                project_dir=project_dir,
                stage2_context=stage2_context,
                kanripo_root=kanripo_root,
                analysis_targets=analysis_targets,
                manifest_output_path=manifest_output_path,
            ),
        )

    should_run = _should_run_stage2(args)

    if not (should_run and args.json):
        _emit_summary(
            manifest,
            manifest_output_path=manifest_output_path,
            session_output_path=session_output_path,
            as_json=args.json,
        )
    if should_run:
        summary = run_stage2_pipeline(
            project_dir=project_dir,
            dotenv_path=resolved_env_file,
            max_fragments=args.max_fragments,
            llm1_workers=args.llm1_workers,
            llm2_workers=args.llm2_workers,
            llm3_workers=args.llm3_workers,
            force_rerun=args.force_rerun,
            progress_callback=_build_progress_printer(as_json=args.json),
        )
        _emit_run_summary(summary, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
