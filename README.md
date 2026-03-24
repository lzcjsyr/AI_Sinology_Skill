# ai-sinology

这个仓库现在是一个以 Skill 驱动的汉学论文工作台。

职责边界已经收束成两层：

- `./.agent/skills/ai-sinology/`
  - 负责阶段一、二、四、五、六的创作性工作、阶段三交接契约，以及工作区契约、项目初始化和进度同步。
- `./runtime/stage3/`
  - 保留阶段三外部运行时需要的配置、环境检查、Kanripo scope 探测、任务 manifest CLI 和 API 烟雾测试。

阶段三的一手史料数据库、检索执行器和真实 API 调用链路都应放在 Skill 外部；本仓库只约束它们最终写回的工作区文件契约。机器可读契约由 `./.agent/skills/ai-sinology/assets/workspace-contract.json` 单独维护。

新建项目时，默认落点是当前工作目录下的 `outputs/<project>/`，并且应立即创建 `project_progress.yaml` 作为项目进度说明文件。

## 当前工作流

1. 用 `$ai-sinology` 或 `python3 .agent/skills/ai-sinology/scripts/init_project.py <project>` 在当前工作目录创建 `outputs/<project>/` 和 `outputs/<project>/project_progress.yaml`
2. 生成 `outputs/<project>/1_journal_targeting.md` 与 `outputs/<project>/1_research_proposal.md`
3. 用同一个 Skill 或结合外部书目/联网检索生成 `outputs/<project>/2_scholarship_map.yaml`
4. 运行 `python3 -m runtime.stage3.cli`，先选择目标项目，再创建 `outputs/<project>/_stage3/` 工作目录与阶段三配置
5. 在仓库外部完成阶段三检索；阶段三过程文件统一写入 `outputs/<project>/_stage3/`，最终结果写回 `outputs/<project>/3_final_corpus.yaml`
6. 继续生成 `outputs/<project>/4_outline_matrix.yaml` 与 `outputs/<project>/4_argument_audit.md`
7. 再生成 `outputs/<project>/5_first_draft.md`
8. 最后生成终稿与投稿包：`6_final_manuscript.md`、`6_abstract_keywords.md`、`6_title_options.md`、`6_anonymous_submission_checklist.md`、`6_claim_boundary.md`，并推荐补 `6_revision_checklist.md`
9. 每推进阶段后，用 `python3 .agent/skills/ai-sinology/scripts/sync_progress.py <project>` 回写 `project_progress.yaml`

如果用户明确需要 `.docx`，阶段六再联动 `doc` skill 或其他外部文档工具；默认交付物是 Markdown 终稿。

## 目录

```text
.
├── .agent/skills/ai-sinology/
│   ├── assets/
│   │   └── workspace-contract.json
│   ├── scripts/
│   │   ├── init_project.py
│   │   ├── project_status.py
│   │   ├── sync_progress.py
│   │   └── workspace_contract.py
│   └── references/
├── runtime/
│   └── stage3/
├── outputs/
│   └── <project>/
│       ├── project_progress.yaml
│       ├── 1_journal_targeting.md
│       ├── 1_research_proposal.md
│       ├── 2_scholarship_map.yaml
│       ├── 3_stage3_manifest.json
│       ├── 3_final_corpus.yaml
│       ├── 4_outline_matrix.yaml
│       ├── 4_argument_audit.md
│       ├── 5_first_draft.md
│       ├── 6_final_manuscript.md
│       ├── 6_abstract_keywords.md
│       ├── 6_title_options.md
│       ├── 6_anonymous_submission_checklist.md
│       ├── 6_claim_boundary.md
│       └── _stage3/
│           ├── session.json
│           └── manifest.json
├── data/
└── tests/
```

## 常用命令

```bash
python3 .agent/skills/ai-sinology/scripts/init_project.py demo
python3 .agent/skills/ai-sinology/scripts/project_status.py --all
python3 .agent/skills/ai-sinology/scripts/sync_progress.py demo
python3 -m runtime.stage3.cli
python3 -m runtime.stage3.cli --project demo --source stage1 --repos KR3j0160,KR3j0161 --env-file .env
python3 -m runtime.stage3.cli --project demo --themes 祈雨,灾异 --scopes KR3j --env-file .env
python3 -m runtime.stage3.cli --project demo --show-checkpoint
python3 -m runtime.stage3.cli --project demo --checkpoint-action start --checkpoint-target KR3j0160
python3 -m runtime.stage3.cli --project demo --checkpoint-action checkpoint --checkpoint-cursor offset=120 --checkpoint-piece-id pb:KR3j0160_010-2b --checkpoint-piece-delta 5
python3 -m runtime.stage3.cli --project demo --checkpoint-action complete --checkpoint-target KR3j0160
python3 -m runtime.stage3.env_check --kanripo-root /path/to/kanripo_repos
python3 -m runtime.stage3.scope_probe --kanripo-root /path/to/kanripo_repos --limit 20
python3 -m runtime.stage3.api_smoke_test --slot llm1 --env-file .env
pytest
```

`runtime.stage3.cli` 会先选择 `outputs/<project>/` 下的目标项目，再在该项目内创建 `outputs/<project>/_stage3/` 工作目录。阶段三的会话状态与过程文件都会写进这个目录，默认可在中断后继续；同时保留 `outputs/<project>/3_stage3_manifest.json` 作为对外 manifest。

`runtime.stage3.cli`、`runtime.stage3.env_check` 和 `runtime.stage3.api_smoke_test` 默认都会读取当前工作目录下的 `.env`；如果需要切换环境文件，再显式传 `--env-file`。

`outputs/<project>/_stage3/session.json` 现在除了保存主题、scope、repo 等配置，还会保存 `retrieval_progress` 断点信息，包括：

- `analysis_targets`：本轮应检索的 scope family / repo 目录清单
- `completed_targets` / `pending_targets`
- `current_target`
- `current_cursor`
- `last_piece_id`
- `completed_piece_count`

因此阶段三即使拆成多次运行，也可以在下次进入项目时直接恢复到上次的检查位置，而不是从头开始。

当前约定下，阶段三至少有两层产物：

- 项目根目录下的正式产物：`3_stage3_manifest.json`、`3_final_corpus.yaml`
- `outputs/<project>/_stage3/` 下的过程产物：`session.json`、`manifest.json`，以及后续外部执行器写入的其他中间文件

当前工作流与旧版相比有三处关键升级：

- 阶段一前置“目标刊物校准”，不再默认先写题目再找刊。
- 阶段二单独构建学术史地图，阶段三只负责一手史料总库，避免材料与学术史混层。
- 阶段六以“投稿包”收尾，不只停在正文终稿。

## 依赖

建议使用 Python 3.10+。

```bash
python3 -m pip install -r requirements.txt
```

- `requirements.txt`：统一依赖入口，包含阶段三环境检查、API 连通性测试和本仓库回归测试所需依赖。
