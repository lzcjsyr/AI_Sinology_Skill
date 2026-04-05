# 阶段三C：学术史地图

## 输入

- `1_journal_targeting.md`
- `1_research_proposal.md`
- `2_primary_corpus.yaml`
- `3a_deepened_thinking.md`
- `outputs/<project>/_stage3b/candidate_papers.md`
- `outputs/<project>/_stage3b/papers/` 中人工补入的 PDF、题录导出与笔记

## 输出

- `outputs/<project>/3c_scholarship_map.md`

## 目标

- 在看过原始文献并完成 `3A` 后，再建立“学界怎么讨论这个问题”的结构化地图。
- 把学术史、争点、可继承路径与不宜越界的论断提前梳理清楚。
- 为阶段四论纲构建提供二手研究坐标，而不是直接产出 prose 式文献综述。
- `3C` 是纯本地写作步骤；联网检索、外部 API 调用与候选集扩展必须在 `3B` 完成。

## 进入 `3C` 的前提

- `3A` 已经落盘为 `3a_deepened_thinking.md`
- `3B` 已经完成若干轮筛选，而不是只有原始搜索结果
- 用户已经确认可以从 `3B` 进入 `3C`
- 候选集已相对稳定，能够看出主要研究路径与核心 works
- `outputs/<project>/_stage3b/candidate_papers.md` 已经整理完成
- `outputs/<project>/_stage3b/papers/` 中至少已有 1 份人工导入的论文、题录导出或笔记
- `3A` 已经明确写出本文当前准备验证和回应的问题
- 当前材料已经足以回答“本文准备回应谁、接续谁、修正谁”

## `3c_scholarship_map.md` 最小结构

```markdown
---
research_question: "本文准备回应的核心问题"
target_journals:
  - "..."
literature_scope_keywords:
  - "..."
period_hint: "近十年为主，可回溯经典文献"
gaps_to_address:
  - "..."
claim_boundaries:
  - "当前证据不宜支撑的强论断"
---

## Core Works

### Scholar A, Work A (2021, 论文)
- 核心观点：...
- 与本文关系：...

## Major Positions

### 路径A
- 核心主张：...
- 代表作品：...

## Debates

### 争点A
- 观点一：...
- 观点二：...

## Gaps To Address

- ...

## Usable Frames

- 可借用的问题框架或方法
```

## 执行规则

- `3C` 不可与 `3B` 连续自动执行，必须在用户确认后单独开始。
- `3C` 必须按以下顺序直接读取文件，再归纳 positions、debates 与 gaps：
  1. `1_journal_targeting.md`
  2. `1_research_proposal.md`
  3. `2_primary_corpus.yaml`
  4. `3a_deepened_thinking.md`
  5. `outputs/<project>/_stage3b/candidate_papers.md`
  6. `outputs/<project>/_stage3b/papers/` 中人工补入的 PDF、题录导出与笔记（核心信息来源！！！）
- 如果 `3a_deepened_thinking.md`、`candidate_papers.md` 或 `papers/` 中的人工补料缺失，就不能进入 `3C`。
- 如果用户尚未确认从 `3B` 进入 `3C`，也不能进入 `3C`。
- `3C` 不再发起联网搜索、网页补检或外部 API 调用；如材料覆盖不足，应退回 `3B` 补检，而不是在 `3C` 临时扩料。
- `3C` 的任务是基于现有本地资料归纳、比较和写作，不再新增候选 works，也不重新打开检索链路。
- front matter 必须保留，至少写出 `research_question`、`target_journals`、`literature_scope_keywords`、`gaps_to_address`、`claim_boundaries`。
- 正文必须使用固定章节：`## Core Works`、`## Major Positions`、`## Debates`、`## Gaps To Address`、`## Usable Frames`。
- `Core Works` 与 `Major Positions` 必须可回溯到具体作品，不允许抽象归纳后找不到来源。
- `claim_boundaries` 必须写，防止后面把“有限推进”写成“彻底改写”。
- 输出必须直接写成结构清晰的 Markdown，不要先产出自由 prose 草稿再等待额外脚本转换。
- `research_question`、`target_journals`、`literature_scope_keywords` 等字段应优先来自 agent 对输入文件的直接读取与归纳，而不是依赖脚本猜测。

## 人工校正点

- 用户可以补充“必须纳入的核心 works”
- 用户可以指出某些高频分支虽然相关，但不是本文要回应的主争点
- 用户可以提醒哪些作者或路径对目标刊物特别关键，应在 `major_positions` 或 `debates` 中优先体现

## 质量检查

- 读完地图后，能够回答“本文准备回应谁、接续谁、修正谁”。
- 能清楚看出至少 2 组主要争点，而不是一串并列摘要。
- 研究缺口与创新边界同时存在，不只有“可写什么”，也有“不能夸什么”。
