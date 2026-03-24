from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = REPO_ROOT / ".agent" / "skills" / "ai-sinology"
SKILL_FILE = SKILL_ROOT / "SKILL.md"
OPENAI_YAML = SKILL_ROOT / "agents" / "openai.yaml"


def _frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    payload: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        payload[key.strip()] = value.strip().strip('"').strip("'")
    return payload


def _openai_interface(path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s{2}([a-z_]+):\s+\"(.*)\"$", raw_line)
        if match:
            payload[match.group(1)] = match.group(2)
    return payload


def _skill_references(path: Path) -> set[str]:
    content = path.read_text(encoding="utf-8")
    references = set()
    for match in re.findall(r"`([^`]+)`", content):
        if match.startswith(("references/", "scripts/", "assets/", "agents/")):
            references.add(match)
    return references


class SkillIntegrityTests(unittest.TestCase):
    def test_skill_references_exist(self) -> None:
        missing = sorted(str(SKILL_ROOT / ref) for ref in _skill_references(SKILL_FILE) if not (SKILL_ROOT / ref).exists())
        self.assertEqual(missing, [])

    def test_openai_yaml_tracks_skill_name_and_prompt(self) -> None:
        frontmatter = _frontmatter(SKILL_FILE)
        interface = _openai_interface(OPENAI_YAML)

        self.assertEqual(interface.get("display_name"), frontmatter.get("name"))
        self.assertTrue(interface.get("short_description"))
        self.assertIn(f"${frontmatter.get('name')}", interface.get("default_prompt", ""))


if __name__ == "__main__":
    unittest.main()
