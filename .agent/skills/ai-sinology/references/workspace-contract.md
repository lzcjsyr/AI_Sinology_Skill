# 工作区文件契约

机器可读真相源位于 `../assets/workspace-contract.json`。
本文件负责给 Skill 提供人类可读解释；若契约变更，先改 JSON，再同步这里。

## 项目目录

所有项目都放在当前工作目录的 `outputs/<project>/` 下。

新建项目时，除 `project_progress.yaml` 外，还应预建：`outputs/<project>/_stage2/` 与 `outputs/<project>/_stage3b/papers/`。

## 项目级进度文件

每个项目都应有：`outputs/<project>/project_progress.yaml`

新建项目时要先创建这个文件，再写阶段文件。

建议最小结构：

```yaml
project_name: "demo"
workspace_root: "/abs/path/to/current/workdir"
project_root: "/abs/path/to/current/workdir/outputs/demo"
current_stage: 1
current_stage_name: "选刊校准与选题构思"
completed_stages: []
available_files: []
next_action: "完成阶段1必选文件: 1_journal_targeting.md、1_research_proposal.md"
last_updated: "2026-03-19T10:00:00+08:00"
notes: "可选，记录人工决策或阻塞点"
```

Skill 在每次推进阶段后都应同步更新这个文件。

## 阶段文件

### 阶段一

- 文件：`1_journal_targeting.md`
- 文件：`1_research_proposal.md`
- 两个文件都视为阶段一必选产物。
- 阶段一完成时，应能明确读出两个结论：经过讨论后确定的研究方向、准备投稿的目标期刊。
- `1_journal_targeting.md` 用于记录目标刊物、风格校准、篇幅体例、期刊定位、写作建议与风险约束。
- 必须包含 YAML front matter。
- front matter 至少包含：
  - `idea`
- 建议同时包含：
  - `target_journal`
  - `settled_research_direction`
  - `stage2_retrieval_themes`
- 如果用户起初没有说明投稿目标，Skill 应先追问；如果目标期刊不在内置单刊 reference 内，Skill 应优先要求用户提供期刊网页并据此提炼要求，只有网页拿不到时才补问期刊级别、文章样式、篇幅与体例等信息。
- `stage2_retrieval_themes` 推荐写成 YAML 列表，给出 2 到 5 个可直接供阶段二执行的检索主题。

### 阶段二

- 文件：`2_primary_corpus.yaml`
- 启动阶段二前，应先确认 `1_journal_targeting.md` 与 `1_research_proposal.md` 两个阶段一正式文件都已生成。
- 阶段二只负责原始文献勘查与一手灵感积累，不与二手学术史混写。
- 阶段二默认直接读取阶段一文件，优先读取 `stage2_retrieval_themes`，没有时才回退到研究方向与 idea 的兜底推断；不等待后置 scholarship map。
- 由 Skill 外部运行时生成；Skill 只约束写回契约。
- 推荐同时提供：`outputs/<project>/_stage2/2_stage2_manifest.json`
- 推荐同时保留：`outputs/<project>/_stage2/session.json`

`2_primary_corpus.yaml` 的最小结构：

```yaml
piece_count: 2
records:
  - piece_id: "pb:KR3j0001_001-1a"
    source_file: "某书名"
    matched_theme: "祈雨"
    original_text: |
      原始史料正文
    note: "可选，外部阶段二写入的简短说明"
```

其中真正关键的是：

- `piece_id`
- `source_file`
- `matched_theme`
- `original_text`

### 阶段三

- 阶段三拆成 `3A`、`3B`、`3C` 三段。
- `3A` 文件：`3a_deepened_thinking.md`
- `3B` 过程目录：`outputs/<project>/_stage3b/`
- `3C` 文件：`3c_scholarship_map.yaml`
- 阶段三要被判定为完成，至少还必须具备：
  - `outputs/<project>/_stage3b/candidate_papers.md`
  - `outputs/<project>/_stage3b/papers/`，且目录内至少有 1 份人工导入的论文、题录导出或笔记
- `3B` 推荐额外保留：
  - `openalex-*.json`
  - `baidu-scholar-*.json`
  - `screening-notes.md`
- 上述 `_stage3b/` 文件都属于过程产物，不替代正式阶段文件。
- `3A` 应先基于阶段一与阶段二原始文献，提炼出更深的问题意识、暂定判断和后续验证重点。
- `3B` 负责二手研究的检索扩展与候选集收敛。
- `3C` 必须读取 `3A` 的思考结果、`candidate_papers.md`，以及 `papers/` 中人工导入的论文/题录/笔记，再生成结构化 scholarship map。

`3c_scholarship_map.yaml` 的最小结构：

```yaml
research_question: "..."
target_journals:
  - "..."
core_works:
  - scholar: "..."
    work: "..."
    claim: "..."
major_positions:
  - label: "路径A"
    claims:
      - "..."
debates:
  - issue: "..."
    positions:
      - label: "观点A"
        claim: "..."
gaps_to_address:
  - "..."
usable_frames:
  - "..."
claim_boundaries:
  - "..."
```

Skill 端真正依赖的字段只有：

- `core_works`
- `major_positions`
- `debates`
- `gaps_to_address`
- `claim_boundaries`

### 阶段四

- 文件：`4_outline_matrix.yaml`
- 文件：`4_argument_audit.md`
- 两个文件都视为阶段四必选产物。
- 最小结构：

```yaml
thesis_statement: "..."
chapters:
  - chapter_title: "..."
    chapter_goal: "..."
    sections:
      - section_title: "..."
        section_goal: "..."
        sub_sections:
          - sub_section_title: "..."
            sub_section_argument: "..."
            evidence_anchors:
              - "pb:KR3j0001_001-1a"
```

`evidence_anchors` 只能引用阶段二 corpus 中真实存在的 `piece_id`。

`4_argument_audit.md` 至少应覆盖：

- 中心论题一句话版本
- 分论点链条是否闭合
- 主要潜在反驳
- 证据短板
- 创新边界与不宜过度宣称之处

### 阶段五

- 文件：`5_first_draft.md`
- 每个小节必须显式保留证据锚点。
- 推荐写法是在小节结尾保留一行：

```text
证据锚点：`pb:...`, `pb:...`
```

### 阶段六

- 必选文件之一：
  - `6_final_manuscript.md`
  - `6_final_manuscript.docx`
- 还应同时具备：
  - `6_abstract_keywords.md`
  - `6_title_options.md`
  - `6_anonymous_submission_checklist.md`
  - `6_claim_boundary.md`
- 推荐附带：
  - `6_revision_checklist.md`

默认以 Markdown 终稿为准；如果生成 `.docx`，也不要丢掉 `piece_id` 追溯信息。
