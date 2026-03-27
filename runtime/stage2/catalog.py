"""解析 Kanripo catalog、校验 analysis_targets，并统计目标语料正文规模。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


CATALOG_SECTION_PATTERN = re.compile(r"^\*\s+KR[1-4]\s+(.+)$")
CATALOG_ENTRY_PATTERN = re.compile(r"^\*\*\s+\[\[file:(KR[1-4][a-z])\.txt\]\[([^\]]+)\]\]$")
FAMILY_TARGET_PATTERN = re.compile(r"^KR[1-4][a-z]$")
REPO_TARGET_PATTERN = re.compile(r"^KR[1-4][a-z]\d{4}$")
PAGE_MARKER_PATTERN = re.compile(r"<pb:[^>]+>")


@dataclass(frozen=True)
class ScopeOption:
    code: str
    section: str
    label: str

    @property
    def display_label(self) -> str:
        return f"{self.section} [{self.label}]"


@dataclass(frozen=True)
class TargetIssue:
    token: str
    detail: str


@dataclass(frozen=True)
class ResolvedAnalysisTarget:
    token: str
    level: str
    repo_dirs: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisTargetSelection:
    tokens: tuple[str, ...]
    resolved_targets: tuple[ResolvedAnalysisTarget, ...]
    issues: tuple[TargetIssue, ...]

    @property
    def analysis_targets(self) -> tuple[str, ...]:
        return tuple(item.token for item in self.resolved_targets)

    @property
    def expanded_repo_dirs(self) -> tuple[str, ...]:
        seen: set[str] = set()
        result: list[str] = []
        for item in self.resolved_targets:
            for repo_dir in item.repo_dirs:
                if repo_dir in seen:
                    continue
                seen.add(repo_dir)
                result.append(repo_dir)
        return tuple(result)

    @property
    def is_valid(self) -> bool:
        return bool(self.resolved_targets) and not self.issues


@dataclass(frozen=True)
class TargetCorpusStat:
    token: str
    level: str
    repo_dir_count: int
    text_file_count: int
    text_char_count: int


@dataclass(frozen=True)
class CorpusOverview:
    targets: tuple[TargetCorpusStat, ...]
    repo_dir_count: int
    text_file_count: int
    text_char_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "repo_dir_count": self.repo_dir_count,
            "text_file_count": self.text_file_count,
            "text_char_count": self.text_char_count,
            "targets": [
                {
                    "token": item.token,
                    "level": item.level,
                    "repo_dir_count": item.repo_dir_count,
                    "text_file_count": item.text_file_count,
                    "text_char_count": item.text_char_count,
                }
                for item in self.targets
            ],
        }


def normalize_scope(scope: str) -> str:
    cleaned = scope.strip()
    if cleaned.lower().startswith("kr") and len(cleaned) > 2:
        return f"KR{cleaned[2:].lower()}"
    return cleaned


def split_target_tokens(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    normalized = (
        str(raw_value)
        .replace("，", " ")
        .replace(",", " ")
        .replace("\n", " ")
        .replace("\t", " ")
    )
    seen: set[str] = set()
    result: list[str] = []
    for token in normalized.split():
        item = normalize_scope(token)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def catalog_root(kanripo_root: Path) -> Path:
    return kanripo_root / "KR-Catalog" / "KR"


def list_available_scope_dirs(kanripo_root: Path) -> list[str]:
    if not kanripo_root.exists():
        return []
    return sorted(
        path.name
        for path in kanripo_root.iterdir()
        if path.is_dir()
        and path.name.startswith("KR")
        and not path.name.startswith(".")
        and path.name != "KR-Catalog"
        and REPO_TARGET_PATTERN.match(path.name)
    )


def list_available_scope_options(kanripo_root: Path) -> list[ScopeOption]:
    root = catalog_root(kanripo_root)
    options: list[ScopeOption] = []
    seen: set[str] = set()

    for idx in range(1, 5):
        catalog_file = root / f"KR{idx}.txt"
        if not catalog_file.exists():
            continue
        section_name = ""
        for raw_line in catalog_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            section_match = CATALOG_SECTION_PATTERN.match(line)
            if section_match:
                section_name = section_match.group(1).strip()
                continue
            entry_match = CATALOG_ENTRY_PATTERN.match(line)
            if not entry_match:
                continue
            code = normalize_scope(entry_match.group(1))
            if code in seen:
                continue
            options.append(
                ScopeOption(
                    code=code,
                    section=section_name or f"KR{idx}",
                    label=entry_match.group(2).strip(),
                )
            )
            seen.add(code)

    if options:
        return options

    fallback_families = sorted({repo_dir[:4] for repo_dir in list_available_scope_dirs(kanripo_root)})
    return [
        ScopeOption(code=scope, section="未分类", label=scope)
        for scope in fallback_families
    ]


def _repo_dirs_by_family(kanripo_root: Path) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for repo_dir in list_available_scope_dirs(kanripo_root):
        mapping.setdefault(repo_dir[:4], []).append(repo_dir)
    return mapping


def resolve_analysis_targets(
    kanripo_root: str | Path,
    *,
    tokens: list[str] | tuple[str, ...] | None = None,
    raw_input: str | None = None,
) -> AnalysisTargetSelection:
    root = Path(kanripo_root).expanduser().resolve()
    normalized_tokens = split_target_tokens(raw_input) if raw_input is not None else split_target_tokens(" ".join(tokens or []))
    if not normalized_tokens:
        return AnalysisTargetSelection(tokens=(), resolved_targets=(), issues=())

    family_map = _repo_dirs_by_family(root)
    available_repo_dirs = {repo_dir for repo_dirs in family_map.values() for repo_dir in repo_dirs}
    issues: list[TargetIssue] = []
    resolved_targets: list[ResolvedAnalysisTarget] = []

    for token in normalized_tokens:
        if FAMILY_TARGET_PATTERN.match(token):
            repo_dirs = tuple(family_map.get(token, []))
            if not repo_dirs:
                issues.append(TargetIssue(token=token, detail="该类目不存在，或本地没有对应目录。"))
                continue
            resolved_targets.append(
                ResolvedAnalysisTarget(
                    token=token,
                    level="family",
                    repo_dirs=repo_dirs,
                )
            )
            continue

        if REPO_TARGET_PATTERN.match(token):
            if token not in available_repo_dirs:
                issues.append(TargetIssue(token=token, detail="该目录不存在。"))
                continue
            resolved_targets.append(
                ResolvedAnalysisTarget(
                    token=token,
                    level="repo",
                    repo_dirs=(token,),
                )
            )
            continue

        issues.append(TargetIssue(token=token, detail="格式不合法；仅支持 KR1a 或 KR1a0001。"))

    selected_families = {item.token for item in resolved_targets if item.level == "family"}
    for item in resolved_targets:
        if item.level != "repo":
            continue
        family_token = item.token[:4]
        if family_token in selected_families:
            issues.append(
                TargetIssue(
                    token=item.token,
                    detail=f"范围重复，已经被 {family_token} 覆盖。",
                )
            )

    return AnalysisTargetSelection(
        tokens=tuple(normalized_tokens),
        resolved_targets=tuple(resolved_targets),
        issues=tuple(issues),
    )


def text_files_for_repo_dir(kanripo_root: Path, repo_dir: str) -> list[Path]:
    repo_path = kanripo_root / repo_dir
    if not repo_path.exists():
        return []
    return sorted(
        path
        for path in repo_path.iterdir()
        if path.is_file() and path.suffix == ".txt"
    )


def _count_text_chars_in_file(path: Path) -> int:
    total = 0
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        content = PAGE_MARKER_PATTERN.sub("", stripped).replace("¶", "")
        content = "".join(content.split())
        total += len(content)
    return total


def measure_corpus_overview(
    kanripo_root: str | Path,
    selection: AnalysisTargetSelection,
) -> CorpusOverview:
    root = Path(kanripo_root).expanduser().resolve()
    target_stats: list[TargetCorpusStat] = []
    repo_dir_seen: set[str] = set()
    text_file_count = 0
    text_char_count = 0

    for item in selection.resolved_targets:
        repo_dir_count = len(item.repo_dirs)
        target_file_count = 0
        target_char_count = 0

        for repo_dir in item.repo_dirs:
            files = text_files_for_repo_dir(root, repo_dir)
            target_file_count += len(files)
            for file_path in files:
                file_char_count = _count_text_chars_in_file(file_path)
                target_char_count += file_char_count
                text_char_count += file_char_count
            text_file_count += len(files)
            if repo_dir in repo_dir_seen:
                continue
            repo_dir_seen.add(repo_dir)

        target_stats.append(
            TargetCorpusStat(
                token=item.token,
                level=item.level,
                repo_dir_count=repo_dir_count,
                text_file_count=target_file_count,
                text_char_count=target_char_count,
            )
        )

    return CorpusOverview(
        targets=tuple(target_stats),
        repo_dir_count=len(repo_dir_seen),
        text_file_count=text_file_count,
        text_char_count=text_char_count,
    )
