# 工作区文件契约

机器可读真相源位于 `../assets/workspace-contract.json`。
本文件负责给 Skill 提供人类可读解释；若契约变更，先改 JSON，再同步这里。

## 项目目录

所有项目都放在当前工作目录的 `outputs/<project>/` 下。

新建项目时，除 `project_progress.yaml` 外，还应预建：`outputs/<project>/_stage2a/papers/`。

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
- 如果用户起初没有说明投稿目标，Skill 应先追问；如果目标期刊不在内置单刊 reference 内，Skill 应优先要求用户提供期刊网页并据此提炼要求，只有网页拿不到时才补问期刊级别、文章样式、篇幅与体例等信息。

### 阶段二

- 文件：`2b_scholarship_map.yaml`
- 这是独立于阶段三一手史料总库的学术史研究产物，不应与史料总库混写。
- 可以由 Skill 结合用户提供书目、PDF、题录和联网检索生成。
- 阶段二虽然只有一个正式阶段文件，但执行上默认拆成 `2A` 与 `2B`：
  - `2A`：检索扩展与候选集收敛
  - `2B`：学术史地图写作
- 若使用 Skill 自带的开放来源脚本，推荐将过程文件保存在 `outputs/<project>/_stage2a/`。
- `outputs/<project>/_stage2a/` 推荐包含：
  - `openalex-*.json`
  - `candidate_papers.md`
  - `screening-notes.md`
  - `papers/`
- 上述 `_stage2a/` 文件都属于过程产物，不替代正式阶段文件。
- `candidate_papers.md` 用于沉淀自动化调研与网页补检后保留的候选论文清单。
- `papers/` 用于存放 `2A` 后人工补入的 PDF、题录导出和读书笔记；`2B` 默认应把这里视为主要依据之一。
- `2B` 应在 `2A` 的候选集相对稳定后再开始；如果来源覆盖不足，需要先停在 `2A` 等待用户补充资料。
- `2b_scholarship_map.yaml` 同时承担阶段三正式交接；阶段三默认直接读取其中的 `stage3_handoff`。

`2b_scholarship_map.yaml` 的最小结构：

```yaml
research_question: "..."
target_journals:
  - "..."
major_positions:
  - scholar: "..."
    work: "..."
    claim: "..."
debates:
  - issue: "..."
    positions:
      - "..."
gaps_to_address:
  - "..."
claim_boundaries:
  - "..."
stage3_handoff:
  target_themes:
    - theme: "..."
      description: "..."
```

其中真正关键的是：

- `major_positions`
- `debates`
- `gaps_to_address`
- `claim_boundaries`
- `stage3_handoff.target_themes`

### 阶段三

- 阶段三开始时，应先选择 `outputs/<project>/` 下的目标项目。
- 随后应创建阶段三工作目录：`outputs/<project>/_stage3/`
- 阶段三过程文件应默认写入该目录，以便中断后继续。
- 阶段三默认读取 `outputs/<project>/2b_scholarship_map.yaml` 中的 `stage3_handoff` 作为检索输入；`1_journal_targeting.md` 与 `1_research_proposal.md` 只作为背景参考。
- 文件：`3_final_corpus.yaml`
- 由 Skill 外部的数据库与 API 检索链路生成。
- Skill 只消费，不负责生产。
- 推荐同时提供：`3_stage3_manifest.json`
- 推荐同时保留：
  - `outputs/<project>/_stage3/session.json`
  - `outputs/<project>/_stage3/manifest.json`

`session.json` 除了配置项，建议至少包含以下断点字段，用于阶段三多次运行时续跑：

- `analysis_targets`
- `retrieval_progress.completed_targets`
- `retrieval_progress.pending_targets`
- `retrieval_progress.current_target`
- `retrieval_progress.current_cursor`
- `retrieval_progress.last_piece_id`
- `retrieval_progress.completed_piece_count`

`3_final_corpus.yaml` 的最小结构：

```yaml
piece_count: 2
records:
  - piece_id: "pb:KR3j0001_001-1a"
    source_file: "某书名"
    matched_theme: "祈雨"
    original_text: |
      原始史料正文
    note: "可选，外部阶段三写入的简短说明"
```

Skill 端真正依赖的字段只有：

- `piece_id`
- `source_file`
- `matched_theme`
- `original_text`

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

`evidence_anchors` 只能引用阶段三 corpus 中真实存在的 `piece_id`。

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
