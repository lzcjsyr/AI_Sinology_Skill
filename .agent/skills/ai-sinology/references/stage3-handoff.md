# 阶段三交接协议

## 定位

- 阶段三的一手史料数据库、检索执行器、批量 API 调用和长流程编排留在 Skill 外部。
- Skill 只负责：
  - 提供阶段二生成的 `stage3_handoff`
  - 提供阶段一生成的目标刊物校准信息作为背景参考
  - 约束阶段三最终写回的文件契约
  - 在阶段四以后消费 `3_final_corpus.yaml`

## 外部执行器必须理解的输入

- 项目目录：`outputs/<project>/`
- 阶段二 scholarship map：`outputs/<project>/2b_scholarship_map.yaml`
- 阶段一目标刊物校准：`outputs/<project>/1_journal_targeting.md`
- 阶段一 proposal：`outputs/<project>/1_research_proposal.md`
- 检索主题：优先读取 scholarship map 中的 `stage3_handoff.target_themes`
- 可选配置：`outputs/<project>/3_stage3_manifest.json`

`stage3_handoff` 的最低机器输入是：

- `target_themes`

如果需要，阶段二还可以继续补充检索重点、材料类型提示与排除项；但这些都属于可选增强，不是最小契约。

## 外部执行器必须写回的输出

- 必选：`outputs/<project>/3_final_corpus.yaml`
- 推荐：`outputs/<project>/3_stage3_manifest.json`
- 过程文件统一写入：`outputs/<project>/_stage3/`

## `3_final_corpus.yaml` 最小字段

- `piece_id`
- `source_file`
- `matched_theme`
- `original_text`

Skill 在阶段四、五、六真正依赖的只有这四个字段。

## `_stage3/` 工作目录建议内容

- `session.json`
- `manifest.json`
- 外部执行器自己产生的中间结果、日志或缓存

`session.json` 至少应保留并持续更新以下断点字段：

- `analysis_targets`
- `retrieval_progress.status`
- `retrieval_progress.completed_targets`
- `retrieval_progress.pending_targets`
- `retrieval_progress.current_target`
- `retrieval_progress.current_cursor`
- `retrieval_progress.last_piece_id`
- `retrieval_progress.completed_piece_count`

如果阶段三被拆成多次运行，外部执行器下一次进入项目时应优先读取这些字段决定续跑位置，而不是重新从第一个目标开始。

## 何时必须停下

- 外部阶段三还没有产出 `3_final_corpus.yaml`，但用户要求直接进入阶段四或之后步骤
- 用户希望把数据库、检索链路或 provider 调度重新塞回 Skill
