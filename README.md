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
2. 先确认投稿目标，再生成 `outputs/<project>/1_journal_targeting.md` 与 `outputs/<project>/1_research_proposal.md`；阶段一结论应明确落成“研究方向 + 投稿期刊”
3. 用同一个 Skill 推进阶段二，但执行上默认拆成两个子环节：
   `2A` 检索扩展与候选集收敛：agent 先读阶段一，再分多轮调用 `python3 .agent/skills/ai-sinology/scripts/stage2a_sources.py ...`，把开放来源结果、人工补料记录和筛选笔记写到 `outputs/<project>/_stage2a/`
   `2B` 学术史地图写作：当 `2A` 的候选集已经相对稳定，再按需要用 `python3 .agent/skills/ai-sinology/scripts/stage2b_scholarship_map.py ...` 生成骨架，并由 agent 完成 `outputs/<project>/2b_scholarship_map.yaml`；该文件同时提供 `stage3_handoff`，作为阶段三正式输入
4. 运行 `python3 -m runtime.stage3.cli`，先选择目标项目，读取 `2b_scholarship_map.yaml` 中的 `stage3_handoff`，再创建 `outputs/<project>/_stage3/` 工作目录与阶段三配置
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
│   │   ├── stage2_common.py
│   │   ├── stage2a_sources.py
│   │   ├── stage2b_scholarship_map.py
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
│       ├── 2b_scholarship_map.yaml
│       ├── _stage2a/
│       │   ├── openalex-*.json
│       │   ├── manual-intake.md
│       │   └── screening-notes.md
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
python3 .agent/skills/ai-sinology/scripts/stage2a_sources.py openalex --project demo --query "汉代 灾异 诠释" --env-file .env
python3 .agent/skills/ai-sinology/scripts/stage2b_scholarship_map.py --project demo --source-json outputs/demo/_stage2a/openalex-xxx.json
python3 -m runtime.stage3.cli
python3 -m runtime.stage3.cli --project demo --source stage2 --repos KR3j0160,KR3j0161 --env-file .env
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

如果用户对 `KR1a`、`KR2k`、`KR3j` 这类 Kanripo family 不熟悉，可先阅读 `runtime/stage3/docs/kanripo_family_guide.md`。该文档提供静态分类导览、代表文本和本地镜像体量说明，适合在正式选择阶段三 scope 前先建立基本认识。

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

阶段一还有两条执行约束：

- 如果用户没有说清投稿目标，Skill 应先追问预期投稿期刊或投稿区间，而不是直接假设。
- 如果目标期刊不在内置 reference 内，Skill 应优先让用户提供期刊官网或投稿须知网页，再自行理解要求并更新到阶段一输出。
- `1_journal_targeting.md` 应写出完整的目标期刊定位与写作建议；`1_research_proposal.md` 应明确当前确定的研究方向与目标期刊。

## 阶段二推荐方案

阶段二仍然只产出一个正式文件：`outputs/<project>/2b_scholarship_map.yaml`。  
但执行上默认拆成两个子环节，这样可以把“agent 的学术判断”和“人工补料”放进清晰的停顿点，而不是混成一整段重流程。

### `2A` 检索扩展与候选集收敛

`2A` 不是纯抓取，而是 agent 主导的迭代式检索。目标不是立刻写地图，而是先把阶段二的候选作品集收敛出来。

`2A` 的职责：

- 读取 `1_journal_targeting.md` 与 `1_research_proposal.md`
- 拆出 3 到 8 组检索轴，而不是只打一条 query
- 用 `OpenAlex` 做首轮检索
- 首轮 `OpenAlex` 后，再用 agent 自身的网页搜索/浏览能力补检高相关结果
- 由 agent 根据题名、摘要、刊物、作者、引用关系判断哪些 works 值得保留
- 由 agent 选出 seed works，并调用 `openalex-expand` 抓一跳引用继续扩展
- 在开放来源不够时，停下来等待用户补充外部资料
- 把过程产物持续写入 `outputs/<project>/_stage2a/`

`2A` 的推荐过程文件：

- `openalex-*.json`
- `candidate_papers.md`
- `screening-notes.md`
  用来记录 agent 为什么保留、剔除或继续追踪某条文献链
- `papers/`
  用于存放 `2A` 后人工补入的 PDF、题录导出与读书笔记

`2A` 应显式保留人工干预点：

- 开放来源明显不够时，先暂停，由用户在外部补充资料后再继续

### `2B` 学术史地图写作

`2B` 的前提不是“API 都跑过了”，而是“候选集已经足够稳定，可以回答本文准备回应谁、接续谁、修正谁”。

`2B` 的职责：

- 基于 `2A` 收束后的候选集，筛出约 20 到 30 篇高相关依据文献
- 生成 `major_positions`、`debates`、`gaps_to_address`、`usable_frames`
- 补全每个 `core_work` 的 `claim` 与 `relevance`
- 明确 `claim_boundaries`，防止后续夸大创新
- 按需要用 `stage2b_scholarship_map.py` 先生成 YAML 骨架，再由 agent 完成学术判断

`2B` 前的最后一个人工校正点：

- 用户可以在进入 `2B` 前补充“必须纳入的核心文献”
- 用户可以指出哪些分支虽然高频但其实偏题，应从地图中排除
- 如果目标刊物有明显偏好，用户可以在这里补充应优先回应的学术路径

### 阶段二的数据入口

阶段二需要的是可靠的二手研究元数据、摘要、题录与争点线索，而不是批量抓取受限站点全文。阶段二仍属于 Skill 主体职责；如需重复调用开放 API，应优先复用 Skill 自带脚本，而不是在每次对话里现场重写调用代码。

推荐按两层入口处理：

- 可直接自动处理的开放入口：
  - `OpenAlex`：阶段二默认主 API，用于 works、authors、sources、topics 与引用关系。
- 外部补料：
  - 用户自行补充导出题录、PDF、DOI、URL 或书目笔记

首轮 `OpenAlex` 之后，还应由 agent 使用网页搜索/浏览补检，优先整理：

- 期刊官网
- DOI 落地页
- 出版社页面
- 高校或研究机构知识库
- 可公开访问的论文数据库落地页

不把普通博客、无稳定出处的转载页或纯聚合搜索结果页直接当作正式依据。

面向这个 Skill 的实践原则是：

- 不把登录态数据库网页抓取当作默认方案。
- 不依赖验证码、反爬强或版权受限的批量全文抓取。
- 优先接收 `DOI`、文章落地页 URL、`RIS`、`BibTeX`、`CSV`、PDF 与人工整理书目。
- Skill 的重点放在“归一化、去重、筛选候选集、提炼 claim、聚类争点、生成 scholarship map”，而不是模拟浏览器抢全文。

需要在环境中显式配置的项目只有：

```bash
OPENALEX_API_KEY=your_openalex_key
```

说明：

- `OPENALEX_API_KEY`：阶段二如果直接调用 OpenAlex API，应配置此变量。
- 其他来源默认按“用户先在外部补充资料，再交给 Skill 继续处理”的模式使用。

更具体的阶段二来源策略见 `./.agent/skills/ai-sinology/references/stage2a-data-intake.md`。

阶段二推荐命令：

```bash
python3 .agent/skills/ai-sinology/scripts/stage2a_sources.py openalex --project demo --query "汉代 灾异 诠释" --env-file .env
python3 .agent/skills/ai-sinology/scripts/stage2a_sources.py openalex-expand --project demo --query "汉代 灾异 诠释" --round-index 1 --seed-id W123 --seed-id W456 --per-page 10 --env-file .env
python3 .agent/skills/ai-sinology/scripts/stage2b_scholarship_map.py --project demo --source-json outputs/demo/_stage2a/openalex-xxx.json
```

更推荐的阶段二流程是：

1. 先由 agent 读取 `1_journal_targeting.md` 与 `1_research_proposal.md`
2. 进入 `2A`：由 agent 自主拆出多组检索轴，而不是固定只打一条 query
3. 先调用 `stage2a_sources.py openalex` 做首轮检索，再由 agent 自己判读哪些 works 值得继续扩展
4. 对 agent 选中的 seed works 调用 `stage2a_sources.py openalex-expand` 抓一跳引用；脚本不负责判断相关性，也不负责自动停轮
5. 首轮 `OpenAlex` 后，再由 agent 用网页搜索/浏览补检高相关作品，只整理达到学术引用标准的页面
6. 在 `outputs/<project>/_stage2a/candidate_papers.md` 中持续维护候选论文清单，作为 `2A` 的明确输出
7. 由 agent 根据每轮结果质量、重复度与偏题程度决定是否继续下一轮；如果开放来源明显不够，就停在 `2A`，等用户把相关 PDF、题录导出和笔记补入 `outputs/<project>/_stage2a/papers/` 后再继续
8. 当候选集相对稳定后，进入 `2B`：由 agent 读取返回 JSON、`candidate_papers.md` 与 `papers/` 目录中的人工补料，筛掉噪声，抽取 `claim`、`relevance`、`debates`
9. 最后按需要用 `stage2b_scholarship_map.py` 生成草稿骨架，再由 agent 完成 `2b_scholarship_map.yaml`，并确认其中的 `stage3_handoff` 已足以直接交给阶段三

## 依赖

建议使用 Python 3.10+。

```bash
python3 -m pip install -r requirements.txt
```

- `requirements.txt`：统一依赖入口，包含阶段三环境检查、API 连通性测试和本仓库回归测试所需依赖。
