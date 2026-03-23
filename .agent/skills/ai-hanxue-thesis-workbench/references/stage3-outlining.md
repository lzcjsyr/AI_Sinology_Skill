# 阶段三：论纲构建

## 输入

- `1_research_proposal.md`
- `2_final_corpus.yaml`

## 输出

- `outputs/<project>/3_outline_matrix.yaml`

## 目标

- 形成三级论纲。
- 让每个最小论证节点都绑定真实 `piece_id`。

## 执行规则

- 先从 proposal 提炼中心论题、争点和章节方向。
- 再按 `matched_theme` 和 `piece_id` 梳理 corpus，给每个小节分配证据。
- 只引用真实存在的 `piece_id`，不补造锚点。
- 优先让一个小节聚焦一个清晰论证，不要把证据堆成素材池。

## 结构要求

- 顶层必须有 `thesis_statement`
- `chapters -> sections -> sub_sections`
- 每个 `sub_section` 至少包含：
  - `sub_section_title`
  - `sub_section_argument`
  - `evidence_anchors`

## 质量检查

- 每个 `evidence_anchors` 至少有一个 `piece_id`。
- 同一条史料不要在多个不相干小节里机械复用。
- 论纲顺序能支撑论文推进，而不是主题拼盘。
