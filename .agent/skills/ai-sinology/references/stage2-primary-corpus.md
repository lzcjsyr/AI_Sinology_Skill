# 阶段二：原始文献勘查与一手灵感

## 输入

- `1_journal_targeting.md`
- `1_research_proposal.md`
- 用户额外指定的文本群、目录或 scope

阶段二运行时优先读取 `stage2_retrieval_themes`。该字段通常来自 `1_research_proposal.md` / `1_journal_targeting.md` 的 YAML front matter；没有该字段时，才退回到 `settled_research_direction` 与 `idea` 的兜底推断。

## 输出

- `outputs/<project>/2_primary_corpus.yaml`
- 推荐：`outputs/<project>/_stage2/2_stage2_manifest.json`
- 过程目录：`outputs/<project>/_stage2/`

## 目标

- 在已有初步想法后，先回到原始文献。
- 通过一手材料获得原始的思考和灵感，而不是先被二手研究框死。
- 为后续 `3A` 的深化思考准备可复核的材料总库。

## 执行规则

- 启动阶段二前，应先确认 `1_journal_targeting.md` 与 `1_research_proposal.md` 两个正式阶段一文件都已存在；缺一时先回补阶段一，而不是靠临时说明继续。
- 阶段二默认直接读取阶段一文件，不等待 scholarship map。
- 如果阶段一已经明确写出 `stage2_retrieval_themes`，阶段二应把它当作首要检索主题来源，而不是自行改写成另一套抽象主题。
- 阶段二只负责原始文献总库与过程断点，不在 Skill 内重建数据库、批量检索或真实执行器。
- 外部运行时应把过程文件统一写入 `outputs/<project>/_stage2/`，便于中断后续跑。
- 如需手动缩小文本范围，可在运行时直接指定 scope 或 repo，不必先补写额外 handoff。
- 阶段二结束时，应能明确读出：当前抓到哪些关键原始材料、它们各自对应什么主题。

## `2_primary_corpus.yaml` 最小结构

```yaml
piece_count: 2
records:
  - piece_id: "pb:KR3j0001_001-1a"
    source_file: "某书名"
    matched_theme: "祈雨"
    original_text: |
      原始史料正文
    note: "可选，记录该条材料为何值得后续分析"
```

Skill 真正依赖的字段只有：

- `piece_id`
- `source_file`
- `matched_theme`
- `original_text`

## `_stage2/` 工作目录建议内容

- `session.json`
- `2_stage2_manifest.json`
- 外部执行器自己产生的中间结果、日志或缓存

`session.json` 至少应持续更新：

- `analysis_targets`
- `retrieval_progress.completed_targets`
- `retrieval_progress.pending_targets`
- `retrieval_progress.current_target`
- `retrieval_progress.current_cursor`
- `retrieval_progress.last_piece_id`
- `retrieval_progress.completed_piece_count`

## 何时必须停下

- 阶段二还没有产出 `2_primary_corpus.yaml`，但用户要求直接进入阶段三或之后步骤
- 用户希望把数据库、检索链路或 provider 调度重新塞回 Skill
