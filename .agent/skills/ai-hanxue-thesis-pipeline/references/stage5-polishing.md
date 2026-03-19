# 阶段五：润色与定稿

## 何时读取本文件

- 修改 `workflow/stage5_polishing.py`
- 修改 `prompts/stage5_subsection_polish.yaml`
- 修改 `prompts/stage5_abstract_keywords.yaml`
- 排查 `5_final_manuscript.docx`、`5_revision_checklist.md`、`5_polish_progress.json`

## 阶段目标

在不破坏引文可追溯性的前提下，对初稿做分段润色、摘要关键词生成、引文核对和 DOCX 输出。

在混合独立模式下，阶段五默认由 skill 直接完成，不要求额外第三方 LLM 运行时。

## 核心文件

- `workflow/stage5_polishing.py`
- `prompts/stage5_subsection_polish.yaml`
- `prompts/stage5_abstract_keywords.yaml`
- `core/project_paths.py`

## 输入

- `4_first_draft.md`
- `_internal/stage2/2_final_corpus.json`

## 输出

- `outputs/<project>/5_final_manuscript.docx`
- `outputs/<project>/5_revision_checklist.md`

## 进度文件

- `outputs/<project>/5_polish_progress.json`

## 代码行为要点

- 先按 heading 切出润色单元，优先尝试 `####`，再退到 `###`、`##`。
- 每个单元单独润色，并在过程中持续回写进度快照。
- `_verify_quotes()` 会把草稿中的引文块与阶段二 corpus 原文逐条核对。
- `.docx` 不是通过 `python-docx` 生成，而是直接拼装简化的 OOXML 压缩包。

## 修改守则

- 不要破坏引文块语义与 `piece_id` 对应关系。
- 不要随意改变 progress 文件的关键字段，续跑逻辑依赖它。
- 改 DOCX 输出时，先确认目标是“稳定可打开”，不要无谓增加复杂文档特性。
- 改摘要或关键词 JSON 结构时，要同步修改解析与空值校验。

## 常见风险

- 标题切片规则变动后，润色单元划分失控。
- 润色时丢掉原始 heading，导致章节结构塌陷。
- DOCX 结构改坏后文件无法被 Word 正常打开。
- 引文核对放松后，最终稿可能出现“看似正常但已失真”的引用。

## 建议测试

- `pytest tests/test_stage_output_optimizations.py`
- 与阶段五相关的回归测试
- 如果改了引文提取或核对，联动验证阶段四输出格式
