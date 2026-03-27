# 阶段三B：检索扩展与候选清单整理

## 目标

- 在 `3A` 的深化思考基础上，整理出一份候选论文清单。
- 为 `3C` 准备可靠的题录、摘要与引用线索。

`3B` 不负责下载论文全文，也不负责替用户批量收集 PDF。论文下载由用户自行完成，之后放入 `outputs/<project>/_stage3b/papers/`。

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
  - 判断相关性
  - 维护 `candidate_papers.md`
  - 决定是否继续下一轮检索
  - 在 API 信息不足时，直接告诉用户当前覆盖不足

## 可用入口与实践顺序

可直接复用的脚本：

- `scripts/stage3b_sources.py`
  - 默认服务 `3B`
  - 默认将过程文件写到 `outputs/<project>/_stage3b/`

`3B` 默认按以下顺序推进：

1. 读取阶段一、阶段二与 `3A`，明确问题、对象、时段与概念轴线。
2. 先完成两个 API 入口的检查与检索。
3. 由 agent 拆出 3 到 8 组检索轴，而不是固定只打一条 query。
4. 中文主题下，优先调用 `stage3b_sources.py baidu-scholar` 做首轮发现与补漏。
5. 再调用 `stage3b_sources.py openalex` 做结构化检索与引用链扩展。
6. 对 agent 选中的 seed works 调用 `stage3b_sources.py openalex-expand --expand-mode references`。
7. 在 `outputs/<project>/_stage3b/candidate_papers.md` 中持续维护候选论文清单。
8. 如果两个 API 的结果仍不足，再由 agent 使用自身搜索/浏览能力补充检索。
9. 当候选集已经足够稳定时，先让用户按 `candidate_papers.md` 手动下载核心论文、题录导出或读书笔记，放入 `outputs/<project>/_stage3b/papers/`。
10. 只有 `papers/` 中已经有人工补入材料后，才进入 `3C`。

## 推荐过程文件

`outputs/<project>/_stage3b/` 推荐保留：

- `openalex-*.json`
- `baidu-scholar-*.json`
- `candidate_papers.md`
- `screening-notes.md`
- `papers/`

其中：

- `candidate_papers.md` 是 `3B` 的核心输出。
- `papers/` 用于存放用户后续自行下载并补入的 PDF、题录导出和读书笔记，不属于 agent 自动下载范围。

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
