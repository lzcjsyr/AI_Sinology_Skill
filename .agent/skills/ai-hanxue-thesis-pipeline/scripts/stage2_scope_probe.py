#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from standalone_kanripo import list_available_scope_dirs, list_available_scope_options, normalize_scope


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="在不依赖当前仓库代码的情况下，列出或校验 Kanripo scope。")
    parser.add_argument("--kanripo-root", required=True, help="外部 kanripo_repos 根目录。")
    parser.add_argument("--limit", type=int, default=0, help="限制输出条目数。")
    parser.add_argument("--filter", help="按 code、section 或 label 过滤。")
    parser.add_argument("--dirs", action="store_true", help="显示精确目录，而不是 scope family。")
    parser.add_argument("--validate", help="校验逗号分隔的 scope token。")
    parser.add_argument("--json", action="store_true", help="输出 JSON。")
    return parser


def split_tokens(raw_value: str) -> list[str]:
    normalized = raw_value.replace("，", ",")
    return [normalize_scope(token) for token in normalized.split(",") if token.strip()]


def status_label(status: str) -> str:
    mapping = {
        "scope_family": "scope 类目",
        "scope_dir": "精确目录",
        "missing_exact_dir_family_exists": "目录缺失但上层 family 存在",
        "missing": "不存在",
    }
    return mapping.get(status, status)


def main() -> int:
    args = build_parser().parse_args()
    kanripo_root = Path(args.kanripo_root).expanduser().resolve()
    if not kanripo_root.exists():
        raise SystemExit(f"Kanripo 根目录不存在: {kanripo_root}")

    scope_options = list_available_scope_options(kanripo_root)
    scope_dirs = list_available_scope_dirs(kanripo_root)
    available_scope_codes = {option.code for option in scope_options}
    available_scope_dirs = set(scope_dirs)

    if args.validate:
        results = []
        for token in split_tokens(args.validate):
            family_match = re.match(r"^(KR[1-4][a-z])", token, re.IGNORECASE)
            family = normalize_scope(family_match.group(1)) if family_match else None
            if token in available_scope_codes:
                status = "scope_family"
            elif token in available_scope_dirs:
                status = "scope_dir"
            elif family and family in available_scope_codes:
                status = "missing_exact_dir_family_exists"
            else:
                status = "missing"
            results.append({"token": token, "status": status, "family": family})
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            for item in results:
                print(
                    f"{item['token']}: {status_label(item['status'])}"
                    + (f" (family={item['family']})" if item["family"] else "")
                )
        return 0

    if args.dirs:
        items = scope_dirs
        if args.filter:
            needle = args.filter.lower()
            items = [item for item in items if needle in item.lower()]
        if args.limit > 0:
            items = items[: args.limit]
        if args.json:
            print(json.dumps(items, ensure_ascii=False, indent=2))
        else:
            for item in items:
                print(item)
        return 0

    items = [
        {
            "code": option.code,
            "section": option.section,
            "label": option.label,
            "display_label": option.display_label,
        }
        for option in scope_options
    ]
    if args.filter:
        needle = args.filter.lower()
        items = [
            item
            for item in items
            if needle in item["code"].lower()
            or needle in item["section"].lower()
            or needle in item["label"].lower()
            or needle in item["display_label"].lower()
        ]
    if args.limit > 0:
        items = items[: args.limit]

    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        for item in items:
            print(f"{item['code']}: {item['display_label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
