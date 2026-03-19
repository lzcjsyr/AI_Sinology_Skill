# 阶段一：选题与构思

## 何时读取本文件

- 修改 `workflow/stage1_topic_selection.py`
- 修改 `prompts/stage1_section_writer.yaml`
- 修改 `prompts/stage1_target_themes.yaml`
- 排查 `1_research_proposal.md` 的结构、front matter 或 `target_themes`

## 目标

根据用户模糊研究意向生成可执行的研究计划书，并提炼出供阶段二直接使用的 `target_themes`。

在混合独立模式下，阶段一默认由 skill 直接完成，不要求额外第三方 LLM 运行时。

## 核心文件

- `workflow/stage1_topic_selection.py`
- `prompts/stage1_section_writer.yaml`
- `prompts/stage1_target_themes.yaml`
- `core/utils.py`

## 输入

- 用户意向 `idea`
- 阶段一模型配置 `stage1`
- 已有 proposal 草稿（续跑时可复用）

## 输出

- `outputs/<project>/1_research_proposal.md`

## 必须保持的结构

- 文件顶部必须有 YAML front matter。
- front matter 至少包含：
  - `idea`
  - `target_themes`
- `target_themes` 必须是阶段二可直接消费的机器可读结构。
- 正文按 section 逐段生成，允许断点续写。

## 代码行为要点

- 阶段一不是一次性整文生成，而是按 section plan 串行写入。
- 如果已有部分草稿，应优先复用已完成小节。
- `target_themes` 是单独生成和去重的，不应与正文逻辑混写。
- 主题数量上限目前被截断在前 3 个。

## 修改守则

- 改 proposal 结构时，要同步确认 `_restore_completed_sections()` 还能正确续写。
- 改 `target_themes` JSON 格式时，要同步确认阶段二提取逻辑仍能消费。
- 不要让主题词变成现代学术结论句；阶段二要拿它去检索一手史料。

## 常见风险

- front matter 丢失，导致阶段二无法读取主题。
- 主题去重策略改坏，导致多个近义主题重复消耗阶段二算力。
- proposal 正文结构变化后，续写逻辑误判小节完成度。

## 建议测试

- `pytest tests/test_prompt_loader.py`
- 与阶段一相关的 utils 或 JSON 解析测试
- 如改了续写逻辑，补回归测试
