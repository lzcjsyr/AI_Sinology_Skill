from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .api_config import STAGE3_MODELS, merged_env, slot_payload
from .catalog import list_available_scope_dirs, list_available_scope_options, normalize_scope


STAGE3_MANIFEST_FILE = "3_stage3_manifest.json"
STAGE3_WORKSPACE_DIR = "_stage3"
STAGE3_WORKSPACE_MANIFEST_FILE = "manifest.json"
STAGE3_SESSION_FILE = "session.json"
RETRIEVAL_PROGRESS_VERSION = 1


@dataclass(frozen=True)
class ThemeItem:
    theme: str
    description: str = ""


@dataclass(frozen=True)
class ProposalContext:
    proposal_path: Path
    idea: str
    target_themes: tuple[ThemeItem, ...]


@dataclass(frozen=True)
class ScopeSelection:
    scope_families: tuple[str, ...]
    repo_dirs: tuple[str, ...]
    missing_scope_families: tuple[str, ...]
    missing_repo_dirs: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.missing_scope_families and not self.missing_repo_dirs


def analysis_targets_from_values(
    scope_families: list[str] | tuple[str, ...] | None,
    repo_dirs: list[str] | tuple[str, ...] | None,
) -> list[str]:
    return unique_normalized(
        [*(scope_families or []), *(repo_dirs or [])],
        normalizer=normalize_scope,
    )


def split_csv(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    normalized = str(raw_value).replace("，", ",").replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def unique_normalized(items: list[str], *, normalizer=str.strip) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        item = normalizer(raw)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
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


def read_front_matter_lines(proposal_path: str | Path) -> list[str]:
    path = Path(proposal_path).expanduser().resolve()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return []

    front_matter: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return front_matter
        front_matter.append(line.rstrip("\n"))
    return []


def parse_idea_from_proposal(proposal_path: str | Path) -> str:
    for line in read_front_matter_lines(proposal_path):
        stripped = line.strip()
        if stripped.startswith("idea:"):
            return _strip_quotes(stripped.split(":", 1)[1])
    return ""


def parse_target_themes_from_proposal(proposal_path: str | Path) -> list[ThemeItem]:
    front_matter = read_front_matter_lines(proposal_path)
    if not front_matter:
        return []

    themes: list[ThemeItem] = []
    current: dict[str, str] | None = None
    in_target_themes = False
    target_indent = 0

    for line in front_matter:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if stripped.startswith("target_themes:"):
            in_target_themes = True
            target_indent = indent
            continue

        if not in_target_themes:
            continue

        if stripped and indent <= target_indent and not stripped.startswith("-"):
            break

        if not stripped:
            continue

        if stripped.startswith("- "):
            if current and current.get("theme"):
                themes.append(
                    ThemeItem(
                        theme=current["theme"].strip(),
                        description=current.get("description", "").strip(),
                    )
                )

            payload = stripped[2:].strip()
            if payload.startswith("theme:"):
                current = {
                    "theme": _strip_quotes(payload.split(":", 1)[1]),
                    "description": "",
                }
            else:
                current = {
                    "theme": _strip_quotes(payload),
                    "description": "",
                }
            continue

        if stripped.startswith("theme:"):
            if current is None:
                current = {"theme": "", "description": ""}
            current["theme"] = _strip_quotes(stripped.split(":", 1)[1])
            continue

        if stripped.startswith("description:"):
            if current is None:
                current = {"theme": "", "description": ""}
            current["description"] = _strip_quotes(stripped.split(":", 1)[1])

    if current and current.get("theme"):
        themes.append(
            ThemeItem(
                theme=current["theme"].strip(),
                description=current.get("description", "").strip(),
            )
        )

    seen: set[str] = set()
    deduped: list[ThemeItem] = []
    for item in themes:
        if not item.theme or item.theme in seen:
            continue
        seen.add(item.theme)
        deduped.append(item)
    return deduped


def load_proposal_context(project_dir: str | Path) -> ProposalContext | None:
    path = Path(project_dir).expanduser().resolve() / "1_research_proposal.md"
    if not path.exists():
        return None
    return ProposalContext(
        proposal_path=path,
        idea=parse_idea_from_proposal(path),
        target_themes=tuple(parse_target_themes_from_proposal(path)),
    )


def resolve_scope_selection(
    kanripo_root: str | Path,
    *,
    scope_families: list[str] | None = None,
    repo_dirs: list[str] | None = None,
) -> ScopeSelection:
    root = Path(kanripo_root).expanduser().resolve()
    available_scope_families = {option.code for option in list_available_scope_options(root)}
    available_repo_dirs = set(list_available_scope_dirs(root))

    normalized_scope_families = unique_normalized(
        scope_families or [],
        normalizer=normalize_scope,
    )
    normalized_repo_dirs = unique_normalized(
        repo_dirs or [],
        normalizer=normalize_scope,
    )

    missing_scope_families = tuple(
        item for item in normalized_scope_families if item not in available_scope_families
    )
    missing_repo_dirs = tuple(
        item for item in normalized_repo_dirs if item not in available_repo_dirs
    )

    return ScopeSelection(
        scope_families=tuple(
            item for item in normalized_scope_families if item not in missing_scope_families
        ),
        repo_dirs=tuple(item for item in normalized_repo_dirs if item not in missing_repo_dirs),
        missing_scope_families=missing_scope_families,
        missing_repo_dirs=missing_repo_dirs,
    )


def slot_summaries(
    *,
    dotenv_path: str | Path | None = None,
    env_values: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    resolved_env = env_values or merged_env(dotenv_path)
    payloads: list[dict[str, Any]] = []
    for slot in sorted(STAGE3_MODELS.keys()):
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
            }
        )
    return payloads


def analysis_targets_from_session(session_payload: dict[str, Any]) -> list[str]:
    return analysis_targets_from_values(
        _as_string_list(session_payload.get("scope_families")),
        _as_string_list(session_payload.get("repo_dirs")),
    )


def reconcile_retrieval_progress(
    analysis_targets: list[str] | tuple[str, ...] | None,
    *,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    targets = analysis_targets_from_values(list(analysis_targets or []), [])
    raw = progress if isinstance(progress, dict) else {}

    completed_targets = [
        item
        for item in unique_normalized(
            _as_string_list(raw.get("completed_targets")),
            normalizer=normalize_scope,
        )
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


def normalize_stage3_session(payload: dict[str, Any]) -> dict[str, Any]:
    content = dict(payload)
    analysis_targets = analysis_targets_from_session(content)
    raw_progress = content.get("retrieval_progress")
    if analysis_targets or isinstance(raw_progress, dict):
        content["analysis_targets"] = analysis_targets
        content["retrieval_progress"] = reconcile_retrieval_progress(
            analysis_targets,
            progress=raw_progress if isinstance(raw_progress, dict) else None,
        )
    else:
        content.pop("analysis_targets", None)
        content.pop("retrieval_progress", None)
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

    normalized_targets = analysis_targets_from_values(list(analysis_targets or []), [])
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


def update_stage3_session_checkpoint(
    project_dir: str | Path,
    *,
    action: str,
    target: str | None = None,
    cursor: str | None = None,
    piece_id: str | None = None,
    note: str | None = None,
    completed_piece_delta: int = 0,
) -> dict[str, Any]:
    session_payload = load_stage3_session(project_dir)
    analysis_targets = analysis_targets_from_session(session_payload)
    session_payload["retrieval_progress"] = update_retrieval_progress(
        analysis_targets,
        progress=session_payload.get("retrieval_progress"),
        action=action,
        target=target,
        cursor=cursor,
        piece_id=piece_id,
        note=note,
        completed_piece_delta=completed_piece_delta,
    )
    save_stage3_session(project_dir, session_payload)
    return session_payload


def stage3_workspace_dir(project_dir: str | Path) -> Path:
    return Path(project_dir).expanduser().resolve() / STAGE3_WORKSPACE_DIR


def ensure_stage3_workspace(project_dir: str | Path) -> Path:
    path = stage3_workspace_dir(project_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def stage3_workspace_manifest_path(project_dir: str | Path) -> Path:
    return stage3_workspace_dir(project_dir) / STAGE3_WORKSPACE_MANIFEST_FILE


def stage3_session_path(project_dir: str | Path) -> Path:
    return stage3_workspace_dir(project_dir) / STAGE3_SESSION_FILE


def load_stage3_session(project_dir: str | Path) -> dict[str, Any]:
    path = stage3_session_path(project_dir)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return normalize_stage3_session(payload) if isinstance(payload, dict) else {}


def save_stage3_session(project_dir: str | Path, payload: dict[str, Any]) -> Path:
    ensure_stage3_workspace(project_dir)
    path = stage3_session_path(project_dir)
    content = normalize_stage3_session(payload)
    content["updated_at"] = _now_iso()
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def build_stage3_manifest(
    *,
    workspace_root: str | Path,
    outputs_root: str | Path,
    project_name: str,
    kanripo_root: str | Path,
    theme_source: str,
    target_themes: list[ThemeItem],
    scope_selection: ScopeSelection,
    proposal_context: ProposalContext | None = None,
    dotenv_path: str | Path | None = None,
    env_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    workspace = Path(workspace_root).expanduser().resolve()
    outputs = Path(outputs_root).expanduser().resolve()
    project_dir = outputs / project_name
    stage3_dir = stage3_workspace_dir(project_dir)
    return {
        "stage3_manifest_version": 1,
        "generated_at": _now_iso(),
        "workspace_root": str(workspace),
        "outputs_root": str(outputs),
        "project_name": project_name,
        "project_dir": str(project_dir),
        "stage3_workspace_dir": str(stage3_dir),
        "stage3_session_path": str(stage3_session_path(project_dir)),
        "stage3_workspace_manifest_path": str(stage3_workspace_manifest_path(project_dir)),
        "proposal_path": str(proposal_context.proposal_path) if proposal_context else "",
        "idea": proposal_context.idea if proposal_context else "",
        "theme_source": theme_source,
        "target_themes": [
            {
                "theme": item.theme,
                "description": item.description,
            }
            for item in target_themes
        ],
        "kanripo_root": str(Path(kanripo_root).expanduser().resolve()),
        "scope_families": list(scope_selection.scope_families),
        "repo_dirs": list(scope_selection.repo_dirs),
        "analysis_targets": list(scope_selection.scope_families + scope_selection.repo_dirs),
        "model_slots": slot_summaries(dotenv_path=dotenv_path, env_values=env_values),
    }


def manifest_path(project_dir: str | Path) -> Path:
    return Path(project_dir).expanduser().resolve() / STAGE3_MANIFEST_FILE


def write_stage3_manifest(project_dir: str | Path, payload: dict[str, Any]) -> Path:
    ensure_stage3_workspace(project_dir)
    path = manifest_path(project_dir)
    workspace_manifest = stage3_workspace_manifest_path(project_dir)
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(content, encoding="utf-8")
    workspace_manifest.write_text(content, encoding="utf-8")
    return path
