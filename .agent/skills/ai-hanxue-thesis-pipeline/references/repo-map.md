# 仓库地图

## 目录

- 核心入口
- 核心模块
- 阶段职责
- Prompt 系统
- 输出与状态目录
- 测试分布
- 常见起手文件

## 核心入口

- `main.py`
  - 解析 CLI 参数。
  - 创建或继续项目。
  - 驱动阶段流转、scope 选择和半自动确认。
- `README.md`
  - 记录用户可见的运行命令、参数和阶段行为。
- `docs/`
  - 保存设计意图：
  - `1_Product_Requirements_PRD.md`
  - `2_System_Architecture_SAD.md`
  - `3_Data_Contracts.md`

## 核心模块

- `core/config.py`
  - 定义 provider 默认值、阶段模型映射、速率限制、运行时参数和环境变量覆盖逻辑。
  - 读取 `.env` 与环境变量。
- `core/llm_client.py`
  - 封装 LiteLLM 的同步与异步调用。
  - 当 provider 提供多 key 时，启用 Router 负载均衡。
- `core/prompt_loader.py`
  - 加载 `prompts/*.yaml`。
  - 强校验 `metadata.step`、模板变量和渲染逻辑。
  - 依赖本地 Ruby 运行时完成 YAML 安全解析。
- `core/state_manager.py`
  - 从 `outputs/<project>/` 的文件推断项目进度。
  - 定义完成态、进行中、重置时需要清理的产物集合。
- `core/project_paths.py`
  - 解析阶段二内部 JSON 与 manifest 路径，同时兼容旧版顶层文件位置。

## 阶段职责

- `workflow/stage1_topic_selection.py`
  - 分节生成 proposal。
  - 提取并去重 `target_themes`。
- `workflow/stage2_data_collection/data_ingestion/parse_kanripo.py`
  - 从 `KR-Catalog` 枚举可选 scope。
  - 把原始文本切成带 `piece_id`、`source_file`、`original_text` 的 fragment JSONL。
- `workflow/stage2_data_collection/archival_screening.py`
  - 生成 screening batches。
  - 执行双模型粗筛与逐片复核。
  - 对重复失败片段写出 manual review 产物。
- `workflow/stage2_data_collection/archival_arbitration.py`
  - 把结果分成共识与争议。
  - 执行 LLM3 仲裁。
  - 输出精简 YAML 与内部 JSON。
- `workflow/stage2_data_collection/rate_control.py`
  - 管理 provider 限流与双模型同步限流。
- `workflow/stage3_outlining.py`
  - 生成论纲，并把锚点约束在已知 `piece_id` 集合内。
- `workflow/stage4_drafting.py`
  - 基于论纲锚点生成小节分析。
  - 输出保留 `piece_id` 的引文块。
- `workflow/stage5_polishing.py`
  - 按切片逐段润色全文。
  - 将草稿中的引文块与阶段二语料核对。
  - 在不依赖外部文档库的情况下输出 `.docx`。

## Prompt 系统

- `prompts/*.yaml`
  - 每个 prompt step 一个文件。
  - `metadata.step` 必须与文件名一致。
  - `variables` 必须与 Python 调用点一致。
  - 下游按 JSON 解析时，prompt 也必须强约束模型只回 JSON。
- 改 prompt 时必须同步改解析器。
- 任何 prompt 契约变化后都要重跑 `tests/test_prompt_loader.py`。

## 输出与状态目录

- `outputs/<project>/`
  - 保存用户可见的阶段产物。
- `outputs/<project>/_processed_data/`
  - 保存阶段二 fragment 与 screening batch 池。
- `outputs/<project>/_internal/stage2/`
  - 保存阶段二内部 JSON 镜像、manifest 与 cursor。
- `outputs/system.log`
  - 保存全局日志。

## 测试分布

- `tests/test_config.py`
  - 配置解析与覆盖逻辑。
- `tests/test_llm_client.py`
  - LiteLLM 封装层行为。
- `tests/test_main_semiauto.py`
  - 主 CLI 的半自动流转。
- `tests/test_project_progress_and_rerun.py`
  - 项目进度推断与重跑清理。
- `tests/test_prompt_loader.py`
  - Prompt 元数据与模板装载。
- `tests/test_stage2_scope_catalog.py`
  - Scope catalog 解析。
- `tests/test_stage2_scope_input_modes.py`
  - 交互式与手动 scope 输入模式。
- `tests/test_stage2_screening.py`
  - 阶段二筛选与复核行为。
- `tests/test_stage2_orchestration.py`
  - 阶段二整体调度与 manifest 逻辑。
- `tests/test_stage2_rate_control.py`
  - 限流计算与节流行为。
- `tests/test_stage2_arbitration_concurrency.py`
  - LLM3 仲裁并发。
- `tests/test_stage_output_optimizations.py`
  - 精简输出结构与阶段产物整形。

## 常见起手文件

- 想加或修改阶段参数：先看 `main.py`。
- 想改 provider、模型或并发默认值：先看 `core/config.py`。
- 想改 prompt 语义：先看 `prompts/*.yaml`，再看对应阶段代码和 `core/prompt_loader.py`。
- 想改续跑或产物判定：先看 `core/state_manager.py` 与 `core/project_paths.py`。
- 想改 Kanripo 检索或阶段二行为：先看 `references/stage2-kanripo-screening.md`，再看 `workflow/stage2_data_collection/`。
