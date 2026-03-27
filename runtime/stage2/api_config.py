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


STAGE2_MODELS: dict[str, Stage2ModelConfig] = {
    "llm1": Stage2ModelConfig(
        slot="llm1",
        provider="volcengine",
        model="deepseek-v3-2-251201",
        rpm=15000,
        tpm=1500000,
    ),
    "llm2": Stage2ModelConfig(
        slot="llm2",
        provider="volcengine",
        model="deepseek-v3-2-251201",
        rpm=15000,
        tpm=1500000,
    ),
    "llm3": Stage2ModelConfig(
        slot="llm3",
        provider="volcengine",
        model="doubao-seed-2-0-pro-260215",
        rpm=30000,
        tpm=5000000,
    ),
}

STAGE2_RUNTIME_DEFAULTS: dict[str, Any] = {
    "screening_batch_max_chars": 300,
    "fragment_max_attempts": 3,
    "max_empty_retries": 2,
    "sync_headroom": 0.85,
    "sync_max_ahead": 128,
    "sync_mode": "lowest_shared",
}


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
    }
