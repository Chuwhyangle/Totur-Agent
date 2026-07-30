# Agent 面试 HTML 语料分层语义切块设计

| 项 | 内容 |
|---|---|
| 日期 | 2026-07-30 |
| 输入语料 | `corpus/Agent_doc/**/*.html` |
| 当前样本 | 11 个去重 HTML：10 讲 Reveal.js 幻灯片 + 1 个课程知识地图 |
| 目标 | 将面试教学 HTML 确定性转换为分层语义 Chunk，并输出可审查、可复现的 JSONL 中间产物 |
| 本阶段边界 | 只实现解析、切块、JSONL 与 Manifest；暂不写入 Chroma，不修改线上检索链路 |

## 1. 决策

采用 **分层语义切块 + JSONL 中间产物**：

1. 保留课程、讲次、`h2` 章节、`h3` 面试题的层级；
2. 同一道题跨多个 Reveal.js 幻灯片时合并为一个语义单元；
3. 同时生成概览块和详情块，使宽泛问题与精确问题都能召回合适内容；
4. 只有完整语义单元超过上限时才继续按段落、列表、表格和代码块切分；
5. 输出稳定 JSONL 与 Manifest，人工检查通过后再单独设计 Chroma 接入。

不采用“一张幻灯片一个块”：当前 534 张内容幻灯片中，约 57.1% 不超过 200 字符，且问题、答案与补充说明经常分布在连续幻灯片中。

不采用“清理标签后固定 512 字符切分”：它会切断面试题、代码、表格和列表，且无法回答“2026 年 Agent 面试主要考什么”一类跨章节概览问题。

## 2. 已观察到的语料结构

### 2.1 Reveal.js 课程文档

10 个课程 HTML 的主要结构为：

```html
<div class="reveal">
  <div class="slides">
    <section>
      <section class="content-slide">
        <h2>Agent 核心</h2>
      </section>
      <section class="content-slide">
        <h3>Q8【中级】ReAct 模式的核心思想？</h3>
        ...
      </section>
      <section class="content-slide">
        <p>这是当前所有 Agent 框架的基础模式。</p>
      </section>
    </section>
  </div>
</div>
```

语义规律：

- `h1` 或 `<title>` 表示讲次标题；
- `h2` 表示章节；
- `h3` 常表示一道面试题、案例或专题；
- 没有新 `h2/h3` 的后续 `content-slide` 通常是上一题的续页；
- `<pre><code>`、`<table>`、`<ul>/<ol>` 是必须保留结构的教学内容；
- 空白过渡页、按钮、进度控件和代码窗口装饰不应进入 Chunk。

按 `h3 + 后续续页` 聚合后的初步统计：

- 约 246 个 `h3` 语义单元；
- 中位长度约 304 字符；
- 约 95.1% 不超过 1000 字符；
- 最长单元约 2610 字符。

这说明“按题聚合，超长再拆”比统一固定长度更符合语料分布。

### 2.2 课程知识地图

`知识地图*.html` 不使用 `section.content-slide`，主要结构为：

```html
<a class="course-card">
  <span class="lesson-no">第 04 讲</span>
  <h3 class="lesson-title">理论面试：LLM/Agent/RAG 基础 40 题</h3>
  <p class="lesson-desc">覆盖 LLM/Agent/RAG/生态四大板块高频考点</p>
  <ul class="lesson-points">...</ul>
</a>
```

它是课程级概览的主要来源，需要独立解析 `.course-card`，不能依赖 Reveal.js 选择器。

## 3. 输出目录与程序边界

```text
app/services/agent_doc_chunker.py
scripts/build_agent_doc_chunks.py
tests/test_agent_doc_chunker.py
corpus/Agent_doc/processed/
  agent_doc_chunks.jsonl
  agent_doc_manifest.json
```

### 3.1 `app/services/agent_doc_chunker.py`

纯解析与切块服务，负责：

- 解析 HTML；
- 清理非正文节点；
- 构建课程、讲次、章节和题目层级；
- 合并续页；
- 生成概览、问答、专题和趋势块；
- 拆分超长语义单元；
- 生成确定性 ID 与 JSON 可序列化记录。

该模块不读取应用环境变量、不访问数据库、不调用模型、不写 Chroma。

### 3.2 `scripts/build_agent_doc_chunks.py`

CLI 负责：

- 扫描输入目录下的 `.html`；
- 检测重复内容哈希；
- 调用切块服务；
- 校验 Chunk；
- 原子写入 JSONL 与 Manifest；
- 输出文件数、各类型 Chunk 数、长度分布和异常统计。

默认命令：

```powershell
.\.venv\Scripts\python.exe scripts\build_agent_doc_chunks.py
```

建议支持的最小参数：

```text
--source-dir corpus/Agent_doc
--output-dir corpus/Agent_doc/processed
--max-chars 1200
--fallback-overlap 100
```

不提前增加模型总结、并发、增量索引或 Chroma 参数。

### 3.3 HTML 解析依赖

在 `requirements.txt` 增加 `beautifulsoup4`，使用 Python 内置 `html.parser` 后端，避免第一版额外引入 Windows 二进制解析依赖。

## 4. HTML 清理与规范化

### 4.1 删除内容

解析后移除：

- `script`、`style`、`noscript`、`svg`；
- Reveal.js 控件、进度条和导航；
- `.scroll-hint`、`.mac-header`、`.mac-dot`、`.chapter-badge`；
- 知识地图中的 `.card-foot`、`.play-icon`；
- 只用于布局且没有正文的空节点。

文件名中的推广后缀不进入展示标题；讲次标题优先取页面 `<title>`、`h1.main-title` 或正文 `h1`。原始文件路径仍完整保留在 `source`。

### 4.2 保留内容

- 标题：转换为层级字段和可读文本；
- 段落：规范化连续空白；
- 列表：输出为 `- item` 或编号列表；
- 表格：输出为 Markdown 风格行，保留表头与单元格顺序；
- 代码：输出 fenced code block，语言优先取 `language-*` class；
- 强调、链接：保留可见文字，默认不把外部 URL 写入正文；
- 图片：第一版只保留非空 `alt`，不做 OCR。

普通正文统一为 `\n` 分隔；代码内部缩进和换行不得被普通空白规范化破坏。

## 5. 层级模型与语义单元

每个 Reveal.js 文档维护：

```text
course_title
lesson_title
current_h2
current_h3
ordered_slides
```

遍历规则：

1. 遇到 `h2`：结束上一语义单元，切换章节；
2. 遇到 `h3`：结束上一 `h3` 单元，开始新题目或专题；
3. 后续幻灯片没有新 `h2/h3`：并入当前单元；
4. 空白幻灯片跳过；
5. `h2` 下没有 `h3` 的正文：形成章节文章单元；
6. 文档开头未归属 `h2` 的有效正文：归入讲次导言，不静默丢弃。

完整 `h3` 单元即使很短也不与下一道题合并。语义完整优先于统一长度。

## 6. Chunk 类型

### 6.1 `course_overview`

由知识地图的课程标题与全部 `.course-card` 生成，包含：

- 课程名称；
- 各讲标题；
- 各讲简介；
- 各讲知识点列表。

用于回答：

- “2026 年 Agent 面试主要考什么？”
- “Agent 面试应该准备哪些方向？”
- “这套课程包含什么？”

如果整体超过 `max_chars`，只允许在课程卡片之间拆分，每个子块重复课程标题并标记 `part_index/part_count`。

### 6.2 `lesson_overview`

每个课程 HTML 生成一个讲次概览，内容由讲次标题、可用副标题和有序 `h2` 标题列表组成，不调用模型总结。

用于回答：

- “理论面试覆盖哪些模块？”
- “代码面试主要分几类？”

### 6.3 `section_overview`

当一个 `h2` 下存在多个 `h3` 时，生成章节概览：章节标题加有序 `h3` 标题列表。

例如：

```text
课程：Agent 求职面试全攻略
讲次：04 · 理论面试
章节：Agent 核心

本章覆盖：
- Q7：Agent 和 Chatbot 的本质区别
- Q8：ReAct 模式的核心思想
- Q9：Plan-Execute 和 ReAct 什么时候选哪个
```

### 6.4 `qa`

`h3` 标题匹配 `Q\d+` 或明确问句时，生成问答块。内容包括该标题及其全部续页正文。

示例：

```text
课程：Agent 求职面试全攻略
讲次：04 · 理论面试
章节：Agent 核心
问题：Q8【中级】ReAct 模式的核心思想？

ReAct = Reasoning + Acting（推理 + 行动）

每一轮：
1. Thought：当前该怎么办？
2. Action：调用什么工具、使用什么参数？
3. Observation：工具返回了什么？
4. 循环，直到产生 Final Answer。

这是当前所有 Agent 框架的基础模式。
```

### 6.5 `topic`

不属于明确问句的 `h3` 专题、案例或代码讲解生成 `topic`。切分边界与 `qa` 相同。

### 6.6 `article`

`h2` 下没有 `h3` 的连续正文生成 `article`，适用于导言、总结、路线图和独立专题。

### 6.7 `trend`

标题或正文明确包含年份范围、`最新进展`、`趋势` 等时效标记的章节，从 `article/topic` 中标记为 `trend`，并提取正文中明确出现的年份到 `time_tags`。

`time_tags` 只反映原文，例如 `[2025, 2026]`；切块程序不得把没有日期的内容推断为“当前最新”。

## 7. 长度与拆分规则

第一版使用字符计数，参数为候选基线，最终必须通过检索评测校准：

```text
max_chars = 1200
fallback_overlap = 100
```

不设置强制最小长度，也不为了填满窗口合并不同题目。

超长单元按以下顺序拆分：

1. 段落边界；
2. 列表项组；
3. 表格行组；
4. 完整代码块；
5. 单个结构块仍超长时，按空行、函数或类定义边界尝试拆分；
6. 最后才使用固定字符滑窗，并保留 `fallback_overlap`。

每个子块必须：

- 重复课程、讲次、章节与题目标题；
- 设置相同 `parent_id`；
- 设置递增 `part_index` 和最终 `part_count`；
- 不把普通题目正文与下一题合并；
- 不产生空块。

`max_chars` 约束正文 `content`；`embedding_text` 因重复层级标题可略长于该值。

## 8. JSONL Schema

`agent_doc_chunks.jsonl` 一行一个 UTF-8 JSON 对象：

```json
{
  "schema_version": 1,
  "chunk_id": "corpus/Agent_doc/.../04-理论面试.html#unit-008#part-00",
  "parent_id": "corpus/Agent_doc/.../04-理论面试.html#unit-008",
  "chunk_type": "qa",
  "source": "corpus/Agent_doc/.../04-理论面试.html",
  "course": "Agent 求职面试全攻略",
  "lesson": "04 · 理论面试",
  "title_path": [
    "Agent 核心",
    "Q8【中级】ReAct 模式的核心思想？"
  ],
  "question": "Q8【中级】ReAct 模式的核心思想？",
  "time_tags": [],
  "slide_start": 18,
  "slide_end": 19,
  "unit_index": 8,
  "part_index": 0,
  "part_count": 1,
  "contains_code": true,
  "content": "ReAct = Reasoning + Acting……",
  "embedding_text": "课程：Agent 求职面试全攻略\n讲次：04 · 理论面试\n章节：Agent 核心\n问题：Q8……\n\nReAct = Reasoning + Acting……",
  "content_sha256": "sha256:<hex>"
}
```

字段约束：

- 所有路径使用相对于项目根目录的 POSIX 路径；
- `chunk_id` 由 `source + unit_index + part_index` 确定，同一输入重复运行保持稳定；
- `parent_id` 标识拆分前语义单元；
- `title_path` 不包含空字符串；
- `question` 仅 `qa` 必填，其他类型为 `null`；
- `slide_start/slide_end` 是解析后的 1-based 内容幻灯片序号；知识地图概览为 `null`；
- `content_sha256` 对规范化后的 `content` 计算；
- `embedding_text` 包含完整层级，后续生成向量时使用；
- `content` 是提供给 Agent 阅读、引用和展示的正文。

输出顺序固定为：规范化 `source`、`unit_index`、`part_index`。

## 9. Manifest

`agent_doc_manifest.json` 记录：

```json
{
  "schema_version": 1,
  "source_root": "corpus/Agent_doc",
  "source_file_count": 11,
  "chunk_count": 0,
  "chunk_counts_by_type": {},
  "max_chars": 1200,
  "fallback_overlap": 100,
  "files": [
    {
      "source": "corpus/Agent_doc/.../04-理论面试.html",
      "content_sha256": "sha256:<hex>",
      "chunk_count": 0
    }
  ],
  "output_sha256": "sha256:<hex>",
  "fingerprint": "sha256:<hex>"
}
```

Manifest 不记录构建时间和绝对路径，保证相同输入与参数产生相同 fingerprint。文件与 Chunk 数由真实构建结果填写，设计文档中的 `0` 只是 Schema 示例。

如果扫描到两个内容 SHA-256 相同的 HTML，第一版直接失败并列出重复路径，避免相同内容污染后续 Top-K。

## 10. 原子输出与失败行为

1. JSONL 与 Manifest 先写入输出目录下的临时文件；
2. 完成所有解析、Schema 和哈希校验后再替换正式文件；
3. 任一 HTML 解码、解析或校验失败时返回非零；
4. 失败不得覆盖已有成功产物；
5. 输入目录不存在、没有 HTML、产生零 Chunk 或发现重复内容时返回清晰错误；
6. PDF 和 PNG 不进入本阶段处理范围。

## 11. 后续检索语义

本阶段只为后续检索保留能力，不实现路由：

- 宽泛问题优先使用 `course_overview`、`lesson_overview`、`section_overview`；
- 精确概念问题优先使用 `qa`、`topic`；
- 包含 `2025`、`2026`、`最新`、`趋势`、`今年` 的问题可提高 `trend` 权重；
- 命中超长单元的一个子块时，可通过 `parent_id` 补充相邻子块；
- 多个同父 Chunk 不应无限占满最终 Top-K，后续检索需要做父级去重或多样性控制。

Chroma 接入时应对 `embedding_text` 生成向量，但保存并返回 `content`。这一变更需要单独的检索设计与评测，不混入当前切块实现。

## 12. 测试与验收

严格 TDD，至少覆盖：

- Reveal.js `content-slide` 顺序解析；
- `h2/h3` 层级继承；
- 问题页与无标题续页合并；
- 遇到新 `h3/h2` 正确结束上一单元；
- 完整短问答不与下一题合并；
- 空白页与装饰控件被过滤；
- 段落、列表、表格和代码结构保留；
- 代码缩进与换行不被压平；
- 超长单元优先按结构边界拆分；
- 单个超长结构块才使用重叠滑窗；
- 每个子块重复完整标题上下文；
- `知识地图` 的 `.course-card` 生成课程概览；
- `2025-2026 最新进展` 提取 `time_tags=[2025, 2026]`；
- 确定性 ID、排序、JSONL 和 Manifest fingerprint；
- 重复 HTML 内容检测；
- 失败时不覆盖已有输出。

真实语料验收：

```text
输入 HTML 文件数 = 11
所有输入 HTML 都记录在 Manifest
知识地图至少产生 course_overview
10 个课程 HTML 都产生 lesson_overview
Q8 ReAct 的问题页和续页位于同一个 parent_id
不存在 script/style/Reveal 控件文本
不存在空 content
所有 source 均为相对 POSIX 路径
相同输入连续运行得到相同 JSONL SHA-256 与 Manifest fingerprint
```

验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_agent_doc_chunker.py -q
.\.venv\Scripts\python.exe scripts\build_agent_doc_chunks.py
.\.venv\Scripts\python.exe -m pytest tests -q
```

## 13. 非目标

本次不做：

- PDF 解析、图片 OCR 或多模态索引；
- 调用 LLM 生成摘要、改写问题或补充关键词；
- 验证文档中薪资、市场、年份和趋势陈述的真实性；
- 自动联网更新“最新面试趋势”；
- 修改现有 Markdown `knowledge_chunker`；
- 修改 `KnowledgeRepository`、Chroma Collection 或线上 `search_learning_notes`；
- 查询分类器、Reranker 或生成层 Prompt 调整；
- 直接把 JSONL 加入正式索引。

完成本阶段后，先人工抽查 JSONL，再基于新增面试语料建立独立检索评测集，最后决定如何接入现有 RAG。
