"""阶段二执行器：切片、双模型筛选、第三模型仲裁，并落盘中间产物。"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .api_config import screening_batch_char_limit, slot_payload, slot_worker_limit
from .catalog import (
    PAGE_MARKER_PATTERN,
    AnalysisTargetSelection,
    ResolvedAnalysisTarget,
    resolve_analysis_targets,
    text_files_for_repo_dir,
)
from .io_utils import append_jsonl, read_json, read_jsonl, write_json, write_jsonl, write_yaml
from .rate_control import RateControllerRegistry, SlotRateController, estimate_request_tokens
from .session import (
    analysis_targets_from_session,
    load_stage2_session,
    manifest_path,
    save_stage2_session,
    stage2_session_path,
    stage2_workspace_dir,
    update_stage2_session_checkpoint,
)


TITLE_PATTERN = re.compile(r"^#\+TITLE:\s*(.+)$", re.MULTILINE)
TECH_COMMENT_PATTERN = re.compile(
    r"\bKR\d+[a-z]?\d*(?:_[A-Za-z0-9\-]+)*\b|_tls_|^pb:",
    re.IGNORECASE,
)
CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
FRAGMENT_FILE_NAME = "fragments.jsonl"
BATCH_FILE_NAME = "batches.jsonl"
LLM1_FILE_NAME = "llm1_screening.jsonl"
LLM2_FILE_NAME = "llm2_screening.jsonl"
CONSENSUS_FILE_NAME = "consensus_records.json"
DISPUTES_FILE_NAME = "disputes.jsonl"
ARBITRATION_FILE_NAME = "llm3_arbitration.jsonl"
FINAL_FILE_NAME = "final_records.jsonl"
SUMMARY_FILE_NAME = "target_summary.json"
TARGETS_DIR_NAME = "targets"
FINAL_CORPUS_FILE_NAME = "2_primary_corpus.yaml"
ProgressCallback = Callable[[dict[str, Any]], None]


class Stage2RunnerError(RuntimeError):
    """阶段二执行器错误。"""


@dataclass(frozen=True)
class Fragment:
    piece_id: str
    source_file: str
    original_text: str
    repo_dir: str
    text_file: str

    def as_dict(self) -> dict[str, str]:
        return {
            "piece_id": self.piece_id,
            "source_file": self.source_file,
            "original_text": self.original_text,
            "repo_dir": self.repo_dir,
            "text_file": self.text_file,
        }


@dataclass(frozen=True)
class Batch:
    batch_id: str
    source_file: str
    repo_dir: str
    piece_ids: tuple[str, ...]
    batch_text: str
    char_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "source_file": self.source_file,
            "repo_dir": self.repo_dir,
            "piece_ids": list(self.piece_ids),
            "batch_text": self.batch_text,
            "char_count": self.char_count,
        }


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _emit_progress(progress_callback: ProgressCallback | None, **payload: Any) -> None:
    if progress_callback is None:
        return
    progress_callback(
        {
            "timestamp": _now_iso(),
            **payload,
        }
    )


def _clean_fragment_text(text: str) -> str:
    lines: list[str] = []
    for raw_line in text.splitlines():
        if raw_line.startswith("#+"):
            continue
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            payload = stripped.lstrip("#").strip()
            if payload and TECH_COMMENT_PATTERN.search(payload):
                continue
        cleaned = PAGE_MARKER_PATTERN.sub("", stripped).replace("¶", "").strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines).strip()


def _normalize_title(raw_title: str) -> str:
    text = str(raw_title).strip()
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    return text or "（未命名文献）"


def _split_file_to_fragments(file_path: Path, repo_dir: str) -> list[Fragment]:
    raw_text = file_path.read_text(encoding="utf-8", errors="ignore")
    title_match = TITLE_PATTERN.search(raw_text)
    source_file = _normalize_title(title_match.group(1)) if title_match else file_path.stem
    matches = list(PAGE_MARKER_PATTERN.finditer(raw_text))

    fragments: list[Fragment] = []
    if not matches:
        cleaned = _clean_fragment_text(raw_text)
        if cleaned:
            fragments.append(
                Fragment(
                    piece_id=f"{file_path.stem}_fallback_0001",
                    source_file=source_file,
                    original_text=cleaned,
                    repo_dir=repo_dir,
                    text_file=file_path.name,
                )
            )
        return fragments

    for index, match in enumerate(matches):
        marker = raw_text[match.start() : match.end()]
        piece_id = marker[4:-1].strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
        cleaned = _clean_fragment_text(raw_text[start:end])
        if not piece_id or not cleaned:
            continue
        fragments.append(
            Fragment(
                piece_id=piece_id,
                source_file=source_file,
                original_text=cleaned,
                repo_dir=repo_dir,
                text_file=file_path.name,
            )
        )
    return fragments


def _build_batches(fragments: list[Fragment]) -> list[Batch]:
    safe_limit = screening_batch_char_limit()
    batches: list[Batch] = []
    current: list[Fragment] = []
    current_chars = 0
    current_source = ""
    current_repo_dir = ""

    def flush() -> None:
        nonlocal current, current_chars, current_source, current_repo_dir
        if not current:
            return
        batch_index = len(batches) + 1
        batch_text_parts: list[str] = []
        for fragment in current:
            batch_text_parts.append(f"### {fragment.piece_id}\n{fragment.original_text}")
        batches.append(
            Batch(
                batch_id=f"batch_{batch_index:06d}",
                source_file=current_source,
                repo_dir=current_repo_dir,
                piece_ids=tuple(fragment.piece_id for fragment in current),
                batch_text="\n\n".join(batch_text_parts),
                char_count=current_chars,
            )
        )
        current = []
        current_chars = 0
        current_source = ""
        current_repo_dir = ""

    for fragment in fragments:
        fragment_chars = len(fragment.original_text.replace("\n", ""))
        if not current:
            current = [fragment]
            current_chars = fragment_chars
            current_source = fragment.source_file
            current_repo_dir = fragment.repo_dir
            continue

        should_flush = (
            fragment.source_file != current_source
            or fragment.repo_dir != current_repo_dir
            or current_chars + fragment_chars > safe_limit
        )
        if should_flush:
            flush()
            current = [fragment]
            current_chars = fragment_chars
            current_source = fragment.source_file
            current_repo_dir = fragment.repo_dir
            continue

        current.append(fragment)
        current_chars += fragment_chars

    flush()
    return batches


def _extract_json_object(text: str) -> dict[str, Any]:
    content = CODE_FENCE_PATTERN.sub("", str(text or "").strip())
    if not content:
        raise Stage2RunnerError("模型返回为空，无法解析 JSON。")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            raise Stage2RunnerError(f"模型输出不是合法 JSON: {content[:400]}") from None
        try:
            payload = json.loads(content[start : end + 1])
        except json.JSONDecodeError as exc:
            raise Stage2RunnerError(f"模型输出 JSON 解析失败: {content[:400]}") from exc
    if not isinstance(payload, dict):
        raise Stage2RunnerError("模型输出顶层必须是 JSON 对象。")
    return payload


def _build_chat_url(base_url: str) -> str:
    raw = str(base_url).rstrip("/")
    if raw.endswith("/chat/completions"):
        return raw
    split = urlsplit(raw)
    path = split.path.rstrip("/") + "/chat/completions"
    return urlunsplit((split.scheme, split.netloc, path, split.query, split.fragment))


class OpenAICompatClient:
    """极简 OpenAI-compatible 客户端，避免额外依赖。"""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_keys: tuple[str, ...],
        slot: str,
        rate_controller: SlotRateController | None = None,
    ) -> None:
        if not api_keys:
            raise Stage2RunnerError(f"{slot} 未配置 API key。")
        self.model = model
        self.base_url = base_url
        self.api_keys = api_keys
        self.slot = slot
        self.rate_controller = rate_controller

    def effective_worker_limit(self, *, requested_workers: int, estimated_tokens: int) -> int:
        if self.rate_controller is None:
            return max(1, int(requested_workers))
        return self.rate_controller.effective_worker_limit(
            requested_workers=requested_workers,
            estimated_tokens=estimated_tokens,
        )

    def _request(
        self,
        *,
        payload: dict[str, Any],
        estimated_tokens: int,
        allow_response_format: bool = True,
    ) -> dict[str, Any]:
        body = dict(payload)
        if not allow_response_format:
            body.pop("response_format", None)
        reservation = (
            self.rate_controller.acquire(estimated_tokens=estimated_tokens)
            if self.rate_controller is not None
            else None
        )
        api_key = reservation.api_key if reservation is not None else self.api_keys[0]
        request = Request(
            _build_chat_url(self.base_url),
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=180) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
                if reservation is not None:
                    usage = response_payload.get("usage") or {}
                    self.rate_controller.finalize(
                        reservation,
                        actual_tokens=int(usage.get("total_tokens") or estimated_tokens),
                    )
                return response_payload
        except HTTPError as exc:
            message = exc.read().decode("utf-8", errors="ignore")
            if allow_response_format and exc.code in {400, 404, 422}:
                if reservation is not None:
                    self.rate_controller.finalize(reservation, actual_tokens=estimated_tokens)
                return self._request(
                    payload=payload,
                    estimated_tokens=estimated_tokens,
                    allow_response_format=False,
                )
            if reservation is not None:
                self.rate_controller.finalize(reservation, actual_tokens=estimated_tokens)
            raise Stage2RunnerError(f"{self.slot} 请求失败: HTTP {exc.code} {message[:500]}") from exc
        except URLError as exc:
            if reservation is not None:
                self.rate_controller.finalize(reservation, actual_tokens=estimated_tokens)
            raise Stage2RunnerError(f"{self.slot} 网络错误: {exc}") from exc

    def chat_json(
        self,
        *,
        messages: list[dict[str, str]],
        max_tokens: int = 4000,
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        response = self._request(
            payload=payload,
            estimated_tokens=estimate_request_tokens(messages=messages, max_tokens=max_tokens),
            allow_response_format=True,
        )
        choices = response.get("choices") or []
        if not choices:
            raise Stage2RunnerError(f"{self.slot} 未返回 choices。")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            text = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
        else:
            text = str(content or "")
        return _extract_json_object(text), response.get("usage") or {}


def _screening_messages(
    *,
    target_themes: list[dict[str, str]],
    batch: Batch,
) -> list[dict[str, str]]:
    theme_lines = []
    for index, item in enumerate(target_themes, start=1):
        theme = str(item.get("theme") or "").strip()
        description = str(item.get("description") or "").strip()
        detail = f" | {description}" if description else ""
        theme_lines.append(f"T{index}: {theme}{detail}")
    themes_block = "\n".join(theme_lines)
    return [
        {
            "role": "system",
            "content": (
                "你是严谨的古籍筛读助手。"
                "你必须只返回一个合法 JSON 对象，不得输出任何额外文字。"
                '格式必须是 {"results":[{"piece_id":"...","matches":[{"theme":"...","is_relevant":true,"reason":"..."}]}]}。'
                "规则：1) 每个输入 piece_id 必须且只出现一次。"
                "2) 每个 piece 的 matches 必须覆盖全部输入主题，theme 文本必须与输入完全一致。"
                "3) is_relevant 为 true 表示该页正文对该主题存在直接证据、关键线索或高度相关的表达。"
                "4) is_relevant 为 false 表示该页正文对该主题无足够直接关联。"
                "5) reason 必须是简短中文理由。"
            ),
        },
        {
            "role": "user",
            "content": (
                "研究主题如下：\n"
                f"{themes_block}\n\n"
                f"文献来源：{batch.source_file}\n"
                f"repo_dir：{batch.repo_dir}\n\n"
                "请逐条判断以下原文分页：\n"
                f"{batch.batch_text}"
            ),
        },
    ]


def _arbitration_messages(
    *,
    theme: str,
    original_text: str,
    llm1_result: dict[str, Any],
    llm2_result: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是第三方学术仲裁助手。"
                "你必须只返回一个合法 JSON 对象，不得输出额外解释。"
                '格式必须是 {"is_relevant":true,"reason":"..."}。'
                "reason 必须为非空中文短句。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"研究主题：{theme}\n\n"
                f"原文：\n{original_text}\n\n"
                f"LLM1 判定：{json.dumps(llm1_result, ensure_ascii=False)}\n"
                f"LLM2 判定：{json.dumps(llm2_result, ensure_ascii=False)}\n\n"
                "请判断这条史料对该主题是否应保留。"
            ),
        },
    ]


def _normalize_screening_payload(
    payload: dict[str, Any],
    *,
    batch: Batch,
    target_themes: list[dict[str, str]],
) -> list[dict[str, Any]]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise Stage2RunnerError(f"{batch.batch_id} 返回缺少 results 列表。")

    theme_names = [str(item.get("theme") or "").strip() for item in target_themes if str(item.get("theme") or "").strip()]
    expected_piece_ids = list(batch.piece_ids)
    expected_set = set(expected_piece_ids)
    seen_piece_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []

    for raw_item in raw_results:
        if not isinstance(raw_item, dict):
            continue
        piece_id = str(raw_item.get("piece_id") or "").strip()
        if piece_id not in expected_set or piece_id in seen_piece_ids:
            continue
        seen_piece_ids.add(piece_id)
        match_map: dict[str, dict[str, Any]] = {}
        for raw_match in raw_item.get("matches") or []:
            if not isinstance(raw_match, dict):
                continue
            theme = str(raw_match.get("theme") or "").strip()
            if theme not in theme_names or theme in match_map:
                continue
            match_map[theme] = {
                "theme": theme,
                "is_relevant": bool(raw_match.get("is_relevant")),
                "reason": str(raw_match.get("reason") or "").strip() or ("相关" if raw_match.get("is_relevant") else "不相关"),
            }
        normalized.append(
            {
                "piece_id": piece_id,
                "matches": [
                    match_map.get(theme)
                    or {
                        "theme": theme,
                        "is_relevant": False,
                        "reason": "未给出判断",
                    }
                    for theme in theme_names
                ],
            }
        )

    missing_piece_ids = [piece_id for piece_id in expected_piece_ids if piece_id not in seen_piece_ids]
    for piece_id in missing_piece_ids:
        normalized.append(
            {
                "piece_id": piece_id,
                "matches": [
                    {
                        "theme": theme,
                        "is_relevant": False,
                        "reason": "模型漏答",
                    }
                    for theme in theme_names
                ],
            }
        )

    normalized.sort(key=lambda item: expected_piece_ids.index(item["piece_id"]))
    return normalized


def _screen_batch(
    *,
    client: OpenAICompatClient,
    slot: str,
    batch: Batch,
    target_themes: list[dict[str, str]],
) -> dict[str, Any]:
    payload, usage = client.chat_json(messages=_screening_messages(target_themes=target_themes, batch=batch), max_tokens=5000)
    results = _normalize_screening_payload(payload, batch=batch, target_themes=target_themes)
    return {
        "slot": slot,
        "model": client.model,
        "batch_id": batch.batch_id,
        "source_file": batch.source_file,
        "repo_dir": batch.repo_dir,
        "piece_ids": list(batch.piece_ids),
        "results": results,
        "usage": usage,
        "generated_at": _now_iso(),
    }


def _normalize_arbitration_payload(payload: dict[str, Any]) -> dict[str, Any]:
    reason = str(payload.get("reason") or "").strip()
    return {
        "is_relevant": bool(payload.get("is_relevant")),
        "reason": reason or "未提供仲裁理由",
    }


def _arbitrate_dispute(
    *,
    client: OpenAICompatClient,
    dispute: dict[str, Any],
) -> dict[str, Any]:
    payload, usage = client.chat_json(
        messages=_arbitration_messages(
            theme=str(dispute["matched_theme"]),
            original_text=str(dispute["original_text"]),
            llm1_result=dispute["llm1_result"],
            llm2_result=dispute["llm2_result"],
        ),
        max_tokens=1200,
    )
    decision = _normalize_arbitration_payload(payload)
    return {
        "dispute_key": dispute["dispute_key"],
        "piece_id": dispute["piece_id"],
        "source_file": dispute["source_file"],
        "matched_theme": dispute["matched_theme"],
        "decision": decision,
        "usage": usage,
        "generated_at": _now_iso(),
    }


def _target_workspace_dir(project_dir: Path, token: str) -> Path:
    return stage2_workspace_dir(project_dir) / TARGETS_DIR_NAME / token


def _ensure_target_workspace(project_dir: Path, token: str) -> Path:
    path = _target_workspace_dir(project_dir, token)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fragments_path(target_dir: Path) -> Path:
    return target_dir / FRAGMENT_FILE_NAME


def _batches_path(target_dir: Path) -> Path:
    return target_dir / BATCH_FILE_NAME


def _slot_output_path(target_dir: Path, slot: str) -> Path:
    return target_dir / (LLM1_FILE_NAME if slot == "llm1" else LLM2_FILE_NAME)


def _consensus_path(target_dir: Path) -> Path:
    return target_dir / CONSENSUS_FILE_NAME


def _disputes_path(target_dir: Path) -> Path:
    return target_dir / DISPUTES_FILE_NAME


def _arbitration_path(target_dir: Path) -> Path:
    return target_dir / ARBITRATION_FILE_NAME


def _final_path(target_dir: Path) -> Path:
    return target_dir / FINAL_FILE_NAME


def _summary_path(target_dir: Path) -> Path:
    return target_dir / SUMMARY_FILE_NAME


def _artifact_state_path(target_dir: Path) -> Path:
    return target_dir / "run_state.json"


def _load_target_state(target_dir: Path) -> dict[str, Any]:
    payload = read_json(_artifact_state_path(target_dir), default={})
    return payload if isinstance(payload, dict) else {}


def _save_target_state(target_dir: Path, *, repo_dirs: tuple[str, ...], max_fragments: int | None) -> None:
    state = _load_target_state(target_dir)
    state.update(
        {
            "repo_dirs": list(repo_dirs),
            "batch_max_chars": screening_batch_char_limit(),
            "max_fragments": max_fragments,
            "phase": "initialized",
            "is_completed": False,
            "updated_at": _now_iso(),
        }
    )
    write_json(_artifact_state_path(target_dir), state)


def _update_target_state(target_dir: Path, **fields: Any) -> None:
    state = _load_target_state(target_dir)
    state.update(fields)
    state["updated_at"] = _now_iso()
    write_json(_artifact_state_path(target_dir), state)


def _summarize_target_state(state: dict[str, Any]) -> str:
    phase = str(state.get("phase") or "unknown")
    if phase == "slot_screening":
        return (
            f"phase={phase}"
            f" | llm1={int(state.get('llm1_completed_batches') or 0)}/{int(state.get('batch_count') or 0)}"
            f" | llm2={int(state.get('llm2_completed_batches') or 0)}/{int(state.get('batch_count') or 0)}"
        )
    if phase == "arbitration":
        return (
            f"phase={phase}"
            f" | llm3={int(state.get('llm3_completed_disputes') or 0)}/{int(state.get('dispute_count') or 0)}"
        )
    if phase == "completed":
        return (
            f"phase={phase}"
            f" | final_records={int(state.get('final_record_count') or 0)}"
            f" | final_pieces={int(state.get('final_piece_count') or 0)}"
        )
    details = []
    for key in ("fragment_count", "batch_count", "dispute_count"):
        if key in state:
            details.append(f"{key}={state[key]}")
    return f"phase={phase}" + (f" | {' | '.join(details)}" if details else "")


def _load_or_build_fragments(
    *,
    kanripo_root: Path,
    target: ResolvedAnalysisTarget,
    target_dir: Path,
    max_fragments: int | None,
) -> list[Fragment]:
    fragments_file = _fragments_path(target_dir)
    existing = read_jsonl(fragments_file)
    if existing:
        return [
            Fragment(
                piece_id=str(item.get("piece_id") or ""),
                source_file=str(item.get("source_file") or ""),
                original_text=str(item.get("original_text") or ""),
                repo_dir=str(item.get("repo_dir") or ""),
                text_file=str(item.get("text_file") or ""),
            )
            for item in existing
            if str(item.get("piece_id") or "").strip() and str(item.get("original_text") or "").strip()
        ]

    fragments: list[Fragment] = []
    for repo_dir in target.repo_dirs:
        for text_file in text_files_for_repo_dir(kanripo_root, repo_dir):
            fragments.extend(_split_file_to_fragments(text_file, repo_dir))
            if max_fragments is not None and len(fragments) >= max_fragments:
                fragments = fragments[:max_fragments]
                break
        if max_fragments is not None and len(fragments) >= max_fragments:
            break

    write_jsonl(fragments_file, [fragment.as_dict() for fragment in fragments])
    return fragments


def _load_or_build_batches(
    *,
    target_dir: Path,
    fragments: list[Fragment],
) -> list[Batch]:
    batches_file = _batches_path(target_dir)
    existing = read_jsonl(batches_file)
    if existing:
        return [
            Batch(
                batch_id=str(item.get("batch_id") or ""),
                source_file=str(item.get("source_file") or ""),
                repo_dir=str(item.get("repo_dir") or ""),
                piece_ids=tuple(str(value) for value in item.get("piece_ids") or [] if str(value).strip()),
                batch_text=str(item.get("batch_text") or ""),
                char_count=int(item.get("char_count") or 0),
            )
            for item in existing
            if str(item.get("batch_id") or "").strip()
        ]

    batches = _build_batches(fragments)
    write_jsonl(batches_file, [batch.as_dict() for batch in batches])
    return batches


def _write_disputes(target_dir: Path, disputes: list[dict[str, Any]]) -> Path:
    return write_jsonl(_disputes_path(target_dir), disputes)


def _load_disputes(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path)


def _load_cached_rows_by_key(path: Path, key: str) -> dict[str, dict[str, Any]]:
    cached: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        token = str(row.get(key) or "").strip()
        if token:
            cached[token] = row
    return cached


def _run_slot_batches(
    *,
    client: OpenAICompatClient,
    slot: str,
    batches: list[Batch],
    target_themes: list[dict[str, str]],
    output_path: Path,
    workers: int,
    project_dir: Path,
    target_token: str,
    progress_callback: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    target_dir = output_path.parent
    cached = _load_cached_rows_by_key(output_path, "batch_id")
    pending_batches = [batch for batch in batches if batch.batch_id not in cached]
    _update_target_state(
        target_dir,
        phase="slot_screening",
        batch_count=len(batches),
        **{f"{slot}_completed_batches": len(cached)},
    )
    if cached:
        _emit_progress(
            progress_callback,
            event="slot_resume",
            target=target_token,
            slot=slot,
            completed=len(cached),
            total=len(batches),
        )
    if not pending_batches:
        return [cached[batch.batch_id] for batch in batches if batch.batch_id in cached]

    batch_map = {batch.batch_id: batch for batch in batches}
    finished_count = len(cached)
    effective_workers = client.effective_worker_limit(
        requested_workers=workers,
        estimated_tokens=max(
            estimate_request_tokens(messages=_screening_messages(target_themes=target_themes, batch=batch), max_tokens=5000)
            for batch in pending_batches
        ),
    )
    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        pending = {
            executor.submit(_screen_batch, client=client, slot=slot, batch=batch, target_themes=target_themes): batch
            for batch in pending_batches
        }
        while pending:
            done, _ = wait(pending.keys(), return_when=FIRST_COMPLETED)
            for future in done:
                batch = pending.pop(future)
                row = future.result()
                append_jsonl(output_path, row)
                cached[batch.batch_id] = row
                finished_count += 1
                _update_target_state(
                    target_dir,
                    phase="slot_screening",
                    batch_count=len(batches),
                    **{f"{slot}_completed_batches": finished_count},
                )
                update_stage2_session_checkpoint(
                    project_dir,
                    action="checkpoint",
                    target=target_token,
                    cursor=f"{slot}:batch={finished_count}/{len(batches)}",
                    piece_id=batch.piece_ids[-1] if batch.piece_ids else "",
                    note=f"{slot} 已完成 {finished_count}/{len(batches)} 个批次",
                )
                _emit_progress(
                    progress_callback,
                    event="slot_progress",
                    target=target_token,
                    slot=slot,
                    completed=finished_count,
                    total=len(batches),
                    batch_id=batch.batch_id,
                )

    return [cached[batch_map_key.batch_id] for batch_map_key in batches if batch_map_key.batch_id in cached]


def _flatten_slot_rows(slot_rows: list[dict[str, Any]], fragment_map: dict[str, Fragment]) -> dict[tuple[str, str], dict[str, Any]]:
    flattened: dict[tuple[str, str], dict[str, Any]] = {}
    for row in slot_rows:
        batch_id = str(row.get("batch_id") or "")
        slot = str(row.get("slot") or "")
        model = str(row.get("model") or "")
        for piece_result in row.get("results") or []:
            piece_id = str(piece_result.get("piece_id") or "").strip()
            fragment = fragment_map.get(piece_id)
            if fragment is None:
                continue
            for match in piece_result.get("matches") or []:
                theme = str(match.get("theme") or "").strip()
                if not theme:
                    continue
                flattened[(piece_id, theme)] = {
                    "piece_id": piece_id,
                    "source_file": fragment.source_file,
                    "original_text": fragment.original_text,
                    "matched_theme": theme,
                    "is_relevant": bool(match.get("is_relevant")),
                    "reason": str(match.get("reason") or "").strip(),
                    "slot": slot,
                    "model": model,
                    "batch_id": batch_id,
                }
    return flattened


def _build_consensus_and_disputes(
    *,
    llm1_map: dict[tuple[str, str], dict[str, Any]],
    llm2_map: dict[tuple[str, str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    keys = sorted(set(llm1_map.keys()) | set(llm2_map.keys()))
    consensus: list[dict[str, Any]] = []
    disputes: list[dict[str, Any]] = []

    for key in keys:
        left = llm1_map.get(key)
        right = llm2_map.get(key)
        if left is None or right is None:
            continue
        if bool(left["is_relevant"]) and bool(right["is_relevant"]):
            consensus.append(
                {
                    "piece_id": left["piece_id"],
                    "source_file": left["source_file"],
                    "matched_theme": left["matched_theme"],
                    "original_text": left["original_text"],
                    "note": f"llm1: {left['reason']} | llm2: {right['reason']}",
                    "judgment": "consensus",
                    "llm1_result": {
                        "is_relevant": left["is_relevant"],
                        "reason": left["reason"],
                        "model": left["model"],
                        "batch_id": left["batch_id"],
                    },
                    "llm2_result": {
                        "is_relevant": right["is_relevant"],
                        "reason": right["reason"],
                        "model": right["model"],
                        "batch_id": right["batch_id"],
                    },
                }
            )
            continue
        if bool(left["is_relevant"]) == bool(right["is_relevant"]):
            continue
        piece_id, theme = key
        disputes.append(
            {
                "dispute_key": f"{piece_id}::{theme}",
                "piece_id": piece_id,
                "source_file": left["source_file"],
                "matched_theme": theme,
                "original_text": left["original_text"],
                "llm1_result": {
                    "is_relevant": left["is_relevant"],
                    "reason": left["reason"],
                    "model": left["model"],
                    "batch_id": left["batch_id"],
                },
                "llm2_result": {
                    "is_relevant": right["is_relevant"],
                    "reason": right["reason"],
                    "model": right["model"],
                    "batch_id": right["batch_id"],
                },
            }
        )

    return consensus, disputes


def _run_arbitration(
    *,
    client: OpenAICompatClient,
    disputes_path: Path,
    output_path: Path,
    workers: int,
    project_dir: Path,
    target_token: str,
    progress_callback: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    disputes = _load_disputes(disputes_path)
    target_dir = output_path.parent
    cached = _load_cached_rows_by_key(output_path, "dispute_key")
    pending_disputes = [dispute for dispute in disputes if dispute["dispute_key"] not in cached]
    _update_target_state(
        target_dir,
        phase="arbitration",
        dispute_count=len(disputes),
        llm3_completed_disputes=len(cached),
    )
    if cached:
        _emit_progress(
            progress_callback,
            event="arbitration_resume",
            target=target_token,
            completed=len(cached),
            total=len(disputes),
        )
    if pending_disputes:
        effective_workers = client.effective_worker_limit(
            requested_workers=workers,
            estimated_tokens=max(
                estimate_request_tokens(
                    messages=_arbitration_messages(
                        theme=str(dispute["matched_theme"]),
                        original_text=str(dispute["original_text"]),
                        llm1_result=dispute["llm1_result"],
                        llm2_result=dispute["llm2_result"],
                    ),
                    max_tokens=1200,
                )
                for dispute in pending_disputes
            ),
        )
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            pending = {
                executor.submit(_arbitrate_dispute, client=client, dispute=dispute): dispute
                for dispute in pending_disputes
            }
            resolved_count = len(cached)
            while pending:
                done, _ = wait(pending.keys(), return_when=FIRST_COMPLETED)
                for future in done:
                    dispute = pending.pop(future)
                    row = future.result()
                    append_jsonl(output_path, row)
                    cached[dispute["dispute_key"]] = row
                    resolved_count += 1
                    _update_target_state(
                        target_dir,
                        phase="arbitration",
                        dispute_count=len(disputes),
                        llm3_completed_disputes=resolved_count,
                    )
                    update_stage2_session_checkpoint(
                        project_dir,
                        action="checkpoint",
                        target=target_token,
                        cursor=f"llm3:dispute={resolved_count}/{len(disputes)}",
                        piece_id=dispute["piece_id"],
                        note=f"llm3 已仲裁 {resolved_count}/{len(disputes)} 条争议",
                    )
                    _emit_progress(
                        progress_callback,
                        event="arbitration_progress",
                        target=target_token,
                        completed=resolved_count,
                        total=len(disputes),
                        piece_id=dispute["piece_id"],
                    )
    return [cached[dispute["dispute_key"]] for dispute in disputes if dispute["dispute_key"] in cached]


def _build_final_records(
    *,
    consensus: list[dict[str, Any]],
    arbitration_rows: list[dict[str, Any]],
    dispute_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    final_map: dict[tuple[str, str], dict[str, Any]] = {}
    for record in consensus:
        key = (record["piece_id"], record["matched_theme"])
        final_map[key] = {
            "piece_id": record["piece_id"],
            "source_file": record["source_file"],
            "matched_theme": record["matched_theme"],
            "original_text": record["original_text"],
            "note": record["note"],
            "judgment": "consensus",
        }
    for arbitration in arbitration_rows:
        decision = arbitration.get("decision") or {}
        if not decision.get("is_relevant"):
            continue
        dispute = dispute_map.get(str(arbitration["dispute_key"]))
        if not dispute:
            continue
        key = (dispute["piece_id"], dispute["matched_theme"])
        final_map[key] = {
            "piece_id": dispute["piece_id"],
            "source_file": dispute["source_file"],
            "matched_theme": dispute["matched_theme"],
            "original_text": dispute["original_text"],
            "note": (
                f"llm1: {dispute['llm1_result']['reason']} | "
                f"llm2: {dispute['llm2_result']['reason']} | "
                f"llm3: {decision.get('reason')}"
            ),
            "judgment": "arbitrated",
        }
    return sorted(final_map.values(), key=lambda item: (item["piece_id"], item["matched_theme"]))


def _primary_corpus_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    unique_piece_ids = {str(record.get("piece_id") or "").strip() for record in records if str(record.get("piece_id") or "").strip()}
    return {
        "piece_count": len(unique_piece_ids),
        "records": [
            {
                "piece_id": record["piece_id"],
                "source_file": record["source_file"],
                "matched_theme": record["matched_theme"],
                "original_text": record["original_text"],
                "note": record["note"],
            }
            for record in records
        ],
    }


def _selection_from_manifest(manifest: dict[str, Any]) -> AnalysisTargetSelection:
    kanripo_root = Path(str(manifest.get("kanripo_root") or "")).expanduser().resolve()
    tokens = [str(item) for item in manifest.get("analysis_targets") or [] if str(item).strip()]
    selection = resolve_analysis_targets(kanripo_root, tokens=tokens)
    if not selection.resolved_targets:
        raise Stage2RunnerError("manifest 中没有可执行的 analysis_targets。")
    if selection.issues:
        details = "; ".join(f"{item.token}: {item.detail}" for item in selection.issues)
        raise Stage2RunnerError(f"analysis_targets 校验失败: {details}")
    return selection


def _load_manifest(project_dir: Path) -> dict[str, Any]:
    payload = read_json(manifest_path(project_dir), default={})
    if not isinstance(payload, dict) or not payload:
        raise Stage2RunnerError(f"缺少 manifest: {manifest_path(project_dir)}")
    return payload


def _target_state_matches(target_dir: Path, *, repo_dirs: tuple[str, ...], max_fragments: int | None) -> bool:
    state = _load_target_state(target_dir)
    if not state:
        return False
    return (
        tuple(str(item) for item in state.get("repo_dirs") or []) == tuple(repo_dirs)
        and int(state.get("batch_max_chars") or 0) == screening_batch_char_limit()
        and state.get("max_fragments") == max_fragments
    )


def _clear_target_workspace(target_dir: Path) -> None:
    for path in target_dir.iterdir():
        if path.is_file():
            path.unlink()


def _build_clients(*, dotenv_path: str | Path | None) -> dict[str, OpenAICompatClient]:
    clients: dict[str, OpenAICompatClient] = {}
    registry = RateControllerRegistry()
    for slot in ("llm1", "llm2", "llm3"):
        payload = slot_payload(slot, dotenv_path=dotenv_path)
        clients[slot] = OpenAICompatClient(
            model=str(payload["model"]),
            base_url=str(payload["base_url"]),
            api_keys=tuple(str(key) for key in payload["api_keys"] or () if str(key).strip()),
            slot=slot,
            rate_controller=registry.get(payload),
        )
    return clients


def _update_session_status(project_dir: Path, *, status: str, note: str = "") -> None:
    session_payload = load_stage2_session(project_dir)
    session_payload["status"] = status
    if note:
        session_payload["last_run_note"] = note
    session_payload["last_run_at"] = _now_iso()
    save_stage2_session(project_dir, session_payload)


def _load_existing_target_final_records(project_dir: Path, target_token: str) -> list[dict[str, Any]]:
    return read_jsonl(_final_path(_target_workspace_dir(project_dir, target_token)))


def run_stage2_pipeline(
    *,
    project_dir: str | Path,
    dotenv_path: str | Path | None = None,
    max_fragments: int | None = None,
    llm1_workers: int | None = None,
    llm2_workers: int | None = None,
    llm3_workers: int | None = None,
    force_rerun: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    project_path = Path(project_dir).expanduser().resolve()
    manifest = _load_manifest(project_path)
    selection = _selection_from_manifest(manifest)
    session_before_run = load_stage2_session(project_path)
    completed_targets_before_run = set(
        str(item) for item in ((session_before_run.get("retrieval_progress") or {}).get("completed_targets") or []) if str(item).strip()
    )
    target_themes = [dict(item) for item in manifest.get("target_themes") or [] if isinstance(item, dict)]
    if not target_themes:
        raise Stage2RunnerError("manifest 中缺少 target_themes，无法执行阶段二。")
    kanripo_root = Path(str(manifest.get("kanripo_root") or "")).expanduser().resolve()
    if not kanripo_root.exists():
        raise Stage2RunnerError(f"Kanripo 根目录不存在: {kanripo_root}")

    if force_rerun:
        update_stage2_session_checkpoint(project_path, action="reset", note="force rerun")
        completed_targets_before_run = set()
    clients = _build_clients(dotenv_path=dotenv_path)
    llm1_workers = max(1, int(llm1_workers if llm1_workers is not None else slot_worker_limit("llm1")))
    llm2_workers = max(1, int(llm2_workers if llm2_workers is not None else slot_worker_limit("llm2")))
    llm3_workers = max(1, int(llm3_workers if llm3_workers is not None else slot_worker_limit("llm3")))
    _update_session_status(project_path, status="running", note="阶段二执行中")
    _emit_progress(
        progress_callback,
        event="pipeline_started",
        project_name=project_path.name,
        target_count=len(selection.resolved_targets),
        analysis_targets=[item.token for item in selection.resolved_targets],
    )

    summaries: list[dict[str, Any]] = []
    merged_final_records: list[dict[str, Any]] = []

    try:
        for target in selection.resolved_targets:
            target_dir = _ensure_target_workspace(project_path, target.token)
            if target.token in completed_targets_before_run and not force_rerun:
                final_records = _load_existing_target_final_records(project_path, target.token)
                if final_records:
                    summary = read_json(_summary_path(target_dir), default={})
                    if isinstance(summary, dict) and summary:
                        summaries.append(summary)
                    merged_final_records.extend(final_records)
                    _emit_progress(
                        progress_callback,
                        event="target_reused",
                        target=target.token,
                        final_record_count=len(final_records),
                    )
                    continue
                update_stage2_session_checkpoint(project_path, action="reset", note="缓存缺失，重新构建阶段二")
                completed_targets_before_run = set()

            update_stage2_session_checkpoint(project_path, action="start", target=target.token, note="开始执行阶段二目标")
            existing_state = _load_target_state(target_dir)
            if existing_state and not force_rerun and not bool(existing_state.get("is_completed")):
                _emit_progress(
                    progress_callback,
                    event="target_resumed",
                    target=target.token,
                    summary=_summarize_target_state(existing_state),
                )
            _update_target_state(target_dir, phase="target_started", is_completed=False)
            _emit_progress(
                progress_callback,
                event="target_started",
                target=target.token,
                repo_dir_count=len(target.repo_dirs),
            )
            if force_rerun or not _target_state_matches(
                target_dir,
                repo_dirs=target.repo_dirs,
                max_fragments=max_fragments,
            ):
                _clear_target_workspace(target_dir)
                _save_target_state(
                    target_dir,
                    repo_dirs=target.repo_dirs,
                    max_fragments=max_fragments,
                )

            fragments = _load_or_build_fragments(
                kanripo_root=kanripo_root,
                target=target,
                target_dir=target_dir,
                max_fragments=max_fragments,
            )
            _emit_progress(
                progress_callback,
                event="fragments_ready",
                target=target.token,
                fragment_count=len(fragments),
            )
            _update_target_state(
                target_dir,
                phase="fragments_ready",
                fragment_count=len(fragments),
            )
            fragment_map = {fragment.piece_id: fragment for fragment in fragments}
            batches = _load_or_build_batches(
                target_dir=target_dir,
                fragments=fragments,
            )
            _emit_progress(
                progress_callback,
                event="batches_ready",
                target=target.token,
                batch_count=len(batches),
            )
            _update_target_state(
                target_dir,
                phase="batches_ready",
                fragment_count=len(fragments),
                batch_count=len(batches),
            )

            llm1_rows = _run_slot_batches(
                client=clients["llm1"],
                slot="llm1",
                batches=batches,
                target_themes=target_themes,
                output_path=_slot_output_path(target_dir, "llm1"),
                workers=llm1_workers,
                project_dir=project_path,
                target_token=target.token,
                progress_callback=progress_callback,
            )
            llm2_rows = _run_slot_batches(
                client=clients["llm2"],
                slot="llm2",
                batches=batches,
                target_themes=target_themes,
                output_path=_slot_output_path(target_dir, "llm2"),
                workers=llm2_workers,
                project_dir=project_path,
                target_token=target.token,
                progress_callback=progress_callback,
            )

            llm1_map = _flatten_slot_rows(llm1_rows, fragment_map)
            llm2_map = _flatten_slot_rows(llm2_rows, fragment_map)
            consensus, disputes = _build_consensus_and_disputes(llm1_map=llm1_map, llm2_map=llm2_map)
            write_json(_consensus_path(target_dir), {"records": consensus})
            disputes_path = _write_disputes(target_dir, disputes)
            _emit_progress(
                progress_callback,
                event="consensus_ready",
                target=target.token,
                consensus_count=len(consensus),
                dispute_count=len(disputes),
            )
            _update_target_state(
                target_dir,
                phase="disputes_ready",
                consensus_count=len(consensus),
                dispute_count=len(disputes),
            )

            arbitration_rows = _run_arbitration(
                client=clients["llm3"],
                disputes_path=disputes_path,
                output_path=_arbitration_path(target_dir),
                workers=llm3_workers,
                project_dir=project_path,
                target_token=target.token,
                progress_callback=progress_callback,
            )
            dispute_map = {str(item["dispute_key"]): item for item in disputes}
            final_records = _build_final_records(
                consensus=consensus,
                arbitration_rows=arbitration_rows,
                dispute_map=dispute_map,
            )
            write_jsonl(_final_path(target_dir), final_records)

            summary = {
                "target": target.token,
                "repo_dir_count": len(target.repo_dirs),
                "fragment_count": len(fragments),
                "batch_count": len(batches),
                "consensus_count": len(consensus),
                "dispute_count": len(disputes),
                "arbitrated_keep_count": sum(
                    1 for item in arbitration_rows if bool((item.get("decision") or {}).get("is_relevant"))
                ),
                "final_record_count": len(final_records),
                "final_piece_count": len({item["piece_id"] for item in final_records}),
                "updated_at": _now_iso(),
            }
            write_json(_summary_path(target_dir), summary)
            _update_target_state(
                target_dir,
                phase="completed",
                is_completed=True,
                final_record_count=summary["final_record_count"],
                final_piece_count=summary["final_piece_count"],
                consensus_count=summary["consensus_count"],
                dispute_count=summary["dispute_count"],
                llm1_completed_batches=len(llm1_rows),
                llm2_completed_batches=len(llm2_rows),
                llm3_completed_disputes=len(arbitration_rows),
            )
            summaries.append(summary)
            merged_final_records.extend(final_records)
            _emit_progress(
                progress_callback,
                event="target_completed",
                target=target.token,
                final_record_count=len(final_records),
                final_piece_count=len({item["piece_id"] for item in final_records}),
            )
            update_stage2_session_checkpoint(
                project_path,
                action="complete",
                target=target.token,
                piece_id=final_records[-1]["piece_id"] if final_records else "",
                completed_piece_delta=len(final_records),
                note=f"{target.token} 完成，保留 {len(final_records)} 条记录",
            )

        payload = _primary_corpus_payload(merged_final_records)
        write_yaml(project_path / FINAL_CORPUS_FILE_NAME, payload)
        summary_payload = {
            "project_name": project_path.name,
            "manifest_path": str(manifest_path(project_path)),
            "session_path": str(stage2_session_path(project_path)),
            "analysis_targets": analysis_targets_from_session(load_stage2_session(project_path)),
            "piece_count": payload["piece_count"],
            "record_count": len(payload["records"]),
            "targets": summaries,
            "updated_at": _now_iso(),
        }
        write_json(stage2_workspace_dir(project_path) / "run_summary.json", summary_payload)
        _update_session_status(project_path, status="completed", note="阶段二执行完成")
        _emit_progress(
            progress_callback,
            event="pipeline_completed",
            project_name=project_path.name,
            piece_count=summary_payload["piece_count"],
            record_count=summary_payload["record_count"],
        )
        return summary_payload
    except Exception as exc:  # noqa: BLE001
        _update_session_status(project_path, status="paused", note=str(exc))
        progress = (load_stage2_session(project_path).get("retrieval_progress") or {})
        current_target = str(progress.get("current_target") or "").strip()
        if current_target:
            _update_target_state(
                _ensure_target_workspace(project_path, current_target),
                phase="failed",
                last_error=str(exc),
                is_completed=False,
            )
        _emit_progress(
            progress_callback,
            event="pipeline_failed",
            project_name=project_path.name,
            error=str(exc),
        )
        raise
