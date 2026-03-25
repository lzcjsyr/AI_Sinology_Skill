# 阶段二B：学术史地图

## 输入

- `1_journal_targeting.md`
- `1_research_proposal.md`
- `2A` 已收束的候选作品集与筛选记录
- 用户提供的参考文献、题录、PDF、DOI / URL 列表或书目
- 如需选择数据来源与环境变量，进一步参见 `references/stage2a-data-intake.md`
- 如需稳定复用开放来源抓取，优先调用 `scripts/stage2a_sources.py` 与 `scripts/stage2b_scholarship_map.py`

## 输出

- `outputs/<project>/2b_scholarship_map.yaml`

## 目标

- 单独建立“学界怎么讨论这个问题”的结构化地图。
- 把学术史、争点、可继承路径与不宜越界的论断提前梳理清楚。
- 为阶段四论纲构建提供二手研究坐标，而不是直接产出 prose 式文献综述。

## 进入 `2B` 的前提

`2B` 不应在“刚抓到第一批结果”时启动。进入 `2B` 前，至少应满足：

- `2A` 已经完成若干轮筛选，而不是只有原始搜索结果
- 候选集已相对稳定，能够看出主要研究路径与核心 works
- 明显的来源缺口已经补过，或已确认暂时无法补齐
- 当前材料已经足以回答“本文准备回应谁、接续谁、修正谁”

## 为什么必须独立成阶段

- 阶段二的学术史地图解决的是“学界已经怎么解释这些问题”。
- 阶段三的一手史料总库解决的是“有什么材料可用”。
- 两者的数据源、筛选标准和分析动作不同，混在一个文件里会导致：
  - 一手材料与二手研究层级混乱。
  - 学术史部分沦为附会式拼接。
  - 创新判断缺乏稳定边界。

## `2b_scholarship_map.yaml` 最小结构

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

- 数据入口默认按以下优先级处理：
  - 开放 API：`OpenAlex`、`Crossref`、`DOAJ`
  - 用户导出的题录文件：`RIS`、`BibTeX`、`CSV`
  - 本地 PDF、DOI 列表、文章 URL 列表与人工笔记
- 如果需要重复执行开放 API 检索，优先把归一化结果写到 `outputs/<project>/_stage2a/`，并把 `manual-intake.md`、`screening-notes.md` 一并视为 `2B` 的输入。
- 如果阶段一已经形成明确研究方向，agent 应基于 `settled_research_direction`、`idea`、`target_themes` 和 proposal 正文自行拆出多组检索轴，而不是只打一条关键词。
- 优先让 agent 根据当前任务上下文决定检索轮次和 query，而不是把“理解研究方向”硬编码成固定脚本；但这部分工作应尽量在 `2A` 完成，而不是拖到 `2B` 才做。
- 如果以 `OpenAlex` 为主入口，默认流程应是：先关键词检索，再由 agent 选出值得继续追踪的 works，然后调用 `openalex-expand` 抓取这些 works 引用的文献。
- `openalex-expand` 只负责一跳引用抓取，不负责判断相关性；哪些结果保留、哪些结果进入下一轮、何时停轮，应由 agent 决定。这些属于 `2A` 的判断前提。
- 优先围绕研究问题、对象、时段、概念去检索，不要只围绕大词检索。
- 进入 `2B` 后，优先提炼“研究路径”和“争点轴线”，而不是继续无边界扩搜或罗列文献名单。
- 不把登录态数据库网页抓取当作默认方案；`CNKI`、`CSSCI`、`JSTOR`、`Project MUSE`、`Airiti`、`CiNii Research`、`J-STAGE` 默认按“先导出、后导入”的模式处理。
- 要区分：
  - 经典奠基性研究
  - 近年代表性论文
  - 与本文直接对话的核心作品
- `core_works` 与 `major_positions` 必须可回溯到具体作品，不允许抽象归纳后找不到来源。
- `claim_boundaries` 必须写，防止后面把“有限推进”写成“彻底改写”。
- 如果目标刊物有明显风格偏好，应在 `target_journals` 和 `usable_frames` 中体现。
- 阶段二通常应收束到约 30 篇高相关依据文献，但这个数量是 agent 的工作目标，不是脚本自动裁剪的阈值。

## 人工校正点

进入 `2B` 后，仍然保留一个轻量的人工校正点：

- 用户可以补充“必须纳入的核心 works”
- 用户可以指出某些高频分支虽然相关，但不是本文要回应的主争点
- 用户可以提醒哪些作者或路径对目标刊物特别关键，应在 `major_positions` 或 `debates` 中优先体现

## 质量检查

- 读完地图后，能够回答“本文准备回应谁、接续谁、修正谁”。
- 能清楚看出至少 2 组主要争点，而不是一串并列摘要。
- 研究缺口与创新边界同时存在，不只有“可写什么”，也有“不能夸什么”。
