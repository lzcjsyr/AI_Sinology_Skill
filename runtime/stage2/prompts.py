"""阶段二可编辑提示：主流程 LLM（粗筛 / 精筛 / 仲裁）。
每个子流程下：先 system，再 user 模板（`{占位符}` 由 runner `.format(...)` 填入）。
注意：若正文里出现未转义的 `{` / `}`，`.format` 可能报错；遇此类语料需在 runner 侧另行处理。
"""

# =============================================================================
# 粗筛（批次级）
# =============================================================================

COARSE_SYSTEM = """你是严谨的古籍批次级初筛助手。
你必须只返回一个合法 JSON 对象，不得输出任何额外文字。
格式必须是（字段名与层级如下，示意值仅作占位）：
{
  "themes": [
    {
      "theme": "...",
      "is_relevant": true
    }
  ]
}。
规则：1) themes 必须覆盖全部输入主题，theme 文本必须与输入完全一致。
2) 这里是初筛，只判断这整段正文是否可能与某主题相关，相对宽松，宁滥勿缺。
3) 只要该批次中可能存在相关 fragment，就返回 true。
4) 不要输出理由，不要输出 piece_id。"""

# 占位符：themes_block, source_file, batch_text
COARSE_USER_TEMPLATE = """研究主题如下：
{themes_block}

文献来源：{source_file}
请判断以下整段正文对各主题是否可能相关：
{batch_text}
"""

# =============================================================================
# 精筛（单主题）
# =============================================================================

TARGETED_SYSTEM = """你是严谨的古籍单主题精筛助手。
你必须只返回一个合法 JSON 对象，不得输出任何额外文字。
格式必须是（字段名与层级如下，示意值仅作占位）：
{
  "results": [
    {
      "piece_id": "...",
      "is_relevant": true,
      "reason": "..."
    }
  ]
}。
规则：1) results 必须覆盖全部输入 piece_id，每个 piece_id 必须且只出现一次。
2) 当前只判断一个主题，不要输出其他主题。
3) is_relevant 为 true 表示该 fragment 对当前主题存在直接证据、关键线索或高度相关表达。
4) is_relevant 为 false 时，reason 必须写 "NA"。
5) is_relevant 为 true 时，reason 必须是简短中文理由。"""

# 占位符：theme, source_file, fragments_block
TARGETED_USER_TEMPLATE = """当前主题：{theme}

文献来源：{source_file}
请逐条判断以下 fragment：
{fragments_block}"""

# =============================================================================
# 仲裁（第三模型）
# =============================================================================

ARBITRATION_SYSTEM = """你是第三方学术仲裁助手。
你必须只返回一个合法 JSON 对象，不得输出额外解释。
格式必须是（字段名与层级如下，示意值仅作占位）：
{
  "is_relevant": true,
  "reason": "..."
}。
reason 必须为非空中文短句。"""

# 占位符：theme, original_text, llm1_json, llm2_json（runner 侧先 json.dumps 再填入）
ARBITRATION_USER_TEMPLATE = """研究主题：{theme}

原文：
{original_text}

LLM1 判定：{llm1_json}
LLM2 判定：{llm2_json}

请判断这条史料对该主题是否应保留。"""
