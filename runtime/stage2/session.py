"""管理阶段二原始文献运行时的工作目录、manifest 和检索断点状态。

仅维护当前 manifest.json（v2）路径；不读取或合并旧版 session.json 等旁路文件。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any

from .api_config import (
    STAGE2_MODELS,
    merged_env,
    screening_batch_char_limit,
    scaled_slot_worker_limit,
    slot_payload,
)
from .catalog import normalize_scope


STAGE2_MANIFEST_FILE = "manifest.json"
STAGE2_WORKSPACE_DIR = "_stage2"
RETRIEVAL_PROGRESS_VERSION = 1
STAGE2_ESTIMATED_REQUEST_SECONDS = 20
STAGE2_TARGETED_SCREENING_RATIO = 0.01
STAGE2_TIMING_UPPER_BOUND_MULTIPLIER = 1.5


@dataclass(frozen=True)
class ThemeItem:
    theme: str
    description: str = ""


@dataclass(frozen=True)
class Stage2Context:
    proposal_path: Path
    journal_path: Path | None
    idea: str
    research_question: str
    retrieval_theme_source: str
    retrieval_themes: tuple[ThemeItem, ...]
    target_themes: tuple[ThemeItem, ...]


def normalize_analysis_targets(
    analysis_targets: list[str] | tuple[str, ...] | None,
) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in analysis_targets or []:
        token = normalize_scope(str(raw))
        if not token or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _non_negative_int(value: object, *, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"').strip("'").strip()


def read_text_lines(path_like: str | Path) -> list[str]:
    path = Path(path_like).expanduser().resolve()
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def parse_frontmatter(path_like: str | Path) -> dict[str, Any]:
    lines = read_text_lines(path_like)
    if not lines or lines[0].strip() != "---":
        return {}

    payload: dict[str, Any] = {}
    index = 1
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped == "---":
            break
        if ":" not in line:
            index += 1
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip()
        normalized_value = value.strip()
        if normalized_value:
            payload[normalized_key] = _strip_quotes(normalized_value)
            index += 1
            continue

        items: list[str] = []
        index += 1
        while index < len(lines):
            nested_line = lines[index]
            nested_stripped = nested_line.strip()
            if nested_stripped == "---":
                break
            if not nested_stripped:
                index += 1
                continue
            if nested_line.lstrip() == nested_line and ":" in nested_line:
                break
            if nested_stripped.startswith("- "):
                item = _strip_quotes(nested_stripped[2:])
                if item:
                    items.append(item)
            index += 1
        payload[normalized_key] = items
        continue
    return payload


def extract_first_sentence(path_like: str | Path) -> str:
    lines = read_text_lines(path_like)
    if not lines:
        return ""

    in_frontmatter = False
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if index == 0 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue
        if not stripped or stripped.startswith("#"):
            continue
        return stripped
    return ""


def _frontmatter_string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_strip_quotes(str(item)) for item in value if _strip_quotes(str(item))]
    text = _strip_quotes(str(value or ""))
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except Exception:  # noqa: BLE001
            parsed = None
        if isinstance(parsed, list):
            return [_strip_quotes(str(item)) for item in parsed if _strip_quotes(str(item))]
    return [text]


def _resolve_stage2_retrieval_themes(*frontmatters: dict[str, Any]) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for frontmatter in frontmatters:
        for key in ("stage2_retrieval_themes", "retrieval_themes"):
            for item in _frontmatter_string_list(frontmatter.get(key)):
                if item in seen:
                    continue
                seen.add(item)
                resolved.append(item)
    return resolved


def infer_target_themes(
    *,
    retrieval_themes: list[str] | tuple[str, ...] | None = None,
    research_question: str,
    idea: str,
    settled_direction: str,
) -> tuple[list[ThemeItem], str]:
    themes: list[ThemeItem] = []
    explicit_themes = [str(item).strip() for item in retrieval_themes or [] if str(item).strip()]
    if explicit_themes:
        for theme in explicit_themes:
            if any(item.theme == theme for item in themes):
                continue
            themes.append(
                ThemeItem(
                    theme=theme,
                    description="阶段一明确给出的阶段二检索主题。",
                )
            )
        return themes, "stage1_frontmatter"

    for raw in (settled_direction, idea, research_question):
        theme = str(raw or "").strip()
        if not theme or any(item.theme == theme for item in themes):
            continue
        themes.append(
            ThemeItem(
                theme=theme,
                description="基于阶段一初步想法与研究方向提炼的初始主题。",
            )
        )
    return themes, "stage1_inference"


def load_stage2_context(project_dir: str | Path) -> Stage2Context | None:
    project_path = Path(project_dir).expanduser().resolve()
    proposal_path = project_path / "1_research_proposal.md"
    if not proposal_path.exists():
        return None

    journal_path = project_path / "1_journal_targeting.md"
    proposal_frontmatter = parse_frontmatter(proposal_path)
    journal_frontmatter = parse_frontmatter(journal_path) if journal_path.exists() else {}
    research_question = (
        proposal_frontmatter.get("settled_research_direction")
        or extract_first_sentence(proposal_path)
        or journal_frontmatter.get("settled_research_direction", "")
    )
    idea = proposal_frontmatter.get("idea") or journal_frontmatter.get("idea", "") or research_question
    settled_direction = proposal_frontmatter.get("settled_research_direction") or journal_frontmatter.get(
        "settled_research_direction",
        "",
    )
    retrieval_themes = _resolve_stage2_retrieval_themes(proposal_frontmatter, journal_frontmatter)
    target_themes, retrieval_theme_source = infer_target_themes(
        retrieval_themes=retrieval_themes,
        research_question=research_question,
        idea=idea,
        settled_direction=settled_direction,
    )

    return Stage2Context(
        proposal_path=proposal_path,
        journal_path=journal_path if journal_path.exists() else None,
        idea=idea,
        research_question=research_question,
        retrieval_theme_source=retrieval_theme_source,
        retrieval_themes=tuple(target_themes),
        target_themes=tuple(target_themes),
    )


def slot_summaries(
    *,
    dotenv_path: str | Path | None = None,
    env_values: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    resolved_env = env_values if env_values is not None else merged_env(dotenv_path)
    payloads: list[dict[str, Any]] = []
    for slot in sorted(STAGE2_MODELS.keys()):
        payload = slot_payload(slot, env_values=resolved_env)
        payloads.append(
            {
                "slot": payload["slot"],
                "provider": payload["provider"],
                "model": payload["model"],
                "base_url": payload["base_url"],
                "api_key_env": payload["api_key_env"],
                "api_keys_env": payload["api_keys_env"],
                "has_api_key": bool(payload["api_key"]) or bool(payload["api_keys"]),
                "rpm": payload["rpm"],
                "tpm": payload["tpm"],
                "max_concurrency": payload["max_concurrency"],
            }
        )
    return payloads


def _stage2_worker_limit(
    model_slots: list[dict[str, Any]],
    slot: str,
    *,
    dotenv_path: str | Path | None = None,
    env_values: dict[str, str] | None = None,
) -> int:
    for item in model_slots:
        if str(item.get("slot") or "") == slot:
            try:
                return max(1, int(item.get("max_concurrency") or 0))
            except (TypeError, ValueError):
                break
    return scaled_slot_worker_limit(slot, dotenv_path=dotenv_path, env_values=env_values)


def _estimate_target_batch_count(item: dict[str, Any]) -> int:
    explicit = _non_negative_int(item.get("batch_count"))
    if explicit:
        return explicit
    text_file_count = _non_negative_int(item.get("text_file_count"))
    text_char_count = _non_negative_int(item.get("text_char_count"))
    if not text_file_count and not text_char_count:
        return 0
    return max(text_file_count, math.ceil(text_char_count / screening_batch_char_limit()))


def _estimate_target_fragment_count(item: dict[str, Any]) -> int:
    explicit = _non_negative_int(item.get("fragment_count"))
    if explicit:
        return explicit
    return max(_non_negative_int(item.get("text_file_count")), _estimate_target_batch_count(item))


def _phase_seconds(*, request_count: int, workers: int, request_seconds: int) -> int:
    safe_request_count = max(0, int(request_count))
    if safe_request_count == 0:
        return 0
    safe_workers = max(1, int(workers))
    return math.ceil(safe_request_count / safe_workers) * max(1, int(request_seconds))


def _estimated_targeted_request_count(*, batch_count: int, ratio: float) -> int:
    safe_batch_count = max(0, int(batch_count))
    if safe_batch_count == 0:
        return 0
    safe_ratio = max(0.0, float(ratio))
    if safe_ratio <= 0:
        return 0
    return math.ceil(safe_batch_count * safe_ratio)


def build_stage2_timing_estimate(
    *,
    corpus_overview: dict[str, Any],
    theme_count: int,
    model_slots: list[dict[str, Any]],
    request_seconds: int = STAGE2_ESTIMATED_REQUEST_SECONDS,
    dotenv_path: str | Path | None = None,
    env_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    safe_theme_count = max(0, int(theme_count))
    resolved_request_seconds = max(1, int(request_seconds))
    llm1_workers = _stage2_worker_limit(
        model_slots,
        "llm1",
        dotenv_path=dotenv_path,
        env_values=env_values,
    )
    llm2_workers = _stage2_worker_limit(
        model_slots,
        "llm2",
        dotenv_path=dotenv_path,
        env_values=env_values,
    )

    target_estimates: list[dict[str, Any]] = []
    total_batch_count = 0
    total_fragment_count = 0
    total_targeted_batch_count = 0
    total_lower_bound_seconds = 0

    raw_targets = [item for item in corpus_overview.get("targets") or [] if isinstance(item, dict)]
    if not raw_targets and (
        _non_negative_int(corpus_overview.get("text_file_count"))
        or _non_negative_int(corpus_overview.get("text_char_count"))
        or _non_negative_int(corpus_overview.get("batch_count"))
        or _non_negative_int(corpus_overview.get("fragment_count"))
    ):
        raw_targets = [dict(corpus_overview)]

    for raw_target in raw_targets:
        item = raw_target if isinstance(raw_target, dict) else {}
        batch_count = _estimate_target_batch_count(item)
        fragment_count = _estimate_target_fragment_count(item)
        targeted_batch_count = _estimated_targeted_request_count(
            batch_count=batch_count,
            ratio=STAGE2_TARGETED_SCREENING_RATIO,
        )
        coarse_seconds = (
            _phase_seconds(request_count=batch_count, workers=llm1_workers, request_seconds=resolved_request_seconds)
            + _phase_seconds(request_count=batch_count, workers=llm2_workers, request_seconds=resolved_request_seconds)
        )
        lower_bound_seconds = (
            coarse_seconds
            + _phase_seconds(
                request_count=targeted_batch_count,
                workers=llm1_workers,
                request_seconds=resolved_request_seconds,
            )
            + _phase_seconds(
                request_count=targeted_batch_count,
                workers=llm2_workers,
                request_seconds=resolved_request_seconds,
            )
        )
        target_estimates.append(
            {
                "token": str(item.get("token") or ""),
                "batch_count": batch_count,
                "fragment_count": fragment_count,
                "targeted_batch_count": targeted_batch_count,
                "lower_bound_seconds": lower_bound_seconds,
            }
        )
        total_batch_count += batch_count
        total_fragment_count += fragment_count
        total_targeted_batch_count += targeted_batch_count
        total_lower_bound_seconds += lower_bound_seconds

    total_upper_bound_seconds = (
        0
        if total_lower_bound_seconds <= 0
        else math.ceil(total_lower_bound_seconds * STAGE2_TIMING_UPPER_BOUND_MULTIPLIER)
    )

    return {
        "request_seconds": resolved_request_seconds,
        "theme_count": safe_theme_count,
        "batch_count": total_batch_count,
        "fragment_count": total_fragment_count,
        "targeted_screening_ratio": STAGE2_TARGETED_SCREENING_RATIO,
        "upper_bound_multiplier": STAGE2_TIMING_UPPER_BOUND_MULTIPLIER,
        "targeted_batch_count": total_targeted_batch_count,
        "lower_bound_seconds": total_lower_bound_seconds,
        "upper_bound_seconds": total_upper_bound_seconds,
        "targets": target_estimates,
    }


def analysis_targets_from_manifest(manifest_payload: dict[str, Any]) -> list[str]:
    return normalize_analysis_targets(_as_string_list(manifest_payload.get("analysis_targets")))


def merge_analysis_target_lists(previous: list[str], incoming: list[str]) -> list[str]:
    prev = normalize_analysis_targets(previous)
    seen = set(prev)
    merged = list(prev)
    for token in normalize_analysis_targets(incoming):
        if token not in seen:
            seen.add(token)
            merged.append(token)
    return merged


def merge_corpus_overview_dicts(
    previous: dict[str, Any] | None,
    incoming: dict[str, Any],
) -> dict[str, Any]:
    if not previous:
        return dict(incoming)
    by_token: dict[str, dict[str, Any]] = {}
    for row in previous.get("targets") or []:
        if isinstance(row, dict) and row.get("token"):
            by_token[str(row["token"])] = dict(row)
    for row in incoming.get("targets") or []:
        if isinstance(row, dict) and row.get("token"):
            by_token[str(row["token"])] = dict(row)
    merged_targets = sorted(by_token.values(), key=lambda r: str(r.get("token", "")))
    repo_dir = sum(int(t.get("repo_dir_count") or 0) for t in merged_targets)
    text_files = sum(int(t.get("text_file_count") or 0) for t in merged_targets)
    chars = sum(int(t.get("text_char_count") or 0) for t in merged_targets)
    frags = sum(int(t.get("fragment_count") or 0) for t in merged_targets)
    batches = sum(int(t.get("batch_count") or 0) for t in merged_targets)
    return {
        "repo_dir_count": repo_dir,
        "text_file_count": text_files,
        "text_char_count": chars,
        "fragment_count": frags,
        "batch_count": batches,
        "targets": merged_targets,
    }


def _slim_model_slots_for_manifest(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slim: list[dict[str, Any]] = []
    for item in slots:
        slim.append(
            {
                "slot": item.get("slot"),
                "provider": item.get("provider"),
                "model": item.get("model"),
                "max_concurrency": item.get("max_concurrency"),
            }
        )
    return slim


def reconcile_retrieval_progress(
    analysis_targets: list[str] | tuple[str, ...] | None,
    *,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    targets = normalize_analysis_targets(list(analysis_targets or []))
    raw = progress if isinstance(progress, dict) else {}

    completed_targets = [
        item
        for item in normalize_analysis_targets(_as_string_list(raw.get("completed_targets")))
        if item in targets
    ]
    current_target = normalize_scope(str(raw.get("current_target") or ""))
    if current_target not in targets or current_target in completed_targets:
        current_target = ""

    pending_targets = [item for item in targets if item not in completed_targets and item != current_target]
    raw_status = str(raw.get("status") or "").strip().lower()
    has_checkpoint = bool(completed_targets or raw.get("current_cursor") or raw.get("last_piece_id"))
    status = "pending"
    if targets and len(completed_targets) == len(targets):
        status, current_target, pending_targets = "completed", "", []
    elif current_target:
        status = raw_status if raw_status in {"running", "paused"} else "running"
    elif has_checkpoint:
        status = raw_status if raw_status in {"running", "paused"} else "paused"

    return {
        "version": RETRIEVAL_PROGRESS_VERSION,
        "status": status,
        "analysis_targets": targets,
        "total_targets": len(targets),
        "completed_targets": completed_targets,
        "pending_targets": pending_targets,
        "current_target": current_target,
        "current_cursor": str(raw.get("current_cursor") or ""),
        "last_piece_id": str(raw.get("last_piece_id") or ""),
        "completed_piece_count": _non_negative_int(raw.get("completed_piece_count")),
        "run_count": _non_negative_int(raw.get("run_count")),
        "notes": str(raw.get("notes") or ""),
        "updated_at": str(raw.get("updated_at") or ""),
    }


def normalize_stage2_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    analysis_targets = normalize_analysis_targets(_as_string_list(payload.get("analysis_targets")))
    raw_progress = payload.get("retrieval_progress")
    status = str(payload.get("status") or "").strip() or "configured"

    content = dict(payload)
    content["stage2_manifest_version"] = 2
    content["status"] = status
    if analysis_targets:
        content["analysis_targets"] = analysis_targets
    else:
        content.pop("analysis_targets", None)
    if analysis_targets or isinstance(raw_progress, dict):
        content["retrieval_progress"] = reconcile_retrieval_progress(
            analysis_targets,
            progress=raw_progress if isinstance(raw_progress, dict) else None,
        )
    else:
        content.pop("retrieval_progress", None)
    for key in ("last_run_note", "last_run_at", "updated_at"):
        value = str(payload.get(key) or "").strip()
        if value:
            content[key] = value
        else:
            content.pop(key, None)
    return content


def update_retrieval_progress(
    analysis_targets: list[str] | tuple[str, ...] | None,
    *,
    progress: dict[str, Any] | None = None,
    action: str,
    target: str | None = None,
    cursor: str | None = None,
    piece_id: str | None = None,
    note: str | None = None,
    completed_piece_delta: int = 0,
) -> dict[str, Any]:
    if completed_piece_delta < 0:
        raise ValueError("completed_piece_delta 不能为负数。")

    normalized_targets = normalize_analysis_targets(list(analysis_targets or []))
    if not normalized_targets and action != "reset":
        raise ValueError("当前 session 尚未配置可检索的 analysis_targets。")

    current = reconcile_retrieval_progress(normalized_targets, progress=progress)
    normalized_target = normalize_scope(target) if target else ""
    if normalized_target and normalized_target not in normalized_targets:
        raise ValueError(f"无效目标，未出现在当前 analysis_targets 中: {normalized_target}")

    updated = dict(current)
    updated["updated_at"] = _now_iso()
    updated["completed_piece_count"] = current["completed_piece_count"] + completed_piece_delta

    if cursor is not None:
        updated["current_cursor"] = cursor
    if piece_id is not None:
        updated["last_piece_id"] = piece_id
    if note is not None:
        updated["notes"] = note.strip()

    if action == "reset":
        return reconcile_retrieval_progress(
            normalized_targets,
            progress={
                "status": "pending",
                "completed_piece_count": 0,
                "run_count": 0,
                "notes": updated["notes"] if note is not None else "",
                "updated_at": updated["updated_at"],
            },
        )

    selected_target = normalized_target or current["current_target"]
    if action == "start":
        selected_target = selected_target or (current["pending_targets"][0] if current["pending_targets"] else "")
        if not selected_target:
            raise ValueError("没有可启动的检索目标。")
        if selected_target in current["completed_targets"]:
            raise ValueError(f"目标已完成，无需重复启动: {selected_target}")
        if current["current_target"] != selected_target:
            updated["run_count"] = current["run_count"] + 1
        updated["status"] = "running"
        updated["current_target"] = selected_target
        return reconcile_retrieval_progress(normalized_targets, progress=updated)

    if action == "checkpoint":
        if not selected_target:
            raise ValueError("checkpoint 需要当前目标；请先 start 或显式提供 target。")
        if selected_target in current["completed_targets"]:
            raise ValueError(f"目标已完成，不能继续 checkpoint: {selected_target}")
        updated["status"] = "running"
        updated["current_target"] = selected_target
        return reconcile_retrieval_progress(normalized_targets, progress=updated)

    if action == "pause":
        if normalized_target:
            updated["current_target"] = normalized_target
        updated["status"] = "paused"
        return reconcile_retrieval_progress(normalized_targets, progress=updated)

    if action == "complete":
        if not selected_target:
            raise ValueError("complete 需要当前目标；请先 start 或显式提供 target。")
        if selected_target not in current["completed_targets"]:
            updated["completed_targets"] = [*current["completed_targets"], selected_target]
        updated["current_target"] = ""
        updated["status"] = "completed" if len(updated["completed_targets"]) == len(normalized_targets) else "paused"
        return reconcile_retrieval_progress(normalized_targets, progress=updated)

    raise ValueError(f"不支持的 retrieval_progress action: {action}")


def summarize_retrieval_progress(progress: dict[str, Any] | None) -> str:
    if not isinstance(progress, dict):
        return "检索断点: 未记录"

    normalized = reconcile_retrieval_progress(progress.get("analysis_targets"), progress=progress)
    total = int(normalized["total_targets"])
    completed = len(normalized["completed_targets"])
    current_target = normalized["current_target"] or "(无)"
    cursor = normalized["current_cursor"] or "(空)"
    piece_id = normalized["last_piece_id"] or "(空)"
    return (
        f"检索断点: {completed}/{total} 已完成"
        f" | 状态={normalized['status']}"
        f" | 当前目标={current_target}"
        f" | cursor={cursor}"
        f" | last_piece_id={piece_id}"
    )


def update_stage2_manifest_checkpoint(
    project_dir: str | Path,
    *,
    action: str,
    target: str | None = None,
    cursor: str | None = None,
    piece_id: str | None = None,
    note: str | None = None,
    completed_piece_delta: int = 0,
) -> dict[str, Any]:
    manifest_payload = load_stage2_manifest(project_dir)
    analysis_targets = analysis_targets_from_manifest(manifest_payload)
    manifest_payload["retrieval_progress"] = update_retrieval_progress(
        analysis_targets,
        progress=manifest_payload.get("retrieval_progress"),
        action=action,
        target=target,
        cursor=cursor,
        piece_id=piece_id,
        note=note,
        completed_piece_delta=completed_piece_delta,
    )
    write_stage2_manifest(project_dir, manifest_payload)
    return manifest_payload


def stage2_workspace_dir(project_dir: str | Path) -> Path:
    return Path(project_dir).expanduser().resolve() / STAGE2_WORKSPACE_DIR


def ensure_stage2_workspace(project_dir: str | Path) -> Path:
    path = stage2_workspace_dir(project_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_json_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}


def load_stage2_manifest(project_dir: str | Path) -> dict[str, Any]:
    payload = _read_json_payload(manifest_path(project_dir))
    if not payload:
        return {}
    return normalize_stage2_manifest(payload)


def build_stage2_manifest(
    *,
    outputs_root: str | Path,
    project_name: str,
    kanripo_root: str | Path,
    analysis_targets: list[str],
    corpus_overview: dict[str, Any],
    stage2_context: Stage2Context,
    dotenv_path: str | Path | None = None,
    env_values: dict[str, str] | None = None,
    model_slots: list[dict[str, Any]] | None = None,
    previous_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    outputs = Path(outputs_root).expanduser().resolve()
    project_dir = outputs / project_name
    resolved_model_slots = list(model_slots) if model_slots is not None else slot_summaries(
        dotenv_path=dotenv_path,
        env_values=env_values,
    )
    prev = previous_manifest if isinstance(previous_manifest, dict) else None
    merged_targets = merge_analysis_target_lists(
        analysis_targets_from_manifest(prev) if prev else [],
        analysis_targets,
    )
    merged_overview = merge_corpus_overview_dicts(prev.get("corpus_overview") if prev else None, corpus_overview)
    resolved_timing_estimate = build_stage2_timing_estimate(
        corpus_overview=merged_overview,
        theme_count=len(stage2_context.target_themes),
        model_slots=resolved_model_slots,
        dotenv_path=dotenv_path,
        env_values=env_values,
    )
    preserved_generated = str((prev or {}).get("generated_at") or "").strip()
    return {
        "stage2_manifest_version": 2,
        "generated_at": preserved_generated or _now_iso(),
        "project_name": project_name,
        "project_dir": str(project_dir),
        "proposal_path": str(stage2_context.proposal_path),
        "journal_path": str(stage2_context.journal_path) if stage2_context.journal_path else "",
        "research_question": stage2_context.research_question,
        "idea": stage2_context.idea,
        "retrieval_theme_source": stage2_context.retrieval_theme_source,
        "target_themes": [
            {
                "theme": item.theme,
                "description": item.description,
            }
            for item in stage2_context.target_themes
        ],
        "kanripo_root": str(Path(kanripo_root).expanduser().resolve()),
        "analysis_targets": merged_targets,
        "corpus_overview": merged_overview,
        "model_slots": _slim_model_slots_for_manifest(resolved_model_slots),
        "timing_estimate": resolved_timing_estimate,
        "status": "configured",
        "retrieval_progress": reconcile_retrieval_progress(
            merged_targets,
            progress=(prev.get("retrieval_progress") if prev else None),
        ),
    }


def manifest_path(project_dir: str | Path) -> Path:
    return stage2_workspace_dir(project_dir) / STAGE2_MANIFEST_FILE


def write_stage2_manifest(project_dir: str | Path, payload: dict[str, Any]) -> Path:
    ensure_stage2_workspace(project_dir)
    path = manifest_path(project_dir)
    content_payload = normalize_stage2_manifest(payload)
    content_payload["updated_at"] = _now_iso()
    content = json.dumps(content_payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(content, encoding="utf-8")
    return path
