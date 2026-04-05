# 阶段三B：检索扩展与候选清单整理

## 目标

- 在 `3A` 的深化思考基础上，整理出一份候选论文清单。
- 为 `3C` 准备可靠的题录、摘要与引用线索。
- `3B` 的交付到 `candidate_papers.md` 为止，不生成 `3c_scholarship_map.md`。

`3B` 不负责下载论文全文，也不负责替用户批量收集 PDF。论文下载由用户自行完成，之后放入 `outputs/<project>/_stage3b/papers/`。`3B` 结束后必须停下来，等待用户确认。

## `3B` 的职责边界

`3B` 不是纯抓取环节，`3B` 本身包含学术判断，但判断范围应收敛在“这篇文献要不要进入候选清单”。

默认分工：

- 脚本负责：
  - 调 API
  - 归一化字段
  - 把过程结果写到 `outputs/<project>/_stage3b/`
- agent 负责：
  - 读取阶段一、阶段二与 `3A`
  - 拆检索轴
  - 用中、英、日三语改写关键词并组织多轮检索
  - 判断相关性
  - 维护 `candidate_papers.md`
  - 决定是否继续下一轮检索
  - 在 API 信息不足时，直接告诉用户当前覆盖不足

## 外部 API 入口

`3B` 是阶段三中唯一允许集中使用外部 API 与联网检索的环节。当前默认入口如下：

- `openalex`
  - 作用：结构化题录查询、作者/机构/年份过滤、英文或跨语种 works 扩展。
  - 适用：需要稳定元数据、DOI、引用关系或跨语种补充时。
- `openalex-expand --expand-mode references`
  - 作用：围绕已选中的 seed works 顺着参考文献表继续扩展。
  - 适用：候选集中已经出现高相关核心 works，准备沿引用链追溯时。

外部 API 在 `3B` 的职责只有三类：

- 发现候选 works
- 补充题录、摘要和引用链
- 为 `candidate_papers.md` 提供可筛选的原始线索

外部 API 不负责：

- 替代 agent 做最终学术判断
- 直接生成 `3C` 的 scholarship map
- 下载全文或代替用户补全 `papers/`

## 多语多轮检索要求

- `3B` 不能只搜一轮，也不能只打一条 query 就结束。
- agent 必须至少使用中文、英文、日文三组关键词进行多轮检索，再汇总候选集。
- 每一轮都应围绕不同检索轴改写关键词，例如：
  - 研究对象
  - 核心概念
  - 时段与朝代
  - 文本、作者或注疏系统
  - 争点或方法词
- 同一检索轴也应做多语改写，而不是只做直译。目标是让不同学术语境下的 works 都有机会被发现。
- 当某一语种命中明显偏弱时，应继续改写该语种关键词，而不是直接放弃该语种。
- `screening-notes.md` 应简要记录每轮使用了哪些中、英、日关键词，以及这一轮新增了哪些高相关 works、排除了哪些噪音。

## 可用入口与实践顺序

可直接复用的脚本：

- `scripts/stage3b_sources.py`
  - 默认服务 `3B`
  - 默认将过程文件写到 `outputs/<project>/_stage3b/`

`3B` 默认按以下顺序推进：

1. 读取阶段一、阶段二与 `3A`，明确问题、对象、时段与概念轴线。
2. 先完成 OpenAlex 入口的检查与首轮检索。
3. 由 agent 拆出 3 到 8 组检索轴，而不是固定只打一条 query。
4. 围绕每组检索轴，分别准备中文、英文、日文关键词，至少做一轮多语检索。
5. 调用 `stage3b_sources.py openalex` 做结构化检索，并记录每轮 query 与主要命中。
6. 对 agent 选中的 seed works 调用 `stage3b_sources.py openalex-expand --expand-mode references`。
7. 在 `outputs/<project>/_stage3b/candidate_papers.md` 中持续维护候选论文清单。
8. 多轮 OpenAlex 检索和引用链扩展后，再由 agent 使用自身搜索/浏览能力补充检索。注意，返回的信息必须符合学术作品引用的要求，不能网络文章。
9. 当候合适的核心论文数量超过30篇，或已经经过多轮、多语搜索并无额外收益时，先停下来，把 `candidate_papers.md` 交给用户确认。
10. 用户确认后，再让用户按 `candidate_papers.md` 手动下载核心论文、题录导出或读书笔记，放入 `outputs/<project>/_stage3b/papers/`。
11. 只有 `papers/` 中已经有人工补入材料后，才进入 `3C`。

## 推荐过程文件

`outputs/<project>/_stage3b/` 推荐保留：

- `openalex-*.json`
- `candidate_papers.md`
- `screening-notes.md`
- `papers/`

其中：

- `candidate_papers.md` 是 `3B` 的核心输出。
- `papers/` 用于存放用户后续自行下载并补入的 PDF、题录导出和读书笔记，不属于 agent 自动下载范围。
- `3C` 启动时可将 `_stage3b/papers/` 中 PDF 转为 **`outputs/<project>/_stage3c/papers_md/`**（MinerU，默认 `vlm`）；`3B` 只需把核心 PDF 放入 `papers/`。
- `openalex-*.json` 是 `3B` 的检索过程记录，供后续人工复核和 `3C` 本地写作时回看，但 `3C` 不再继续调用 API。

## 人工干预点

- 用户负责下载论文，并把文件放入 `outputs/<project>/_stage3b/papers/`
- agent 不负责代替用户下载全文
- 进入 `3C` 前，`papers/` 里至少应有 1 份人工导入的论文、题录导出或笔记
- 如果来源不足，agent 直接说明不足，而不是展开额外补料流程

## `3B` 完成标志

- 已经形成一份相对稳定的候选论文清单
- 候选集中已有若干核心 works，而不只是零散线索
- 当前题录、摘要与引用线索已足以支撑后续 scholarship map 整理
- 当前没有明显必要继续扩大检索
- 已经可以据 `candidate_papers.md` 指导用户向 `papers/` 补入核心论文与笔记，供 `3C` 读取
- 此时停止，等待用户确认，不直接进入 `3C`
