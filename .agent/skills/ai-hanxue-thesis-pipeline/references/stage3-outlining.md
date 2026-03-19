# 阶段三：论纲构建

## 何时读取本文件

- 修改 `workflow/stage3_outlining.py`
- 修改 `prompts/stage3_outline.yaml`
- 排查 `3_outline_matrix.yaml`
- 排查 `piece_id` 锚点失真、无效或被篡改的问题

## 阶段目标

基于阶段一的研究主题与阶段二的可信史料，生成三级论文大纲，并把每个论证节点锚定到真实存在的 `piece_id`。

在混合独立模式下，阶段三默认由 skill 直接完成，不要求额外第三方 LLM 运行时。

## 核心文件

- `workflow/stage3_outlining.py`
- `prompts/stage3_outline.yaml`
- `core/project_paths.py`

## 输入

- `1_research_proposal.md`
- `_internal/stage2/2_final_corpus.json`

## 输出

- `outputs/<project>/3_outline_matrix.yaml`

## 必须保持的结构

- 顶层字段：
  - `thesis_statement`
  - `chapters`
- `chapters -> sections -> sub_sections`
- 每个 `sub_section` 要包含：
  - `sub_section_title`
  - `sub_section_argument`
  - `evidence_anchors`

## 代码行为要点

- 阶段三读取的是阶段二内部 JSON，而不是用户向 YAML。
- `_sanitize_outline()` 会把非法锚点修正到已知 `piece_id` 集合中。
- prompt 里给模型的是主题与语料摘要，而不是整个 corpus 全量正文。

## 修改守则

- 不要放松对 `evidence_anchors` 的校验。
- 如果改层级结构，必须同步修改阶段四读取逻辑。
- 如果想让模型看到更多上下文，优先改摘要策略，不要直接把整个 corpus 生硬塞进 prompt。

## 常见风险

- 章节结构变化后，阶段四找不到 `sub_sections`。
- 锚点字段改名后，后续阶段无法取证。
- 模型返回结构稍变，`parse_json_from_text()` 后的修复逻辑没有跟上。

## 建议测试

- `pytest tests/test_prompt_loader.py`
- 与阶段三输出结构相关的回归测试
- 如影响阶段四，联动跑起草相关测试
