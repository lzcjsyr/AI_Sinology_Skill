# 阶段二：原始文献勘查与一手灵感

## 输入

- `1_journal_targeting.md`
- `1_research_proposal.md`
- 用户额外指定的文本群、目录或 scope

阶段二由 Skill 外部运行时执行。Skill 只关心前置文件是否齐备，以及外部运行时最终写回什么产物供后续阶段读取。

## 输出

- `outputs/<project>/2_primary_corpus.yaml`
- 推荐：`outputs/<project>/_stage2/manifest.json`
- 过程目录：`outputs/<project>/_stage2/`

## 目标

- 在已有初步想法后，先回到原始文献。
- 通过一手材料获得原始的思考和灵感，而不是先被二手研究框死。
- 为后续 `3A` 的深化思考准备可复核的材料总库。

## 执行规则

- 启动阶段二前，应先确认 `1_journal_targeting.md` 与 `1_research_proposal.md` 两个正式阶段一文件都已存在；缺一时先回补阶段一，而不是靠临时说明继续。
- 阶段二默认直接读取阶段一文件，不等待 scholarship map。
- 如果阶段一已经明确写出 `stage2_retrieval_themes`，外部运行时应优先把它作为检索主题来源。
- Skill 不在这里重述数据库、批量检索、provider 调度、checkpoint 或仲裁实现；这些都属于外部运行时职责。
- Skill 对阶段二的要求只有两点：一是产出 `2_primary_corpus.yaml`，二是让后续阶段能直接读出关键原始材料及其主题归属。

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
- `note`

后续阶段默认把它当作“可复核的一手材料总库”，而不是去理解外部运行时内部怎样得到这些记录。

## `_stage2/` 目录约定

- `manifest.json` 可作为外部运行时的补充说明保留。
- 其他日志、缓存或中间文件由外部运行时自行决定，Skill 不依赖其内部结构。

## 何时必须停下

- 阶段二还没有产出 `2_primary_corpus.yaml`，但用户要求直接进入阶段三或之后步骤
- 用户希望把数据库、检索链路或 provider 调度重新塞回 Skill
