# 阶段四：论纲构建

## 输入

- `1_research_proposal.md`
- `2_scholarship_map.yaml`
- `3_final_corpus.yaml`

## 输出

- `outputs/<project>/4_outline_matrix.yaml`
- `outputs/<project>/4_argument_audit.md`

## 目标

- 形成三级论纲。
- 让每个最小论证节点都绑定真实 `piece_id`。

## 执行规则

- 先从 proposal 提炼中心论题、争点和章节方向。
- 再从 scholarship map 提炼必须回应的学术史节点与论断边界。
- 再按 `matched_theme` 和 `piece_id` 梳理 corpus，给每个小节分配证据。
- 只引用真实存在的 `piece_id`，不补造锚点。
- 优先让一个小节聚焦一个清晰论证，不要把证据堆成素材池。

## A刊导向协作指南

- 先搭建“总论题 -> 分论点 -> 子论证 -> 证据锚点”的推理结构，再安排章节标题。
- 每个章节都要回答一个不可跳过的子问题；如果删掉某章而全文不受影响，说明结构仍然松散。
- 每个 `sub_section_argument` 都应是可被反驳的判断，不要写成材料简介或常识结论。
- 论纲中应显性安排：
  - 学术史辨析节点。
  - 概念澄清节点。
  - 关键反论或替代解释的回应节点。
- 不要按“材料一章、材料二章、材料三章”来排目录；目录顺序应体现论证递进。

## 结构要求

- 顶层必须有 `thesis_statement`
- `chapters -> sections -> sub_sections`
- 每个 `sub_section` 至少包含：
  - `sub_section_title`
  - `sub_section_argument`
  - `evidence_anchors`

## 建议写法

- `thesis_statement` 应当是一句完整判断，而不是研究主题。
- 每章开头先写章目标，再下分节；每节之间要能看出推进关系。
- `sub_section_title` 尽量是判断式或问题式，不要只写名词短语。
- `evidence_anchors` 优先选择最能支撑本节核心主张的 1 到 3 个锚点，避免泛滥堆砌。
- 若同一 `piece_id` 被复用于多个小节，必须确保各节分析角度不同，否则说明结构分工有问题。
- 在完成论纲后，立即补写 `4_argument_audit.md`，不要把论证体检拖到初稿阶段。

## 质量检查

- 每个 `evidence_anchors` 至少有一个 `piece_id`。
- 同一条史料不要在多个不相干小节里机械复用。
- 论纲顺序能支撑论文推进，而不是主题拼盘。
- 仅看论纲就能看出本文准备如何回应既有研究，而不是只看出要讨论哪些材料。
- 每章标题与小节标题之间不存在“上位概念过大、下位论证过散”的断裂。
- `4_argument_audit.md` 已明确记录主要风险、潜在反驳和证据短板。
