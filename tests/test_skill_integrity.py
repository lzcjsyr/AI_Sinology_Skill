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
        self.assertFalse((SKILL_ROOT / "scripts" / "stage3c_scholarship_map.py").exists())

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
        stage2_text = (SKILL_ROOT / "references" / "stage2-primary-corpus.md").read_text(encoding="utf-8")

        self.assertIn("如果用户没有说清投稿目标，先追问", skill_text)
        self.assertIn("stage2_retrieval_themes", skill_text)
        self.assertIn("史料目录建议", skill_text)
        self.assertIn("四库全书目录", skill_text)
        self.assertIn("Kanripo 文件夹名称", skill_text)
        self.assertIn("如果用户给出的目标期刊不在现有 skills 的内置期刊介绍内", planning_text)
        self.assertIn("优先请用户提供该刊官网、征稿说明、投稿须知", planning_text)
        self.assertIn("包含完整的目标期刊定位与写作建议", planning_text)
        self.assertIn("stage2_retrieval_themes", planning_text)
        self.assertIn("仍应保持纯主题文本", planning_text)
        self.assertIn('{"1":"T","2":"F"}', planning_text)
        self.assertIn("四部丛刊目录", planning_text)
        self.assertIn("KR1*", planning_text)
        self.assertIn("KR2k", planning_text)
        self.assertIn("经过讨论后确定的研究方向、准备投稿的目标期刊", contract_text)
        self.assertIn("优先要求用户提供期刊网页并据此提炼要求", contract_text)
        self.assertIn("stage2_retrieval_themes", contract_text)
        self.assertIn('{"1":"T","2":"F"}', contract_text)
        self.assertIn("史料目录建议", contract_text)
        self.assertIn("优先读取 `stage2_retrieval_themes`", stage2_text)
        self.assertIn('{"1":"T","2":"F"}', stage2_text)
        self.assertIn("两个正式阶段一文件都已存在", stage2_text)
        self.assertIn("两个阶段一正式文件都已生成", contract_text)

    def test_stage3_docs_keep_agent_judgment_outside_fetch_scripts(self) -> None:
        skill_text = SKILL_FILE.read_text(encoding="utf-8")
        intake_text = (SKILL_ROOT / "references" / "stage3b-data-intake.md").read_text(encoding="utf-8")
        scholarship_text = (SKILL_ROOT / "references" / "stage3c-scholarship-map.md").read_text(encoding="utf-8")

        self.assertIn("阶段三分成 `3A`、`3B`、`3C` 三段", skill_text)
        self.assertIn("主流程由 agent 自主执行", skill_text)
        self.assertIn("更倚重 `baidu-scholar` 做首轮发现与补漏", skill_text)
        self.assertIn("读取 `referenced_works`", skill_text)
        self.assertIn("`3B` 本身包含学术判断", skill_text)
        self.assertIn("`3C` 必须读取 `1_journal_targeting.md`", skill_text)
        self.assertIn("`outputs/<project>/_stage3b/papers/` 中至少已有 1 份人工导入论文", skill_text)
        self.assertIn("references/stage3b-data-intake.md", skill_text)
        self.assertIn("references/stage3c-scholarship-map.md", skill_text)
        self.assertIn("再直接写出 `3c_scholarship_map.yaml`", skill_text)
        self.assertIn("`3B` 不是纯抓取环节", intake_text)
        self.assertIn("候选论文清单", intake_text)
        self.assertIn("优先调用 `stage3b_sources.py baidu-scholar`", intake_text)
        self.assertIn("`stage3b_sources.py openalex-expand --expand-mode references`", intake_text)
        self.assertIn("candidate_papers.md", intake_text)
        self.assertIn("papers/", intake_text)
        self.assertIn("人工干预点", intake_text)
        self.assertIn("进入 `3C`", intake_text)
        self.assertIn("只有 `papers/` 中已经有人工补入材料后，才进入 `3C`", intake_text)
        self.assertIn("进入 `3C` 的前提", scholarship_text)
        self.assertIn("`outputs/<project>/_stage3b/candidate_papers.md` 已经整理完成", scholarship_text)
        self.assertIn("`outputs/<project>/_stage3b/papers/` 中至少已有 1 份人工导入的论文", scholarship_text)
        self.assertIn("默认应先让 `百度学术` 承担中文发现与摘要补强", scholarship_text)
        self.assertIn("openalex-expand --expand-mode references", scholarship_text)
        self.assertIn("candidate_papers.md", scholarship_text)
        self.assertIn("`outputs/<project>/_stage3b/papers/`", scholarship_text)
        self.assertIn("`3C` 默认由 agent 直接完成，不再依赖单独的写作脚本。", scholarship_text)
        self.assertIn("如果 `3a_deepened_thinking.md`、`candidate_papers.md` 或 `papers/` 中的人工补料缺失，就不能进入 `3C`。", scholarship_text)
        self.assertIn("固定 YAML 结构", scholarship_text)
        self.assertIn("不把学术判断硬塞进抓取脚本", skill_text)
        self.assertIn("agent 不负责代替用户下载全文", intake_text)
        self.assertNotIn("2A", skill_text)
        self.assertNotIn("2B", skill_text)
        self.assertNotIn("stage2a_sources.py", skill_text)
        self.assertNotIn("stage2b_scholarship_map.py", skill_text)
        self.assertNotIn("stage3c_scholarship_map.py", skill_text)
        self.assertNotIn("stage3c_scholarship_map.py", scholarship_text)


if __name__ == "__main__":
    unittest.main()
