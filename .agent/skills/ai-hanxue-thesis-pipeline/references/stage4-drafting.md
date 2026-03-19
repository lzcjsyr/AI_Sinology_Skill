# 阶段四：初稿撰写

## 何时读取本文件

- 修改 `workflow/stage4_drafting.py`
- 修改 `prompts/stage4_subsection_analysis.yaml`
- 排查 `4_first_draft.md`
- 排查引文块、引注区或小节生成逻辑

## 阶段目标

在受控证据约束下，把阶段三的论纲节点扩展成可读的论文初稿，同时保留清晰的引文块和 `piece_id` 追溯关系。

在混合独立模式下，阶段四默认由 skill 直接完成，不要求额外第三方 LLM 运行时。

## 核心文件

- `workflow/stage4_drafting.py`
- `prompts/stage4_subsection_analysis.yaml`
- `core/project_paths.py`

## 输入

- `3_outline_matrix.yaml`
- `_internal/stage2/2_final_corpus.json`

## 输出

- `outputs/<project>/4_first_draft.md`

## 必须保持的结构

- 标题层级：
  - `# 论文初稿`
  - `##` 章
  - `###` 节
  - `####` 小节
- 引文块格式：

```text
> [piece_id] 第一行
> 后续行
```

- 末尾保留“初排版引注区”。

## 代码行为要点

- 每个小节会单独调用模型生成：
  - 主题句
  - 分析
  - 小结
- 引文块由代码根据阶段二 corpus 直接拼入，不依赖模型自由转述。
- `used_piece_ids` 会汇总到引注区。

## 修改守则

- 不要改变引文块的基本格式；阶段五会从这里提取并核对原文。
- 如果改 Markdown 层级，必须同步修改阶段五分段润色的 heading 切片逻辑。
- 不要让模型直接自由发明引文正文；引文必须来自 corpus。

## 常见风险

- heading 层级一变，阶段五切片计划失效。
- 引文块格式一变，阶段五 `_extract_quote_blocks()` 识别失败。
- 证据列表裁剪过度，导致模型分析失去必要上下文。

## 建议测试

- 与阶段四输出结构相关的回归测试
- 如改了引文块格式，必须联动验证阶段五
