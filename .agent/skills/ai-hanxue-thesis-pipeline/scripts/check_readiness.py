#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repo_helpers import ensure_workspace_on_syspath, find_workspace_root, merged_env, module_available


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查当前仓库是否满足真实流水线运行的前置条件。")
    parser.add_argument("--workspace", help="仓库根目录，默认自动探测。")
    parser.add_argument("--json", action="store_true", help="输出 JSON，而不是纯文本。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workspace_root = find_workspace_root(args.workspace)
    ensure_workspace_on_syspath(workspace_root)

    from core.config import (
        PIPELINE_LLM_CONFIG,
        PROVIDER_API_KEYS_ENV_NAMES,
        PROVIDER_API_KEY_ENV_NAMES,
    )
    from workflow.stage2_data_collection.data_ingestion.parse_kanripo import (
        list_available_scope_dirs,
        list_available_scope_options,
    )

    env_values = merged_env(workspace_root)
    kanripo_root = workspace_root / "data" / "kanripo_repos"
    catalog_root = kanripo_root / "KR-Catalog" / "KR"

    providers = sorted(
        {
            str(config.get("provider") or "").strip()
            for config in PIPELINE_LLM_CONFIG.values()
            if str(config.get("provider") or "").strip()
        }
    )
    provider_status = {}
    for provider in providers:
        direct_key_name = PROVIDER_API_KEY_ENV_NAMES.get(provider, "")
        pool_key_name = PROVIDER_API_KEYS_ENV_NAMES.get(provider, "")
        direct_key = env_values.get(direct_key_name, "").strip()
        pool_key = env_values.get(pool_key_name, "").strip()
        provider_status[provider] = {
            "direct_key_env": direct_key_name,
            "pool_key_env": pool_key_name,
            "has_direct_key": bool(direct_key),
            "has_key_pool": bool(pool_key),
        }

    scope_options = list_available_scope_options(kanripo_root) if kanripo_root.exists() else []
    scope_dirs = list_available_scope_dirs(kanripo_root) if kanripo_root.exists() else []

    checks = {
        "workspace_root": str(workspace_root),
        "has_main_py": (workspace_root / "main.py").exists(),
        "has_core_dir": (workspace_root / "core").is_dir(),
        "has_workflow_dir": (workspace_root / "workflow").is_dir(),
        "has_prompts_dir": (workspace_root / "prompts").is_dir(),
        "has_dotenv_file": (workspace_root / ".env").exists(),
        "has_kanripo_root": kanripo_root.is_dir(),
        "has_kanripo_catalog": catalog_root.is_dir(),
        "scope_family_count": len(scope_options),
        "scope_dir_count": len(scope_dirs),
        "has_litellm": module_available("litellm"),
        "has_prompt_toolkit": module_available("prompt_toolkit"),
        "providers": provider_status,
    }

    ready = (
        checks["has_main_py"]
        and checks["has_core_dir"]
        and checks["has_workflow_dir"]
        and checks["has_prompts_dir"]
        and checks["has_kanripo_root"]
        and checks["has_kanripo_catalog"]
        and checks["has_litellm"]
        and checks["has_prompt_toolkit"]
        and all(
            status["has_direct_key"] or status["has_key_pool"]
            for status in provider_status.values()
        )
    )
    checks["ready_for_live_run"] = ready

    if args.json:
        print(json.dumps(checks, ensure_ascii=False, indent=2))
    else:
        print(f"仓库根目录: {checks['workspace_root']}")
        print(f"main.py: {'正常' if checks['has_main_py'] else '缺失'}")
        print(f"core/: {'正常' if checks['has_core_dir'] else '缺失'}")
        print(f"workflow/: {'正常' if checks['has_workflow_dir'] else '缺失'}")
        print(f"prompts/: {'正常' if checks['has_prompts_dir'] else '缺失'}")
        print(f".env: {'存在' if checks['has_dotenv_file'] else '缺失'}")
        print(f"kanripo 根目录: {'正常' if checks['has_kanripo_root'] else '缺失'}")
        print(f"kanripo catalog: {'正常' if checks['has_kanripo_catalog'] else '缺失'}")
        print(f"scope family 数量: {checks['scope_family_count']}")
        print(f"scope 目录数量: {checks['scope_dir_count']}")
        print(f"litellm: {'正常' if checks['has_litellm'] else '缺失'}")
        print(f"prompt_toolkit: {'正常' if checks['has_prompt_toolkit'] else '缺失'}")
        for provider, status in provider_status.items():
            has_keys = status["has_direct_key"] or status["has_key_pool"]
            print(
                f"provider:{provider}: {'正常' if has_keys else '缺失'} "
                f"(direct={status['direct_key_env']} pool={status['pool_key_env']})"
            )
        print(f"可直接真实运行: {'是' if ready else '否'}")

    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
