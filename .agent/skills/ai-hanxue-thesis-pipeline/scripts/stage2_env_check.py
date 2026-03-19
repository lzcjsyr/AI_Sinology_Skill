#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from stage2_api_config import STAGE2_MODELS, merged_env, slot_payload
from standalone_kanripo import list_available_scope_dirs, list_available_scope_options


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查混合独立模式下阶段二的运行前置条件。")
    parser.add_argument("--kanripo-root", required=True, help="外部 kanripo_repos 根目录。")
    parser.add_argument("--env-file", help="可选 .env 文件路径。默认尝试当前目录下的 .env。")
    parser.add_argument("--json", action="store_true", help="输出 JSON。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    kanripo_root = Path(args.kanripo_root).expanduser().resolve()
    catalog_root = kanripo_root / "KR-Catalog" / "KR"
    env_file = args.env_file or ".env"
    env_values = merged_env(env_file)

    providers = {
        slot: slot_payload(slot, env_values=env_values)
        for slot in sorted(STAGE2_MODELS.keys())
    }
    checks = {
        "kanripo_root": str(kanripo_root),
        "has_kanripo_root": kanripo_root.is_dir(),
        "has_kanripo_catalog": catalog_root.is_dir(),
        "scope_family_count": len(list_available_scope_options(kanripo_root)) if kanripo_root.exists() else 0,
        "scope_dir_count": len(list_available_scope_dirs(kanripo_root)) if kanripo_root.exists() else 0,
        "has_litellm": module_available("litellm"),
        "slots": {
            slot: {
                "provider": payload["provider"],
                "model": payload["model"],
                "base_url": payload["base_url"],
                "api_key_env": payload["api_key_env"],
                "api_keys_env": payload["api_keys_env"],
                "has_api_key": bool(payload["api_key"]) or bool(payload["api_keys"]),
                "rpm": payload["rpm"],
                "tpm": payload["tpm"],
            }
            for slot, payload in providers.items()
        },
    }
    ready = (
        checks["has_kanripo_root"]
        and checks["has_kanripo_catalog"]
        and checks["has_litellm"]
        and all(slot["has_api_key"] for slot in checks["slots"].values())
    )
    checks["ready_for_stage2"] = ready

    if args.json:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
    else:
        print(f"kanripo 根目录: {checks['kanripo_root']}")
        print(f"env 文件: {Path(env_file).expanduser().resolve() if env_file else '未指定'}")
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
        print(f"阶段二可直接运行: {'是' if ready else '否'}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
