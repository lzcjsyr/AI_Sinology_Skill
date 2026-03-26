from __future__ import annotations

# Build a Stage 2 scholarship-map draft from already fetched source JSON files.
# This script only assembles a stable YAML scaffold and copies structured fields.
# It does not replace the agent's research judgment about debates, positions,
# relevance, or final claim boundaries.

import argparse
from collections import Counter
from pathlib import Path
import re
from typing import Any

from stage2_common import ensure_stage2a_dir, load_json, now_iso, yaml_list, yaml_quote


PLACEHOLDER = "待结合研究问题与目标刊物人工补写"
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "between",
    "through",
    "study",
    "studies",
    "research",
    "ancient",
    "china",
    "chinese",
    "early",
    "late",
    "on",
    "of",
    "in",
    "to",
    "a",
    "an",
}


def read_text(path: str | Path | None) -> str:
    if path is None:
        return ""
    target = Path(path).expanduser()
    if not target.exists():
        return ""
    return target.read_text(encoding="utf-8")


def extract_first_sentence(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("#").strip()
        if not line or line.startswith("---"):
            continue
        return line[:160]
    return ""


def extract_target_journals(text: str) -> list[str]:
    journals: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "《" in line and "》" in line:
            start = line.find("《")
            end = line.find("》", start + 1)
            if start >= 0 and end > start:
                journals.append(line[start + 1 : end].strip())
    deduped: list[str] = []
    for item in journals:
        if item and item not in deduped:
            deduped.append(item)
    return deduped[:5]


def load_records(paths: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        payload = load_json(path)
        current = payload if isinstance(payload, list) else payload.get("records", [])
        if isinstance(current, list):
            for item in current:
                if isinstance(item, dict):
                    records.append(item)
    return records


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for record in records:
        doi = str(record.get("doi", "")).strip().lower()
        title = str(record.get("title", "")).strip().lower()
        year = str(record.get("year", "")).strip()
        key = doi or f"{title}|{year}"
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def top_keywords(records: list[dict[str, Any]], limit: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for record in records:
        title = str(record.get("title", ""))
        for token in re.findall(r"[A-Za-z]{4,}", title.lower()):
            if token in STOPWORDS:
                continue
            counter[token] += 1
    return [token for token, _ in counter.most_common(limit)]


def summarize_claim(record: dict[str, Any]) -> str:
    abstract = str(record.get("abstract", "")).strip()
    if abstract:
        return abstract[:120]
    return PLACEHOLDER


def infer_stage3_themes(*, keywords: list[str], research_question: str) -> list[dict[str, str]]:
    candidates: list[str] = []
    for item in keywords:
        normalized = str(item).strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    if not candidates and research_question.strip():
        candidates.append(research_question.strip()[:24])

    if not candidates:
        candidates.append("待补阶段三检索主题")

    return [
        {
            "theme": item,
            "description": f"围绕“{item}”检索与当前研究问题直接相关的一手材料。",
        }
        for item in candidates[:5]
    ]


def core_work_lines(records: list[dict[str, Any]]) -> list[str]:
    if not records:
        return [
            "  - scholar: \"待补充\"",
            "    work: \"待补充\"",
            "    year: \"\"",
            "    type: \"\"",
            f"    claim: {yaml_quote(PLACEHOLDER)}",
            f"    relevance: {yaml_quote(PLACEHOLDER)}",
        ]

    ranked = sorted(
        records,
        key=lambda item: (int(item.get("cited_by_count") or 0), int(item.get("year") or 0)),
        reverse=True,
    )
    lines: list[str] = []
    for record in ranked[:12]:
        authors = [str(item).strip() for item in record.get("authors", []) if str(item).strip()]
        scholar = "、".join(authors[:3]) if authors else "待补作者"
        lines.extend(
            [
                f"  - scholar: {yaml_quote(scholar)}",
                f"    work: {yaml_quote(str(record.get('title', '')).strip() or '待补题名')}",
                f"    year: {yaml_quote(str(record.get('year', '')).strip())}",
                f"    type: {yaml_quote(str(record.get('type', '')).strip())}",
                f"    claim: {yaml_quote(summarize_claim(record))}",
                f"    relevance: {yaml_quote(PLACEHOLDER)}",
            ]
        )
        journal = str(record.get("journal", "")).strip()
        if journal:
            lines.append(f"    journal: {yaml_quote(journal)}")
        doi = str(record.get("doi", "")).strip()
        if doi:
            lines.append(f"    doi: {yaml_quote(doi)}")
        source = str(record.get("source", "")).strip()
        if source:
            lines.append(f"    source: {yaml_quote(source)}")
    return lines


def render_yaml(
    *,
    research_question: str,
    target_journals: list[str],
    keywords: list[str],
    source_files: list[str],
    records: list[dict[str, Any]],
    period_hint: str,
) -> str:
    stage3_themes = infer_stage3_themes(
        keywords=keywords,
        research_question=research_question,
    )
    lines = [
        f"research_question: {yaml_quote(research_question or PLACEHOLDER)}",
        "target_journals:",
    ]
    lines.extend(yaml_list(target_journals or ["待补目标期刊"], indent=2))
    lines.extend(
        [
            "literature_scope:",
            "  keywords:",
        ]
    )
    lines.extend(yaml_list(keywords or ["待补关键词"], indent=4))
    lines.append(f"  period_hint: {yaml_quote(period_hint)}")
    lines.append("  source_files:")
    lines.extend(yaml_list(source_files or ["待补阶段二来源文件"], indent=4))
    lines.append("core_works:")
    lines.extend(core_work_lines(records))
    lines.extend(
        [
            "major_positions:",
            f"  - label: {yaml_quote('待人工归纳：路径A')}",
            "    claims:",
            f"      - {yaml_quote(PLACEHOLDER)}",
            "    representative_works:",
            f"      - {yaml_quote('从 core_works 中挑选并补写')}",
            "debates:",
            f"  - issue: {yaml_quote('待人工提炼的核心争点')}",
            "    positions:",
            f"      - label: {yaml_quote('观点A')}",
            f"        claim: {yaml_quote(PLACEHOLDER)}",
            f"      - label: {yaml_quote('观点B')}",
            f"        claim: {yaml_quote(PLACEHOLDER)}",
            "gaps_to_address:",
            f"  - {yaml_quote(PLACEHOLDER)}",
            "usable_frames:",
            f"  - {yaml_quote('待从阶段二核心文献中归纳的问题框架或方法')}",
            "claim_boundaries:",
            f"  - {yaml_quote('当前证据暂不支持“首次”“填补空白”“彻底改写通说”等强论断')}",
            "stage3_handoff:",
            "  target_themes:",
        ]
    )
    for item in stage3_themes:
        lines.extend(
            [
                f"    - theme: {yaml_quote(item['theme'])}",
                f"      description: {yaml_quote(item['description'])}",
            ]
        )
    lines.append(f"generated_at: {yaml_quote(now_iso())}")
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将阶段 2A 来源 JSON 汇总为 2B 学术史地图草稿。")
    parser.add_argument("--project", required=True, help="项目名。")
    parser.add_argument("--outputs", default="outputs", help="项目输出目录，默认是 ./outputs。")
    parser.add_argument("--source-json", action="append", default=[], help="阶段 2A 来源 JSON，可重复传入。")
    parser.add_argument("--proposal-file", help="显式指定阶段一 research proposal 文件。")
    parser.add_argument("--journal-file", help="显式指定阶段一 journal targeting 文件。")
    parser.add_argument("--research-question", default="", help="显式覆盖研究问题。")
    parser.add_argument("--target-journal", action="append", default=[], help="显式补充目标期刊，可重复传入。")
    parser.add_argument("--keyword", action="append", default=[], help="显式补充检索关键词，可重复传入。")
    parser.add_argument("--period-hint", default="近十年为主，可回溯经典文献", help="文献时间范围提示。")
    parser.add_argument("--output", help="自定义输出路径，默认写入 outputs/<project>/2b_scholarship_map.yaml。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    outputs_root = Path(args.outputs).expanduser().resolve()
    project_root = outputs_root / args.project
    project_root.mkdir(parents=True, exist_ok=True)
    ensure_stage2a_dir(args.project, outputs_root)

    proposal_file = Path(args.proposal_file).expanduser() if args.proposal_file else project_root / "1_research_proposal.md"
    journal_file = Path(args.journal_file).expanduser() if args.journal_file else project_root / "1_journal_targeting.md"
    proposal_text = read_text(proposal_file)
    journal_text = read_text(journal_file)

    research_question = args.research_question.strip() or extract_first_sentence(proposal_text)
    target_journals = args.target_journal or extract_target_journals(journal_text)
    records = dedupe_records(load_records(args.source_json))
    keywords = args.keyword or top_keywords(records)
    source_files = [Path(path).name for path in args.source_json]

    payload = render_yaml(
        research_question=research_question,
        target_journals=target_journals,
        keywords=keywords,
        source_files=source_files,
        records=records,
        period_hint=args.period_hint,
    )
    output_path = Path(args.output).expanduser().resolve() if args.output else project_root / "2b_scholarship_map.yaml"
    output_path.write_text(payload, encoding="utf-8")
    print(f"已写入阶段 2B 学术史地图草稿: {output_path}")
    print(f"合并来源记录数: {len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
