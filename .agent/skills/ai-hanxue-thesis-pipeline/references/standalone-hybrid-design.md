# 混合独立模式设计

## 目标边界

当前建议的独立形态不是“把五个阶段全部做成脚本运行时”，而是：

- 阶段一：由 skill 直接完成
- 阶段二：由 skill 内脚本独立运行，并调用第三方 LLM
- 阶段三：由 skill 直接完成
- 阶段四：由 skill 直接完成
- 阶段五：由 skill 直接完成

这样可以把最重、最依赖批量计算的部分脚本化，同时避免过早把其余阶段的文本生成与润色逻辑全部封装进运行时。

## 独立运行最小条件

- skill 本体
- 外部 Kanripo 语料目录
- 第三方 LLM API key
- 一个可写工作目录，用于放阶段二中间产物与最终史料总库

不要求依赖当前仓库的 `core/`、`workflow/`、`prompts/`。

## 当前推荐目录关系

```text
skill/
├── SKILL.md
├── references/
├── scripts/
│   ├── stage2_api_config.py
│   ├── standalone_kanripo.py
│   ├── stage2_env_check.py
│   ├── stage2_scope_probe.py
│   └── stage2_api_smoke_test.py
└── ...

external/
└── kanripo_repos/

workspace/
└── outputs/
```

## 配置原则

- 非敏感参数写在 `scripts/stage2_api_config.py`
- 真正的 API key 仍通过环境变量提供
- `kanripo_root` 与 `workspace` 通过 CLI 参数传入

## 为什么只脚本化阶段二

- 阶段二涉及真实大规模语料遍历、并发、限流、断点续跑和审计元数据，最适合程序化。
- 阶段一、三、四、五以结构化写作为主，当前更适合由 skill 直接执行，而不是额外维护另一套脚本运行时。
- 这样可以把“维护成本最高”的脚本范围控制在真正必要的地方。

## 后续如需继续独立化

如果未来要把阶段三到五也脚本化，建议按顺序推进：

1. 先脚本化阶段三的结构输出
2. 再脚本化阶段四的引文块拼接
3. 最后脚本化阶段五的润色和 DOCX 输出

不要一次性把后三阶段整体迁入运行时，否则会立刻引入大量 prompt、格式和回归维护负担。
