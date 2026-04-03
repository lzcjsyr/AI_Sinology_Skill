"""提供阶段二外部入口，负责确认调研范围并写入 stage2 manifest。"""

from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import sys
from typing import Any
import unicodedata

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from runtime.stage2.catalog import measure_corpus_overview, resolve_analysis_targets
from runtime.stage2.runner import run_stage2_pipeline
from runtime.stage2.session import (
    Stage2Context,
    ThemeItem,
    analysis_targets_from_manifest,
    build_stage2_timing_estimate,
    build_stage2_manifest,
    ensure_stage2_workspace,
    load_stage2_context,
    load_stage2_manifest,
    manifest_path,
    slot_summaries,
    stage2_workspace_dir,
    summarize_retrieval_progress,
    update_stage2_manifest_checkpoint,
    write_stage2_manifest,
)

DEFAULT_KANRIPO_ROOT = "data/kanripo_repos"
DEFAULT_ENV_FILE = ".env"
STAGE2_GUIDE_PATH = Path(__file__).resolve().parent / "docs" / "kanripo_family_guide.md"

# 阶段一写入的占位说明；CLI 只展示主题句，不重复这类套话
_THEME_DESC_BOILERPLATE = frozenset(
    {
        "阶段一明确给出的阶段二检索主题。",
        "基于阶段一初步想法与研究方向提炼的初始主题。",
    }
)

_ANSI_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
}


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


def _supports_ansi(stream: Any) -> bool:
    if os.getenv("NO_COLOR") is not None:
        return False
    if os.getenv("TERM", "").lower() == "dumb":
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def _style(text: str, *styles: str, stream: Any = sys.stdout) -> str:
    if not styles or not _supports_ansi(stream):
        return text
    prefix = "".join(_ANSI_CODES[name] for name in styles if name in _ANSI_CODES and name != "reset")
    if not prefix:
        return text
    return f"{prefix}{text}{_ANSI_CODES['reset']}"


def _section_title(title: str, *, stream: Any = sys.stdout) -> str:
    return _style(f"== {title} ==", "bold", "cyan", stream=stream)


def _label(label: str, *, stream: Any = sys.stdout) -> str:
    return _style(label, "bold", stream=stream)


def _muted(text: str, *, stream: Any = sys.stdout) -> str:
    return _style(text, "dim", stream=stream)


def _bullet(text: str, *, stream: Any = sys.stdout, tone: str = "cyan") -> str:
    return f"  {_style('•', tone, stream=stream)} {text}"


def _kv(label: str, value: object, *, stream: Any = sys.stdout, width: int = 14) -> str:
    return f"{_label(label.ljust(width), stream=stream)} {value}"


def _kv_display(label: str, value: object, *, label_width: int, stream: Any = sys.stdout) -> str:
    """按终端显示宽度对齐标签列（中日文等宽字符），便于多行值纵向对齐。"""
    return f"{_label(_pad_display(label, label_width), stream=stream)}  {value}"


def _soft_section_break(*, stream: Any = sys.stdout) -> None:
    print(file=stream)


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
    return width


def _pad_display(text: str, width: int) -> str:
    return text + (" " * max(0, width - _display_width(text)))


def _render_box(title: str, lines: list[str]) -> str:
    inner_width = max([_display_width(title), *(_display_width(line) for line in lines)], default=0)
    rendered = [
        f"┌{'─' * (inner_width + 2)}┐",
        f"│ {_pad_display(title, inner_width)} │",
        f"├{'─' * (inner_width + 2)}┤",
    ]
    rendered.extend(f"│ {_pad_display(line, inner_width)} │" for line in lines)
    rendered.append(f"└{'─' * (inner_width + 2)}┘")
    return "\n".join(rendered)


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
        help="直接更新 outputs/<project>/_stage2/2_stage2_manifest.json 中的检索断点，不重新进入配置流程。",
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
    print(_section_title("可用项目", stream=sys.stdout))
    for index, project_name in enumerate(projects, start=1):
        status = inspect_project(outputs_root, project_name)
        print(_bullet(
            f"{index}. {project_name}"
            f" | 下一阶段={status.next_stage}"
            f" | 已完成到阶段={status.highest_completed_stage}"
        , stream=sys.stdout))

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
    return str(Path.cwd() / DEFAULT_ENV_FILE)


def _resolve_runtime_path(raw_value: str, *, default_relative: str) -> Path:
    candidate = Path(raw_value if raw_value else default_relative).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    if raw_value and raw_value != default_relative:
        return candidate.resolve()
    return (WORKSPACE_ROOT / default_relative).resolve()


def _path_rel_workspace(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(WORKSPACE_ROOT.resolve()))
    except ValueError:
        return str(path)


def _hr(*, stream: Any = sys.stdout, width: int = 52) -> None:
    print(_muted("─" * width, stream=stream), file=stream)


def _theme_line_for_cli(item: ThemeItem) -> str:
    desc = (item.description or "").strip()
    if desc and desc not in _THEME_DESC_BOILERPLATE:
        return f"{item.theme} · {desc}"
    return item.theme


def _print_intro(
    stage2_context: Stage2Context,
    kanripo_root: Path,
    model_slots: list[dict[str, Any]],
) -> None:
    stream = sys.stdout
    print()
    print(_section_title("阶段二配置", stream=stream))
    path_tag_w = max(_display_width("数据简介"), _display_width("数据源"))
    _hr(stream=stream)
    print(
        _kv_display(
            "数据简介",
            _muted(_path_rel_workspace(STAGE2_GUIDE_PATH), stream=stream),
            label_width=path_tag_w,
            stream=stream,
        )
    )
    print(
        _kv_display(
            "数据源",
            _muted(_path_rel_workspace(kanripo_root), stream=stream),
            label_width=path_tag_w,
            stream=stream,
        )
    )
    _hr(stream=stream)

    slot_labels = {
        "llm1": "模型1（第一轮筛选）",
        "llm2": "模型2（第二轮筛选）",
        "llm3": "模型3（仲裁）",
    }
    model_label_w = max(_display_width(label) for label in slot_labels.values())

    _soft_section_break(stream=stream)
    for payload in model_slots:
        slot = str(payload.get("slot") or "")
        label = slot_labels.get(slot, slot)
        prov = str(payload.get("provider") or "").strip()
        model = str(payload.get("model") or "").strip()
        detail = f"{prov} · {model}" if prov else model
        print(_kv_display(label, detail, label_width=model_label_w, stream=stream))

    rq = stage2_context.research_question or "（未填写）"
    # 不与模型标签列同宽，避免「研究问题」与正文之间空白过大
    rq_tag_w = _display_width("研究问题")
    _soft_section_break(stream=stream)
    print(_kv_display("研究问题", rq, label_width=rq_tag_w, stream=stream))

    theme_title = (
        "阶段一检索主题"
        if stage2_context.retrieval_theme_source == "stage1_frontmatter"
        else "阶段一提炼主题"
    )
    _soft_section_break(stream=stream)
    print(_label(f"{theme_title}:", stream=stream), file=stream)
    for item in stage2_context.retrieval_themes:
        print(_bullet(_theme_line_for_cli(item), stream=stream))


def _print_selection_errors(issues: tuple[Any, ...]) -> None:
    stream = sys.stdout
    print()
    print(_section_title("输入有误", stream=stream))
    print(_muted("请修正以下目标后重新输入。", stream=stream))
    for issue in issues:
        print(_bullet(f"{issue.token}: {issue.detail}", stream=stream, tone="red"))


def _format_int(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _clip_text(text: object, max_chars: int = 40) -> str:
    s = str(text or "")
    if len(s) <= max_chars:
        return s
    return s[: max(0, max_chars - 1)] + "…"


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
    line = (
        f"估时 | 主题 {_format_int(timing_estimate.get('theme_count', 0))}"
        f" | 片段 {_format_int(timing_estimate.get('fragment_count', 0))}"
        f" | 批次 {_format_int(timing_estimate.get('batch_count', 0))}"
        f" | 预估耗时 {_format_duration(timing_estimate.get('lower_bound_seconds', 0))}"
        f" - {_format_duration(timing_estimate.get('upper_bound_seconds', 0))}"
        f"（按单次请求 {_format_int(timing_estimate.get('request_seconds', 0))} 秒）"
    )
    print(_style(line, "yellow", stream=sys.stdout))


def _print_corpus_overview(overview: Any, timing_estimate: dict[str, Any] | None = None) -> None:
    lines = ["正文字符数仅供预估工作量使用。", ""]
    for item in overview.targets:
        level_label = "类目" if item.level == "family" else "目录"
        lines.extend(
            [
                f"{item.token} [{level_label}]",
                f"  目录数      {_format_int(item.repo_dir_count)}",
                f"  文本数      {_format_int(item.text_file_count)}",
                f"  正文规模    {_format_int(item.text_char_count)} 字",
                "",
            ]
        )
    lines.extend(
        [
            "合计",
            f"  目录数      {_format_int(overview.repo_dir_count)}",
            f"  文本数      {_format_int(overview.text_file_count)}",
            f"  正文规模    {_format_int(overview.text_char_count)} 字",
        ]
    )
    if timing_estimate:
        lines.extend(
            [
                "",
                "估时",
                f"  主题数      {_format_int(timing_estimate.get('theme_count', 0))}",
                f"  片段数      {_format_int(timing_estimate.get('fragment_count', 0))}",
                f"  批次数      {_format_int(timing_estimate.get('batch_count', 0))}",
                (
                    "  预估耗时    "
                    f"{_format_duration(timing_estimate.get('lower_bound_seconds', 0))}"
                    f" - {_format_duration(timing_estimate.get('upper_bound_seconds', 0))}"
                ),
                f"  单次请求    {_format_int(timing_estimate.get('request_seconds', 0))} 秒",
            ]
        )
    print()
    print(_render_box("调研范围统计", lines))


def _prompt_analysis_targets(
    kanripo_root: Path,
    *,
    default_targets: list[str] | None = None,
    theme_count: int,
    model_slots: list[dict[str, Any]],
) -> tuple[list[str], dict[str, object], dict[str, Any]]:
    default_value = " ".join(default_targets or []) or None
    print()
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


def _manifest_snapshot_payload(project_dir: Path, manifest_data: dict[str, Any]) -> dict[str, Any]:
    progress = manifest_data.get("retrieval_progress")
    return {
        "project_name": project_dir.name,
        "project_dir": str(project_dir),
        "stage2_workspace_dir": str(stage2_workspace_dir(project_dir)),
        "analysis_targets": analysis_targets_from_manifest(manifest_data),
        "retrieval_progress": progress or {},
        "summary": summarize_retrieval_progress(progress),
        "manifest_path": str(manifest_path(project_dir)),
    }


def _handle_checkpoint_command(args: argparse.Namespace, outputs_root: Path) -> int:
    if not args.project:
        raise SystemExit("checkpoint 模式必须提供 --project。")

    project_dir, _ = _resolve_project(outputs_root, args.project)
    ensure_stage2_workspace(project_dir)

    if args.show_checkpoint:
        payload = _manifest_snapshot_payload(project_dir, load_stage2_manifest(project_dir))
    else:
        try:
            manifest_data = update_stage2_manifest_checkpoint(
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
        payload = _manifest_snapshot_payload(project_dir, manifest_data)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print()
    print(_section_title("断点摘要", stream=sys.stdout))
    print(_kv("项目", payload["project_name"], stream=sys.stdout))
    print(payload["summary"])
    if payload["analysis_targets"]:
        print(_kv("analysis_targets", ", ".join(payload["analysis_targets"]), stream=sys.stdout))
    print(_kv("manifest 文件", payload["manifest_path"], stream=sys.stdout))
    return 0


def _emit_summary(
    manifest: dict[str, Any],
    *,
    manifest_output_path: Path | None,
    as_json: bool,
) -> None:
    payload = dict(manifest)
    payload["manifest_path"] = str(manifest_output_path) if manifest_output_path else ""

    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    stream = sys.stdout
    print()
    print(_section_title("配置摘要", stream=stream))
    print(_kv("项目", payload["project_name"], stream=stream))
    print(_kv("analysis_targets", ", ".join(payload["analysis_targets"]), stream=stream))
    print(
        _kv(
            "预估正文规模",
            f"{_format_int(payload['corpus_overview']['text_char_count'])} 字"
            f" | 文本 {_format_int(payload['corpus_overview']['text_file_count'])}"
            f" | 目录 {_format_int(payload['corpus_overview']['repo_dir_count'])}",
            stream=stream,
        )
    )
    _print_timing_estimate(payload.get("timing_estimate"))
    print(_kv("阶段二工作目录", payload["stage2_workspace_dir"], stream=stream))
    if manifest_output_path:
        print(_kv("manifest", f"已写入 {manifest_output_path}", stream=stream))
    else:
        print(_kv("manifest", "仅预览，未写入文件。", stream=stream))


def _emit_run_summary(summary: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    stream = sys.stdout
    print()
    print(_section_title("阶段二执行完成", stream=stream))
    print(_kv("项目", summary["project_name"], stream=stream))
    print(_kv("analysis_targets", ", ".join(summary["analysis_targets"]), stream=stream))
    print(_kv("最终保留", f"{summary['piece_count']} 个 piece_id / {summary['record_count']} 条记录", stream=stream))
    for item in summary.get("targets") or []:
        print(_bullet(
            f"{item['target']} · 切片 {item['fragment_count']} · 批 {item['batch_count']}"
            f" · 候选 {item.get('candidate_pair_count', 0)} · 一致 {item['consensus_count']}"
            f" · 分歧 {item['dispute_count']} · 保留 {item['final_record_count']}"
        , stream=stream, tone="green"))


def _build_progress_printer(*, as_json: bool):
    stream = sys.stderr if as_json else sys.stdout
    event_styles = {
        "pipeline_started": ("bold", "cyan"),
        "pipeline_completed": ("bold", "green"),
        "pipeline_failed": ("bold", "red"),
        "target_started": ("bold", "blue"),
        "target_completed": ("green",),
        "target_resumed": ("yellow",),
        "target_reused": ("yellow",),
        "slot_waiting": ("dim",),
        "arbitration_waiting": ("dim",),
    }

    slot_labels = {"llm1": "模型1", "llm2": "模型2", "llm3": "模型3"}
    ctx_target: str | None = None
    last_waiting_line: str | None = None

    def reset_ctx() -> None:
        nonlocal ctx_target
        ctx_target = None

    def subline(target: str, detail: str) -> str:
        """同一检索目标下，首行带「▸ 目标」，后续行缩进，避免重复目标名。"""
        nonlocal ctx_target
        if ctx_target != target:
            ctx_target = target
            return f"▸ {target}  ·  {detail}"
        return f"    ·  {detail}"

    def emit(event: dict[str, Any]) -> None:
        nonlocal last_waiting_line, ctx_target
        event_name = str(event.get("event") or "").strip()
        if not event_name:
            return

        line: str

        if event_name == "pipeline_started":
            reset_ctx()
            targets = [str(t) for t in (event.get("analysis_targets") or []) if str(t).strip()]
            if len(targets) <= 4:
                tail = "、".join(targets) if targets else "（无）"
            else:
                tail = "、".join(targets[:4]) + f" 等共 {len(targets)} 个"
            line = f"阶段二 · {event['project_name']} · {event['target_count']} 个目标 · {tail}"
        elif event_name == "target_started":
            line = f"▸ {event['target']}  ·  文献目录 {_format_int(event['repo_dir_count'])} 个"
            ctx_target = str(event["target"])
        elif event_name == "target_resumed":
            ctx_target = str(event["target"])
            line = f"▸ {event['target']}  ·  续跑 {_clip_text(event['summary'], 72)}"
        elif event_name == "target_reused":
            ctx_target = str(event["target"])
            line = f"▸ {event['target']}  ·  复用缓存，已保留 {_format_int(event['final_record_count'])} 条"
        elif event_name == "fragments_ready":
            line = subline(event["target"], f"切片 {_format_int(event['fragment_count'])} 段")
        elif event_name == "batches_ready":
            line = subline(event["target"], f"分批 {_format_int(event['batch_count'])} 批")
        elif event_name == "candidate_pairs_ready":
            line = subline(event["target"], f"候选主题 {_format_int(event['candidate_pair_count'])} 对")
        elif event_name == "slot_resume":
            stage = str(event.get("stage") or "targeted")
            stage_label = "粗筛" if stage == "coarse" else "精筛"
            lab = slot_labels.get(str(event.get("slot")), str(event.get("slot")))
            line = subline(
                event["target"],
                f"续跑 {lab}·{stage_label} {_format_int(event['completed'])}/{_format_int(event['total'])}",
            )
        elif event_name == "slot_progress":
            stage = str(event.get("stage") or "targeted")
            lab = slot_labels.get(str(event.get("slot")), str(event.get("slot")))
            if stage == "coarse":
                line = subline(
                    event["target"],
                    f"{lab} 粗筛 {_format_int(event['completed'])}/{_format_int(event['total'])} · {event['batch_id']}",
                )
            else:
                th = _clip_text(event.get("theme"), 44)
                line = subline(
                    event["target"],
                    f"{lab} 精筛 {_format_int(event['completed'])}/{_format_int(event['total'])} · {event['batch_id']} · {th}",
                )
        elif event_name == "slot_waiting":
            stage = str(event.get("stage") or "targeted")
            stage_label = "粗筛" if stage == "coarse" else "精筛"
            lab = slot_labels.get(str(event.get("slot")), str(event.get("slot")))
            line = subline(
                event["target"],
                f"限流等待 · {lab}·{stage_label} {_format_int(event['completed'])}/{_format_int(event['total'])} · 并发 {event['in_flight']}",
            )
        elif event_name == "consensus_ready":
            line = subline(
                event["target"],
                f"双模型一致 {_format_int(event['consensus_count'])} · 分歧 {_format_int(event['dispute_count'])}",
            )
        elif event_name == "arbitration_resume":
            line = subline(
                event["target"],
                f"续跑 模型3 仲裁 {_format_int(event['completed'])}/{_format_int(event['total'])}",
            )
        elif event_name == "arbitration_progress":
            line = subline(
                event["target"],
                f"模型3 仲裁 {_format_int(event['completed'])}/{_format_int(event['total'])} · {event['piece_id']}",
            )
        elif event_name == "arbitration_waiting":
            line = subline(
                event["target"],
                f"限流等待 · 模型3 仲裁 {_format_int(event['completed'])}/{_format_int(event['total'])} · 并发 {event['in_flight']}",
            )
        elif event_name == "target_completed":
            line = (
                f"✓ {event['target']} 完成 · 保留 {_format_int(event['final_record_count'])} 条"
                f" · {_format_int(event['final_piece_count'])} 段"
            )
            ctx_target = None
        elif event_name == "pipeline_completed":
            reset_ctx()
            line = (
                f"阶段二完成 · {event['project_name']}"
                f" · {_format_int(event['piece_count'])} 段 · {_format_int(event['record_count'])} 条"
            )
        elif event_name == "pipeline_failed":
            reset_ctx()
            line = f"阶段二失败 · {event['project_name']} · {event['error']}"
        else:
            line = f"阶段二 · {json.dumps(event, ensure_ascii=False)}"

        if event_name in ("slot_waiting", "arbitration_waiting"):
            if line == last_waiting_line:
                return
            last_waiting_line = line
        else:
            last_waiting_line = None

        print(_style(line, *event_styles.get(event_name, ()), stream=stream), file=stream, flush=True)

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

    resumed_manifest = load_stage2_manifest(project_dir)
    if resumed_manifest and not args.json:
        print()
        print(_section_title("续跑状态", stream=sys.stdout))
        print(_kv("manifest", manifest_path(project_dir), stream=sys.stdout))
        print(summarize_retrieval_progress(resumed_manifest.get("retrieval_progress")))

    kanripo_root = _resolve_runtime_path(args.kanripo_root, default_relative=DEFAULT_KANRIPO_ROOT)
    if not kanripo_root.exists():
        raise SystemExit(f"Kanripo 根目录不存在: {kanripo_root}")

    resolved_env_file = _resolved_env_file(args.env_file)
    model_slots = slot_summaries(dotenv_path=resolved_env_file)

    if not args.json:
        _print_intro(stage2_context, kanripo_root, model_slots)
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
            default_targets=analysis_targets_from_manifest(resumed_manifest),
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
    if not args.no_write:
        manifest_output_path = write_stage2_manifest(project_dir, manifest)

    should_run = _should_run_stage2(args)

    if not (should_run and args.json):
        _emit_summary(
            manifest,
            manifest_output_path=manifest_output_path,
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
