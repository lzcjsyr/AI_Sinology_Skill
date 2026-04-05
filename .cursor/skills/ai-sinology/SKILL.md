---
name: ai-sinology
description: 用于撰写和推进中国古代文学、古典文献、古代文论、文学批评史与相关文献学方向的论文项目。适用于选题、选刊、研究计划、阶段二原始文献勘查、阶段三的深化思考与学术史梳理、论纲设计、初稿写作、终稿润色，以及管理当前仓库中的项目初始化、阶段进度与工作区契约；当用户要求按阶段推进论文、补全 outputs 项目目录中的阶段文件，或调整相关脚本与契约时使用。
---

# 中国古代文学论文 Skill

## 先判断任务

- 先判断当前任务属于哪一类：新建项目、推进某一阶段、查看项目状态、修改契约或脚本。
- 已有项目时，先看 `outputs/<project>/project_progress.yaml`；没有项目时，先用 `scripts/init_project.py` 创建项目目录。
- 只读取当前任务需要的 reference，不要一次性把全部 reference 读进上下文。

## 按需读取

- 新建项目、确认阶段文件、查看文件命名：读 `references/workspace-contract.md`。
- 了解仓库结构，或准备改脚本职责：读 `references/repo-map.md`。
- 阶段一：先读 `references/stage1-planning.md`。
  选刊分流再读 `references/stage1_journals_intro.md`；按国内 A 刊标准推进时再读 `references/a-journal-writing.md`。
- 阶段二：读 `references/stage2-primary-corpus.md`。
- 阶段三：先读 `references/stage3a-deepened-thinking.md`；进入检索收敛时再读 `references/stage3b-data-intake.md`；进入学术史地图写作时再读 `references/stage3c-scholarship-map.md`。
- 阶段四：读 `references/stage4-outlining.md` 和 `references/stage4-argument-audit.md`。
- 阶段五：读 `references/stage5-drafting.md`。
- 阶段六：读 `references/stage6-polishing.md` 和 `references/stage6-submission-package.md`。

## 全局硬约束

- 把重点放在论文判断、材料组织和写作推进，不要把输出写成流程说明或项目管理清单。
- 把整个过程视为投稿准备，而不是信息拼装；默认目标是问题意识清楚、学术史位置明确、一手材料可复核、论证链条闭合。
- 遇到较长文件时，允许分多轮持续写入；优先保证每一轮都能稳定落盘。
- 如无充分证据，不要宣称“首次”“填补空白”或“彻底改写学界认识”。
- 不要伪造文献、引文、出处或 `piece_id`；没有来源支撑的判断不能写进正文结论。
- 阶段细则、结构模板、质量检查和示例，统一以对应 `references/` 文档为准，不要把细节再复制回本文件。

## 工具与职责边界

- 项目初始化与进度同步，优先复用 `scripts/init_project.py` 与 `scripts/sync_progress.py`。
- 阶段三开放来源检索，优先复用 `scripts/stage3b_sources.py`，不要每次现场重写抓取代码。
- 工作区契约的机器可读真相源是 `assets/workspace-contract.json`；契约变动时先改这里，再同步 `references/workspace-contract.md`。
- 阶段二运行时、数据库、批量 API 调用属于外部 runtime 职责，不要重新塞回 Skill。
- 脚本负责确定性执行与过程文件落盘；agent 负责学术判断、取舍和写作推进。

## 项目与文件规则

- 所有项目都放在 `outputs/<project>/` 下。
- 新建项目时，同时创建 `outputs/<project>/project_progress.yaml` 与 `outputs/<project>/_stage3b/papers/`。
- 每推进一个阶段，都更新 `project_progress.yaml`；优先使用 `scripts/sync_progress.py`。
- 阶段二过程文件统一放在 `outputs/<project>/_stage2/`。
- 阶段三二手研究过程文件与人工补料统一放在 `outputs/<project>/_stage3b/`。
- 默认终稿是 `6_final_manuscript.md`；只有用户明确要求时，才额外产出 `.docx`。

## 需要停下来问用户的情况

- `references/workspace-contract.md` 规定的前置产物尚未落盘，但用户要求直接跳到后续阶段。
- 阶段一中，用户没有说清投稿目标，或目标期刊超出内置资料且缺少可核对网页。
- 阶段三需要从 `3A` 进入 `3B`，或从 `3B` 进入 `3C`，但用户还没确认。
- 阶段三需要进入 `3C`，但 `candidate_papers.md` 或 `papers/` 中人工补料尚未满足要求。
- 用户希望放宽来源追溯约束，或允许没有来源的论据进入正文。
- 用户要求把阶段二真实检索逻辑或批量 API 调用重新塞回 Skill。
- 用户要求 `.docx`，但当前上下文没有可用的文档处理能力。

## 常用命令

```bash
python3 .agent/skills/ai-sinology/scripts/init_project.py demo
python3 .agent/skills/ai-sinology/scripts/sync_progress.py demo
python3 .agent/skills/ai-sinology/scripts/stage3b_sources.py --env-file .env --project demo openalex --query "汉代 灾异 诠释"
python3 .agent/skills/ai-sinology/scripts/stage3b_sources.py --env-file .env --project demo openalex-expand --query "汉代 灾异 诠释" --seed-id W123 --expand-mode references
python3 -m runtime.stage2.cli
```
