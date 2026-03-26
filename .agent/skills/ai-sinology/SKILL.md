---
name: ai-sinology
description: 用于撰写和推进中国古代文学、古典文献、古代文论、文学批评史与相关文献学方向的论文项目。适用于选题、选刊、研究计划、学术史梳理、一手材料交接后的论纲设计、初稿写作、终稿润色，以及管理当前仓库中的项目初始化、阶段进度与工作区契约；当用户要求按阶段推进论文、补全 `outputs/<project>/` 阶段文件，或调整相关脚本与契约时使用。
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
- 阶段二：先读 `references/stage2b-scholarship-map.md` 理解正式输出，再读 `references/stage2a-data-intake.md` 理解 `2A` 检索扩展与候选集收敛；需要稳定复用开放 API 时，优先调用 `scripts/stage2a_sources.py` 和 `scripts/stage2b_scholarship_map.py`，不要每次现场重写抓取代码；如果需要按国内 A 刊标准推进，再加读 `references/a-journal-writing.md`。
- 阶段三交接：读 `references/stage3-handoff.md`。
- 阶段四：读 `references/stage4-outlining.md` 和 `references/stage4-argument-audit.md`。
  如果需要按国内 A 刊标准推进，再加读 `references/a-journal-writing.md`。
- 阶段五：读 `references/stage5-drafting.md`。
  如果需要按国内 A 刊标准推进，再加读 `references/a-journal-writing.md`。
- 阶段六：读 `references/stage6-polishing.md` 和 `references/stage6-submission-package.md`。
  如果需要按国内 A 刊标准推进，再加读 `references/a-journal-writing.md`。

## 核心写作规则

- 把重点放在论文判断、材料组织和写作推进，不要把输出写成流程说明或项目管理清单。
- 把整个过程视为投稿准备，而不是信息拼装。默认目标是：问题意识清楚、学术史位置明确、一手材料可复核、论证链条闭合。
- 阶段一先收束两个结果：明确的研究方向、明确的目标期刊。
- 如果用户没有说清投稿目标，先追问。
- 如果用户点名的目标期刊不在现有单刊 reference 内，优先请用户提供该刊官网、征稿说明、投稿须知或近年栏目页链接；先据此提炼要求，再继续阶段一。
- 阶段一只负责为阶段二收束研究方向与投稿约束，不直接承担阶段三正式交接。
- 阶段二只负责学术史地图，不要和阶段三的一手材料总库混写。
- 阶段二默认拆成 `2A` 与 `2B` 两个子环节：`2A` 负责检索扩展与候选集收敛，`2B` 负责学术史地图写作；正式阶段文件是 `2b_scholarship_map.yaml`。
- 阶段二如需重复抓取 `OpenAlex` 等开放来源，优先复用 `scripts/stage2a_sources.py`。
- 阶段二的主流程应由 agent 自主执行：先读阶段一，判断研究对象、概念轴线、时段和候选争点，再分多轮调用 `scripts/stage2a_sources.py`，完成 `2A` 的候选集收敛，最后进入 `2B` 完成 scholarship map 写作。
- 如果阶段二以 `OpenAlex` 为主入口，默认先做关键词检索，再由 agent 阅读返回结果、挑出值得继续追踪的作品，沿这些作品的引用链继续扩展；首轮 `OpenAlex` 后，还应使用 agent 自身的网页搜索/浏览能力补检，优先整理期刊官网、DOI 落地页、出版社页面、机构知识库与可引用数据库落地页，不把普通博客或聚合站当作依据。
- `2A` 本身包含学术判断：agent 应根据题名、摘要、刊物、作者与引用链判断哪些结果保留、哪些结果继续扩展、哪些结果应剔除。
- `openalex-expand` 只负责按 agent 给定的 seed works 抓取一跳引用，不负责判断是否相关，也不负责决定是否继续下一轮。
- `OpenAlex` 多轮扩展的默认目标是沉淀约 30 篇高相关作品；轮次由 agent 结合每轮新增结果质量、重复度和偏题程度决定，不要求机械跑满固定轮数。
- `2A` 除 JSON 过程文件外，还应明确沉淀 `outputs/<project>/_stage2a/candidate_papers.md`，把自动化调研与网页补检后保留的候选论文清单写清楚，供用户补料与 `2B` 继续使用。
- 如果开放来源覆盖明显不足，阶段二应停在 `2A`，等待用户补充外部资料后再继续。
- 初始化项目时，同时创建 `outputs/<project>/_stage2a/papers/`，用于存放阶段 `2A` 后人工补入的 PDF、题录导出和读书笔记；`2B` 默认把该目录视为主要依据之一。
- `2B` 应在候选集相对稳定后再开始；这时重点是归纳 positions、debates、gaps 和 claim boundaries，而不是继续无边界扩搜。
- `2B` 产出的 `2b_scholarship_map.yaml` 应同时沉淀面向阶段三的 handoff：至少给出 `stage3_handoff.target_themes`，必要时补充检索重点、材料类型提示与排除项。
- `scripts/stage2b_scholarship_map.py` 只是草稿骨架工具，不替代 agent 的学术判断。
- 阶段三默认读取阶段二 handoff，不再把阶段一 front matter 当作正式输入契约；阶段一文件只保留为背景参考。
- 阶段三只负责材料交接与消费，不在 Skill 内重建数据库、批量检索或真实执行器。
- 阶段四先搭建“中心论题 -> 分论点 -> 证据节点”的骨架，再做论证审计，不要跳过压力测试直接起草。
- 阶段五每一节都要形成“论点 -> 史料 -> 分析 -> 学术回应”的链条，不能只堆史料，也不能只讲空泛理论。
- 阶段六保留论证结构与锚点，完成终稿、摘要关键词、题目备选、匿名投稿检查和论断边界说明。
- 如无充分证据，不要宣称“首次”“填补空白”或“彻底改写学界认识”。
- 不要伪造文献、引文、出处或 `piece_id`。没有来源支撑的判断，不能写进正文结论。

## 项目与文件规则

- 所有项目都放在 `outputs/<project>/` 下。
- 新建项目时，同时创建 `outputs/<project>/project_progress.yaml`。
- 每推进一个阶段，都更新 `project_progress.yaml`；优先使用 `scripts/sync_progress.py`。
- 工作区契约的机器可读真相源是 `assets/workspace-contract.json`；契约变动时，先改这里，再同步 `references/workspace-contract.md`。
- 阶段二过程文件与人工补料说明推荐放在 `outputs/<project>/_stage2a/`。
- 新建项目时，同时创建 `outputs/<project>/_stage2a/papers/`。
- 阶段三过程文件统一放在 `outputs/<project>/_stage3/`。
- 阶段三完成后，项目里至少要有 `outputs/<project>/3_final_corpus.yaml`；如已生成 `outputs/<project>/3_stage3_manifest.json`，一并保留。
- 默认终稿是 `6_final_manuscript.md`；只有用户明确要求时，才额外产出 `.docx`。

## 常用命令

```bash
python3 .agent/skills/ai-sinology/scripts/init_project.py demo
python3 .agent/skills/ai-sinology/scripts/project_status.py --all
python3 .agent/skills/ai-sinology/scripts/sync_progress.py demo
python3 .agent/skills/ai-sinology/scripts/stage2a_sources.py openalex --project demo --query "汉代 灾异 诠释" --env-file .env
python3 .agent/skills/ai-sinology/scripts/stage2a_sources.py openalex-expand --project demo --query "汉代 灾异 诠释" --round-index 1 --seed-id W123 --seed-id W456 --env-file .env
python3 .agent/skills/ai-sinology/scripts/stage2b_scholarship_map.py --project demo --source-json outputs/demo/_stage2a/openalex-*.json
python3 -m runtime.stage3.cli
```

更具体的阶段三交接方式，放在 `references/stage3-handoff.md`，不要把长命令和运行细节塞回这里。

## 需要停下来问用户的情况

- 阶段二还没有产出 `2b_scholarship_map.yaml`，但用户要求直接进入阶段四或之后。
- 阶段三还没有产出 `3_final_corpus.yaml`，但用户要求直接进入阶段四或之后。
- 用户希望放宽 `piece_id` 追溯约束，或允许没有来源的论据进入正文。
- 用户要求把阶段三数据库、真实检索逻辑或批量 API 调用重新塞回 Skill。
- 用户要求 `.docx`，但当前上下文没有可用的文档处理能力。
