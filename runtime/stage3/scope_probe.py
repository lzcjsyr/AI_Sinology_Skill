"""列出、校验并统计 Stage3 可用的 Kanripo analysis_targets。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .catalog import (
    list_available_scope_dirs,
    list_available_scope_options,
    measure_corpus_overview,
    resolve_analysis_targets,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="列出或校验外部 Kanripo analysis_targets。")
    parser.add_argument("--kanripo-root", required=True, help="外部 kanripo_repos 根目录。")
    parser.add_argument("--limit", type=int, default=0, help="限制输出条目数。")
    parser.add_argument("--filter", help="按 code、section 或 label 过滤。")
    parser.add_argument("--dirs", action="store_true", help="显示精确目录，而不是 family 类目。")
    parser.add_argument(
        "--validate",
        help="校验调研范围字符串，支持 KR1a / KR1a0001，逗号或空格分隔。",
    )
    parser.add_argument("--stats", action="store_true", help="配合 --validate 输出正文规模统计。")
    parser.add_argument("--json", action="store_true", help="输出 JSON。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    kanripo_root = Path(args.kanripo_root).expanduser().resolve()
    if not kanripo_root.exists():
        raise SystemExit(f"Kanripo 根目录不存在: {kanripo_root}")

    if args.validate:
        selection = resolve_analysis_targets(kanripo_root, raw_input=args.validate)
        payload: dict[str, object] = {
            "analysis_targets": list(selection.analysis_targets),
            "issues": [{"token": item.token, "detail": item.detail} for item in selection.issues],
        }
        if args.stats and selection.is_valid:
            payload["corpus_overview"] = measure_corpus_overview(kanripo_root, selection).as_dict()

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0 if selection.is_valid else 1

        if selection.issues:
            print("输入有误:")
            for issue in selection.issues:
                print(f"  - {issue.token}: {issue.detail}")
            return 1

        print(f"analysis_targets: {', '.join(selection.analysis_targets)}")
        if args.stats:
            overview = measure_corpus_overview(kanripo_root, selection)
            print(
                f"合计 | 目录 {overview.repo_dir_count}"
                f" | 文本 {overview.text_file_count}"
                f" | 正文约 {overview.text_char_count} 字"
            )
        return 0

    if args.dirs:
        items = list_available_scope_dirs(kanripo_root)
    else:
        options = list_available_scope_options(kanripo_root)
        if args.filter:
            matcher = re.compile(re.escape(args.filter), re.IGNORECASE)
            options = [
                item
                for item in options
                if matcher.search(item.code) or matcher.search(item.section) or matcher.search(item.label)
            ]
        items = [f"{item.code}\t{item.section}\t{item.label}" for item in options]

    if args.limit > 0:
        items = items[: args.limit]

    if args.json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    for item in items:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
