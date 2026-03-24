---
name: ai-sinology
description: 用于以 Skill 方式推进汉学论文项目。适用于阶段一选刊与研究计划、阶段二学术史地图、阶段三一手史料总库、阶段四论纲与论证审计、阶段五初稿写作、阶段六润色定稿，以及管理当前仓库中的工作区契约、项目初始化和与外部阶段三史料总库的交接。
---

# AI 汉学论文工作台

## 先读哪些文件

- 先读 `references/repo-map.md`，确认这个仓库现在只保留 Skill 与外部阶段三运行时。
- 用户明确要求按国内 A 刊标准推进，或任务涉及阶段一、二、四、五、六的学术写作判断时，再读 `references/a-journal-writing.md`。
- 涉及阶段边界、输出文件或 `piece_id` 约束时，再读 `references/workspace-contract.md`。
- 涉及 Skill 与外部阶段三执行器之间的交接时，再读 `references/stage3-handoff.md`。
- 只处理某一阶段时，只加载对应阶段 reference，不要把所有 reference 一次性读进上下文。

## 不可破坏的约束

- 把这个仓库视为 Skill 工作台，不要重新引入 `main.py`、`core/`、`workflow/`、`prompts/` 这一类旧流水线骨架。
- 新建项目时，始终把项目目录创建在当前工作目录的 `outputs/<project>/` 下，不要写到别的目录。
- 新建项目时，始终同时创建 `outputs/<project>/project_progress.yaml`，用于说明当前阶段、已完成文件和下一步。
- 工作区契约的机器可读真相源是 `assets/workspace-contract.json`；若契约变动，先改这里，再同步更新 reference 文档。
- 把阶段三数据库、真实检索执行器和批量 API 调用留在 Skill 外部。
- 运行阶段三 CLI 时，先选择 `outputs/<project>/` 下的项目，再创建并使用 `outputs/<project>/_stage3/` 作为阶段三工作目录。
- 外部阶段三的过程文件应统一写入 `outputs/<project>/_stage3/`。
- 外部阶段三最终至少写回 `outputs/<project>/3_final_corpus.yaml`，并保留 `outputs/<project>/3_stage3_manifest.json`。
- 在阶段四、五、六中始终保留 `piece_id` 可追溯性，不要伪造或重写不存在的锚点。
- 默认终稿是 `6_final_manuscript.md`；只有用户明确要求时，才额外产出 `.docx`。

## 按任务类型处理

## A刊导向协作总则

- 把整个流程都当作“面向匿名审稿与编辑初筛的投稿工作流”，不是信息拼装。
- 默认目标是：问题意识清楚、学术史位置明确、一手材料可复核、论证链条闭合、注释与引文经得起编辑核查。
- 阶段一先完成目标刊物校准，再回答“学界已做了什么、还缺什么、我凭什么用这批材料推进一步”，再落到题目和章节想象。
- 阶段二单独构建学术史地图；其数据源、筛选逻辑和分析动作与阶段三不同，不要混写成一个文件。
- 阶段三只负责一手史料总库，不承担学术史判断。
- 阶段四先搭建“中心论题 -> 分论点 -> 证据节点”的推理骨架，再做一次论证审计，不要跳过压力测试直接起草。
- 阶段五每一节都要让论点、史料、分析、学术回应成链条，不允许只有史料转述或只有理论空话。
- 阶段六默认按顶刊编辑视角做终检，并交付投稿包，而不只是单一终稿文件。
- 如无充分证据，不要宣称“首次”“填补空白”“完全改写学界认识”；只能在学术史比较后谨慎判断创新幅度。
- 可以用 AI 做语言润色、结构梳理、检索提示，但不得伪造文献、伪造引文、伪造 `piece_id`，也不得让 AI 代写核心观点与主体论证。

### 阶段一

- 读取 `references/stage1-planning.md`。
- 如用户要求按国内 A 刊标准起稿，同时读取 `references/a-journal-writing.md`。
- 产出 `1_journal_targeting.md` 与 `1_research_proposal.md`，不要再为这一阶段补脚本。

### 阶段二

- 读取 `references/stage2-scholarship-map.md`。
- 如用户要求按国内 A 刊标准推进，同时读取 `references/a-journal-writing.md`。
- 基于阶段一的题目校准与研究计划，结合用户提供文献、数据库结果或联网检索，生成 `2_scholarship_map.yaml`。

### 阶段三

- 读取 `references/stage3-handoff.md`。
- 外部执行器至少写回 `3_final_corpus.yaml`。
- 阶段三完成不等于学术史工作完成。

### 阶段四

- 读取 `references/stage4-outlining.md`。
- 再读 `references/stage4-argument-audit.md`。
- 如用户要求按国内 A 刊标准推进，同时读取 `references/a-journal-writing.md`。
- 使用阶段二 scholarship map 与阶段三 corpus 生成 `4_outline_matrix.yaml` 与 `4_argument_audit.md`。

### 阶段五

- 读取 `references/stage5-drafting.md`。
- 如用户要求按国内 A 刊标准推进，同时读取 `references/a-journal-writing.md`。
- 基于论纲、论证审计和 corpus 写出带 `piece_id` 锚点的初稿。

### 阶段六

- 读取 `references/stage6-polishing.md`。
- 再读 `references/stage6-submission-package.md`。
- 如用户要求按国内 A 刊标准推进，同时读取 `references/a-journal-writing.md`。
- 保留论证结构与锚点，完成终稿、摘要关键词、题目备选、匿名投稿检查与论断边界说明。

### 改仓库结构或契约

- 先读 `references/repo-map.md`、`references/workspace-contract.md` 和 `assets/workspace-contract.json`。
- 把通用工作区辅助逻辑优先放在当前 Skill 的 `scripts/`，只把阶段三外部执行必需的运行时留在 `runtime/stage3/`。

### 新建项目

- 优先调用 `scripts/init_project.py` 初始化 `outputs/<project>/` 和 `project_progress.yaml`。
- 再开始写 `1_research_proposal.md` 或其他阶段文件。
- 每推进一个阶段，都同步更新 `project_progress.yaml`；优先调用 `scripts/sync_progress.py`。

## Skill 内部辅助命令

```bash
python3 .agent/skills/ai-sinology/scripts/init_project.py demo
python3 .agent/skills/ai-sinology/scripts/project_status.py --all
python3 .agent/skills/ai-sinology/scripts/sync_progress.py demo
```

## 外部阶段三辅助命令

```bash
python3 -m runtime.stage3.cli
python3 -m runtime.stage3.cli --project demo --source stage1 --repos KR3j0160,KR3j0161
python3 -m runtime.stage3.cli --project demo --show-checkpoint
python3 -m runtime.stage3.cli --project demo --checkpoint-action checkpoint --checkpoint-cursor offset=120 --checkpoint-piece-id pb:KR3j0160_010-2b
python3 -m runtime.stage3.env_check --kanripo-root /path/to/kanripo_repos
python3 -m runtime.stage3.scope_probe --kanripo-root /path/to/kanripo_repos --limit 20
python3 -m runtime.stage3.api_smoke_test --slot llm1 --env-file .env
```

阶段三 CLI 会在项目目录下维护：

- 正式 manifest：`outputs/<project>/3_stage3_manifest.json`
- 阶段三工作目录：`outputs/<project>/_stage3/`
- 续跑会话文件：`outputs/<project>/_stage3/session.json`

如果阶段三拆成多次运行，外部执行器下次进入项目时应优先读取 `session.json` 里的 `retrieval_progress`，按 `current_target`、`current_cursor`、`last_piece_id` 等断点继续，而不是重头扫描。

## 需要停下来问用户的情况

- 阶段二还没有产出 `2_scholarship_map.yaml`，但用户要求直接进入阶段四或之后的步骤。
- 外部阶段三还没有产出 `3_final_corpus.yaml`，但用户要求直接进入阶段四或之后的步骤。
- 用户希望放宽 `piece_id` 追溯约束，或者允许没有来源的论据进入终稿。
- 用户要求把阶段三数据库或真实检索逻辑重新塞回 Skill 内。
- 用户要求 `.docx`，但当前任务上下文没有启用合适的文档处理能力。
