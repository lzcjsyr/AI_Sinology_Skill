# 阶段二：学术史地图

## 输入

- `1_journal_targeting.md`
- `1_research_proposal.md`
- 用户提供的参考文献、题录、PDF 或书目
- 必要时的联网检索结果

## 输出

- `outputs/<project>/2_scholarship_map.yaml`

## 目标

- 单独建立“学界怎么讨论这个问题”的结构化地图。
- 把学术史、争点、可继承路径与不宜越界的论断提前梳理清楚。
- 为阶段四论纲构建提供二手研究坐标，而不是直接产出 prose 式文献综述。

## 为什么必须独立成阶段

- 阶段二的学术史地图解决的是“学界已经怎么解释这些问题”。
- 阶段三的一手史料总库解决的是“有什么材料可用”。
- 两者的数据源、筛选标准和分析动作不同，混在一个文件里会导致：
  - 一手材料与二手研究层级混乱。
  - 学术史部分沦为附会式拼接。
  - 创新判断缺乏稳定边界。

## `2_scholarship_map.yaml` 最小结构

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
      - label: "观点B"
        claim: "..."
gaps_to_address:
  - "..."
usable_frames:
  - "可借用的问题框架或方法"
claim_boundaries:
  - "当前证据不宜支撑的强论断"
```

## 执行规则

- 优先围绕研究问题、对象、时段、概念去检索，不要只围绕大词检索。
- 优先提炼“研究路径”和“争点轴线”，而不是罗列文献名单。
- 要区分：
  - 经典奠基性研究
  - 近年代表性论文
  - 与本文直接对话的核心作品
- `core_works` 与 `major_positions` 必须可回溯到具体作品，不允许抽象归纳后找不到来源。
- `claim_boundaries` 必须写，防止后面把“有限推进”写成“彻底改写”。
- 如果目标刊物有明显风格偏好，应在 `target_journals` 和 `usable_frames` 中体现。

## 质量检查

- 读完地图后，能够回答“本文准备回应谁、接续谁、修正谁”。
- 能清楚看出至少 2 组主要争点，而不是一串并列摘要。
- 研究缺口与创新边界同时存在，不只有“可写什么”，也有“不能夸什么”。
