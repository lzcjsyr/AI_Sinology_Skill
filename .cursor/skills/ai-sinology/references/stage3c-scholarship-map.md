# 阶段三C：学术史地图

## 输入

- `1_journal_targeting.md`
- `1_research_proposal.md`
- `2_primary_corpus.yaml`
- `3a_deepened_thinking.md`
- `outputs/<project>/_stage3b/candidate_papers.md`
- `outputs/<project>/_stage3c/papers_md/` 中由 MinerU（默认 **`vlm`**）从 PDF 转换得到的 `*_mineru.md`（与 `_stage3b/papers/` 一一对应；**二手全文阅读主入口**）
- `outputs/<project>/_stage3b/papers/` 中人工补入的 PDF（归档与核对原件）、题录导出与笔记（非 PDF 不必转换）

## 输出

- `outputs/<project>/3c_scholarship_map.md`

## 目标

- 在看过原始文献并完成 `3A` 后，再建立“学界怎么讨论这个问题”的结构化地图。
- 把学术史、争点、可继承路径与不宜越界的论断提前梳理清楚。
- 为阶段四论纲构建提供二手研究坐标，而不是直接产出 prose 式文献综述。
- `3C` 是纯本地写作步骤；联网检索、外部 API 调用与候选集扩展必须在 `3B` 完成。

## 每次启动 `3C` 时先做：PDF → Markdown 检查（MinerU）

在进入本节「进入 `3C` 的前提」与后文写作步骤之前，**先**完成全文可读化检查：

1. **范围**：仅针对 `outputs/<project>/_stage3b/papers/` 下所有 `*.pdf`（含子目录）。题录、笔记等非 PDF 不参与本步骤。
2. **期望落盘位置**：`outputs/<project>/_stage3c/papers_md/`，与 `papers/` 内相对路径一致，文件名为 `{原名}_mineru.md`。  
   - 例：`papers/foo/bar.pdf` → `_stage3c/papers_md/foo/bar_mineru.md`。
3. **检查方式**：对每个 PDF，若对应的 `_stage3c/papers_md/.../*_mineru.md` 不存在或为 0 字节，则视为**未就绪**。
4. **未就绪时**：先调用 MinerU 转换，再进入 `3C` 正文。默认使用 **`vlm`**（与仓库根目录 `test_mineru_v4_batch.py` 一致的 v4 批量上传流程）。项目内封装脚本为：
   - `uv run python .cursor/skills/ai-sinology/scripts/stage3c_mineru_pdfs.py <project>`（在**仓库根目录**执行；默认合并根目录 `.env` 与 **`.cursor/skills/ai-sinology/.env`**，同名键以后者为准）
   - 在根目录 `.env` 和/或 **技能目录** `.cursor/skills/ai-sinology/.env` 中配置 **`MINERU_API_TOKEN`** 或 **`MINERU_TOKEN`**（均可只放技能目录；已 `.gitignore`，勿提交）；可选 `MINERU_MODEL_VERSION=vlm`（默认即 `vlm`）、`MINERU_POLL_TIMEOUT_SEC`（单文件轮询超时，默认 `600`）。也可用 `--env-file` 指定单一文件。
   - 仅检查不调用 API：`... stage3c_mineru_pdfs.py <project> --dry-run`
   - 已存在仍重转：`... --force`
5. **依赖**：系统需可用 `curl`（用于 PUT 预签名 URL）。
6. **全部就绪后**，再执行下文「进入 `3C` 的前提」与「执行规则」中的阅读与写作顺序。

说明：`3C` 不联网扩料；本步骤仅把 **本地已有 PDF** 转为 Markdown。

## 进入 `3C` 的前提

- `3A` 已经落盘为 `3a_deepened_thinking.md`
- `3B` 已经完成若干轮筛选，而不是只有原始搜索结果
- 用户已经确认可以从 `3B` 进入 `3C`
- 候选集已相对稳定，能够看出主要研究路径与核心 works
- `outputs/<project>/_stage3b/candidate_papers.md` 已经整理完成
- `outputs/<project>/_stage3b/papers/` 中至少已有 1 份人工导入的论文、题录导出或笔记
- 对 `_stage3b/papers/` 中每一份 PDF，已通过上节检查，在 **`_stage3c/papers_md/`** 中具备对应的 `*_mineru.md`（若无 PDF 仅题录/笔记，则无需本项）
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
- **每次启动 `3C` 时**，须先完成上文「每次启动 `3C` 时先做：PDF → Markdown 检查（MinerU）」，再进入本列表。
- `3C` 必须按以下顺序直接读取文件，再归纳 positions、debates 与 gaps：
  1. `1_journal_targeting.md`
  2. `1_research_proposal.md`
  3. `2_primary_corpus.yaml`
  4. `3a_deepened_thinking.md`
  5. `outputs/<project>/_stage3b/candidate_papers.md`
  6. `outputs/<project>/_stage3c/papers_md/` 中与各 PDF 对应的 `*_mineru.md`（二手论文正文阅读的主材料）
  7. `outputs/<project>/_stage3b/papers/` 中的题录导出、笔记，以及需要核对版式或扫描件时对照的 PDF（核心信息来源！！！）
- 如果 `3a_deepened_thinking.md`、`candidate_papers.md` 或 `papers/` 中的人工补料缺失，或 `papers/` 中有 PDF 但未完成对应的 `_stage3c/papers_md/*_mineru.md`，就不能进入 `3C` 正文写作。
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
