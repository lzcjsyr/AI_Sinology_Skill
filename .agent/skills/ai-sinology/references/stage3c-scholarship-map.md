# 阶段三C：学术史地图

## 输入

- `1_journal_targeting.md`
- `1_research_proposal.md`
- `2_primary_corpus.yaml`
- `3a_deepened_thinking.md`
- `outputs/<project>/_stage3b/candidate_papers.md`
- `outputs/<project>/_stage3b/papers/` 中人工补入的 PDF、题录导出与笔记
- 用户提供的参考文献、题录、PDF、DOI / URL 列表或书目
- 如需选择数据来源与环境变量，进一步参见 `references/stage3b-data-intake.md`
- 如需稳定复用开放来源抓取，优先调用 `scripts/stage3b_sources.py`

## 输出

- `outputs/<project>/3c_scholarship_map.yaml`

## 目标

- 在看过原始文献并完成 `3A` 后，再建立“学界怎么讨论这个问题”的结构化地图。
- 把学术史、争点、可继承路径与不宜越界的论断提前梳理清楚。
- 为阶段四论纲构建提供二手研究坐标，而不是直接产出 prose 式文献综述。

## 进入 `3C` 的前提

- `3A` 已经落盘为 `3a_deepened_thinking.md`
- `3B` 已经完成若干轮筛选，而不是只有原始搜索结果
- 候选集已相对稳定，能够看出主要研究路径与核心 works
- `outputs/<project>/_stage3b/candidate_papers.md` 已经整理完成
- `outputs/<project>/_stage3b/papers/` 中至少已有 1 份人工导入的论文、题录导出或笔记
- `3A` 已经明确写出本文当前准备验证和回应的问题
- 当前材料已经足以回答“本文准备回应谁、接续谁、修正谁”

## `3c_scholarship_map.yaml` 最小结构

```yaml
research_question: "..."
target_journals:
  - "..."
literature_scope:
  keywords:
    - "..."
  period_hint: "近十年为主，可回溯经典文献"
core_works:
  - scholar: "..."
    work: "..."
    year: 2021
    type: "论文"
    claim: "核心观点"
    relevance: "与本文关系"
major_positions:
  - label: "路径A"
    claims:
      - "..."
    representative_works:
      - "..."
debates:
  - issue: "争点"
    positions:
      - label: "观点A"
        claim: "..."
gaps_to_address:
  - "..."
usable_frames:
  - "可借用的问题框架或方法"
claim_boundaries:
  - "当前证据不宜支撑的强论断"
```

## 执行规则

- `3C` 默认由 agent 直接完成，不再依赖单独的写作脚本。
- `3C` 必须按以下顺序直接读取文件，再归纳 positions、debates 与 gaps：
  1. `1_journal_targeting.md`
  2. `1_research_proposal.md`
  3. `2_primary_corpus.yaml`
  4. `3a_deepened_thinking.md`
  5. `outputs/<project>/_stage3b/candidate_papers.md`
  6. `outputs/<project>/_stage3b/papers/` 中人工补入的 PDF、题录导出与笔记
- 如果 `3a_deepened_thinking.md`、`candidate_papers.md` 或 `papers/` 中的人工补料缺失，就不能进入 `3C`。
- 如果研究对象以中文论文为主，默认应先让 `百度学术` 承担中文发现与摘要补强，再由 agent 把高质量 seed 映射到 `OpenAlex`，调用 `openalex-expand --expand-mode references` 沿参考文献表扩展。
- 如果开放来源覆盖不足，优先追加新一轮 query 改写与补检，而不是提前进入 `3C` 用稀薄候选集硬写地图。
- 优先围绕研究问题、对象、时段、概念去检索，不要只围绕大词检索。
- `core_works` 与 `major_positions` 必须可回溯到具体作品，不允许抽象归纳后找不到来源。
- `claim_boundaries` 必须写，防止后面把“有限推进”写成“彻底改写”。
- 输出必须直接写成 `3c_scholarship_map.yaml` 的固定 YAML 结构，不要先产出 prose 式草稿再等待额外脚本转换。
- `research_question`、`target_journals`、`literature_scope.keywords` 等字段应优先来自 agent 对输入文件的直接读取与归纳，而不是依赖脚本猜测。

## 人工校正点

- 用户可以补充“必须纳入的核心 works”
- 用户可以指出某些高频分支虽然相关，但不是本文要回应的主争点
- 用户可以提醒哪些作者或路径对目标刊物特别关键，应在 `major_positions` 或 `debates` 中优先体现

## 质量检查

- 读完地图后，能够回答“本文准备回应谁、接续谁、修正谁”。
- 能清楚看出至少 2 组主要争点，而不是一串并列摘要。
- 研究缺口与创新边界同时存在，不只有“可写什么”，也有“不能夸什么”。
