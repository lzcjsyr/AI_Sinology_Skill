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
        self.assertIn("阶段六", interface.get("default_prompt", ""))
        self.assertIn("项目初始化", interface.get("default_prompt", ""))
        self.assertIn("工作区契约", interface.get("default_prompt", ""))

    def test_stage1_docs_capture_journal_clarification_rules(self) -> None:
        skill_text = SKILL_FILE.read_text(encoding="utf-8")
        planning_text = (SKILL_ROOT / "references" / "stage1-planning.md").read_text(encoding="utf-8")
        contract_text = (SKILL_ROOT / "references" / "workspace-contract.md").read_text(encoding="utf-8")

        self.assertIn("如果用户没有说清投稿目标，先追问", skill_text)
        self.assertIn("如果用户给出的目标期刊不在现有 skills 的单刊 reference 内", planning_text)
        self.assertIn("优先请用户提供该刊官网、征稿说明、投稿须知", planning_text)
        self.assertIn("包含完整的目标期刊定位与写作建议", planning_text)
        self.assertIn("经过讨论后确定的研究方向、准备投稿的目标期刊", contract_text)
        self.assertIn("优先要求用户提供期刊网页并据此提炼要求", contract_text)

    def test_stage2_docs_keep_agent_judgment_outside_fetch_scripts(self) -> None:
        skill_text = SKILL_FILE.read_text(encoding="utf-8")
        intake_text = (SKILL_ROOT / "references" / "stage2a-data-intake.md").read_text(encoding="utf-8")
        scholarship_text = (SKILL_ROOT / "references" / "stage2b-scholarship-map.md").read_text(encoding="utf-8")
        handoff_text = (SKILL_ROOT / "references" / "stage3-handoff.md").read_text(encoding="utf-8")

        self.assertIn("阶段二默认拆成 `2A` 与 `2B`", skill_text)
        self.assertIn("阶段二的主流程应由 agent 自主执行", skill_text)
        self.assertIn("`2A` 本身包含学术判断", skill_text)
        self.assertIn("网页搜索/浏览能力补检", skill_text)
        self.assertIn("candidate_papers.md", skill_text)
        self.assertIn("_stage2a/papers/", skill_text)
        self.assertIn("面向阶段三的 handoff", skill_text)
        self.assertIn("“agent 多轮调脚本”", intake_text)
        self.assertIn("`2A` 不是纯抓取环节", intake_text)
        self.assertIn("首轮 `OpenAlex` 后的网页补检", intake_text)
        self.assertIn("candidate_papers.md", intake_text)
        self.assertIn("papers/", intake_text)
        self.assertIn("人工干预点", intake_text)
        self.assertIn("进入 `2B`", intake_text)
        self.assertIn("进入 `2B` 的前提", scholarship_text)
        self.assertIn("candidate_papers.md", scholarship_text)
        self.assertIn("papers/` 目录", scholarship_text)
        self.assertIn("stage3_handoff.target_themes", scholarship_text)
        self.assertIn("优先让 agent 根据当前任务上下文决定检索轮次和 query", scholarship_text)
        self.assertIn("不负责判断是否相关", skill_text)
        self.assertIn("都应由 agent 判断", intake_text)
        self.assertIn("不负责判断相关性", scholarship_text)
        self.assertIn("优先读取 scholarship map 中的 `stage3_handoff.target_themes`", handoff_text)
        self.assertNotIn("stage2_pipeline.py", skill_text)
        self.assertNotIn("stage2_pipeline.py", intake_text)
        self.assertNotIn("stage2_pipeline.py", scholarship_text)


if __name__ == "__main__":
    unittest.main()
