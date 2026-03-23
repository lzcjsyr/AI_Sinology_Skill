from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .api_config import STAGE2_MODELS, merged_env, slot_payload
from .catalog import list_available_scope_dirs, list_available_scope_options, normalize_scope


STAGE2_MANIFEST_FILE = "2_stage2_manifest.json"


@dataclass(frozen=True)
class ThemeItem:
    theme: str
    description: str = ""


@dataclass(frozen=True)
class ProposalContext:
    proposal_path: Path
    idea: str
    target_themes: tuple[ThemeItem, ...]


@dataclass(frozen=True)
class ScopeSelection:
    scope_families: tuple[str, ...]
    repo_dirs: tuple[str, ...]
    missing_scope_families: tuple[str, ...]
    missing_repo_dirs: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.missing_scope_families and not self.missing_repo_dirs


def split_csv(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    normalized = str(raw_value).replace("，", ",").replace("\n", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def unique_normalized(items: list[str], *, normalizer=str.strip) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        item = normalizer(raw)
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"').strip("'").strip()


def read_front_matter_lines(proposal_path: str | Path) -> list[str]:
    path = Path(proposal_path).expanduser().resolve()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return []

    front_matter: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return front_matter
        front_matter.append(line.rstrip("\n"))
    return []


def parse_idea_from_proposal(proposal_path: str | Path) -> str:
    for line in read_front_matter_lines(proposal_path):
        stripped = line.strip()
        if stripped.startswith("idea:"):
            return _strip_quotes(stripped.split(":", 1)[1])
    return ""


def parse_target_themes_from_proposal(proposal_path: str | Path) -> list[ThemeItem]:
    front_matter = read_front_matter_lines(proposal_path)
    if not front_matter:
        return []

    themes: list[ThemeItem] = []
    current: dict[str, str] | None = None
    in_target_themes = False
    target_indent = 0

    for line in front_matter:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if stripped.startswith("target_themes:"):
            in_target_themes = True
            target_indent = indent
            continue

        if not in_target_themes:
            continue

        if stripped and indent <= target_indent and not stripped.startswith("-"):
            break

        if not stripped:
            continue

        if stripped.startswith("- "):
            if current and current.get("theme"):
                themes.append(
                    ThemeItem(
                        theme=current["theme"].strip(),
                        description=current.get("description", "").strip(),
                    )
                )

            payload = stripped[2:].strip()
            if payload.startswith("theme:"):
                current = {
                    "theme": _strip_quotes(payload.split(":", 1)[1]),
                    "description": "",
                }
            else:
                current = {
                    "theme": _strip_quotes(payload),
                    "description": "",
                }
            continue

        if stripped.startswith("theme:"):
            if current is None:
                current = {"theme": "", "description": ""}
            current["theme"] = _strip_quotes(stripped.split(":", 1)[1])
            continue

        if stripped.startswith("description:"):
            if current is None:
                current = {"theme": "", "description": ""}
            current["description"] = _strip_quotes(stripped.split(":", 1)[1])

    if current and current.get("theme"):
        themes.append(
            ThemeItem(
                theme=current["theme"].strip(),
                description=current.get("description", "").strip(),
            )
        )

    seen: set[str] = set()
    deduped: list[ThemeItem] = []
    for item in themes:
        if not item.theme or item.theme in seen:
            continue
        seen.add(item.theme)
        deduped.append(item)
    return deduped


def load_proposal_context(project_dir: str | Path) -> ProposalContext | None:
    path = Path(project_dir).expanduser().resolve() / "1_research_proposal.md"
    if not path.exists():
        return None
    return ProposalContext(
        proposal_path=path,
        idea=parse_idea_from_proposal(path),
        target_themes=tuple(parse_target_themes_from_proposal(path)),
    )


def resolve_scope_selection(
    kanripo_root: str | Path,
    *,
    scope_families: list[str] | None = None,
    repo_dirs: list[str] | None = None,
) -> ScopeSelection:
    root = Path(kanripo_root).expanduser().resolve()
    available_scope_families = {option.code for option in list_available_scope_options(root)}
    available_repo_dirs = set(list_available_scope_dirs(root))

    normalized_scope_families = unique_normalized(
        scope_families or [],
        normalizer=normalize_scope,
    )
    normalized_repo_dirs = unique_normalized(
        repo_dirs or [],
        normalizer=normalize_scope,
    )

    missing_scope_families = tuple(
        item for item in normalized_scope_families if item not in available_scope_families
    )
    missing_repo_dirs = tuple(
        item for item in normalized_repo_dirs if item not in available_repo_dirs
    )

    return ScopeSelection(
        scope_families=tuple(
            item for item in normalized_scope_families if item not in missing_scope_families
        ),
        repo_dirs=tuple(item for item in normalized_repo_dirs if item not in missing_repo_dirs),
        missing_scope_families=missing_scope_families,
        missing_repo_dirs=missing_repo_dirs,
    )


def slot_summaries(
    *,
    dotenv_path: str | Path | None = None,
    env_values: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    resolved_env = env_values or merged_env(dotenv_path)
    payloads: list[dict[str, Any]] = []
    for slot in sorted(STAGE2_MODELS.keys()):
        payload = slot_payload(slot, env_values=resolved_env)
        payloads.append(
            {
                "slot": payload["slot"],
                "provider": payload["provider"],
                "model": payload["model"],
                "base_url": payload["base_url"],
                "api_key_env": payload["api_key_env"],
                "api_keys_env": payload["api_keys_env"],
                "has_api_key": bool(payload["api_key"]) or bool(payload["api_keys"]),
                "rpm": payload["rpm"],
                "tpm": payload["tpm"],
            }
        )
    return payloads


def build_stage2_manifest(
    *,
    workspace_root: str | Path,
    outputs_root: str | Path,
    project_name: str,
    kanripo_root: str | Path,
    theme_source: str,
    target_themes: list[ThemeItem],
    scope_selection: ScopeSelection,
    proposal_context: ProposalContext | None = None,
    dotenv_path: str | Path | None = None,
    env_values: dict[str, str] | None = None,
) -> dict[str, Any]:
    workspace = Path(workspace_root).expanduser().resolve()
    outputs = Path(outputs_root).expanduser().resolve()
    project_dir = outputs / project_name
    return {
        "stage2_manifest_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "workspace_root": str(workspace),
        "outputs_root": str(outputs),
        "project_name": project_name,
        "project_dir": str(project_dir),
        "proposal_path": str(proposal_context.proposal_path) if proposal_context else "",
        "idea": proposal_context.idea if proposal_context else "",
        "theme_source": theme_source,
        "target_themes": [
            {
                "theme": item.theme,
                "description": item.description,
            }
            for item in target_themes
        ],
        "kanripo_root": str(Path(kanripo_root).expanduser().resolve()),
        "scope_families": list(scope_selection.scope_families),
        "repo_dirs": list(scope_selection.repo_dirs),
        "analysis_targets": list(scope_selection.scope_families + scope_selection.repo_dirs),
        "model_slots": slot_summaries(dotenv_path=dotenv_path, env_values=env_values),
    }


def manifest_path(project_dir: str | Path) -> Path:
    return Path(project_dir).expanduser().resolve() / STAGE2_MANIFEST_FILE


def write_stage2_manifest(project_dir: str | Path, payload: dict[str, Any]) -> Path:
    path = manifest_path(project_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
