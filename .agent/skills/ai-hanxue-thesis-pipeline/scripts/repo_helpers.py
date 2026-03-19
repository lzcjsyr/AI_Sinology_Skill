#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def find_workspace_root(start: str | Path | None = None) -> Path:
    current = Path(start or __file__).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (
            (candidate / "main.py").exists()
            and (candidate / "core").is_dir()
            and (candidate / "workflow").is_dir()
            and (candidate / "prompts").is_dir()
        ):
            return candidate
    raise RuntimeError("Unable to locate the repository root from the provided path.")


def ensure_workspace_on_syspath(workspace_root: Path) -> None:
    root = str(workspace_root)
    if root not in sys.path:
        sys.path.insert(0, root)


def parse_dotenv(dotenv_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not dotenv_path.exists():
        return values
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def merged_env(workspace_root: Path) -> dict[str, str]:
    merged = parse_dotenv(workspace_root / ".env")
    for key, value in os.environ.items():
        merged[key] = value
    return merged


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def normalize_scope_token(raw_value: str) -> str:
    token = raw_value.strip().replace("，", ",")
    if token.lower().startswith("kr") and len(token) > 2:
        return f"KR{token[2:].lower()}"
    return token
