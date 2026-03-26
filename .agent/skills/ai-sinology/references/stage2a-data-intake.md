# 阶段二A：检索扩展与候选集收敛

## 目标

`2A` 是阶段二的前半段。它服务于 `2b_scholarship_map.yaml`，但自身的直接目标不是写地图，而是先收敛出一批可靠、可扩展、可人工补强的候选作品集。

`2A` 需要优先获得：

- 可验证的题录元数据
- 摘要、关键词、目录或短引文
- 引用关系与期刊来源信息
- 足以支持 `major_positions`、`debates`、`gaps_to_address` 的研究线索
- 一份可继续人工补料的候选论文清单

`2A` 不以批量抓取受限全文为目标。

## `2A` 的职责边界

`2A` 不是纯抓取环节，它本身就包含学术判断。默认分工如下：

- 脚本负责：
  - 调 API
  - 归一化字段
  - 去重合并
  - 把过程结果写到 `outputs/<project>/_stage2a/`
- agent 负责：
  - 拆检索轴
  - 判断相关性
  - 选择 seed works
  - 在首轮 `OpenAlex` 后发起网页搜索补检
  - 决定是否继续下一轮扩展
  - 判断何时停轮
  - 判断何时需要暂停等待用户补料

换句话说，`2A` 的学术判断重点是：

- 这篇文献是否真的与当前研究问题直接相关
- 它是“核心对话对象”，还是只是背景噪声
- 它引用出去的那条链是否值得继续追
- 当前候选集是否已经足够稳定，可以进入 `2B`

## 推荐入口分层

### 第一层：可直接自动处理的开放入口

- `OpenAlex`
  - 适合做阶段二默认主 API。
  - 可用于 works、authors、sources、topics、related works 与 citation graph。
  - 直接 API 模式应配置 `OPENALEX_API_KEY`。
### 第二层：外部补料

开放来源不够时，默认由用户在外部补充资料，再回到 `2A` 继续收敛。

优先接收的输入形态：

- `RIS`
- `BibTeX`
- `CSV`
- DOI 列表
- 文章落地页 URL 列表
- PDF
- 人工整理的书目或读书笔记

Skill 接手后的任务是：

- 统一字段
- 去重与合并版本
- 补 DOI / 年份 / 刊名 / 作者名
- 形成候选作品集
- 生成 `candidate_papers.md`
- 记录哪些作品值得继续扩展
- 为进入 `2B` 准备基础材料

## 不建议作为默认方案的入口

- 登录态网页自动抓取
- 需要验证码或高频反爬的网站
- Google Scholar 批量抓取
- 版权受限全文的批量下载

这些入口可以作为人工补漏线索，但不应成为 Skill 的默认数据面。

## 首轮 `OpenAlex` 后的网页补检

首轮 `OpenAlex` 检索后，agent 应再使用自身网页搜索/浏览能力做一轮补检，用来补足题录、摘要、刊物页面与高相关作品线索。

优先接受为正式依据的网页来源：

- 期刊官网与出版社页面
- DOI 落地页
- 高校或研究机构知识库
- 可公开访问的论文数据库落地页

不应把以下页面直接当作正式依据：

- 普通博客
- 无署名转载页
- 只做聚合、不提供稳定出处的搜索结果页

## API Key 与环境变量

推荐在仓库根目录 `.env` 中配置：

```bash
OPENALEX_API_KEY=your_openalex_key
```

规则：

- 需要直接调用 OpenAlex API 时，检查 `OPENALEX_API_KEY` 是否存在。
- 若缺少 `OPENALEX_API_KEY`，则阶段二应退回到：
  - 用户导出题录
  - DOI / URL 列表
  - PDF / 书目笔记
  - 仅做少量网页补全

## 推荐脚本路径

阶段二如需重复调用开放 API，不应每次现场重写抓取代码，优先复用 Skill 自带脚本：

- `scripts/stage2a_sources.py`
  - 负责读取 `.env`、调用 `OpenAlex`、输出归一化 JSON。
  - 其中 `openalex-expand` 子命令只负责根据 agent 选定的 `seed_id` 抓取一跳引用结果，供下一轮人工判读。
  - 默认可将过程文件写到 `outputs/<project>/_stage2a/`。
- `scripts/stage2b_scholarship_map.py`
  - 负责合并多个阶段二来源 JSON，并生成 `2b_scholarship_map.yaml` 草稿骨架。
  - 它只做稳定的字段汇总与模板落盘，不替代人工的学术判断。

这里的最佳实践边界是：

- “怎么调用 API、怎么统一字段、怎么落盘”适合写成脚本。
- “阶段一到底拆成哪些检索轴、哪些结果保留、如何归纳成 positions / debates / gaps”应由 agent 在当前任务上下文里判断，不宜写成重启发式 pipeline。
- 因此阶段二推荐采用“agent 多轮调脚本”的方式，而不是把整套研究判断硬塞进一个自动脚本。是否相关、是否继续扩展、哪些结果进入约 30 篇依据文献清单，都应由 agent 判断。

## `2A` 的推荐过程文件

`outputs/<project>/_stage2a/` 推荐保留：

- `openalex-*.json`
- `candidate_papers.md`
- `screening-notes.md`
  用来简要记录 agent 的筛选与扩展判断
- `papers/`
  用于存放用户在 `2A` 后人工补入的 PDF、题录导出与读书笔记

这些都属于过程产物，不替代正式的 `2b_scholarship_map.yaml`。

常用命令：

```bash
python3 .agent/skills/ai-sinology/scripts/stage2a_sources.py openalex --project demo --query "汉代 灾异 诠释" --env-file .env
python3 .agent/skills/ai-sinology/scripts/stage2a_sources.py openalex-expand --project demo --query "汉代 灾异 诠释" --round-index 1 --seed-id W123 --seed-id W456 --per-page 10 --env-file .env
python3 .agent/skills/ai-sinology/scripts/stage2b_scholarship_map.py --project demo \
  --source-json outputs/demo/_stage2a/openalex-xxx.json
```

## 面向 Skill 的实践决策

`2A` 默认按以下顺序推进：

1. 读取阶段一产物，明确研究问题、对象、时段、概念轴线。
2. 由 agent 根据阶段一内容拆出 3 到 8 组检索轴；通常至少包括：
   - 研究方向整句
   - 研究对象 + 核心概念
   - 时段 + 争点
   - 中英文互译后的主题词
3. 如果以 `OpenAlex` 为主入口，优先执行“关键词首轮检索 -> agent 判读结果 -> 对选中的 seed works 调用 `openalex-expand` 抓一跳引用 -> 再判读是否继续下一轮”的流程。
4. 首轮 `OpenAlex` 后，再由 agent 用网页搜索/浏览补检高相关结果，优先核对期刊官网、DOI 落地页、出版社页面与机构知识库。
5. `OpenAlex` 扩展的收束目标通常是约 30 篇高相关作品；如果新增结果已经明显衰减、重复度升高或偏题，agent 应主动停轮，不必机械跑满上限。
6. 脚本只负责稳定取数、字段归一化和过程落盘；哪些作品相关、哪些作品值得进入下一轮，必须由 agent 结合摘要、题名、期刊与上下文判断。
7. 用 `OpenAlex` 建立开放候选集，并把 JSON 过程文件写到 `outputs/<project>/_stage2a/`；同时维护 `candidate_papers.md`。
8. 如果开放来源明显不够，停在 `2A`，等待用户补充外部资料。
9. 用户补料后，把 PDF、题录导出和读书笔记放入 `outputs/<project>/_stage2a/papers/`，再由 agent 继续筛选、补链和收束。
10. 当候选集已经足够稳定时，再进入 `2B`，而不是在 `2A` 里直接写完整 scholarship map。

## 人工干预点

以下情况不应硬撑自动流程，而应显式停在 `2A`，等待人工介入：

- 开放来源明显不够，继续扩展的收益已经很低
- 需要用户在外部补充资料后，候选集才有继续收敛的意义

## `2A` 完成标志

满足以下条件时，可以从 `2A` 进入 `2B`：

- 候选集已经能覆盖主要研究路径，而不是只剩单一分支
- 已经识别出若干核心 works 和可继续放弃的噪声 works
- 新一轮扩展的新增结果质量明显下降，或重复度显著升高
- 当前没有明显来源缺口，或已有条件先进入 `2B`
