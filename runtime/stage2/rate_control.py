"""阶段二模型请求的轻量限流与多 key 负载均衡。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from threading import Lock
import time
from typing import Any

from .api_config import STAGE2_RUNTIME_DEFAULTS


WINDOW_SECONDS = 60.0


def estimate_request_tokens(*, messages: list[dict[str, str]], max_tokens: int) -> int:
    prompt_chars = sum(len(str(message.get("content") or "")) for message in messages)
    overhead = int(STAGE2_RUNTIME_DEFAULTS.get("request_token_overhead", 64) or 64)
    return max(1, prompt_chars + int(max_tokens) + overhead)


@dataclass(frozen=True)
class RateReservation:
    api_key: str
    request_id: int
    estimated_tokens: int


@dataclass
class _TokenEvent:
    timestamp: float
    request_id: int
    tokens: int


class _KeyState:
    def __init__(self) -> None:
        self.requests: deque[float] = deque()
        self.tokens: deque[_TokenEvent] = deque()

    def cleanup(self, now: float) -> None:
        while self.requests and now - self.requests[0] >= WINDOW_SECONDS:
            self.requests.popleft()
        while self.tokens and now - self.tokens[0].timestamp >= WINDOW_SECONDS:
            self.tokens.popleft()

    def token_load(self) -> int:
        return sum(event.tokens for event in self.tokens)


class SlotRateController:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_keys: tuple[str, ...],
        rpm: int,
        tpm: int,
    ) -> None:
        if not api_keys:
            raise ValueError("api_keys 不能为空。")
        self.provider = provider
        self.model = model
        self.api_keys = tuple(api_keys)
        self.rpm = max(1, int(rpm))
        self.tpm = max(1, int(tpm))
        self.headroom = float(STAGE2_RUNTIME_DEFAULTS.get("sync_headroom", 0.85) or 0.85)
        self.latency_seconds = float(STAGE2_RUNTIME_DEFAULTS.get("request_latency_seconds", 12.0) or 12.0)
        self._rpm_limit = max(1, int(self.rpm * self.headroom))
        self._tpm_limit = max(1, int(self.tpm * self.headroom))
        self._states = {api_key: _KeyState() for api_key in self.api_keys}
        self._lock = Lock()
        self._cursor = 0
        self._request_id = 0

    def effective_worker_limit(self, *, requested_workers: int, estimated_tokens: int) -> int:
        desired = max(1, int(requested_workers))
        safe_tokens = max(1, int(estimated_tokens))
        rpm_based = max(1, math.floor(self._rpm_limit * self.latency_seconds / WINDOW_SECONDS))
        tpm_based = max(1, math.floor(self._tpm_limit * self.latency_seconds / (WINDOW_SECONDS * safe_tokens)))
        capacity = max(1, min(rpm_based, tpm_based) * len(self.api_keys))
        return min(desired, capacity)

    def acquire(self, *, estimated_tokens: int) -> RateReservation:
        safe_tokens = max(1, int(estimated_tokens))
        while True:
            with self._lock:
                now = time.monotonic()
                best_key = ""
                best_score: tuple[float, int, int, int] | None = None
                for index, api_key in enumerate(self.api_keys):
                    state = self._states[api_key]
                    state.cleanup(now)
                    delay = self._next_delay(state, now=now, estimated_tokens=safe_tokens)
                    load_bias = (index - self._cursor) % len(self.api_keys)
                    score = (delay, len(state.requests), state.token_load(), load_bias)
                    if best_score is None or score < best_score:
                        best_key = api_key
                        best_score = score
                assert best_score is not None
                if best_score[0] <= 0:
                    self._request_id += 1
                    request_id = self._request_id
                    state = self._states[best_key]
                    state.requests.append(now)
                    state.tokens.append(_TokenEvent(timestamp=now, request_id=request_id, tokens=safe_tokens))
                    self._cursor = (self.api_keys.index(best_key) + 1) % len(self.api_keys)
                    return RateReservation(api_key=best_key, request_id=request_id, estimated_tokens=safe_tokens)
                sleep_for = best_score[0]
            time.sleep(min(max(sleep_for, 0.01), 1.0))

    def finalize(self, reservation: RateReservation, *, actual_tokens: int | None = None) -> None:
        tokens = max(1, int(actual_tokens or reservation.estimated_tokens))
        with self._lock:
            state = self._states.get(reservation.api_key)
            if state is None:
                return
            for event in state.tokens:
                if event.request_id == reservation.request_id:
                    event.tokens = tokens
                    return

    def _next_delay(self, state: _KeyState, *, now: float, estimated_tokens: int) -> float:
        delays = [0.0]
        if len(state.requests) >= self._rpm_limit:
            delays.append(WINDOW_SECONDS - (now - state.requests[0]))
        total_tokens = state.token_load()
        if total_tokens + estimated_tokens > self._tpm_limit and state.tokens:
            remaining = total_tokens + estimated_tokens
            for event in state.tokens:
                remaining -= event.tokens
                if remaining <= self._tpm_limit:
                    delays.append(WINDOW_SECONDS - (now - event.timestamp))
                    break
        return max(delays)


class RateControllerRegistry:
    def __init__(self) -> None:
        self._controllers: dict[tuple[str, str, tuple[str, ...], int, int], SlotRateController] = {}

    def get(self, payload: dict[str, Any]) -> SlotRateController:
        api_keys = tuple(str(item) for item in payload.get("api_keys") or () if str(item).strip())
        signature = (
            str(payload.get("provider") or ""),
            str(payload.get("model") or ""),
            tuple(api_keys),
            int(payload.get("rpm") or 0),
            int(payload.get("tpm") or 0),
        )
        controller = self._controllers.get(signature)
        if controller is None:
            controller = SlotRateController(
                provider=str(payload["provider"]),
                model=str(payload["model"]),
                api_keys=api_keys,
                rpm=int(payload["rpm"]),
                tpm=int(payload["tpm"]),
            )
            self._controllers[signature] = controller
        return controller
