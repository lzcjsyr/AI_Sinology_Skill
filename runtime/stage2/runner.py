"""阶段二执行器：切片、批次粗筛、单主题精筛、第三模型仲裁，并落盘中间产物。"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from socket import timeout as SocketTimeout
import time
from typing import Any, Callable, Iterable, Iterator, TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .api_config import (
    RateControllerRegistry,
    STAGE2_RUNTIME_DEFAULTS,
    SlotRateController,
    estimate_request_tokens,
    fallback_payload,
    scaled_slot_worker_limit,
    screening_batch_char_limit,
    slot_payload,
)
from .catalog import (
    PAGE_MARKER_PATTERN,
    TECH_COMMENT_PATTERN,
    AnalysisTargetSelection,
    ResolvedAnalysisTarget,
    resolve_analysis_targets,
    text_files_for_repo_dir,
)
from .io_utils import read_json, read_jsonl, write_json, write_jsonl, write_yaml
from .prompts import (
    ARBITRATION_LLM1_LABEL,
    ARBITRATION_LLM2_LABEL,
    ARBITRATION_ORIGINAL_LABEL,
    ARBITRATION_SYSTEM,
    ARBITRATION_TASK,
    ARBITRATION_THEME_LABEL,
    COARSE_SYSTEM,
    COARSE_USER_INSTRUCTION,
    COARSE_USER_LEAD,
    SOURCE_FILE_LABEL,
    TARGETED_SYSTEM,
    TARGETED_USER_INSTRUCTION,
    TARGETED_USER_THEME_LABEL,
)
from .session import (
    analysis_targets_from_manifest,
    load_stage2_manifest,
    manifest_path,
    stage2_workspace_dir,
    update_stage2_manifest_checkpoint,
    write_stage2_manifest,
)


TITLE_PATTERN = re.compile(r"^#\+TITLE:\s*(.+)$", re.MULTILINE)
CODE_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
FRAGMENT_FILE_NAME = "fragments.jsonl"
BATCH_FILE_NAME = "batches.jsonl"
LLM1_COARSE_FILE_NAME = "llm1_coarse_screening.jsonl"
LLM2_COARSE_FILE_NAME = "llm2_coarse_screening.jsonl"
LLM1_FILE_NAME = "llm1_screening.jsonl"
LLM2_FILE_NAME = "llm2_screening.jsonl"
CONSENSUS_FILE_NAME = "consensus_records.json"
DISPUTES_FILE_NAME = "disputes.jsonl"
ARBITRATION_FILE_NAME = "llm3_arbitration.jsonl"
FINAL_FILE_NAME = "final_records.jsonl"
MANUAL_REVIEW_FILE_NAME = "manual_review_queue.jsonl"
MANUAL_REVIEW_REPORT_FILE_NAME = "MANUAL_REVIEW_REQUIRED.md"
TARGETS_DIR_NAME = "targets"
FINAL_CORPUS_FILE_NAME = "2_primary_corpus.yaml"
PIPELINE_STATE_VERSION = 2
ProgressCallback = Callable[[dict[str, Any]], None]
HTTP_429_MAX_RETRIES = 4
HTTP_429_BACKOFF_SECONDS = 2.0
HTTP_429_BACKOFF_CAP_SECONDS = 30.0
TRANSIENT_HTTP_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
WorkItem = TypeVar("WorkItem")
TaskResult = TypeVar("TaskResult")
MANUAL_REVIEW_REQUIRED_REASON = "MANUAL_REVIEW_REQUIRED"


class Stage2RunnerError(RuntimeError):
    """阶段二执行器错误。"""


class Stage2FormatError(Stage2RunnerError):
    """模型返回结构不符合阶段二契约。"""


class Stage2FallbackExhaustedError(Stage2FormatError):
    """主模型与 fallback 均未能返回可用结构。"""

    def __init__(
        self,
        *,
        primary_error: str,
        fallback_errors: list[str],
        fallback_model: str,
    ) -> None:
        self.primary_error = primary_error
        self.fallback_errors = list(fallback_errors)
        self.fallback_model = fallback_model
        detail = "; ".join(self.fallback_errors) if self.fallback_errors else "无返回"
        super().__init__(
            f"主模型格式失败：{primary_error} | fallback={fallback_model} 连续失败 {len(self.fallback_errors)} 次：{detail}"
        )


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


def _request_timeout_seconds() -> float:
    return max(5.0, float(STAGE2_RUNTIME_DEFAULTS.get("request_timeout_seconds", 120.0) or 120.0))


def _network_error_max_retries() -> int:
    return max(0, int(STAGE2_RUNTIME_DEFAULTS.get("network_error_max_retries", 3) or 3))


def _stall_heartbeat_seconds() -> float:
    return max(5.0, float(STAGE2_RUNTIME_DEFAULTS.get("stall_heartbeat_seconds", 30.0) or 30.0))


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
        batch_text_parts = [fragment.original_text for fragment in current]
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


def _theme_names(target_themes: list[dict[str, str]]) -> list[str]:
    return [str(item.get("theme") or "").strip() for item in target_themes if str(item.get("theme") or "").strip()]


def _extract_json_object(text: str) -> dict[str, Any]:
    content = CODE_FENCE_PATTERN.sub("", str(text or "").strip())
    if not content:
        raise Stage2FormatError("模型返回为空，无法解析 JSON。")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start < 0 or end <= start:
            raise Stage2FormatError(f"模型输出不是合法 JSON: {content[:400]}") from None
        try:
            payload = json.loads(content[start : end + 1])
        except json.JSONDecodeError as exc:
            raise Stage2FormatError(f"模型输出 JSON 解析失败: {content[:400]}") from exc
    if not isinstance(payload, dict):
        raise Stage2FormatError("模型输出顶层必须是 JSON 对象。")
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
        provider: str = "",
        rate_controller: SlotRateController | None = None,
        fallback_client: OpenAICompatClient | None = None,
        fallback_max_retries: int = 0,
    ) -> None:
        if not api_keys:
            raise Stage2RunnerError(f"{slot} 未配置 API key。")
        self.model = model
        self.base_url = base_url
        self.api_keys = api_keys
        self.slot = slot
        self.provider = provider
        self.rate_controller = rate_controller
        self.fallback_client = fallback_client
        self.fallback_max_retries = max(0, int(fallback_max_retries))

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
        attempt = 0
        request_timeout = _request_timeout_seconds()
        network_retry_limit = _network_error_max_retries()
        while True:
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
                with urlopen(request, timeout=request_timeout) as response:
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
                if exc.code in TRANSIENT_HTTP_STATUS_CODES and attempt < min(HTTP_429_MAX_RETRIES, network_retry_limit):
                    attempt += 1
                    time.sleep(self._http_retry_delay(exc, attempt=attempt))
                    continue
                raise Stage2RunnerError(f"{self.slot} 请求失败: HTTP {exc.code} {message[:500]}") from exc
            except (URLError, TimeoutError, SocketTimeout) as exc:
                if reservation is not None:
                    self.rate_controller.finalize(reservation, actual_tokens=estimated_tokens)
                if attempt < network_retry_limit:
                    attempt += 1
                    time.sleep(self._http_retry_delay(None, attempt=attempt))
                    continue
                raise Stage2RunnerError(f"{self.slot} 网络错误: {exc}") from exc

    @staticmethod
    def _http_retry_delay(exc: HTTPError | None, *, attempt: int) -> float:
        if exc is not None:
            retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
            if retry_after is not None:
                try:
                    return max(0.0, min(float(retry_after), HTTP_429_BACKOFF_CAP_SECONDS))
                except (TypeError, ValueError):
                    pass
        return min(HTTP_429_BACKOFF_SECONDS * (2 ** max(0, attempt - 1)), HTTP_429_BACKOFF_CAP_SECONDS)

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
            raise Stage2FormatError(f"{self.slot} 未返回 choices。")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            text = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
        else:
            text = str(content or "")
        return _extract_json_object(text), response.get("usage") or {}


def _coarse_screening_messages(
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
        {"role": "system", "content": COARSE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"{COARSE_USER_LEAD}{themes_block}\n\n"
                f"{SOURCE_FILE_LABEL}{batch.source_file}\n"
                f"{COARSE_USER_INSTRUCTION}{batch.batch_text}"
            ),
        },
    ]


def _targeted_screening_messages(
    *,
    theme: str,
    batch: Batch,
    fragment_map: dict[str, Fragment],
) -> list[dict[str, str]]:
    fragment_lines: list[str] = []
    for piece_id in batch.piece_ids:
        fragment = fragment_map.get(piece_id)
        if fragment is None:
            continue
        fragment_lines.append(f"### {piece_id}\n{fragment.original_text}")
    return [
        {"role": "system", "content": TARGETED_SYSTEM},
        {
            "role": "user",
            "content": (
                f"{TARGETED_USER_THEME_LABEL}{theme}\n\n"
                f"{SOURCE_FILE_LABEL}{batch.source_file}\n"
                f"{TARGETED_USER_INSTRUCTION}{'\n\n'.join(fragment_lines)}"
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
        {"role": "system", "content": ARBITRATION_SYSTEM},
        {
            "role": "user",
            "content": (
                f"{ARBITRATION_THEME_LABEL}{theme}\n\n"
                f"{ARBITRATION_ORIGINAL_LABEL}{original_text}\n\n"
                f"{ARBITRATION_LLM1_LABEL}{json.dumps(llm1_result, ensure_ascii=False)}\n"
                f"{ARBITRATION_LLM2_LABEL}{json.dumps(llm2_result, ensure_ascii=False)}\n\n"
                f"{ARBITRATION_TASK}"
            ),
        },
    ]


def _normalize_coarse_screening_payload(
    payload: dict[str, Any],
    *,
    target_themes: list[dict[str, str]],
) -> list[dict[str, Any]]:
    raw_results = payload.get("themes")
    if not isinstance(raw_results, list):
        raise Stage2FormatError("粗筛返回缺少 themes 列表。")

    theme_names = _theme_names(target_themes)
    match_map: dict[str, dict[str, Any]] = {}
    for raw_item in raw_results:
        if not isinstance(raw_item, dict):
            continue
        theme = str(raw_item.get("theme") or "").strip()
        if theme not in theme_names or theme in match_map:
            continue
        match_map[theme] = {
            "theme": theme,
            "is_relevant": bool(raw_item.get("is_relevant")),
        }
    return [
        match_map.get(theme)
        or {
            "theme": theme,
            "is_relevant": False,
        }
        for theme in theme_names
    ]


def _normalize_targeted_screening_payload(
    payload: dict[str, Any],
    *,
    batch: Batch,
) -> list[dict[str, Any]]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise Stage2FormatError(f"{batch.batch_id} 返回缺少 results 列表。")

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
        is_relevant = bool(raw_item.get("is_relevant"))
        reason = str(raw_item.get("reason") or "").strip()
        normalized.append(
            {
                "piece_id": piece_id,
                "is_relevant": is_relevant,
                "reason": reason if is_relevant else "NA",
            }
        )

    for piece_id in expected_piece_ids:
        if piece_id in seen_piece_ids:
            continue
        normalized.append(
            {
                "piece_id": piece_id,
                "is_relevant": False,
                "reason": "NA",
            }
        )

    order = {pid: idx for idx, pid in enumerate(expected_piece_ids)}
    normalized.sort(key=lambda item: order[item["piece_id"]])
    return normalized


def _compact_usage_stats(usage: dict[str, Any]) -> dict[str, Any]:
    """保留 completion/prompt/total 等汇总字段，去掉各平台附带的 *_tokens_details 嵌套。"""
    if not isinstance(usage, dict):
        return {}
    out = dict(usage)
    out.pop("prompt_tokens_details", None)
    out.pop("completion_tokens_details", None)
    return out


def _screen_batch_coarse(
    *,
    client: OpenAICompatClient,
    slot: str,
    batch: Batch,
    target_themes: list[dict[str, str]],
) -> dict[str, Any]:
    def invoke(active_client: OpenAICompatClient) -> dict[str, Any]:
        payload, usage = active_client.chat_json(
            messages=_coarse_screening_messages(target_themes=target_themes, batch=batch),
            max_tokens=400,
        )
        return {
            "batch_id": batch.batch_id,
            "source_file": batch.source_file,
            "repo_dir": batch.repo_dir,
            "themes": _normalize_coarse_screening_payload(payload, target_themes=target_themes),
            "usage": _compact_usage_stats(usage),
        }

    try:
        return _run_with_format_fallback(client=client, invoke=invoke)
    except Stage2FallbackExhaustedError as exc:
        return _coarse_manual_review_row(
            client=client,
            batch=batch,
            target_themes=target_themes,
            exc=exc,
        )
    except Exception as exc:  # noqa: BLE001
        raise Stage2RunnerError(f"{slot} 粗筛失败 | batch={batch.batch_id}: {exc}") from exc


def _screen_batch_targeted(
    *,
    client: OpenAICompatClient,
    slot: str,
    batch: Batch,
    theme: str,
    fragment_map: dict[str, Fragment],
) -> dict[str, Any]:
    def invoke(active_client: OpenAICompatClient) -> dict[str, Any]:
        payload, usage = active_client.chat_json(
            messages=_targeted_screening_messages(theme=theme, batch=batch, fragment_map=fragment_map),
            max_tokens=5000,
        )
        return {
            "batch_id": batch.batch_id,
            "batch_theme_key": f"{batch.batch_id}::{theme}",
            "matched_theme": theme,
            "source_file": batch.source_file,
            "repo_dir": batch.repo_dir,
            "piece_ids": list(batch.piece_ids),
            "results": _normalize_targeted_screening_payload(payload, batch=batch),
            "usage": _compact_usage_stats(usage),
        }

    try:
        return _run_with_format_fallback(client=client, invoke=invoke)
    except Stage2FallbackExhaustedError as exc:
        return _targeted_manual_review_row(
            batch=batch,
            theme=theme,
            exc=exc,
        )
    except Exception as exc:  # noqa: BLE001
        raise Stage2RunnerError(f"{slot} 精筛失败 | batch={batch.batch_id} | theme={theme}: {exc}") from exc


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
    def invoke(active_client: OpenAICompatClient) -> dict[str, Any]:
        payload, usage = active_client.chat_json(
            messages=_arbitration_messages(
                theme=str(dispute["matched_theme"]),
                original_text=str(dispute["original_text"]),
                llm1_result=dispute["llm1_result"],
                llm2_result=dispute["llm2_result"],
            ),
            max_tokens=1200,
        )
        return {
            "dispute_key": dispute["dispute_key"],
            "piece_id": dispute["piece_id"],
            "source_file": dispute["source_file"],
            "matched_theme": dispute["matched_theme"],
            "decision": _normalize_arbitration_payload(payload),
            "usage": usage,
            "generated_at": _now_iso(),
            "provider": active_client.provider,
            "model": active_client.model,
            "used_format_fallback": active_client is not client,
        }

    try:
        return _run_with_format_fallback(client=client, invoke=invoke)
    except Stage2FallbackExhaustedError as exc:
        return _arbitration_manual_review_row(client=client, dispute=dispute, exc=exc)
    except Exception as exc:  # noqa: BLE001
        raise Stage2RunnerError(f"llm3 仲裁失败 | piece_id={dispute['piece_id']}: {exc}") from exc


def _iter_windowed_futures(
    *,
    executor: ThreadPoolExecutor,
    items: Iterable[WorkItem],
    max_in_flight: int,
    submit_job: Callable[[WorkItem], Future[Any]],
    on_wait: Callable[[int], None] | None = None,
) -> Iterator[tuple[WorkItem, Future[Any]]]:
    pending: dict[Future[Any], WorkItem] = {}
    iterator = iter(items)
    window_size = max(1, int(max_in_flight))

    def refill() -> None:
        while len(pending) < window_size:
            try:
                item = next(iterator)
            except StopIteration:
                return
            pending[submit_job(item)] = item

    refill()
    while pending:
        done, _ = wait(
            pending.keys(),
            timeout=_stall_heartbeat_seconds(),
            return_when=FIRST_COMPLETED,
        )
        if not done:
            if on_wait is not None:
                on_wait(len(pending))
            continue
        for future in done:
            item = pending.pop(future)
            yield item, future
        refill()


def _run_with_format_fallback(
    *,
    client: OpenAICompatClient,
    invoke: Callable[[OpenAICompatClient], TaskResult],
) -> TaskResult:
    try:
        return invoke(client)
    except Stage2FormatError as primary_error:
        fallback_client = client.fallback_client
        if fallback_client is None or client.fallback_max_retries <= 0:
            raise
        fallback_errors: list[str] = []
        for _ in range(client.fallback_max_retries):
            try:
                return invoke(fallback_client)
            except Stage2FormatError as fallback_error:
                fallback_errors.append(str(fallback_error))
        raise Stage2FallbackExhaustedError(
            primary_error=str(primary_error),
            fallback_errors=fallback_errors,
            fallback_model=fallback_client.model,
        ) from primary_error


def _manual_review_reason(exc: Stage2FallbackExhaustedError) -> str:
    return f"自动兜底失败，需人工审核。{exc}"


def _coarse_manual_review_row(
    *,
    client: OpenAICompatClient,
    batch: Batch,
    target_themes: list[dict[str, str]],
    exc: Stage2FallbackExhaustedError,
) -> dict[str, Any]:
    fallback_client = client.fallback_client
    return {
        "batch_id": batch.batch_id,
        "source_file": batch.source_file,
        "repo_dir": batch.repo_dir,
        "themes": [{"theme": theme, "is_relevant": True} for theme in _theme_names(target_themes)],
        "usage": {},
        "needs_manual_review": True,
        "manual_review_stage": "coarse",
        "manual_review_key": batch.batch_id,
        "manual_review_reason": _manual_review_reason(exc),
        "primary_error": exc.primary_error,
        "fallback_errors": exc.fallback_errors,
        "piece_ids": list(batch.piece_ids),
    }


def _targeted_manual_review_row(
    *,
    batch: Batch,
    theme: str,
    exc: Stage2FallbackExhaustedError,
) -> dict[str, Any]:
    return {
        "batch_id": batch.batch_id,
        "batch_theme_key": f"{batch.batch_id}::{theme}",
        "matched_theme": theme,
        "source_file": batch.source_file,
        "repo_dir": batch.repo_dir,
        "piece_ids": list(batch.piece_ids),
        "results": [
            {
                "piece_id": piece_id,
                "is_relevant": True,
                "reason": MANUAL_REVIEW_REQUIRED_REASON,
            }
            for piece_id in batch.piece_ids
        ],
        "usage": {},
        "needs_manual_review": True,
        "manual_review_stage": "targeted",
        "manual_review_key": f"{batch.batch_id}::{theme}",
        "manual_review_reason": _manual_review_reason(exc),
        "primary_error": exc.primary_error,
        "fallback_errors": exc.fallback_errors,
    }


def _arbitration_manual_review_row(
    *,
    client: OpenAICompatClient,
    dispute: dict[str, Any],
    exc: Stage2FallbackExhaustedError,
) -> dict[str, Any]:
    fallback_client = client.fallback_client
    return {
        "dispute_key": dispute["dispute_key"],
        "piece_id": dispute["piece_id"],
        "source_file": dispute["source_file"],
        "matched_theme": dispute["matched_theme"],
        "original_text": dispute["original_text"],
        "decision": {
            "is_relevant": True,
            "reason": MANUAL_REVIEW_REQUIRED_REASON,
        },
        "usage": {},
        "generated_at": _now_iso(),
        "provider": fallback_client.provider if fallback_client is not None else client.provider,
        "model": fallback_client.model if fallback_client is not None else client.model,
        "used_format_fallback": True,
        "needs_manual_review": True,
        "manual_review_stage": "arbitration",
        "manual_review_key": dispute["dispute_key"],
        "manual_review_reason": _manual_review_reason(exc),
        "primary_error": exc.primary_error,
        "fallback_errors": exc.fallback_errors,
    }


def _manual_review_entries_from_row(
    *,
    row: dict[str, Any],
    fragment_map: dict[str, Fragment],
    slot: str | None = None,
) -> list[dict[str, Any]]:
    if not bool(row.get("needs_manual_review")):
        return []

    stage = str(row.get("manual_review_stage") or "")
    generated_at = str(row.get("generated_at") or _now_iso())
    resolved_slot = slot if slot is not None else str(row.get("slot") or "")
    base = {
        "manual_review_stage": stage,
        "slot": resolved_slot,
        "batch_id": str(row.get("batch_id") or ""),
        "manual_review_reason": str(row.get("manual_review_reason") or ""),
        "primary_error": str(row.get("primary_error") or ""),
        "fallback_errors": list(row.get("fallback_errors") or []),
        "generated_at": generated_at,
    }
    entries: list[dict[str, Any]] = []

    if stage == "coarse":
        candidate_themes = [str(item.get("theme") or "") for item in row.get("themes") or [] if str(item.get("theme") or "").strip()]
        for piece_id in row.get("piece_ids") or []:
            fragment = fragment_map.get(str(piece_id))
            entries.append(
                {
                    **base,
                    "manual_review_key": f"{row.get('manual_review_key')}::{piece_id}",
                    "piece_id": str(piece_id),
                    "source_file": fragment.source_file if fragment is not None else str(row.get("source_file") or ""),
                    "repo_dir": fragment.repo_dir if fragment is not None else str(row.get("repo_dir") or ""),
                    "text_file": fragment.text_file if fragment is not None else "",
                    "matched_theme": "",
                    "candidate_themes": candidate_themes,
                    "original_text": fragment.original_text if fragment is not None else "",
                }
            )
        return entries

    if stage == "targeted":
        matched_theme = str(row.get("matched_theme") or "")
        for piece_id in row.get("piece_ids") or []:
            fragment = fragment_map.get(str(piece_id))
            entries.append(
                {
                    **base,
                    "manual_review_key": f"{row.get('manual_review_key')}::{piece_id}",
                    "piece_id": str(piece_id),
                    "source_file": fragment.source_file if fragment is not None else str(row.get("source_file") or ""),
                    "repo_dir": fragment.repo_dir if fragment is not None else str(row.get("repo_dir") or ""),
                    "text_file": fragment.text_file if fragment is not None else "",
                    "matched_theme": matched_theme,
                    "candidate_themes": [matched_theme] if matched_theme else [],
                    "original_text": fragment.original_text if fragment is not None else "",
                }
            )
        return entries

    piece_id = str(row.get("piece_id") or "")
    fragment = fragment_map.get(piece_id)
    entries.append(
        {
            **base,
            "manual_review_key": str(row.get("manual_review_key") or ""),
            "piece_id": piece_id,
            "source_file": fragment.source_file if fragment is not None else str(row.get("source_file") or ""),
            "repo_dir": fragment.repo_dir if fragment is not None else str(row.get("repo_dir") or ""),
            "text_file": fragment.text_file if fragment is not None else "",
            "matched_theme": str(row.get("matched_theme") or ""),
            "candidate_themes": [str(row.get("matched_theme") or "")] if str(row.get("matched_theme") or "").strip() else [],
            "original_text": fragment.original_text if fragment is not None else str(row.get("original_text") or ""),
        }
    )
    return entries


def _render_manual_review_report(target_dir: Path) -> None:
    rows = read_jsonl(_manual_review_path(target_dir))
    lines = [
        "# Manual Review Required",
        "",
        "以下 fragment 需要人工审核。自动筛查与 fallback 均未能稳定返回可用结构化结果。",
        "",
    ]
    if not rows:
        lines.append("当前无需要人工审核的 fragment。")
        _manual_review_report_path(target_dir).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    for index, row in enumerate(rows, start=1):
        piece_id = str(row.get("piece_id") or "")
        theme = str(row.get("matched_theme") or "")
        candidate_themes = [str(item) for item in row.get("candidate_themes") or [] if str(item).strip()]
        theme_line = theme or (" / ".join(candidate_themes) if candidate_themes else "待人工判断主题")
        lines.extend(
            [
                f"## {index}. {piece_id or '未知 piece_id'} | {row.get('manual_review_stage') or 'unknown'} | {theme_line}",
                "",
                f"- 文献: {row.get('source_file') or ''}",
                f"- 目录: {row.get('repo_dir') or ''}",
                f"- 批次: {row.get('batch_id') or ''}",
                f"- 时间: {row.get('generated_at') or ''}",
                f"- 原因: {row.get('manual_review_reason') or ''}",
            ]
        )
        if candidate_themes and not theme:
            lines.append(f"- 候选主题: {'; '.join(candidate_themes)}")
        lines.extend(
            [
                "",
                "```text",
                str(row.get("original_text") or ""),
                "```",
                "",
            ]
        )
    _manual_review_report_path(target_dir).write_text("\n".join(lines), encoding="utf-8")


def _append_manual_review_entries(
    target_dir: Path,
    row: dict[str, Any],
    fragment_map: dict[str, Fragment],
    *,
    slot: str | None = None,
) -> None:
    entries = _manual_review_entries_from_row(row=row, fragment_map=fragment_map, slot=slot)
    if not entries:
        return
    manual_path = _manual_review_path(target_dir)
    combined = read_jsonl(manual_path)
    combined.extend(entries)
    write_jsonl(manual_path, combined)
    _render_manual_review_report(target_dir)


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


def _coarse_output_path(target_dir: Path, slot: str) -> Path:
    return target_dir / (LLM1_COARSE_FILE_NAME if slot == "llm1" else LLM2_COARSE_FILE_NAME)


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


def _manual_review_path(target_dir: Path) -> Path:
    return target_dir / MANUAL_REVIEW_FILE_NAME


def _manual_review_report_path(target_dir: Path) -> Path:
    return target_dir / MANUAL_REVIEW_REPORT_FILE_NAME


def _artifact_state_path(target_dir: Path) -> Path:
    return target_dir / "run_state.json"


def _load_target_state(target_dir: Path) -> dict[str, Any]:
    payload = read_json(_artifact_state_path(target_dir), default={})
    return payload if isinstance(payload, dict) else {}


def _save_target_state(target_dir: Path, *, repo_dirs: tuple[str, ...], max_fragments: int | None) -> None:
    state = _load_target_state(target_dir)
    state.update(
        {
            "pipeline_state_version": PIPELINE_STATE_VERSION,
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
    if phase == "coarse_screening":
        return (
            f"phase={phase}"
            f" | llm1={int(state.get('llm1_completed_batches') or 0)}/{int(state.get('batch_count') or 0)}"
            f" | llm2={int(state.get('llm2_completed_batches') or 0)}/{int(state.get('batch_count') or 0)}"
        )
    if phase == "targeted_screening":
        return (
            f"phase={phase}"
            f" | pairs={int(state.get('candidate_pair_count') or 0)}"
            f" | llm1={int(state.get('llm1_completed_pairs') or 0)}/{int(state.get('candidate_pair_count') or 0)}"
            f" | llm2={int(state.get('llm2_completed_pairs') or 0)}/{int(state.get('candidate_pair_count') or 0)}"
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
    for key in ("fragment_count", "batch_count", "candidate_pair_count", "dispute_count"):
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
    return write_json(_disputes_path(target_dir), {"records": disputes})


def _load_disputes(path: Path) -> list[dict[str, Any]]:
    payload = read_json(path, default=None)
    if isinstance(payload, dict):
        rows = payload.get("records")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return read_jsonl(path)


def _load_cached_rows_by_key(path: Path, key: str) -> dict[str, dict[str, Any]]:
    cached: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        token = str(row.get(key) or "").strip()
        if token:
            cached[token] = row
    return cached


def _run_coarse_batches(
    *,
    client: OpenAICompatClient,
    slot: str,
    batches: list[Batch],
    fragment_map: dict[str, Fragment],
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
        phase="coarse_screening",
        batch_count=len(batches),
        **{f"{slot}_completed_batches": len(cached)},
    )
    if cached:
        _emit_progress(
            progress_callback,
            event="slot_resume",
            target=target_token,
            slot=slot,
            stage="coarse",
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
            estimate_request_tokens(messages=_coarse_screening_messages(target_themes=target_themes, batch=batch), max_tokens=400)
            for batch in pending_batches
        ),
    )
    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        for batch, future in _iter_windowed_futures(
            executor=executor,
            items=pending_batches,
            max_in_flight=effective_workers,
            submit_job=lambda item: executor.submit(
                _screen_batch_coarse,
                client=client,
                slot=slot,
                batch=item,
                target_themes=target_themes,
            ),
            on_wait=lambda in_flight: _emit_progress(
                progress_callback,
                event="slot_waiting",
                target=target_token,
                slot=slot,
                stage="coarse",
                completed=finished_count,
                total=len(batches),
                in_flight=in_flight,
            ),
        ):
            row = future.result()
            cached[batch.batch_id] = row
            write_jsonl(output_path, [cached[b.batch_id] for b in batches if b.batch_id in cached])
            _append_manual_review_entries(target_dir, row, fragment_map, slot=slot)
            finished_count += 1
            _update_target_state(
                target_dir,
                phase="coarse_screening",
                batch_count=len(batches),
                **{f"{slot}_completed_batches": finished_count},
            )
            update_stage2_manifest_checkpoint(
                project_dir,
                action="checkpoint",
                target=target_token,
                cursor=f"{slot}:coarse_batch={finished_count}/{len(batches)}",
                piece_id=batch.piece_ids[-1] if batch.piece_ids else "",
                note=f"{slot} 粗筛已完成 {finished_count}/{len(batches)} 个批次",
            )
            _emit_progress(
                progress_callback,
                event="slot_progress",
                target=target_token,
                slot=slot,
                stage="coarse",
                completed=finished_count,
                total=len(batches),
                batch_id=batch.batch_id,
            )

    return [cached[batch_map_key.batch_id] for batch_map_key in batches if batch_map_key.batch_id in cached]


def _build_candidate_pairs(
    *,
    batches: list[Batch],
    target_themes: list[dict[str, str]],
    llm1_rows: list[dict[str, Any]],
    llm2_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    batch_map = {batch.batch_id: batch for batch in batches}
    batch_order = {batch.batch_id: index for index, batch in enumerate(batches)}
    theme_order = {theme: index for index, theme in enumerate(_theme_names(target_themes))}
    positive_keys: set[tuple[str, str]] = set()

    for rows in (llm1_rows, llm2_rows):
        for row in rows:
            batch_id = str(row.get("batch_id") or "").strip()
            if batch_id not in batch_map:
                continue
            for item in row.get("themes") or []:
                theme = str(item.get("theme") or "").strip()
                if theme not in theme_order:
                    continue
                if bool(item.get("is_relevant")):
                    positive_keys.add((batch_id, theme))

    pairs = [
        {
            "batch_theme_key": f"{batch_id}::{theme}",
            "batch_id": batch_id,
            "matched_theme": theme,
            "source_file": batch_map[batch_id].source_file,
            "repo_dir": batch_map[batch_id].repo_dir,
            "piece_ids": list(batch_map[batch_id].piece_ids),
        }
        for batch_id, theme in sorted(
            positive_keys,
            key=lambda item: (batch_order.get(item[0], 0), theme_order.get(item[1], 0), item[1]),
        )
    ]
    return pairs


def _run_targeted_pairs(
    *,
    client: OpenAICompatClient,
    slot: str,
    candidate_pairs: list[dict[str, Any]],
    batches: list[Batch],
    fragment_map: dict[str, Fragment],
    output_path: Path,
    workers: int,
    project_dir: Path,
    target_token: str,
    progress_callback: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    target_dir = output_path.parent
    cached = _load_cached_rows_by_key(output_path, "batch_theme_key")
    pending_pairs = [pair for pair in candidate_pairs if pair["batch_theme_key"] not in cached]
    _update_target_state(
        target_dir,
        phase="targeted_screening",
        candidate_pair_count=len(candidate_pairs),
        **{f"{slot}_completed_pairs": len(cached)},
    )
    if cached:
        _emit_progress(
            progress_callback,
            event="slot_resume",
            target=target_token,
            slot=slot,
            stage="targeted",
            completed=len(cached),
            total=len(candidate_pairs),
        )
    if not pending_pairs:
        return [cached[pair["batch_theme_key"]] for pair in candidate_pairs if pair["batch_theme_key"] in cached]

    batch_map = {batch.batch_id: batch for batch in batches}
    finished_count = len(cached)
    effective_workers = client.effective_worker_limit(
        requested_workers=workers,
        estimated_tokens=max(
            estimate_request_tokens(
                messages=_targeted_screening_messages(
                    theme=str(pair["matched_theme"]),
                    batch=batch_map[str(pair["batch_id"])],
                    fragment_map=fragment_map,
                ),
                max_tokens=5000,
            )
            for pair in pending_pairs
        ),
    )
    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        for pair, future in _iter_windowed_futures(
            executor=executor,
            items=pending_pairs,
            max_in_flight=effective_workers,
            submit_job=lambda item: executor.submit(
                _screen_batch_targeted,
                client=client,
                slot=slot,
                batch=batch_map[str(item["batch_id"])],
                theme=str(item["matched_theme"]),
                fragment_map=fragment_map,
            ),
            on_wait=lambda in_flight: _emit_progress(
                progress_callback,
                event="slot_waiting",
                target=target_token,
                slot=slot,
                stage="targeted",
                completed=finished_count,
                total=len(candidate_pairs),
                in_flight=in_flight,
            ),
        ):
            row = future.result()
            key = str(pair["batch_theme_key"])
            cached[key] = row
            write_jsonl(
                output_path,
                [cached[str(p["batch_theme_key"])] for p in candidate_pairs if str(p["batch_theme_key"]) in cached],
            )
            _append_manual_review_entries(target_dir, row, fragment_map, slot=slot)
            finished_count += 1
            _update_target_state(
                target_dir,
                phase="targeted_screening",
                candidate_pair_count=len(candidate_pairs),
                **{f"{slot}_completed_pairs": finished_count},
            )
            update_stage2_manifest_checkpoint(
                project_dir,
                action="checkpoint",
                target=target_token,
                cursor=f"{slot}:targeted_pair={finished_count}/{len(candidate_pairs)}",
                piece_id=str((pair.get("piece_ids") or [""])[-1] or ""),
                note=f"{slot} 精筛已完成 {finished_count}/{len(candidate_pairs)} 个候选主题",
            )
            _emit_progress(
                progress_callback,
                event="slot_progress",
                target=target_token,
                slot=slot,
                stage="targeted",
                completed=finished_count,
                total=len(candidate_pairs),
                batch_id=str(pair["batch_id"]),
                theme=str(pair["matched_theme"]),
            )

    return [cached[str(pair["batch_theme_key"])] for pair in candidate_pairs if str(pair["batch_theme_key"]) in cached]


def _flatten_targeted_rows(
    slot_rows: list[dict[str, Any]],
    fragment_map: dict[str, Fragment],
    *,
    slot: str,
    model: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    flattened: dict[tuple[str, str], dict[str, Any]] = {}
    for row in slot_rows:
        batch_id = str(row.get("batch_id") or "")
        theme = str(row.get("matched_theme") or "").strip()
        if not theme:
            continue
        for piece_result in row.get("results") or []:
            piece_id = str(piece_result.get("piece_id") or "").strip()
            fragment = fragment_map.get(piece_id)
            if fragment is None:
                continue
            flattened[(piece_id, theme)] = {
                "piece_id": piece_id,
                "source_file": fragment.source_file,
                "original_text": fragment.original_text,
                "matched_theme": theme,
                "is_relevant": bool(piece_result.get("is_relevant")),
                "reason": str(piece_result.get("reason") or "").strip(),
                "slot": str(slot),
                "model": str(model),
                "batch_id": batch_id,
                "needs_manual_review": bool(row.get("needs_manual_review")) or str(piece_result.get("reason") or "") == MANUAL_REVIEW_REQUIRED_REASON,
                "manual_review_reason": str(row.get("manual_review_reason") or "").strip(),
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
            manual_review_reasons = [
                str(item.get("manual_review_reason") or "").strip()
                for item in (left, right)
                if bool(item.get("needs_manual_review"))
            ]
            consensus.append(
                {
                    "piece_id": left["piece_id"],
                    "source_file": left["source_file"],
                    "matched_theme": left["matched_theme"],
                    "original_text": left["original_text"],
                    "note": f"llm1: {left['reason']} | llm2: {right['reason']}",
                    "judgment": "consensus",
                    "needs_manual_review": bool(left.get("needs_manual_review")) or bool(right.get("needs_manual_review")),
                    "manual_review_reason": " | ".join(item for item in manual_review_reasons if item),
                    "llm1_result": {
                        "is_relevant": left["is_relevant"],
                        "reason": left["reason"],
                        "model": left["model"],
                        "batch_id": left["batch_id"],
                        "needs_manual_review": bool(left.get("needs_manual_review")),
                    },
                    "llm2_result": {
                        "is_relevant": right["is_relevant"],
                        "reason": right["reason"],
                        "model": right["model"],
                        "batch_id": right["batch_id"],
                        "needs_manual_review": bool(right.get("needs_manual_review")),
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
                    "needs_manual_review": bool(left.get("needs_manual_review")),
                },
                "llm2_result": {
                    "is_relevant": right["is_relevant"],
                    "reason": right["reason"],
                    "model": right["model"],
                    "batch_id": right["batch_id"],
                    "needs_manual_review": bool(right.get("needs_manual_review")),
                },
            }
        )

    return consensus, disputes


def _run_arbitration(
    *,
    client: OpenAICompatClient,
    disputes_path: Path,
    fragment_map: dict[str, Fragment],
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
            resolved_count = len(cached)
            for dispute, future in _iter_windowed_futures(
                executor=executor,
                items=pending_disputes,
                max_in_flight=effective_workers,
                submit_job=lambda item: executor.submit(_arbitrate_dispute, client=client, dispute=item),
                on_wait=lambda in_flight: _emit_progress(
                    progress_callback,
                    event="arbitration_waiting",
                    target=target_token,
                    completed=resolved_count,
                    total=len(disputes),
                    in_flight=in_flight,
                ),
            ):
                row = future.result()
                cached[dispute["dispute_key"]] = row
                write_jsonl(
                    output_path,
                    [cached[d["dispute_key"]] for d in disputes if d["dispute_key"] in cached],
                )
                _append_manual_review_entries(target_dir, row, fragment_map, slot="llm3")
                resolved_count += 1
                _update_target_state(
                    target_dir,
                    phase="arbitration",
                    dispute_count=len(disputes),
                    llm3_completed_disputes=resolved_count,
                )
                update_stage2_manifest_checkpoint(
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
            "needs_manual_review": bool(record.get("needs_manual_review")),
            "manual_review_reason": str(record.get("manual_review_reason") or "").strip(),
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
            "needs_manual_review": bool(arbitration.get("needs_manual_review")),
            "manual_review_reason": str(arbitration.get("manual_review_reason") or "").strip(),
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
                "needs_manual_review": bool(record.get("needs_manual_review")),
                "manual_review_reason": str(record.get("manual_review_reason") or "").strip(),
            }
            for record in records
        ],
    }


def _merge_primary_corpus_records(*record_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for records in record_groups:
        for record in records:
            piece_id = str(record.get("piece_id") or "").strip()
            matched_theme = str(record.get("matched_theme") or "").strip()
            if not piece_id:
                continue
            merged[(piece_id, matched_theme)] = {
                "piece_id": piece_id,
                "source_file": str(record.get("source_file") or "").strip(),
                "matched_theme": matched_theme,
                "original_text": str(record.get("original_text") or ""),
                "note": str(record.get("note") or ""),
                "needs_manual_review": bool(record.get("needs_manual_review")),
                "manual_review_reason": str(record.get("manual_review_reason") or "").strip(),
            }
    return sorted(merged.values(), key=lambda item: (item["piece_id"], item["matched_theme"]))


def _load_project_final_records(project_dir: Path) -> list[dict[str, Any]]:
    targets_dir = stage2_workspace_dir(project_dir) / TARGETS_DIR_NAME
    if not targets_dir.exists():
        return []
    return _merge_primary_corpus_records(
        *[read_jsonl(_final_path(target_dir)) for target_dir in sorted(path for path in targets_dir.iterdir() if path.is_dir())]
    )


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
    payload = load_stage2_manifest(project_dir)
    if not payload:
        raise Stage2RunnerError(f"缺少 manifest: {manifest_path(project_dir)}")
    return payload


def _target_state_matches(target_dir: Path, *, repo_dirs: tuple[str, ...], max_fragments: int | None) -> bool:
    state = _load_target_state(target_dir)
    if not state:
        return False
    return (
        int(state.get("pipeline_state_version") or 0) == PIPELINE_STATE_VERSION
        and
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
    fallback_config = fallback_payload(dotenv_path=dotenv_path)
    fallback_client: OpenAICompatClient | None = None
    if fallback_config.get("enabled"):
        fallback_client = OpenAICompatClient(
            model=str(fallback_config["model"]),
            base_url=str(fallback_config["base_url"]),
            api_keys=tuple(str(key) for key in fallback_config["api_keys"] or () if str(key).strip()),
            slot="fallback",
            provider=str(fallback_config["provider"]),
            rate_controller=None,
        )
    for slot in ("llm1", "llm2", "llm3"):
        payload = slot_payload(slot, dotenv_path=dotenv_path)
        clients[slot] = OpenAICompatClient(
            model=str(payload["model"]),
            base_url=str(payload["base_url"]),
            api_keys=tuple(str(key) for key in payload["api_keys"] or () if str(key).strip()),
            slot=slot,
            provider=str(payload["provider"]),
            rate_controller=registry.get(payload),
            fallback_client=fallback_client,
            fallback_max_retries=int(fallback_config.get("max_retries") or 0),
        )
    return clients


def _update_manifest_status(project_dir: Path, *, status: str, note: str = "") -> None:
    manifest_payload = load_stage2_manifest(project_dir)
    manifest_payload["status"] = status
    if note:
        manifest_payload["last_run_note"] = note
    manifest_payload["last_run_at"] = _now_iso()
    write_stage2_manifest(project_dir, manifest_payload)


def _load_existing_target_final_records(project_dir: Path, target_token: str) -> list[dict[str, Any]]:
    return read_jsonl(_final_path(_target_workspace_dir(project_dir, target_token)))


def _target_summary_from_state(state: dict[str, Any]) -> dict[str, Any]:
    if not state or not bool(state.get("is_completed")):
        return {}
    keys = (
        "target",
        "repo_dir_count",
        "fragment_count",
        "batch_count",
        "candidate_pair_count",
        "consensus_count",
        "dispute_count",
        "arbitrated_keep_count",
        "final_record_count",
        "final_piece_count",
        "manual_review_count",
        "manual_review_report_path",
        "updated_at",
    )
    summary = {key: state[key] for key in keys if key in state}
    return summary if str(summary.get("target") or "").strip() else {}


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
    session_before_run = load_stage2_manifest(project_path)
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
        update_stage2_manifest_checkpoint(project_path, action="reset", note="force rerun")
        completed_targets_before_run = set()
    clients = _build_clients(dotenv_path=dotenv_path)
    llm1_workers = max(
        1,
        int(llm1_workers if llm1_workers is not None else scaled_slot_worker_limit("llm1", dotenv_path=dotenv_path)),
    )
    llm2_workers = max(
        1,
        int(llm2_workers if llm2_workers is not None else scaled_slot_worker_limit("llm2", dotenv_path=dotenv_path)),
    )
    llm3_workers = max(
        1,
        int(llm3_workers if llm3_workers is not None else scaled_slot_worker_limit("llm3", dotenv_path=dotenv_path)),
    )
    _update_manifest_status(project_path, status="running", note="阶段二执行中")
    _emit_progress(
        progress_callback,
        event="pipeline_started",
        project_name=project_path.name,
        target_count=len(selection.resolved_targets),
        analysis_targets=[item.token for item in selection.resolved_targets],
    )

    summaries: list[dict[str, Any]] = []

    try:
        for target in selection.resolved_targets:
            target_dir = _ensure_target_workspace(project_path, target.token)
            if target.token in completed_targets_before_run and not force_rerun:
                final_records = _load_existing_target_final_records(project_path, target.token)
                if final_records:
                    summary = _target_summary_from_state(_load_target_state(target_dir))
                    if summary:
                        summaries.append(summary)
                    _emit_progress(
                        progress_callback,
                        event="target_reused",
                        target=target.token,
                        final_record_count=len(final_records),
                    )
                    continue
                update_stage2_manifest_checkpoint(project_path, action="reset", note="缓存缺失，重新构建阶段二")
                completed_targets_before_run = set()

            update_stage2_manifest_checkpoint(project_path, action="start", target=target.token, note="开始执行阶段二目标")
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

            llm1_coarse_rows = _run_coarse_batches(
                client=clients["llm1"],
                slot="llm1",
                batches=batches,
                fragment_map=fragment_map,
                target_themes=target_themes,
                output_path=_coarse_output_path(target_dir, "llm1"),
                workers=llm1_workers,
                project_dir=project_path,
                target_token=target.token,
                progress_callback=progress_callback,
            )
            llm2_coarse_rows = _run_coarse_batches(
                client=clients["llm2"],
                slot="llm2",
                batches=batches,
                fragment_map=fragment_map,
                target_themes=target_themes,
                output_path=_coarse_output_path(target_dir, "llm2"),
                workers=llm2_workers,
                project_dir=project_path,
                target_token=target.token,
                progress_callback=progress_callback,
            )
            candidate_pairs = _build_candidate_pairs(
                batches=batches,
                target_themes=target_themes,
                llm1_rows=llm1_coarse_rows,
                llm2_rows=llm2_coarse_rows,
            )
            _emit_progress(
                progress_callback,
                event="candidate_pairs_ready",
                target=target.token,
                candidate_pair_count=len(candidate_pairs),
            )
            _update_target_state(
                target_dir,
                phase="targeted_ready",
                candidate_pair_count=len(candidate_pairs),
            )

            llm1_rows = _run_targeted_pairs(
                client=clients["llm1"],
                slot="llm1",
                candidate_pairs=candidate_pairs,
                batches=batches,
                fragment_map=fragment_map,
                output_path=_slot_output_path(target_dir, "llm1"),
                workers=llm1_workers,
                project_dir=project_path,
                target_token=target.token,
                progress_callback=progress_callback,
            )
            llm2_rows = _run_targeted_pairs(
                client=clients["llm2"],
                slot="llm2",
                candidate_pairs=candidate_pairs,
                batches=batches,
                fragment_map=fragment_map,
                output_path=_slot_output_path(target_dir, "llm2"),
                workers=llm2_workers,
                project_dir=project_path,
                target_token=target.token,
                progress_callback=progress_callback,
            )

            llm1_map = _flatten_targeted_rows(
                llm1_rows,
                fragment_map,
                slot="llm1",
                model=str(clients["llm1"].model),
            )
            llm2_map = _flatten_targeted_rows(
                llm2_rows,
                fragment_map,
                slot="llm2",
                model=str(clients["llm2"].model),
            )
            consensus, disputes = _build_consensus_and_disputes(llm1_map=llm1_map, llm2_map=llm2_map)
            write_json(_consensus_path(target_dir), {"records": consensus})
            disputes_path = _write_disputes(target_dir, disputes)
            _emit_progress(
                progress_callback,
                event="consensus_ready",
                target=target.token,
                candidate_pair_count=len(candidate_pairs),
                consensus_count=len(consensus),
                dispute_count=len(disputes),
            )
            _update_target_state(
                target_dir,
                phase="disputes_ready",
                candidate_pair_count=len(candidate_pairs),
                consensus_count=len(consensus),
                dispute_count=len(disputes),
            )

            arbitration_rows = _run_arbitration(
                client=clients["llm3"],
                disputes_path=disputes_path,
                fragment_map=fragment_map,
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
            manual_review_rows = read_jsonl(_manual_review_path(target_dir))

            summary = {
                "target": target.token,
                "repo_dir_count": len(target.repo_dirs),
                "fragment_count": len(fragments),
                "batch_count": len(batches),
                "candidate_pair_count": len(candidate_pairs),
                "consensus_count": len(consensus),
                "dispute_count": len(disputes),
                "arbitrated_keep_count": sum(
                    1 for item in arbitration_rows if bool((item.get("decision") or {}).get("is_relevant"))
                ),
                "final_record_count": len(final_records),
                "final_piece_count": len({item["piece_id"] for item in final_records}),
                "manual_review_count": len(manual_review_rows),
                "manual_review_report_path": str(_manual_review_report_path(target_dir)) if manual_review_rows else "",
                "updated_at": _now_iso(),
            }
            _update_target_state(
                target_dir,
                phase="completed",
                is_completed=True,
                **summary,
                llm1_completed_batches=len(llm1_coarse_rows),
                llm2_completed_batches=len(llm2_coarse_rows),
                llm1_completed_pairs=len(llm1_rows),
                llm2_completed_pairs=len(llm2_rows),
                llm3_completed_disputes=len(arbitration_rows),
            )
            summaries.append(summary)
            _emit_progress(
                progress_callback,
                event="target_completed",
                target=target.token,
                final_record_count=len(final_records),
                final_piece_count=len({item["piece_id"] for item in final_records}),
            )
            update_stage2_manifest_checkpoint(
                project_path,
                action="complete",
                target=target.token,
                piece_id=final_records[-1]["piece_id"] if final_records else "",
                completed_piece_delta=len(final_records),
                note=f"{target.token} 完成，保留 {len(final_records)} 条记录",
            )

        payload = _primary_corpus_payload(_load_project_final_records(project_path))
        write_yaml(project_path / FINAL_CORPUS_FILE_NAME, payload)
        summary_payload = {
            "project_name": project_path.name,
            "manifest_path": str(manifest_path(project_path)),
            "analysis_targets": analysis_targets_from_manifest(load_stage2_manifest(project_path)),
            "piece_count": payload["piece_count"],
            "record_count": len(payload["records"]),
            "targets": summaries,
            "updated_at": _now_iso(),
        }
        _update_manifest_status(project_path, status="completed", note="阶段二执行完成")
        _emit_progress(
            progress_callback,
            event="pipeline_completed",
            project_name=project_path.name,
            piece_count=summary_payload["piece_count"],
            record_count=summary_payload["record_count"],
        )
        return summary_payload
    except Exception as exc:  # noqa: BLE001
        _update_manifest_status(project_path, status="paused", note=str(exc))
        progress = (load_stage2_manifest(project_path).get("retrieval_progress") or {})
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
