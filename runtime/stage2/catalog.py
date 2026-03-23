from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


CATALOG_SECTION_PATTERN = re.compile(r"^\*\s+KR[1-4]\s+(.+)$")
CATALOG_ENTRY_PATTERN = re.compile(r"^\*\*\s+\[\[file:(KR[1-4][a-z])\.txt\]\[([^\]]+)\]\]$")


@dataclass(frozen=True)
class ScopeOption:
    code: str
    section: str
    label: str

    @property
    def display_label(self) -> str:
        return f"{self.section} [{self.label}]"


def normalize_scope(scope: str) -> str:
    cleaned = scope.strip()
    if cleaned.lower().startswith("kr") and len(cleaned) > 2:
        return f"KR{cleaned[2:].lower()}"
    return cleaned


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

    return [
        ScopeOption(code=scope, section="未分类", label=scope)
        for scope in list_available_scope_dirs(kanripo_root)
    ]
