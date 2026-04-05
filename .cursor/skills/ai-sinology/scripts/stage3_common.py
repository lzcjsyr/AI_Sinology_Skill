from __future__ import annotations

# Shared helpers for the Stage 3 secondary-literature scripts.

from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any

# 本文件位于 ai-sinology/scripts/，故上级目录即为技能根（`.cursor/skills/ai-sinology/`）。
SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKILL_DOTENV = SKILL_ROOT / ".env"


def parse_dotenv(dotenv_path: str | Path | None) -> dict[str, str]:
    if dotenv_path is None:
        return {}
    path = Path(dotenv_path).expanduser()
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def merged_env(dotenv_path: str | Path | None = None, env_values: dict[str, str] | None = None) -> dict[str, str]:
    values = parse_dotenv(dotenv_path)
    values.update(os.environ)
    if env_values:
        values.update(env_values)
    return values


def merged_env_skill_layered(
    *,
    workspace_dotenv: Path | None = None,
    skill_dotenv: Path | None = None,
) -> dict[str, str]:
    """先读仓库根目录 `.env`，再读技能目录 `.env`（同名键以后者为准），最后 `os.environ` 覆盖。"""
    workspace_dotenv = workspace_dotenv or (Path.cwd() / ".env")
    skill_dotenv = skill_dotenv or DEFAULT_SKILL_DOTENV
    values = parse_dotenv(workspace_dotenv)
    values.update(parse_dotenv(skill_dotenv))
    values.update(os.environ)
    return values


def resolve_stage3_env(explicit_env_file: str | Path | None) -> dict[str, str]:
    """若指定 `--env-file`：仅加载该文件 + `os.environ`；若省略：根目录与技能目录分层合并。"""
    if explicit_env_file is not None:
        return merged_env(Path(explicit_env_file).expanduser())
    return merged_env_skill_layered()


def ensure_stage3b_dir(project: str, outputs_root: str | Path) -> Path:
    root = Path(outputs_root).expanduser().resolve()
    target = root / project / "_stage3b"
    target.mkdir(parents=True, exist_ok=True)
    return target


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def dump_json(path: str | Path, payload: Any) -> None:
    Path(path).expanduser().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(value: str, limit: int = 48) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", value.strip()).strip("-").lower()
    if not cleaned:
        return "query"
    return cleaned[:limit].rstrip("-") or "query"


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def yaml_list(items: list[str], indent: int = 0) -> list[str]:
    prefix = " " * indent
    if not items:
        return [f"{prefix}[]"]
    return [f"{prefix}- {yaml_quote(item)}" for item in items]
