# 仓库地图

## 目录

- `./.agent/skills/ai-hanxue-thesis-workbench/`
  - 当前主 Skill。
  - 负责阶段一、三、四、五的创作方法与约束。
- `./runtime/stage2/`
  - 外部阶段二运行时的辅助模块。
  - 只负责配置、环境检查、scope 探测和 API 烟雾测试。
- `./runtime/workspace_contract.py`
  - 工作区文件契约与阶段完成判定。
- `./runtime/project_status.py`
  - 查看 `outputs/` 下各项目进度。
- `./outputs/`
  - 每个研究项目的实际产物目录。
- `./data/`
  - 可选的本地数据区；Kanripo 数据不再被 Skill 直接绑定。

## 仓库原则

- 这是 Skill-first 仓库，不再维护旧的 CLI orchestration。
- 创作规则写进 Skill reference，运行时探测和连通性检查写进 `runtime/`。
- 任何阶段契约改动，都要同时修改 `references/workspace-contract.md` 与 `runtime/workspace_contract.py`。

## 常见落点

- 改阶段二模型槽位、provider 或 env key 名：
  - `runtime/stage2/api_config.py`
- 改 Kanripo scope catalog 解析：
  - `runtime/stage2/catalog.py`
- 改工作区阶段判定或文件名：
  - `runtime/workspace_contract.py`
  - `references/workspace-contract.md`
- 改阶段一写法：
  - `references/stage1-planning.md`
- 改阶段三写法：
  - `references/stage3-outlining.md`
- 改阶段四写法：
  - `references/stage4-drafting.md`
- 改阶段五写法：
  - `references/stage5-polishing.md`

## 验证

```bash
pytest
python3 -m runtime.project_status --all
python3 -m runtime.stage2.env_check --kanripo-root /path/to/kanripo_repos
```
