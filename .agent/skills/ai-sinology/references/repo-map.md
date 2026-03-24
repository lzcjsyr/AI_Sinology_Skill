# 仓库地图

## 目录

- `./.agent/skills/ai-sinology/`
  - 当前主 Skill。
  - 负责阶段一、二、四、五、六的创作方法、阶段三交接契约、工作区契约和项目辅助脚本。
- `./.agent/skills/ai-sinology/assets/`
  - Skill 内部的机器可读资源。
  - `workspace-contract.json` 是工作区契约的单一真相源。
- `./.agent/skills/ai-sinology/scripts/`
  - Skill 内部的确定性辅助脚本。
  - 负责项目初始化、进度同步和项目状态检查。
- `./runtime/stage3/`
  - 外部阶段三运行时的辅助模块。
  - 负责阶段三项目选择、`_stage3/` 工作目录初始化、会话续跑、manifest 配置、环境检查、scope 探测和 API 烟雾测试。
- `./outputs/`
  - 每个研究项目的实际产物目录。
  - 阶段三过程文件统一放在 `outputs/<project>/_stage3/`。
- `./data/`
  - 可选的本地数据区；Kanripo 数据不再被 Skill 直接绑定。

## 仓库原则

- 这是 Skill-first 仓库，不再维护旧的 CLI orchestration。
- 创作规则写进 Skill reference，确定性辅助逻辑优先写进 Skill `scripts/`，运行时探测和连通性检查写进 `runtime/stage3/`。
- 工作区契约先修改 `assets/workspace-contract.json`，再同步更新 `references/workspace-contract.md`。

## 常见落点

- 改工作区阶段判定或文件名：
  - `.agent/skills/ai-sinology/assets/workspace-contract.json`
  - `.agent/skills/ai-sinology/scripts/workspace_contract.py`
  - `.agent/skills/ai-sinology/references/workspace-contract.md`
- 改项目初始化或进度同步：
  - `.agent/skills/ai-sinology/scripts/init_project.py`
  - `.agent/skills/ai-sinology/scripts/sync_progress.py`
- 改项目状态查看：
  - `.agent/skills/ai-sinology/scripts/project_status.py`
- 改阶段三模型槽位、provider 或 env key 名：
  - `runtime/stage3/api_config.py`
- 改 Kanripo scope catalog 解析：
  - `runtime/stage3/catalog.py`
- 改阶段一写法：
  - `references/stage1-planning.md`
- 改阶段二写法：
  - `references/stage2-scholarship-map.md`
- 改阶段三写法：
  - `references/stage3-handoff.md`
- 改阶段四写法：
  - `references/stage4-outlining.md`
  - `references/stage4-argument-audit.md`
- 改阶段五写法：
  - `references/stage5-drafting.md`
- 改阶段六写法：
  - `references/stage6-polishing.md`
  - `references/stage6-submission-package.md`

## 验证

```bash
pytest
python3 .agent/skills/ai-sinology/scripts/project_status.py --all
python3 -m runtime.stage3.env_check --kanripo-root /path/to/kanripo_repos
```
