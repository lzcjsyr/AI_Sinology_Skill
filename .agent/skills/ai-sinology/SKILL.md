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
- 阶段一：读 `references/stage1-planning.md`。
  选刊时先读 `references/stage1-venues.md`，锁定目标期刊后再读对应的单刊 reference；如果需要按国内 A 刊标准推进，再加读 `references/a-journal-writing.md`。
- 阶段二：读 `references/stage2-primary-corpus.md`。
- 阶段三：先读 `references/stage3a-deepened-thinking.md`；进入文献检索收敛时再读 `references/stage3b-data-intake.md`；进入学术史地图写作时再读 `references/stage3c-scholarship-map.md`。如需稳定复用开放 API，优先调用 `scripts/stage3b_sources.py`，不要每次现场重写抓取代码；如果需要按国内 A 刊标准推进，再加读 `references/a-journal-writing.md`。
- 阶段四：读 `references/stage4-outlining.md` 和 `references/stage4-argument-audit.md`。
  如果需要按国内 A 刊标准推进，再加读 `references/a-journal-writing.md`。
- 阶段五：读 `references/stage5-drafting.md`。
  如果需要按国内 A 刊标准推进，再加读 `references/a-journal-writing.md`。
- 阶段六：读 `references/stage6-polishing.md` 和 `references/stage6-submission-package.md`。
  如果需要按国内 A 刊标准推进，再加读 `references/a-journal-writing.md`。

## 核心写作规则

- 总原则：
  - 把重点放在论文判断、材料组织和写作推进，不要把输出写成流程说明或项目管理清单。
  - 把整个过程视为投稿准备，而不是信息拼装。默认目标是：问题意识清楚、学术史位置明确、一手材料可复核、论证链条闭合。
  - 如无充分证据，不要宣称“首次”“填补空白”或“彻底改写学界认识”。
  - 不要伪造文献、引文、出处或 `piece_id`。没有来源支撑的判断，不能写进正文结论。

- 阶段一：
  - 先收束两个结果：明确的研究方向、明确的目标期刊。
  - 如果用户没有说清投稿目标，先追问。
  - 如果用户点名的目标期刊不在现有单刊 reference 内，优先请用户提供该刊官网、征稿说明、投稿须知或近年栏目页链接；先据此提炼要求，再继续阶段一。
  - 阶段一只负责收束研究方向、投稿约束与阶段二入口，不替代后续一手材料整理与学术史判断。
  - 阶段一必须给阶段二写出明确的检索主题，优先放进 YAML front matter 的 `stage2_retrieval_themes`。

- 阶段二：
  - 阶段二先去查原始文献，获得原始思考和灵感。
  - 阶段二只负责一手材料勘查与总库整理，不与学术史地图混写。
  - 启动阶段二前，应先确认 `1_journal_targeting.md` 与 `1_research_proposal.md` 两个正式阶段一文件都已落盘；不要用临时口头 handoff 代替。
  - 阶段二默认直接读取阶段一文件，优先读取 `stage2_retrieval_themes`，没有时才退回到研究方向与 idea 的兜底推断；不等待后置 scholarship map。
  - 正式阶段文件是 `2_primary_corpus.yaml`；如有运行时配置，额外保留 `2_stage2_manifest.json` 与 `outputs/<project>/_stage2/`。

- 阶段三总则：
  - 阶段三分成 `3A`、`3B`、`3C` 三段。
  - `3A` 先基于阶段一初步想法与阶段二原始文献，整理出更深的判断。
  - `3B` 再做二手研究检索扩展与候选集收敛。
  - `3C` 最后生成学术史地图。
  - 阶段三如需重复抓取开放来源，优先复用 `scripts/stage3b_sources.py`；主流程由 agent 自主执行，`3C` 由 agent 直接读取前序文件并输出固定 YAML，不把学术判断硬塞进抓取脚本。

- 阶段三 `3A`：
  - `3A` 要先回到原始文献，提炼问题张力、材料启发、可成立的暂定判断与需要后续验证的点。
  - 正式输出是 `3a_deepened_thinking.md`。

- 阶段三 `3B`：
  - `3B` 本身包含学术判断：agent 要先读阶段一、阶段二和 `3A`，再分多轮完成检索扩展、候选集收敛与筛选记录，不能把 `3B` 做成“只跑一遍 API”的纯抓取环节。
  - 中文主题原则上更倚重 `baidu-scholar` 做首轮发现与补漏，再切到 `OpenAlex` 读取 `referenced_works` 沿引用链扩展。
  - 更具体的检索轮次、关键词改写、网页补检、停轮条件与过程文件要求，统一见 `references/stage3b-data-intake.md`。

- 阶段三 `3C`：
  - `3C` 应在 `3A` 已落盘、`3B` 的候选集相对稳定、且 `outputs/<project>/_stage3b/papers/` 中至少已有 1 份人工导入论文/题录/笔记后再开始，重点是归纳 positions、debates、gaps 和 claim boundaries，而不是继续无边界扩搜。
  - `3C` 必须读取 `1_journal_targeting.md`、`1_research_proposal.md`、`2_primary_corpus.yaml`、`3a_deepened_thinking.md`、`outputs/<project>/_stage3b/candidate_papers.md` 与 `outputs/<project>/_stage3b/papers/` 中的人工补料，再直接写出 `3c_scholarship_map.yaml`。
  - 正式输出是 `3c_scholarship_map.yaml`。
  - 更具体的进入条件、结构要求与质量检查，统一见 `references/stage3c-scholarship-map.md`。

- 阶段四：
  - 先搭建“中心论题 -> 分论点 -> 证据节点”的骨架，再做论证审计，不要跳过压力测试直接起草。

- 阶段五：
  - 每一节都要形成“论点 -> 史料 -> 分析 -> 学术回应”的链条，不能只堆史料，也不能只讲空泛理论。

- 阶段六：
  - 保留论证结构与锚点，完成终稿、摘要关键词、题目备选、匿名投稿检查和论断边界说明。

## 项目与文件规则

- 所有项目都放在 `outputs/<project>/` 下。
- 新建项目时，同时创建 `outputs/<project>/project_progress.yaml`。
- 每推进一个阶段，都更新 `project_progress.yaml`；优先使用 `scripts/sync_progress.py`。
- 工作区契约的机器可读真相源是 `assets/workspace-contract.json`；契约变动时，先改这里，再同步 `references/workspace-contract.md`。
- 阶段二过程文件统一放在 `outputs/<project>/_stage2/`。
- 新建项目时，同时创建 `outputs/<project>/_stage3b/papers/`。
- 阶段二完成后，项目里至少要有 `outputs/<project>/2_primary_corpus.yaml`；如已生成 `outputs/<project>/2_stage2_manifest.json`，一并保留。
- 阶段三的二手研究过程文件与人工补料说明推荐放在 `outputs/<project>/_stage3b/`。
- 阶段三完成后，项目里至少要有 `outputs/<project>/3a_deepened_thinking.md`、`outputs/<project>/_stage3b/candidate_papers.md`、`outputs/<project>/_stage3b/papers/` 中的人工补料，以及 `outputs/<project>/3c_scholarship_map.yaml`。
- 默认终稿是 `6_final_manuscript.md`；只有用户明确要求时，才额外产出 `.docx`。

## 常用命令

```bash
python3 .agent/skills/ai-sinology/scripts/init_project.py demo
python3 .agent/skills/ai-sinology/scripts/sync_progress.py demo
python3 .agent/skills/ai-sinology/scripts/stage3b_sources.py baidu-scholar --project demo --query "汉代 灾异 诠释" --env-file .env
python3 .agent/skills/ai-sinology/scripts/stage3b_sources.py openalex-expand --project demo --query "汉代 灾异 诠释" --seed-id W123 --expand-mode references --env-file .env
python3 -m runtime.stage2.cli
```

更具体的阶段命令、阶段二原始文献流程与阶段三执行细则，放在对应的 `references/` 文档里，不要把长命令和运行细节塞回这里。

## 需要停下来问用户的情况

- 阶段二还没有产出 `2_primary_corpus.yaml`，但用户要求直接进入阶段三或之后。
- 阶段三还没有产出 `3a_deepened_thinking.md`、`outputs/<project>/_stage3b/candidate_papers.md`、`outputs/<project>/_stage3b/papers/` 中的人工补料，或 `3c_scholarship_map.yaml`，但用户要求直接进入阶段四或之后。
- 用户希望放宽 `piece_id` 追溯约束，或允许没有来源的论据进入正文。
- 用户要求把阶段二数据库、真实检索逻辑或批量 API 调用重新塞回 Skill。
- 用户要求 `.docx`，但当前上下文没有可用的文档处理能力。
