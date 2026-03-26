from __future__ import annotations

# Fetch normalized Stage 2 source data from public scholarly APIs.
# This script is deliberately limited to deterministic work:
# reading env vars, calling OpenAlex,
# normalizing fields, and writing JSON artifacts for later agent review.

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from stage2_common import dump_json, ensure_stage2a_dir, merged_env, now_iso, slugify


OPENALEX_ENDPOINT = "https://api.openalex.org/works"
DEFAULT_TIMEOUT = 30
OpenAlexFetcher = Callable[..., tuple[dict[str, str | int], list[dict[str, Any]]]]


def build_openalex_params(
    *,
    query: str = "",
    per_page: int,
    page: int,
    mailto: str = "",
    api_key: str = "",
    filter_expr: str = "",
    sort: str = "",
) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "per-page": per_page,
        "page": page,
    }
    if query:
        params["search"] = query
    if filter_expr:
        params["filter"] = filter_expr
    if sort:
        params["sort"] = sort
    if mailto:
        params["mailto"] = mailto
    if api_key:
        params["api_key"] = api_key
    return params


def fetch_json(endpoint: str, params: dict[str, str | int]) -> dict[str, Any]:
    query_string = urlencode(params)
    request = Request(
        f"{endpoint}?{query_string}",
        headers={
            "Accept": "application/json",
            "User-Agent": "ai-sinology-stage2/1.0",
        },
    )
    with urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def short_openalex_id(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("https://openalex.org/"):
        return raw.rsplit("/", 1)[-1]
    if "/" in raw and raw.startswith("http"):
        return raw.rstrip("/").rsplit("/", 1)[-1]
    return raw


def openalex_abstract_text(inverted_index: dict[str, list[int]] | None) -> str:
    if not inverted_index:
        return ""
    positions: dict[int, str] = {}
    for token, indexes in inverted_index.items():
        for index in indexes:
            positions[index] = token
    return " ".join(token for _, token in sorted(positions.items()))


def extract_openalex_keywords(work: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("keywords", "topics", "concepts"):
        for item in work.get(field, []) or []:
            if isinstance(item, dict):
                for key in ("display_name", "keyword", "term"):
                    value = str(item.get(key, "")).strip()
                    if value and value not in values:
                        values.append(value)
                        break
    primary_topic = work.get("primary_topic") or {}
    primary_name = str(primary_topic.get("display_name", "")).strip()
    if primary_name and primary_name not in values:
        values.insert(0, primary_name)
    return values[:12]


def normalize_openalex_work(work: dict[str, Any]) -> dict[str, Any]:
    authors = [
        author.get("author", {}).get("display_name", "").strip()
        for author in work.get("authorships", [])
        if author.get("author", {}).get("display_name")
    ]
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    return {
        "source": "openalex",
        "id": work.get("id", ""),
        "openalex_id": short_openalex_id(work.get("id")),
        "doi": (work.get("doi") or "").replace("https://doi.org/", ""),
        "title": work.get("display_name", ""),
        "year": work.get("publication_year"),
        "type": work.get("type", ""),
        "authors": authors,
        "journal": source.get("display_name", ""),
        "abstract": openalex_abstract_text(work.get("abstract_inverted_index")),
        "cited_by_count": work.get("cited_by_count", 0),
        "landing_page_url": primary_location.get("landing_page_url", ""),
        "pdf_url": primary_location.get("pdf_url", ""),
        "keywords": extract_openalex_keywords(work),
        "referenced_works": [short_openalex_id(item) for item in work.get("referenced_works", []) if short_openalex_id(item)],
        "related_works": [short_openalex_id(item) for item in work.get("related_works", []) if short_openalex_id(item)],
        "cited_by_api_url": str(work.get("cited_by_api_url", "")).strip(),
        "openalex_relevance_score": work.get("relevance_score"),
    }


def record_key(record: dict[str, Any]) -> str:
    openalex_id = short_openalex_id(record.get("openalex_id") or record.get("id"))
    if openalex_id:
        return f"openalex:{openalex_id.lower()}"
    doi = str(record.get("doi", "")).strip().lower()
    if doi:
        return f"doi:{doi}"
    title = str(record.get("title", "")).strip().lower()
    year = str(record.get("year", "")).strip()
    if title:
        return f"title:{title}|{year}"
    return ""


def merge_text_list(primary: list[str], secondary: list[str]) -> list[str]:
    values: list[str] = []
    for item in [*primary, *secondary]:
        value = str(item).strip()
        if value and value not in values:
            values.append(value)
    return values


def annotate_records(records: list[dict[str, Any]], *, round_index: int, discovered_via: str, parent_id: str = "") -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for record in records:
        payload = dict(record)
        payload["discovered_round"] = round_index
        payload["discovered_via"] = discovered_via
        if parent_id:
            payload["parent_ids"] = [parent_id]
        annotated.append(payload)
    return annotated


def upsert_records(record_map: dict[str, dict[str, Any]], records: list[dict[str, Any]]) -> int:
    added = 0
    for record in records:
        key = record_key(record)
        if not key:
            continue
        current = record_map.get(key)
        if current is None:
            record_map[key] = dict(record)
            added += 1
            continue
        current["keywords"] = merge_text_list(
            [str(item) for item in current.get("keywords", [])],
            [str(item) for item in record.get("keywords", [])],
        )
        current["parent_ids"] = merge_text_list(
            [str(item) for item in current.get("parent_ids", [])],
            [str(item) for item in record.get("parent_ids", [])],
        )
        current["referenced_works"] = merge_text_list(
            [str(item) for item in current.get("referenced_works", [])],
            [str(item) for item in record.get("referenced_works", [])],
        )
        current["related_works"] = merge_text_list(
            [str(item) for item in current.get("related_works", [])],
            [str(item) for item in record.get("related_works", [])],
        )
        if not current.get("abstract") and record.get("abstract"):
            current["abstract"] = record["abstract"]
        if not current.get("journal") and record.get("journal"):
            current["journal"] = record["journal"]
        if not current.get("landing_page_url") and record.get("landing_page_url"):
            current["landing_page_url"] = record["landing_page_url"]
        if not current.get("pdf_url") and record.get("pdf_url"):
            current["pdf_url"] = record["pdf_url"]
        current["discovered_round"] = min(
            int(current.get("discovered_round") or 0),
            int(record.get("discovered_round") or 0),
        )
    return added


def sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda item: (
            int(item.get("cited_by_count") or 0),
            int(item.get("year") or 0),
            str(item.get("title", "")).lower(),
        ),
        reverse=True,
    )


def fetch_openalex_records(
    *,
    query: str,
    per_page: int,
    page: int,
    filter_expr: str = "",
    mailto: str = "",
    api_key: str = "",
    sort: str = "",
) -> tuple[dict[str, str | int], list[dict[str, Any]]]:
    params = build_openalex_params(
        query=query,
        per_page=per_page,
        page=page,
        filter_expr=filter_expr,
        mailto=mailto,
        api_key=api_key,
        sort=sort,
    )
    raw = fetch_json(OPENALEX_ENDPOINT, params)
    return params, [normalize_openalex_work(item) for item in raw.get("results", [])]


def expand_openalex_citations(
    *,
    query: str,
    seed_ids: list[str],
    per_page: int,
    page: int,
    round_index: int,
    filter_expr: str = "",
    mailto: str = "",
    api_key: str = "",
    fetcher: OpenAlexFetcher = fetch_openalex_records,
) -> dict[str, Any]:
    record_map: dict[str, dict[str, Any]] = {}
    fetches: list[dict[str, Any]] = []
    normalized_seed_ids = [short_openalex_id(seed_id) for seed_id in seed_ids if short_openalex_id(seed_id)]

    for parent_id in normalized_seed_ids:
        current_filter = f"cited_by:{parent_id}"
        if filter_expr:
            current_filter = f"{current_filter},{filter_expr}"
        params, cited_records = fetcher(
            query="",
            per_page=per_page,
            page=page,
            filter_expr=current_filter,
            mailto=mailto,
            api_key=api_key,
            sort="cited_by_count:desc",
        )
        annotated = annotate_records(
            cited_records,
            round_index=round_index,
            discovered_via="cited_by",
            parent_id=parent_id,
        )
        upsert_records(record_map, annotated)
        fetches.append(
            {
                "parent_id": parent_id,
                "params": params,
                "retrieved_count": len(annotated),
            }
        )

    return {
        "provider": "openalex-expand",
        "query": query,
        "retrieved_at": now_iso(),
        "params": {
            "seed_ids": normalized_seed_ids,
            "per_page": per_page,
            "page": page,
            "round_index": round_index,
            "filter": filter_expr,
        },
        "record_count": len(record_map),
        "records": sort_records(list(record_map.values())),
        "fetches": fetches,
    }


def default_output_path(
    *,
    provider: str,
    query: str,
    project: str | None,
    outputs_root: str | Path,
) -> Path:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    name = f"{provider}-{slugify(query)}-{timestamp}.json"
    if project:
        return ensure_stage2a_dir(project, outputs_root) / name
    return Path(name).resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="抓取阶段 2A 开放来源并归一化为本地 JSON。")
    parser.add_argument("--env-file", default=".env", help="环境变量文件，默认读取当前目录 .env。")
    parser.add_argument("--project", help="项目名。提供后默认把结果写入 outputs/<project>/_stage2a/。")
    parser.add_argument("--outputs", default="outputs", help="项目输出目录，默认是 ./outputs。")
    parser.add_argument("--output", help="自定义输出 JSON 路径。")

    subparsers = parser.add_subparsers(dest="provider", required=True)

    openalex = subparsers.add_parser("openalex", help="从 OpenAlex 抓取 works。")
    openalex.add_argument("--query", required=True, help="检索词。")
    openalex.add_argument("--per-page", type=int, default=25, help="每页条数。")
    openalex.add_argument("--page", type=int, default=1, help="页码。")
    openalex.add_argument("--filter", default="", help="OpenAlex filter 表达式。")
    openalex.add_argument("--mailto", default="", help="显式覆盖 polite identification。")
    openalex.add_argument("--api-key", default="", help="显式覆盖 OPENALEX_API_KEY。")

    openalex_expand = subparsers.add_parser("openalex-expand", help="基于 agent 选定的 seed works，抓取这些 works 引用的文献。")
    openalex_expand.add_argument("--query", default="", help="当前检索轴说明，仅用于记录上下文与输出命名。")
    openalex_expand.add_argument("--seed-id", action="append", required=True, help="要展开引用链的 OpenAlex work id，可重复传入。")
    openalex_expand.add_argument("--filter", default="", help="OpenAlex filter 表达式。")
    openalex_expand.add_argument("--per-page", type=int, default=10, help="每个 seed 展开的引用条数。")
    openalex_expand.add_argument("--page", type=int, default=1, help="OpenAlex 引用结果页码。")
    openalex_expand.add_argument("--round-index", type=int, default=1, help="当前是第几轮扩展，由 agent 维护。")
    openalex_expand.add_argument("--mailto", default="", help="显式覆盖 polite identification。")
    openalex_expand.add_argument("--api-key", default="", help="显式覆盖 OPENALEX_API_KEY。")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    env = merged_env(args.env_file)

    if args.provider == "openalex":
        params, records = fetch_openalex_records(
            query=args.query,
            per_page=args.per_page,
            page=args.page,
            filter_expr=args.filter,
            mailto=args.mailto,
            api_key=args.api_key or env.get("OPENALEX_API_KEY", ""),
        )
        payload = {
            "provider": args.provider,
            "query": args.query,
            "retrieved_at": now_iso(),
            "params": params,
            "record_count": len(records),
            "records": records,
        }
    else:
        payload = expand_openalex_citations(
            query=args.query,
            seed_ids=args.seed_id,
            per_page=args.per_page,
            page=args.page,
            round_index=args.round_index,
            filter_expr=args.filter,
            mailto=args.mailto,
            api_key=args.api_key or env.get("OPENALEX_API_KEY", ""),
        )

    output_path = Path(args.output).expanduser().resolve() if args.output else default_output_path(
        provider=args.provider,
        query=args.query,
        project=args.project,
        outputs_root=args.outputs,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(output_path, payload)
    print(f"已写入阶段 2A 来源结果: {output_path}")
    print(f"记录数: {payload.get('record_count', 0)}")
    if args.provider == "openalex-expand":
        print(f"本轮种子: {', '.join(payload.get('params', {}).get('seed_ids', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
