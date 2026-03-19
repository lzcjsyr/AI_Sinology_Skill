# 阶段二：Kanripo 检索与高并发筛选

## 何时读取本文件

- 修改 `workflow/stage2_data_collection/` 下任意核心模块
- 修改 scope 选择、Kanripo 切片、筛选、仲裁、限流、断点续跑
- 排查 `2_final_corpus.yaml`、`2_stage_manifest.json`、cursor、manual review 等阶段二产物

## 阶段目标

在选定的 Kanripo 语料范围内做穷举式检索，把原始文本切成带学术定位坐标的片段，通过双模型高并发筛选与第三模型仲裁，产出可信的结构化史料总库。

在混合独立模式下，阶段二是唯一必须依赖第三方 LLM API 的阶段。

## 核心文件

- `workflow/stage2_data_collection/data_ingestion/parse_kanripo.py`
- `workflow/stage2_data_collection/archival_screening.py`
- `workflow/stage2_data_collection/archival_arbitration.py`
- `workflow/stage2_data_collection/rate_control.py`
- `workflow/stage2_data_collection/__init__.py`
- `core/config.py`
- `core/project_paths.py`
- `core/state_manager.py`

如果脱离当前仓库运行，优先使用 skill 内这组独立文件：

- `scripts/stage2_api_config.py`
- `scripts/standalone_kanripo.py`
- `scripts/stage2_env_check.py`
- `scripts/stage2_scope_probe.py`
- `scripts/stage2_api_smoke_test.py`

## 必经链路

1. 读取或校验 scope。
2. 把 Kanripo 原始文本切成 fragment JSONL。
3. 在同一 `source_file` 内按字符上限贪心合并成 screening batches。
4. 用 LLM1 和 LLM2 做粗筛与逐片复核。
5. 用纯代码分成共识与争议。
6. 用 LLM3 对争议做仲裁。
7. 产出最终总库与人工复核清单。

不要把这条链路简化成“读几段文本然后手工挑选”，那样不再是这个项目的完整阶段二。

## Scope 与语料发现

- 语料根目录：`data/kanripo_repos/`
- Catalog 根目录：`data/kanripo_repos/KR-Catalog/KR/`
- 支持两类输入：
  - `KR1a` 这类 scope family
  - `KR3j0160` 这类精确目录
- `main.py` 支持：
  - 基于 catalog 的交互式多选
  - 手动逗号输入
  - 父子归并，例如 `KR1a,KR1a0006 -> KR1a`

## 切片规则

`parse_kanripo.py` 定义了阶段二最关键的纯代码契约：

- 先从 `#+TITLE:` 提取书名，写入 `source_file`
- 再按 `<pb:...>` 分片
- 标签内部字符串直接作为 `piece_id`
- 片段正文清洗技术标记与空白行
- 输出到 `_processed_data/kanripo_fragments.jsonl`

单个 fragment 至少包含：

- `piece_id`
- `source_file`
- `original_text`

## 双模型筛选

`archival_screening.py` 是阶段二主引擎。

- 先粗筛 batch，再拆回 piece 逐片复核
- batch 仅在同一 `source_file` 内合并
- `screening_batch_max_chars` 控制 batch 大小
- 落盘文件：
  - `2_llm1_raw.jsonl`
  - `2_llm2_raw.jsonl`
- 多次失败后写：
  - `2_screening_failed_pieces.yaml`
  - `_internal/stage2/2_screening_failed_pieces.json`

## 仲裁与总库

`archival_arbitration.py` 先做纯代码比较，再调用 LLM3。

- 双方都相关：进入共识
- 双方都不相关：直接丢弃
- 只有一方相关：进入争议，由 LLM3 仲裁

当前对外 YAML 使用统一包裹结构：

```yaml
piece_count: 12
records:
  - ...
```

适用于：

- `2_consensus_data.yaml`
- `2_disputed_data.yaml`
- `2_llm3_verified.yaml`
- `2_screening_failed_pieces.yaml`
- `2_final_corpus.yaml`

## 断点续跑与签名

- manifest：
  - `_internal/stage2/2_stage_manifest.json`
- cursor：
  - `_internal/stage2/.cursor_llm1.json`
  - `_internal/stage2/.cursor_llm2.json`

签名至少包含：

- selected scopes
- `target_themes`
- `screening_batch_max_chars`
- 阶段二三套模型的 provider 和 model

只有签名一致且最终总库尚未生成时，才允许续跑。签名不一致应清理重跑，不要强行复用旧中间产物。

## 运行参数

关键运行参数在 `core/config.py`，并可被 CLI 或环境变量覆盖：

- `llm1_concurrency`
- `llm2_concurrency`
- `arbitration_concurrency`
- `screening_batch_max_chars`
- `fragment_max_attempts`
- `max_empty_retries`
- `sync_headroom`
- `sync_max_ahead`
- 各阶段 RPM/TPM 覆盖

修改并发或限流时，要同时理解三层控制：

- provider 自身限速
- 双模型同步节流
- 基于请求 token 估算出的自动并发

## 修改守则

- 不要破坏 `(piece_id, matched_theme)` 作为原始记录主键的事实。
- 不要删掉 `_internal/stage2/` JSON 镜像；阶段三和排障都依赖它。
- 不要让失败片段悄悄按“不相关”吞掉；它们必须进入 manual review。
- 不要只改 prompt 不改解析逻辑，或只改解析逻辑不改测试。

## 常见风险

- scope 不相关，导致整个阶段二空跑。
- `target_themes` 太抽象，导致召回质量崩掉。
- 清理规则或签名规则改坏，导致续跑时复用脏数据。
- localization 元数据被误删，导致审计和排障能力下降。

## 建议测试

- `pytest tests/test_stage2_scope_catalog.py`
- `pytest tests/test_stage2_scope_input_modes.py`
- `pytest tests/test_stage2_screening.py`
- `pytest tests/test_stage2_piece_analysis.py`
- `pytest tests/test_stage2_orchestration.py`
- `pytest tests/test_stage2_rate_control.py`
- `pytest tests/test_stage2_arbitration_concurrency.py`
- `pytest tests/test_stage_output_optimizations.py`
