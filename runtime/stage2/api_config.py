"""阶段二外部运行时的模型槽位、API 环境变量和请求参数组装。"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any


PROVIDER_DEFAULT_BASE_URLS: dict[str, str] = {
    "siliconflow": "https://api.siliconflow.cn/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "volcengine": "https://ark.cn-beijing.volces.com/api/v3",
    "aliyun": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

PROVIDER_API_KEY_ENV_NAMES: dict[str, str] = {
    "siliconflow": "SILICONFLOW_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "volcengine": "VOLCENGINE_API_KEY",
    "aliyun": "ALIYUN_API_KEY",
}

PROVIDER_API_KEYS_ENV_NAMES: dict[str, str] = {
    "siliconflow": "SILICONFLOW_API_KEYS",
    "openrouter": "OPENROUTER_API_KEYS",
    "volcengine": "VOLCENGINE_API_KEYS",
    "aliyun": "ALIYUN_API_KEYS",
}


@dataclass(frozen=True)
class Stage2ModelConfig:
    slot: str
    provider: str
    model: str
    rpm: int
    tpm: int
    max_concurrency: int


STAGE2_MODELS: dict[str, Stage2ModelConfig] = {
    "llm1": Stage2ModelConfig(
        slot="llm1",
        provider="volcengine",
        model="doubao-seed-2-0-lite-260215",
        rpm=30000,
        tpm=5000000,
        max_concurrency=80,
    ),
    "llm2": Stage2ModelConfig(
        slot="llm2",
        provider="volcengine",
        model="doubao-seed-2-0-lite-260215",
        rpm=30000,
        tpm=5000000,
        max_concurrency=80,
    ),
    "llm3": Stage2ModelConfig(
        slot="llm3",
        provider="volcengine",
        model="doubao-seed-2-0-pro-260215",
        rpm=30000,
        tpm=5000000,
        max_concurrency=80,
    ),
}

STAGE2_RUNTIME_DEFAULTS: dict[str, Any] = {
    "screening_batch_max_chars": 500,
    "sync_headroom": 0.85,
    "request_latency_seconds": 12.0,
    "request_token_overhead": 64,
    "request_timeout_seconds": 120.0,
    "network_error_max_retries": 3,
    "stall_heartbeat_seconds": 30.0,
}
STAGE2_FALLBACK_DEFAULTS: dict[str, Any] = {
    "provider": "openrouter",
    "model": "anthropic/claude-sonnet-4.6",
    "max_retries": 3,
}


def screening_batch_char_limit() -> int:
    return max(1, int(STAGE2_RUNTIME_DEFAULTS["screening_batch_max_chars"]))


def slot_worker_limit(slot: str) -> int:
    config = STAGE2_MODELS[slot]
    return max(1, int(config.max_concurrency))


def scaled_slot_worker_limit(
    slot: str,
    *,
    dotenv_path: str | Path | None = None,
    env_values: dict[str, str] | None = None,
) -> int:
    """在 STAGE2_MODELS 的每槽位基准并发上乘以已解析的 API key 个数（至少为 1）。"""
    base = slot_worker_limit(slot)
    provider = STAGE2_MODELS[slot].provider
    _, api_keys = resolve_provider_keys(provider, dotenv_path=dotenv_path, env_values=env_values)
    return base * max(1, len(api_keys))


def _parse_key_pool(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    seen: set[str] = set()
    keys: list[str] = []
    for raw in str(value).replace("\n", ",").split(","):
        key = raw.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return tuple(keys)


def parse_dotenv(dotenv_path: str | Path | None) -> dict[str, str]:
    if dotenv_path is None:
        return {}
    path = Path(dotenv_path).expanduser()
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def merged_env(dotenv_path: str | Path | None = None) -> dict[str, str]:
    values = parse_dotenv(dotenv_path)
    values.update(os.environ)
    return values


def resolve_provider_keys(
    provider: str,
    *,
    dotenv_path: str | Path | None = None,
    env_values: dict[str, str] | None = None,
) -> tuple[str, tuple[str, ...]]:
    env = env_values if env_values is not None else merged_env(dotenv_path)
    env_name = PROVIDER_API_KEY_ENV_NAMES.get(provider, "")
    pool_env_name = PROVIDER_API_KEYS_ENV_NAMES.get(provider, "")
    single = env.get(env_name, "").strip()
    pool = list(_parse_key_pool(env.get(pool_env_name, "")))
    if single and single not in pool:
        pool.append(single)
    primary = pool[0] if pool else ""
    return primary, tuple(pool)


def slot_payload(
    slot: str,
    *,
    dotenv_path: str | Path | None = None,
    env_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    config = STAGE2_MODELS[slot]
    api_key, api_keys = resolve_provider_keys(
        config.provider,
        dotenv_path=dotenv_path,
        env_values=env_values,
    )
    return {
        "slot": config.slot,
        "provider": config.provider,
        "model": config.model,
        "base_url": PROVIDER_DEFAULT_BASE_URLS[config.provider],
        "api_key_env": PROVIDER_API_KEY_ENV_NAMES[config.provider],
        "api_keys_env": PROVIDER_API_KEYS_ENV_NAMES[config.provider],
        "api_key": api_key,
        "api_keys": api_keys,
        "rpm": config.rpm,
        "tpm": config.tpm,
        "max_concurrency": scaled_slot_worker_limit(slot, dotenv_path=dotenv_path, env_values=env_values),
    }


def fallback_payload(
    *,
    dotenv_path: str | Path | None = None,
    env_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env_values if env_values is not None else merged_env(dotenv_path)
    provider = str(env.get("STAGE2_FALLBACK_PROVIDER") or STAGE2_FALLBACK_DEFAULTS["provider"]).strip().lower()
    model = str(env.get("STAGE2_FALLBACK_MODEL") or STAGE2_FALLBACK_DEFAULTS["model"]).strip()
    base_url = str(env.get("STAGE2_FALLBACK_BASE_URL") or PROVIDER_DEFAULT_BASE_URLS.get(provider, "")).strip()
    max_retries = max(
        0,
        int(env.get("STAGE2_FALLBACK_MAX_RETRIES") or STAGE2_FALLBACK_DEFAULTS["max_retries"]),
    )

    dedicated_keys = list(_parse_key_pool(env.get("STAGE2_FALLBACK_API_KEYS", "")))
    dedicated_primary = str(env.get("STAGE2_FALLBACK_API_KEY") or "").strip()
    if dedicated_primary and dedicated_primary not in dedicated_keys:
        dedicated_keys.insert(0, dedicated_primary)

    provider_primary = ""
    provider_pool: tuple[str, ...] = ()
    if provider:
        provider_primary, provider_pool = resolve_provider_keys(provider, env_values=env)

    api_keys = tuple(dedicated_keys) or provider_pool
    api_key = api_keys[0] if api_keys else provider_primary
    return {
        "slot": "fallback",
        "provider": provider,
        "model": model,
        "base_url": base_url,
        "api_key": api_key,
        "api_keys": api_keys,
        "max_retries": max_retries,
        "enabled": bool(provider and model and base_url and api_keys and max_retries > 0),
    }
