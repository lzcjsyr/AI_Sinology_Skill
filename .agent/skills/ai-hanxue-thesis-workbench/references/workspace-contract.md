# 工作区文件契约

## 项目目录

所有项目都放在当前工作目录的 `outputs/<project>/` 下。

## 项目级进度文件

每个项目都应有：`outputs/<project>/project_progress.yaml`

新建项目时要先创建这个文件，再写阶段文件。

建议最小结构：

```yaml
project_name: "demo"
workspace_root: "/abs/path/to/current/workdir"
project_root: "/abs/path/to/current/workdir/outputs/demo"
current_stage: 1
current_stage_name: "选题与构思"
completed_stages: []
available_files: []
next_action: "撰写 1_research_proposal.md"
last_updated: "2026-03-19T10:00:00+08:00"
notes: "可选，记录人工决策或阻塞点"
```

Skill 在每次推进阶段后都应同步更新这个文件。

## 阶段文件

### 阶段一

- 文件：`1_research_proposal.md`
- 必须包含 YAML front matter。
- front matter 至少包含：
  - `idea`
  - `target_themes`
- `target_themes` 必须是给阶段二检索使用的主题，而不是最终论文结论句。

### 阶段二

- 文件：`2_final_corpus.yaml`
- 由 Skill 外部的数据库与 API 检索链路生成。
- Skill 只消费，不负责生产。
- 推荐同时提供：`2_stage2_manifest.json`

`2_final_corpus.yaml` 的最小结构：

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

Skill 端真正依赖的字段只有：

- `piece_id`
- `source_file`
- `matched_theme`
- `original_text`

### 阶段三

- 文件：`3_outline_matrix.yaml`
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

### 阶段四

- 文件：`4_first_draft.md`
- 每个小节必须显式保留证据锚点。
- 推荐写法是在小节结尾保留一行：

```text
证据锚点：`pb:...`, `pb:...`
```

### 阶段五

- 必选文件之一：
  - `5_final_manuscript.md`
  - `5_final_manuscript.docx`
- 推荐附带：
  - `5_revision_checklist.md`

默认以 Markdown 终稿为准；如果生成 `.docx`，也不要丢掉 `piece_id` 追溯信息。
