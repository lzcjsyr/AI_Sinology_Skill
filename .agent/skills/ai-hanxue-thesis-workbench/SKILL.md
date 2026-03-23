---
name: ai-hanxue-thesis-workbench
description: 用于以 Skill 方式推进汉学论文项目，而不是维护脚本流水线。适用于阶段一选题计划、阶段三论纲构建、阶段四初稿写作、阶段五润色定稿，以及围绕外部阶段二史料总库整理当前仓库的结构、产物契约和工作区文件。
---

# AI 汉学论文工作台

## 先读哪些文件

- 先读 `references/repo-map.md`，确认这个仓库现在只保留 Skill 与外部阶段二运行时。
- 涉及阶段边界、输出文件或 `piece_id` 约束时，再读 `references/workspace-contract.md`。
- 只处理某一阶段时，只加载对应阶段 reference，不要把所有 reference 一次性读进上下文。

## 不可破坏的约束

- 把这个仓库视为 Skill 工作台，不要重新引入 `main.py`、`core/`、`workflow/`、`prompts/` 这一类旧流水线骨架。
- 新建项目时，始终把项目目录创建在当前工作目录的 `outputs/<project>/` 下，不要写到别的目录。
- 新建项目时，始终同时创建 `outputs/<project>/project_progress.yaml`，用于说明当前阶段、已完成文件和下一步。
- 把阶段二数据库、真实检索执行器和批量 API 调用留在 Skill 外部。
- 只要求外部阶段二把结果写回 `outputs/<project>/2_final_corpus.yaml`，并可选附带 `2_stage2_manifest.json`。
- 在阶段三、四、五中始终保留 `piece_id` 可追溯性，不要伪造或重写不存在的锚点。
- 默认终稿是 `5_final_manuscript.md`；只有用户明确要求时，才额外产出 `.docx`。

## 按任务类型处理

### 阶段一

- 读取 `references/stage1-planning.md`。
- 直接创作 `1_research_proposal.md`，不要再为这一阶段补脚本。

### 阶段三

- 读取 `references/stage3-outlining.md`。
- 只使用阶段一 proposal 和外部阶段二 corpus 生成论纲。

### 阶段四

- 读取 `references/stage4-drafting.md`。
- 基于论纲和 corpus 写出带 `piece_id` 锚点的初稿。

### 阶段五

- 读取 `references/stage5-polishing.md`。
- 保留论证结构与锚点，只做学术表达、章节衔接和终稿整备。

### 改仓库结构或契约

- 先读 `references/repo-map.md` 和 `references/workspace-contract.md`。
- 把运行时辅助逻辑放在 `runtime/`，把创作性知识放在当前 Skill 的 reference 中。

### 新建项目

- 先在当前工作目录下创建 `outputs/<project>/`。
- 立即写入 `outputs/<project>/project_progress.yaml`。
- 再开始写 `1_research_proposal.md` 或其他阶段文件。
- 每推进一个阶段，都同步更新 `project_progress.yaml`。

## 外部阶段二辅助命令

```bash
python3 -m runtime.project_status --all
python3 -m runtime.stage2.cli
python3 -m runtime.stage2.cli --project demo --source stage1 --repos KR3j0160,KR3j0161
python3 -m runtime.stage2.env_check --kanripo-root /path/to/kanripo_repos
python3 -m runtime.stage2.scope_probe --kanripo-root /path/to/kanripo_repos --limit 20
python3 -m runtime.stage2.api_smoke_test --slot llm1 --env-file .env
```

## 需要停下来问用户的情况

- 外部阶段二还没有产出 `2_final_corpus.yaml`，但用户要求直接进入阶段三或之后的步骤。
- 用户希望放宽 `piece_id` 追溯约束，或者允许没有来源的论据进入终稿。
- 用户要求把阶段二数据库或真实检索逻辑重新塞回 Skill 内。
- 用户要求 `.docx`，但当前任务上下文没有启用合适的文档处理能力。
