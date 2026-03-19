---
name: ai-hanxue-thesis-pipeline
description: 用于操作、扩展和迁移这套五阶段 AI 汉学论文流程。涉及 Kanripo 语料检索、scope 选择、阶段二高并发多模型筛选与仲裁、阶段产物契约、断点续跑逻辑，或把本 skill 改造成“阶段二脚本独立运行、其余阶段由 skill 直接完成”的混合模式时使用。
---

# AI 汉学论文流水线

## 概览

当前 skill 支持两种工作方式：

- 仓库联动模式：直接操作当前仓库中的 `main.py`、`workflow/`、`prompts/` 与 `outputs/`。
- 混合独立模式：仅阶段二通过 skill 内脚本独立运行，阶段一、三、四、五由 skill 依据 reference 直接完成，不再要求额外第三方 LLM 运行时。

无论哪种模式，都必须保留五阶段顺序与 `piece_id` 追溯链路。

## 先读这些

- 先读 `README.md`，理解 CLI 参数、执行方式和用户可见行为。
- 修改架构、提示词、状态机、测试时先读 `references/repo-map.md`。
- 只改某一个阶段时，优先只加载该阶段对应的 reference 文件，不要把五个阶段一次性全读进上下文。
- 如果目标是把 skill 脱离当前仓库运行，再读 `references/standalone-hybrid-design.md`。

## 不可破坏的约束

- 五个阶段顺序固定：选题、史料、论纲、初稿、润色。
- 对“完整项目 skill”而言，阶段二必须保留 Kanripo 检索、切片、双模型筛选与 LLM3 仲裁，不能退化成手工摘录文本。
- 在混合独立模式下，只有阶段二需要外部第三方 LLM；阶段一、三、四、五默认由 skill 按 reference 直接产出内容。
- 用户可编辑提示词留在 `prompts/*.yaml`；调度、校验、断点续跑逻辑留在 Python。
- 项目状态以 `outputs/<project>/` 为准，优先扩展 `core/state_manager.py` 和 `core/project_paths.py`，不要额外发明隐式状态。
- `piece_id` 必须在阶段二、三、四、五之间贯通，后续阶段不得伪造锚点。
- 阶段二机器向数据镜像写入 `_internal/stage2/*.json`；给人看的 YAML 和 Markdown 保持精简。
- 任何契约变化都要同步改代码、prompt、reference 和测试。

## 阶段参考文件

- `references/stage1-topic-selection.md`
  - 阶段一：选题与构思。
- `references/stage2-kanripo-screening.md`
  - 阶段二：Kanripo 检索、切片、双模型高并发筛选、仲裁与总库汇编。
- `references/stage3-outlining.md`
  - 阶段三：论纲构建与证据锚点映射。
- `references/stage4-drafting.md`
  - 阶段四：受控起草与引文块生成。
- `references/stage5-polishing.md`
  - 阶段五：分段润色、引文核对与 DOCX 输出。
- `references/standalone-hybrid-design.md`
  - 混合独立模式的边界、目录结构与迁移策略。

## 常用命令

在仓库根目录执行：

```bash
python3 .agent/skills/ai-hanxue-thesis-pipeline/scripts/check_readiness.py
python3 .agent/skills/ai-hanxue-thesis-pipeline/scripts/list_kanripo_scopes.py --limit 20
python3 .agent/skills/ai-hanxue-thesis-pipeline/scripts/list_kanripo_scopes.py --validate KR1a,KR3j0160
python3 .agent/skills/ai-hanxue-thesis-pipeline/scripts/project_status.py --all
python3 main.py --new-project demo --idea "研究晚明通俗小说中的商人形象" --scopes KR3j --scope-dirs KR3j0160 --yes
```

在混合独立模式下，优先使用这些脚本：

```bash
python3 .agent/skills/ai-hanxue-thesis-pipeline/scripts/stage2_env_check.py --kanripo-root /path/to/kanripo_repos
python3 .agent/skills/ai-hanxue-thesis-pipeline/scripts/stage2_scope_probe.py --kanripo-root /path/to/kanripo_repos --limit 20
python3 .agent/skills/ai-hanxue-thesis-pipeline/scripts/stage2_api_smoke_test.py --slot llm1
```

## 按任务类型处理

### 跑整条流水线

1. 先跑 `check_readiness.py`，确认依赖、语料目录、`.env` 和 provider key 状态。
2. 如果用户还没定检索范围，用 `list_kanripo_scopes.py` 先列 scope。
3. 如果是续跑需求，用 `project_status.py` 先看当前项目处在哪一阶段。
4. 只有明确需要局部运行时才给 `main.py` 传阶段边界参数。
5. 宣布完成前，检查 `outputs/<project>/` 是否真的出现了该阶段应有产物。

### 以混合独立模式工作

1. 阶段一由 skill 直接生成研究计划与 `target_themes`。
2. 阶段二通过 skill 内脚本读取外部 Kanripo 目录，并调用第三方 LLM。
3. 阶段三、四、五由 skill 基于前序产物直接生成与润色，不要求额外脚本化模型运行。
4. 若将来需要把阶段三到五也脚本化，应作为后续增量任务单独设计，不与当前目标混写。

### 改架构、prompt 或状态机

1. 先读 `references/repo-map.md`，再读受影响阶段的独立 reference。
2. prompt YAML 和 Python 解析器必须一起改。
3. 保持 `metadata.step`、模板变量、严格 JSON 或 YAML 结构与 `core/prompt_loader.py`、阶段代码完全同步。
4. 先跑定向测试，再决定是否跑全量测试。

### 改阶段二

1. 先读 `references/stage2-kanripo-screening.md`。
2. 保持这条链路不变：
   `scope 选择 -> parse_kanripo_to_fragments -> screening batches -> llm1/llm2 筛选与复核 -> 共识/争议分流 -> llm3 仲裁 -> final corpus / manual review`
3. 保持 manifest 签名、cursor、内部 JSON 镜像和 rate control 逻辑一致。
4. 修改筛选策略前先读相关 stage2 tests。

### 排查产物或续跑逻辑

1. 改代码前先读 `outputs/<project>/` 与 `_internal/stage2/` 的真实产物。
2. 阶段完成判定和重跑清理以 `StateManager` 语义为准。
3. 优先修状态推断或 manifest 处理，不要手工篡改生成产物来“糊过去”。

## 如何使用这些 reference

- `references/repo-map.md`
  - 看入口、模块边界、测试分布、输出目录和常见落点文件。
- `references/stage1-topic-selection.md`
  - 处理阶段一相关任务时读取。
- `references/stage2-kanripo-screening.md`
  - 处理 Kanripo、scope、切片、双模型筛选、仲裁、失败恢复时读取。
- `references/stage3-outlining.md`
  - 处理论纲结构与 `piece_id` 锚点绑定时读取。
- `references/stage4-drafting.md`
  - 处理初稿生成、引文块与小节级分析时读取。
- `references/stage5-polishing.md`
  - 处理润色切片、引文核对、摘要关键词和 DOCX 输出时读取。
- `references/standalone-hybrid-design.md`
  - 处理“skill 本体 + 外部 Kanripo + 技能内阶段二配置文件”这一运行形态时读取。

## 辅助脚本

- `scripts/check_readiness.py`
  - 检查 live run 前置条件：语料、依赖、`.env`、provider key。
- `scripts/list_kanripo_scopes.py`
  - 列出可选 scope 家族，或校验用户给出的 scope token。
- `scripts/project_status.py`
  - 汇总 `outputs/` 中项目的阶段状态。
- `scripts/stage2_api_config.py`
  - 单独维护阶段二 provider、model、base URL、env key 名和关键限流参数。
- `scripts/stage2_env_check.py`
  - 独立检查外部 Kanripo 目录与阶段二 API 配置。
- `scripts/stage2_scope_probe.py`
  - 在不依赖当前仓库代码的情况下，列出或校验外部 Kanripo scope。
- `scripts/stage2_api_smoke_test.py`
  - 用阶段二配置做最小 API 连通性测试。

## 测试策略

- 先跑定向测试：
  - `pytest tests/test_prompt_loader.py`
  - `pytest tests/test_project_progress_and_rerun.py`
  - `pytest tests/test_stage2_scope_catalog.py`
  - `pytest tests/test_stage2_scope_input_modes.py`
  - `pytest tests/test_stage2_screening.py`
  - `pytest tests/test_stage2_orchestration.py`
  - `pytest tests/test_stage2_rate_control.py`
- 当阶段契约或共享组件变化较大时，再跑：
  - `pytest`

## 需要及时停下来问用户的情况

- `data/kanripo_repos` 缺失，或被替换成了不同目录结构的语料。
- 需求会削弱 `piece_id` 可追溯性，或删掉阶段二交叉验证。
- 需要真实跑 LLM，但当前 API key、依赖或 provider 环境不满足。
- 用户希望把阶段三到五也脚本化执行，但当前 skill 仅承诺阶段二外部 API 独立运行。
