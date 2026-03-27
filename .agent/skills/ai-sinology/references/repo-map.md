# 仓库地图

## 主要目录

- `./.agent/skills/ai-sinology/`
  当前主 Skill。这里放写作规则、项目脚本和工作区契约。
- `./.agent/skills/ai-sinology/references/`
  各阶段的说明文档。只在对应任务发生时再读。
- `./.agent/skills/ai-sinology/scripts/`
  本地辅助脚本。负责项目初始化、进度同步和项目状态查看。
- `./.agent/skills/ai-sinology/assets/workspace-contract.json`
  工作区契约的机器可读真相源。
- `./runtime/stage3/`
  模块名暂沿用 `stage3`，实际负责阶段二原始文献运行时的辅助执行、检查和续跑。
- `./outputs/`
  每个论文项目的实际产物目录。

## 常见修改点

- 改工作区阶段判定、文件名或契约：
  - `./.agent/skills/ai-sinology/assets/workspace-contract.json`
  - `./.agent/skills/ai-sinology/scripts/workspace_contract.py`
  - `./.agent/skills/ai-sinology/references/workspace-contract.md`
- 改项目初始化或进度同步：
  - `./.agent/skills/ai-sinology/scripts/init_project.py`
  - `./.agent/skills/ai-sinology/scripts/sync_progress.py`
- 改项目状态查看：
  - `./.agent/skills/ai-sinology/scripts/project_status.py`
- 改阶段一写法：
  - `./.agent/skills/ai-sinology/references/stage1-planning.md`
  - `./.agent/skills/ai-sinology/references/stage1-venues.md`
  - `./.agent/skills/ai-sinology/references/` 下对应的单刊文件
- 改阶段二写法：
  - `./.agent/skills/ai-sinology/references/stage2-primary-corpus.md`
- 改阶段三交接：
  - `./.agent/skills/ai-sinology/references/stage3a-deepened-thinking.md`
  - `./.agent/skills/ai-sinology/references/stage3b-data-intake.md`
  - `./.agent/skills/ai-sinology/references/stage3c-scholarship-map.md`
  - `./runtime/stage3/`
- 改阶段四写法：
  - `./.agent/skills/ai-sinology/references/stage4-outlining.md`
  - `./.agent/skills/ai-sinology/references/stage4-argument-audit.md`
- 改阶段五写法：
  - `./.agent/skills/ai-sinology/references/stage5-drafting.md`
- 改阶段六写法：
  - `./.agent/skills/ai-sinology/references/stage6-polishing.md`
  - `./.agent/skills/ai-sinology/references/stage6-submission-package.md`

## 验证

```bash
pytest
python3 .agent/skills/ai-sinology/scripts/project_status.py --all
python3 -m runtime.stage3.env_check --kanripo-root /path/to/kanripo_repos
```
