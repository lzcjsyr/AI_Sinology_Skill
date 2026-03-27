# ai-sinology

这个仓库是一个以 Skill 驱动的汉学论文工作台。

## 职责边界

- `./.agent/skills/ai-sinology/`
  - 负责阶段一、三、四、五、六的写作性工作，以及项目初始化、进度同步、工作区契约和阶段三开放来源脚本。
- `./runtime/stage2/`
  - 负责阶段二的一手史料外部运行时：Kanripo scope 校验、正文规模统计、manifest/session 管理、断点续跑和 API/环境烟雾测试。

阶段二的一手史料数据库、本地检索执行器和真实 API 调用链路都放在 Skill 外部；本仓库只约束它们最终写回的工作区文件契约。机器可读契约由 `./.agent/skills/ai-sinology/assets/workspace-contract.json` 维护。

## 当前工作流

1. 用 `$ai-sinology` 或 `python3 .agent/skills/ai-sinology/scripts/init_project.py <project>` 创建 `outputs/<project>/` 和 `project_progress.yaml`
2. 完成阶段一，生成 `1_journal_targeting.md` 与 `1_research_proposal.md`；建议在 front matter 中显式写入 `stage2_retrieval_themes`
3. 运行 `python3 -m runtime.stage2.cli`，从阶段一输入出发读取检索主题并确认阶段二原始文献检索范围，生成：
   - `outputs/<project>/2_stage2_manifest.json`
   - `outputs/<project>/_stage2/session.json`
   - `outputs/<project>/_stage2/manifest.json`
4. 在仓库外部完成阶段二原始文献勘查，并写回 `outputs/<project>/2_primary_corpus.yaml`
5. 回到 Skill 内推进阶段三：
   - `3A` 生成 `3a_deepened_thinking.md`
   - `3B` 用 `stage3b_sources.py` 检索扩展与候选集收敛，维护 `outputs/<project>/_stage3b/candidate_papers.md`
   - 人工根据 `candidate_papers.md` 下载核心论文、题录导出或笔记，放入 `outputs/<project>/_stage3b/papers/`
   - `3C` 由 agent 必须读取阶段一、阶段二、`3A`、`candidate_papers.md` 与 `papers/` 中人工补料，直接完成 `3c_scholarship_map.yaml`
6. 继续生成 `4_outline_matrix.yaml` 与 `4_argument_audit.md`
7. 生成 `5_first_draft.md`
8. 最后生成终稿与投稿包：`6_final_manuscript.md`、`6_abstract_keywords.md`、`6_title_options.md`、`6_anonymous_submission_checklist.md`、`6_claim_boundary.md`，并推荐补 `6_revision_checklist.md`
9. 每推进阶段后，用 `python3 .agent/skills/ai-sinology/scripts/sync_progress.py <project>` 回写 `project_progress.yaml`

如果用户明确需要 `.docx`，阶段六再联动 `doc` skill 或其他外部文档工具；默认交付物是 Markdown。

## 目录

```text
.
├── .agent/skills/ai-sinology/
│   ├── assets/
│   │   └── workspace-contract.json
│   ├── scripts/
│   │   ├── init_project.py
│   │   ├── project_status.py
│   │   ├── stage3_common.py
│   │   ├── stage3b_sources.py
│   │   ├── sync_progress.py
│   │   └── workspace_contract.py
│   └── references/
├── runtime/
│   └── stage2/
├── outputs/
│   └── <project>/
│       ├── project_progress.yaml
│       ├── 1_journal_targeting.md
│       ├── 1_research_proposal.md
│       ├── 2_primary_corpus.yaml
│       ├── 2_stage2_manifest.json
│       ├── _stage2/
│       │   ├── session.json
│       │   └── manifest.json
│       ├── 3a_deepened_thinking.md
│       ├── 3c_scholarship_map.yaml
│       ├── _stage3b/
│       │   ├── openalex-*.json
│       │   ├── baidu-scholar-*.json
│       │   ├── candidate_papers.md
│       │   ├── screening-notes.md
│       │   └── papers/
│       ├── 4_outline_matrix.yaml
│       ├── 4_argument_audit.md
│       ├── 5_first_draft.md
│       ├── 6_final_manuscript.md
│       ├── 6_abstract_keywords.md
│       ├── 6_title_options.md
│       ├── 6_anonymous_submission_checklist.md
│       └── 6_claim_boundary.md
├── data/
└── tests/
```

## 常用命令

```bash
python3 .agent/skills/ai-sinology/scripts/init_project.py demo
python3 .agent/skills/ai-sinology/scripts/project_status.py --all
python3 .agent/skills/ai-sinology/scripts/sync_progress.py demo

python3 -m runtime.stage2.cli --project demo --kanripo-root /path/to/kanripo_repos
python3 -m runtime.stage2.cli --project demo --targets KR3j0160,KR3j0161 --env-file .env
python3 -m runtime.stage2.cli --project demo --show-checkpoint
python3 -m runtime.stage2.cli --project demo --checkpoint-action start --checkpoint-target KR3j0160
python3 -m runtime.stage2.cli --project demo --checkpoint-action checkpoint --checkpoint-cursor offset=120 --checkpoint-piece-id pb:KR3j0160_010-2b --checkpoint-piece-delta 5
python3 -m runtime.stage2.cli --project demo --checkpoint-action complete --checkpoint-target KR3j0160
python3 -m runtime.stage2.env_check --kanripo-root /path/to/kanripo_repos
python3 -m runtime.stage2.scope_probe --kanripo-root /path/to/kanripo_repos --limit 20
python3 -m runtime.stage2.api_smoke_test --slot llm1 --env-file .env
python3 -m runtime.stage2.baidu_scholar_smoke_test --query "汉代 灾异" --env-file .env

python3 .agent/skills/ai-sinology/scripts/stage3b_sources.py baidu-scholar --project demo --query "汉代 灾异 诠释" --env-file .env
python3 .agent/skills/ai-sinology/scripts/stage3b_sources.py openalex --project demo --query "汉代 灾异 诠释" --env-file .env
python3 .agent/skills/ai-sinology/scripts/stage3b_sources.py openalex-expand --project demo --query "汉代 灾异 诠释" --round-index 1 --seed-id W123 --seed-id W456 --expand-mode references --per-page 10 --env-file .env
pytest
```

## 阶段二运行时

`runtime.stage2.cli` 会读取 `1_journal_targeting.md` 与 `1_research_proposal.md`。如果阶段一 front matter 已提供 `stage2_retrieval_themes`，运行时优先直接采用；没有时，才从 `settled_research_direction`、`idea` 等字段做兜底推断。随后它会在项目内创建 `outputs/<project>/_stage2/` 工作目录，并维护：

- `analysis_targets`
- `retrieval_progress.completed_targets`
- `retrieval_progress.pending_targets`
- `retrieval_progress.current_target`
- `retrieval_progress.current_cursor`
- `retrieval_progress.last_piece_id`
- `retrieval_progress.completed_piece_count`

如果用户不熟悉 `KR1a`、`KR2k`、`KR3j` 这类 Kanripo family，可先阅读 `runtime/stage2/docs/kanripo_family_guide.md`。

## 阶段三

阶段三严格拆成三段：

- `3A`：回到阶段二原始文献，写 `3a_deepened_thinking.md`
- `3B`：做二手研究检索扩展与候选集收敛，过程文件写到 `_stage3b/`
- `3C`：由 agent 读取阶段一、阶段二、`3A`、`_stage3b/candidate_papers.md` 与 `_stage3b/papers/` 中人工导入材料，生成 `3c_scholarship_map.yaml`

阶段三不再存在 `2A/2B` 表述，也不再依赖 `2b_scholarship_map.yaml` 或 `stage3_handoff`。

## 依赖

建议使用 Python 3.10+。

```bash
python3 -m pip install -r requirements.txt
```
