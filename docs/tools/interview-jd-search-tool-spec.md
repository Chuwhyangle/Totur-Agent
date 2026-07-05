# Tool Spec: interview_jd_search

## 1. 工具定位

`interview_jd_search` 是 Tutor Agent 的第一个真实工具调用能力。它让 Agent 可以搜索已经保存到本地 SQLite 的技术岗位 JD，并把岗位职责、技能要求、关键词、面试重点和 JD 原文片段返回给模型。

这个工具的核心价值不是替模型生成答案，而是给模型提供“当前项目里真实存在的岗位资料”。模型随后基于这些资料组织模拟面试、复习建议、追问和回答点评。

## 2. 目标

- 允许 Agent 根据用户的岗位方向、技术主题或面试意图搜索已保存 JD。
- 返回模型可直接使用的结构化岗位资料。
- 支持技术面试训练场景中的出题、追问、点评和复习重点规划。
- 保持工具接口小而稳定，后续可以在不改变入参和出参的前提下升级内部检索实现。

## 3. 非目标

- 不做互联网搜索。
- 不爬取招聘网站。
- 不读取 PDF、Word 或简历文件。
- 不做向量检索、embedding 或完整 RAG。
- 不做工具结果缓存。
- 不做并发工具调用。
- 不要求模型知道或传入数据库 `id`。
- 不直接生成最终用户回复。
- 不新增独立面试 session 状态表。

## 4. 适用场景

Agent 应该在这些场景优先调用 `interview_jd_search`：

- 用户想准备某个技术岗位面试。
- 用户要求根据 JD 或岗位要求制定复习重点。
- 用户要求模拟 AI Agent、RAG、Python AI、AI 全栈等技术面试。
- 用户要求根据岗位要求出题、追问或点评回答。
- 用户回答面试题后，Agent 需要判断回答是否覆盖岗位要求里的核心技能。

Agent 不应该在这些场景调用该工具：

- 普通寒暄。
- 用户询问当前产品功能怎么用。
- 用户表达情绪或闲聊。
- 总结当前对话。
- 与 JD、岗位、面试准备无关的普通学习辅导。

## 5. 工具接口

工具名：

```text
interview_jd_search
```

工具描述：

```text
Search saved technical interview job descriptions for responsibilities, skills, keywords, interview focus, and excerpts.
```

Python 调用边界：

```python
def search_interview_jds(query: str, limit: int = 3) -> dict[str, Any]:
    ...
```

OpenAI-compatible tool schema：

```json
{
  "type": "function",
  "function": {
    "name": "interview_jd_search",
    "description": "Search saved technical interview job descriptions for responsibilities, skills, keywords, interview focus, and excerpts.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "The role direction, technical topic, or interview intent to search for."
        },
        "limit": {
          "type": "integer",
          "description": "Maximum number of JD results to return.",
          "minimum": 1,
          "maximum": 5,
          "default": 3
        }
      },
      "required": ["query"],
      "additionalProperties": false
    }
  }
}
```

## 6. 参数说明

`query`

- 必填。
- 类型为非空字符串。
- 表达用户当前想搜索的岗位方向、技术主题或面试意图。
- 示例：`"AI Agent 工具调用 RAG 面试"`、`"Vue 全栈"`、`"Python LLM 应用开发"`。

`limit`

- 可选。
- 类型为整数。
- 默认值为 `3`。
- 最小值为 `1`，最大值为 `5`。
- 当前实现会对非法或越界值做安全归一化：无法解析时使用默认值，小于 `1` 时按 `1`，大于 `5` 时按 `5`。

不支持的参数：

- `id`：数据库内部记录编号，不暴露给模型。
- `user_id`：第一版工具搜索所有已保存 JD，暂不把权限边界交给模型控制。
- `raw_sql`：工具不接受 SQL，避免模型直接访问数据库。

## 7. 数据来源

运行时数据来源：

```text
SQLite interview_jds 表
```

示例数据来源：

```text
app/data/sample_interview_jds.json
```

工具运行时不直接搜索 JSON 文件。JSON 只用于开发、演示或初始化样例数据；真实搜索读取 SQLite 中已经保存的 JD 记录。

相关字段：

- `title`
- `role_family`
- `seniority`
- `raw_text`
- `responsibilities`
- `must_have`
- `core_skills`
- `preferred_skills`
- `bonus_skills`
- `keywords`
- `interview_focus`
- `updated_at`

工具输出不包含数据库 `id`。

## 8. 检索策略

第一版使用关键词检索，不做向量检索。

检索字段与权重：

| 字段 | 权重 |
| --- | ---: |
| `title` | 4 |
| `role_family` | 4 |
| `core_skills` | 3 |
| `keywords` | 3 |
| `interview_focus` | 3 |
| `responsibilities` | 2 |
| `must_have` | 2 |
| `preferred_skills` | 2 |
| `bonus_skills` | 2 |
| `raw_text` | 1 |

查询词处理：

- 将 query 转成小写并去掉首尾空白。
- 提取英文、数字、技术符号和连续中文词段。
- 对常见技术词做补充识别，例如 `ai`、`llm`、`rag`、`mcp`、`python`、`fastapi`、`langchain`、`工具调用`、`智能体`、`全栈`。
- 对每条 JD 逐字段计算命中分数。

排序策略：

```text
先按 match_score 降序，再按 updated_at 降序，最后按 title 降序。
```

返回策略：

```text
只返回前 limit 条命中的 JD。
```

## 9. 成功返回

有匹配结果时：

```json
{
  "ok": true,
  "query": "Agent RAG",
  "items": [
    {
      "title": "Python AI Agent 开发工程师",
      "role_family": "python_ai_agent_engineer",
      "seniority": "junior_mid",
      "match_score": 12,
      "matched_fields": ["core_skills", "keywords", "interview_focus"],
      "responsibilities": [
        "基于 LLM 开发 AI Agent",
        "封装 Function Calling 工具接口"
      ],
      "must_have": [
        "Python 编程能力",
        "大模型 API 调用经验"
      ],
      "core_skills": [
        "Python",
        "LLM API",
        "Function Calling",
        "RAG"
      ],
      "preferred_skills": [
        "MCP",
        "A2A"
      ],
      "bonus_skills": [
        "NetOps/AIOps"
      ],
      "keywords": [
        "Python",
        "Agent",
        "LLM",
        "Function Calling",
        "RAG"
      ],
      "interview_focus": [
        "Agent 工具调用流程",
        "RAG 基本架构"
      ],
      "raw_text_excerpt": "负责 Agent 工具调用和 RAG 应用开发..."
    }
  ],
  "summary": {
    "returned_count": 1,
    "searched_count": 2
  }
}
```

无匹配结果时仍然是成功执行：

```json
{
  "ok": true,
  "query": "量子通信产品经理",
  "items": [],
  "summary": {
    "returned_count": 0,
    "searched_count": 1
  },
  "message": "No interview JD matched the query."
}
```

## 10. 错误返回

空 query：

```json
{
  "ok": false,
  "error": "invalid_arguments",
  "message": "query must be a non-empty string."
}
```

未知工具名由 `ToolExecutor` 处理：

```json
{
  "ok": false,
  "error": "tool_not_found",
  "message": "unknown tool: unknown_tool"
}
```

工具参数不是 JSON object 时由 `ToolExecutor` 处理：

```json
{
  "ok": false,
  "error": "invalid_arguments",
  "message": "tool arguments must be a JSON object."
}
```

工具运行异常由 `ToolExecutor` 兜底：

```json
{
  "ok": false,
  "error": "tool_execution_failed",
  "message": "tool execution failed: <reason>"
}
```

## 11. Agent 使用规则

模型拿到工具结果后，不应该把 JD 原文和字段机械堆给用户，而应该把结果转化为教学或面试训练动作。

推荐行为：

- 提炼岗位核心要求。
- 根据 JD 重点问一道面试题。
- 点评用户回答覆盖了哪些岗位要求。
- 指出遗漏点，并给出更面试化的表达。
- 在 `items` 为空时说明当前 JD 库没有匹配资料，再给出通用兜底建议。

限制：

- 模拟面试时一次只问一个问题。
- 不声称工具结果来自互联网。
- 不编造工具没有返回的具体 JD 信息。
- 不把 `match_score` 当作岗位匹配百分比，它只是内部排序分数。

## 12. Message 回填方式

当模型发起 tool call：

```json
{
  "name": "interview_jd_search",
  "arguments": {
    "query": "AI Agent RAG 面试",
    "limit": 3
  }
}
```

后端执行工具后，把工具结果作为 `role="tool"` 消息回填给模型。模型第二次调用时基于工具结果生成最终 `TutorReply` JSON。

第一版 `/chat` 每次请求最多执行一轮工具调用。第二次模型调用不再传入 tools，避免工具循环。

## 13. 风险与处理

LLM 传错参数：

- `ToolExecutor` 解析参数。
- `search_interview_jds` 校验 query。
- 返回结构化错误，允许模型生成兜底回复。

无匹配 JD：

- 工具返回 `ok=true` 和空 `items`。
- Agent 需要明确说明“当前已保存 JD 中没有匹配结果”。
- Agent 可以用通用经验继续辅导，但要说明不是基于已保存 JD。

返回内容过长：

- 工具只返回 `raw_text_excerpt`，不返回完整 `raw_text`。
- `limit` 最大为 `5`。
- 单个 excerpt 当前限制为约 `140` 字符。

死循环调用：

- 第一版由 Agent 编排层限制每次 `/chat` 最多一轮工具调用。
- 第二次模型调用不再提供 tools。

工具执行超时：

- 当前实现是本地 SQLite 小数据量关键词检索，没有单独 timeout。
- 如果后续检索接入网络、向量数据库或 MCP，应在 `ToolExecutor` 层增加 per-tool timeout，并把超时转换为结构化错误：

```json
{
  "ok": false,
  "error": "tool_timeout",
  "message": "tool execution timed out."
}
```

数据隔离：

- 当前第一版工具搜索所有已保存 JD。
- 如果后续引入多用户隔离，应在工具执行上下文中注入 `user_id`，而不是让模型直接传 `user_id`。

## 14. 验收标准

- `ToolRegistry.get_tools_schema()` 暴露 `interview_jd_search`。
- schema 只包含 `query` 和 `limit`，不包含数据库 `id`。
- `ToolExecutor` 可以执行字典参数形式的工具调用。
- `ToolExecutor` 可以执行 JSON 字符串参数形式的工具调用。
- 未知工具名返回 `tool_not_found`。
- 非法参数返回 `invalid_arguments`。
- 搜索 `Agent RAG` 能返回 AI Agent 相关 JD。
- 搜索 `Vue 全栈` 能返回 AI 全栈相关 JD。
- 搜索不存在主题时返回空 `items`，而不是报错。
- `limit` 能限制返回数量。
- 工具输出不暴露数据库 `id`。
- `/chat` 工具路径中，模型第一次请求工具，后端执行工具，模型第二次生成最终 `TutorReply` JSON。

## 15. 当前相关文件

- `app/services/agent/tools/interview_jd_search.py`
- `app/services/agent/tools/registry.py`
- `app/services/agent/tools/executor.py`
- `tests/test_interview_jd_search.py`
- `tests/test_agent_tools.py`
- `docs/superpowers/specs/2026-07-04-technical-interview-tool-calling-design.md`

## 16. 后续演进

接口保持不变时，可以替换或增强内部实现：

- 从关键词检索升级到 embedding 检索。
- 增加 rerank。
- 增加 `user_id` 执行上下文，实现多用户隔离。
- 将工具封装成 MCP server。
- 增加 `parse_job_description`，从 raw JD 自动抽取结构化字段。
- 增加 `jd_project_match`，把 JD 要求和用户项目经历做匹配。
