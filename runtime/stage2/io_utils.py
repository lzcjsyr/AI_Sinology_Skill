"""阶段二运行时的基础文件读写与轻量 YAML 输出。"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


JSONL_RECORDS_KEY = "records"

_SAFE_YAML_SCALAR_PATTERN = re.compile(r"^[\w\u4e00-\u9fff\-./:()%]+$")


def read_json(path: str | Path, *, default: Any = None) -> Any:
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        return default
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def write_json(path: str | Path, payload: Any) -> Path:
    file_path = Path(path).expanduser().resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return file_path


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read stage-2 list artifacts.

    Supports:
    - Pretty-printed ``{\"records\": [ {...}, ... ]}`` (same shape as ``disputes.jsonl``)
    - Legacy JSONL: one compact JSON object per line
    """
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        return []
    text = file_path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        inner = payload.get(JSONL_RECORDS_KEY)
        if isinstance(inner, list):
            return [row for row in inner if isinstance(row, dict)]
        return [payload]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    rows: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> Path:
    """Write list artifacts as indented JSON with a ``records`` wrapper (human-readable, like disputes)."""
    return write_json(path, {JSONL_RECORDS_KEY: rows})


def append_jsonl(path: str | Path, row: dict[str, Any]) -> Path:
    rows = read_jsonl(path)
    rows.append(row)
    return write_jsonl(path, rows)


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if _SAFE_YAML_SCALAR_PATTERN.match(text):
        return text
    return json.dumps(text, ensure_ascii=False)


def _yaml_lines(value: Any, *, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(_yaml_lines(item, indent=indent + 2))
                continue
            text = str(item) if item is not None else ""
            if isinstance(item, str) and "\n" in text:
                lines.append(f"{prefix}{key}: |")
                lines.extend(f"{' ' * (indent + 2)}{chunk}" for chunk in text.splitlines())
                continue
            lines.append(f"{prefix}{key}: {_yaml_scalar(item)}")
        return lines

    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, dict):
                child_lines = _yaml_lines(item, indent=indent + 2)
                if child_lines:
                    first = child_lines[0].lstrip()
                    lines.append(f"{prefix}- {first}")
                    lines.extend(child_lines[1:])
                else:
                    lines.append(f"{prefix}- {{}}")
                continue
            if isinstance(item, list):
                lines.append(f"{prefix}-")
                lines.extend(_yaml_lines(item, indent=indent + 2))
                continue
            text = str(item) if item is not None else ""
            if isinstance(item, str) and "\n" in text:
                lines.append(f"{prefix}- |")
                lines.extend(f"{' ' * (indent + 2)}{chunk}" for chunk in text.splitlines())
                continue
            lines.append(f"{prefix}- {_yaml_scalar(item)}")
        return lines

    return [f"{prefix}{_yaml_scalar(value)}"]


def dump_yaml(payload: Any) -> str:
    return "\n".join(_yaml_lines(payload)) + "\n"


def write_yaml(path: str | Path, payload: Any) -> Path:
    file_path = Path(path).expanduser().resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(dump_yaml(payload), encoding="utf-8")
    return file_path
