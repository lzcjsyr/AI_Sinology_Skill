"""检查阶段二外部运行时依赖、Kanripo 数据目录和 API 配置是否就绪。"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

from .api_config import STAGE2_MODELS, merged_env, slot_payload
from .catalog import catalog_root, list_available_scope_dirs, list_available_scope_options
from .session import slot_summaries


def static_checks(kanripo_root: str | Path, *, env_file: str | Path | None = None) -> dict[str, Any]:
    resolved_root = Path(kanripo_root).expanduser().resolve()
    catalog = catalog_root(resolved_root)
    slots = slot_summaries(dotenv_path=env_file or ".env")
    checks = {
        "kanripo_root": str(resolved_root),
        "has_kanripo_root": resolved_root.is_dir(),
        "has_kanripo_catalog": catalog.is_dir(),
        "scope_family_count": len(list_available_scope_options(resolved_root)) if resolved_root.exists() else 0,
        "scope_dir_count": len(list_available_scope_dirs(resolved_root)) if resolved_root.exists() else 0,
        "has_litellm": importlib.util.find_spec("litellm") is not None,
        "slots": {
            payload["slot"]: {
                "provider": payload["provider"],
                "model": payload["model"],
                "base_url": payload["base_url"],
                "api_key_env": payload["api_key_env"],
                "api_keys_env": payload["api_keys_env"],
                "has_api_key": payload["has_api_key"],
                "rpm": payload["rpm"],
                "tpm": payload["tpm"],
            }
            for payload in slots
        },
    }
    checks["ready_for_stage2"] = (
        checks["has_kanripo_root"]
        and checks["has_kanripo_catalog"]
        and checks["has_litellm"]
        and all(slot["has_api_key"] for slot in checks["slots"].values())
    )
    return checks


def api_smoke_test(slot: str, *, env_file: str | Path | None = None) -> dict[str, Any]:
    payload = slot_payload(slot, env_values=merged_env(env_file or ".env"))
    if not payload["api_key"] and not payload["api_keys"]:
        raise SystemExit(
            f"{slot} 缺少 API key，请检查 {payload['api_key_env']} 或 {payload['api_keys_env']}。"
        )

    try:
        from litellm import completion
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"未安装 litellm: {exc}") from exc

    response = completion(
        model=payload["model"],
        messages=[
            {"role": "system", "content": "你是一个严格遵守格式的助手。"},
            {"role": "user", "content": "请只返回一个极短 JSON：{\"ok\":true}"},
        ],
        temperature=0.0,
        custom_llm_provider="openai",
        api_key=payload["api_key"],
        api_base=payload["base_url"],
        timeout=60,
        num_retries=2,
        max_tokens=32,
        response_format={"type": "json_object"},
    )

    if hasattr(response, "model_dump"):
        data = response.model_dump()
    elif hasattr(response, "dict"):
        data = response.dict()
    else:
        data = dict(response)

    return {
        "slot": slot,
        "provider": payload["provider"],
        "model": payload["model"],
        "content": (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""),
        "usage": data.get("usage"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查外部阶段二运行时的前置条件。")
    parser.add_argument("--kanripo-root", help="外部 kanripo_repos 根目录。")
    parser.add_argument("--env-file", help="可选 .env 文件路径。默认读取当前目录下的 .env。")
    parser.add_argument(
        "--api-smoke-test",
        action="store_true",
        help="改为执行指定模型槽位的最小在线连通性测试。",
    )
    parser.add_argument("--slot", choices=sorted(STAGE2_MODELS.keys()), default="llm1", help="smoke test 使用哪个模型槽位。")
    parser.add_argument("--json", action="store_true", help="输出 JSON。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.api_smoke_test:
        result = api_smoke_test(args.slot, env_file=args.env_file)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"slot: {result['slot']}")
            print(f"provider: {result['provider']}")
            print(f"model: {result['model']}")
            print(f"content: {result['content']}")
            print(f"usage: {result['usage']}")
        return 0

    if not args.kanripo_root:
        raise SystemExit("静态检查模式必须提供 --kanripo-root。")

    checks = static_checks(args.kanripo_root, env_file=args.env_file)
    if args.json:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
    else:
        print(f"kanripo 根目录: {checks['kanripo_root']}")
        print(f"kanripo 根目录状态: {'正常' if checks['has_kanripo_root'] else '缺失'}")
        print(f"kanripo catalog: {'正常' if checks['has_kanripo_catalog'] else '缺失'}")
        print(f"scope family 数量: {checks['scope_family_count']}")
        print(f"scope 目录数量: {checks['scope_dir_count']}")
        print(f"litellm: {'正常' if checks['has_litellm'] else '缺失'}")
        for slot, payload in checks["slots"].items():
            print(
                f"{slot}: {payload['provider']} / {payload['model']} / "
                f"{'已配置 key' if payload['has_api_key'] else '缺少 key'}"
            )
        print(f"阶段二可直接运行: {'是' if checks['ready_for_stage2'] else '否'}")
    return 0 if checks["ready_for_stage2"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
