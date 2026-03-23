# AI 汉学 Skill 工作台

这个仓库现在是一个以 Skill 驱动的汉学论文工作台，不再维护 `main.py + workflow/` 的五阶段脚本流水线。

职责边界已经收束成两层：

- `./.agent/skills/ai-hanxue-thesis-workbench/`
  - 负责阶段一、三、四、五的创作性工作。
- `./runtime/stage2/`
  - 保留阶段二外部运行时需要的配置、环境检查、Kanripo scope 探测、任务 manifest CLI 和 API 烟雾测试。

阶段二的数据库、检索执行器和真实 API 调用链路都应放在 Skill 外部；本仓库只约束它们最终写回的工作区文件契约。

新建项目时，默认落点是当前工作目录下的 `outputs/<project>/`，并且应立即创建 `project_progress.yaml` 作为项目进度说明文件。

## 当前工作流

1. 用 `$ai-hanxue-thesis-workbench` 在当前工作目录创建 `outputs/<project>/` 和 `outputs/<project>/project_progress.yaml`
2. 生成 `outputs/<project>/1_research_proposal.md`
3. 在仓库外部完成阶段二检索，并写回 `outputs/<project>/2_final_corpus.yaml`
4. 用同一个 Skill 生成 `outputs/<project>/3_outline_matrix.yaml`
5. 继续生成 `outputs/<project>/4_first_draft.md`
6. 最后生成 `outputs/<project>/5_final_manuscript.md` 和 `outputs/<project>/5_revision_checklist.md`

如果用户明确需要 `.docx`，阶段五再联动 `doc` skill 或其他外部文档工具；默认交付物是 Markdown 终稿。

## 目录

```text
.
├── .agent/skills/ai-hanxue-thesis-workbench/
├── runtime/
│   ├── project_status.py
│   ├── workspace_contract.py
│   └── stage2/
├── outputs/
├── data/
└── tests/
```

## 常用命令

```bash
python3 -m runtime.project_status --all
python3 -m runtime.stage2.cli
python3 -m runtime.stage2.cli --project demo --source stage1 --repos KR3j0160,KR3j0161
python3 -m runtime.stage2.cli --project demo --themes 祈雨,灾异 --scopes KR3j
python3 -m runtime.stage2.env_check --kanripo-root /path/to/kanripo_repos
python3 -m runtime.stage2.scope_probe --kanripo-root /path/to/kanripo_repos --limit 20
python3 -m runtime.stage2.api_smoke_test --slot llm1 --env-file .env
pytest
```

`runtime.stage2.cli` 会把阶段二配置写成 `outputs/<project>/2_stage2_manifest.json`。它既可以读取 `1_research_proposal.md` 里的 `target_themes` 作为默认分析主题，也支持人工直接输入主题、scope family 和精确 repo 目录。

## 依赖

```bash
python3 -m pip install -r requirements.txt
```

当前只保留阶段二连通性测试需要的 `litellm`。
