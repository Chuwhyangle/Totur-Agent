# 技术面试 Tutor Agent 工具调用设计

## 1. 文档目标

这份文档定义 Tutor Agent 下一阶段的工具调用能力。后续开发以本文档为准，再基于它拆实现计划。

当前项目已经具备：

- FastAPI 后端和 `/chat` 聊天接口
- React 前端聊天界面
- SQLite 对话历史
- 多会话管理
- 会话滚动摘要
- `TutorAgentService`、`PromptBuilder`、`ResponseParser`、`MemoryManager` 等 Agent Core 组件

下一阶段的目标不是做通用工具平台，也不是直接上完整 RAG，而是先完成一个小而真实的 function calling 闭环：

```text
用户提出技术面试训练需求
-> 模型判断需要查目标岗位 JD
-> 后端执行 interview_jd_search 工具
-> 工具返回职责、技能要求、关键词、面试重点和原文片段
-> 模型基于工具结果生成结构化导师回复
```

## 2. 产品定位

这一阶段的 Tutor Agent 从“普通学习辅导”向“技术面试训练导师”扩展。

第一版聚焦技术面试，而不是期末复习、考公考研、论文学习或代码检查。

目标用户场景：

- 用户想准备某个技术岗位面试
- 用户想知道某类 JD 应该重点准备什么
- 用户希望 Agent 根据岗位要求问一道题
- 用户回答后，希望 Agent 按岗位职责、核心技能和面试重点指出覆盖点和漏点
- 用户想继续被追问，模拟真实面试
- 用户想把当前项目经验转化为面试表达

第一版重点是让 Agent 像面试教练，而不是像百科问答机器人。

## 3. 为什么需要工具

LLM 本身已经擅长：

- 解释概念
- 生成示例答案
- 模拟面试官语气
- 润色回答
- 生成练习题

但 LLM 只靠自身记忆做不好这些事：

- 不知道当前资料库里有哪些真实 JD
- 不知道某个岗位到底强调哪些职责和技术栈
- 不知道岗位优先项和加分项的权重
- 不能稳定围绕同一批 JD 给用户组织训练
- 不能基于用户自己的 JD、项目经历和历史薄弱点做个性化训练

所以工具调用的价值是让 Agent 接触“外部真实资料”，而不是凭空编答案。

第一版工具不追求大而全，只解决一个核心问题：

```text
当用户进行技术面试训练时，Agent 可以主动检索已保存的 JD，并基于岗位职责、技能要求和面试重点提问、点评和追问。
```

## 4. 与 RAG、MCP 的关系

本阶段采用 function calling 作为调用机制。

三者关系如下：

```text
function calling / tool calling：模型如何请求外部工具
RAG：工具内部如何检索资料并把资料提供给模型
MCP：未来如何把工具作为独立服务暴露给多个客户端或 Agent
```

第一版：

```text
interview_jd_search = function calling + SQLite JD 关键词搜索
```

未来升级：

```text
interview_jd_search = function calling + embedding 向量检索 + rerank
```

再往后：

```text
ToolExecutor -> MCP client -> 外部 interview JD/material MCP server
```

因此，本阶段先做 function calling，不直接实现完整 RAG 或 MCP。这样可以先学习清楚 Agent 编排闭环，同时不堵死后续演进路径。

## 5. 方案比较

### 推荐方案：岗位 JD 搜索工具

工具名：

```text
interview_jd_search
```

能力：

- 搜索已保存的技术岗位 JD
- 返回岗位职责、核心技能、优先技能、关键词、面试重点和原文片段
- 支持 Agent 根据真实岗位要求组织模拟面试、备考建议和追问

优点：

- 工具价值明显
- 实现范围小
- 已经有 JD 存储地基和真实样例数据
- 可以自然升级为 JD RAG、JD + 项目匹配、题库联动
- 与当前 Tutor Agent 的“技术面试复习”方向贴合

缺点：

- 第一版不能直接返回标准题库答案
- 需要 Agent 把岗位要求转化成面试流程

### 替代方案：技术面试题库搜索

工具名可以是：

```text
interview_material_search
```

能力覆盖题目、评分点、常见误区和追问。

优点是更像传统面试题库，缺点是第一版还没有整理好题库数据，而且容易把重点放在“查题”而不是“围绕目标岗位训练”上。该工具放到 JD 搜索之后实现。

### 进阶替代：JD + 简历匹配工具

工具名可以是：

```text
jd_resume_match
```

能力：

- 读取用户粘贴的 JD
- 读取用户简历或项目经历
- 找出岗位要求和用户经历的匹配点
- 生成项目追问

这个方向产品感更强，但第一版输入流程和数据结构更复杂，暂不作为首个工具。

## 6. 第一版功能范围

第一版只做一个工具：

```text
interview_jd_search
```

第一版支持四种对话能力：

1. 岗位重点识别

```text
用户：我想准备 AI Agent 开发岗位面试。
Agent：调用 interview_jd_search，找到相关 JD，提炼岗位职责、核心技能和面试重点。
```

2. 模拟面试开场

```text
用户：根据这个岗位问我一道题。
Agent：调用 interview_jd_search，围绕 JD 中的 Agent、RAG、Function Calling 等要求提出一道面试题。
```

3. 面试回答点评

```text
用户回答上一道题。
Agent：调用 interview_jd_search，参考 JD 的核心技能和面试重点，指出回答和岗位要求的匹配点、漏点和补强方向。
```

4. 追问

```text
用户：继续追问我。
Agent：调用 interview_jd_search，基于 JD 中的职责和优先技能继续追问。
```

## 7. 第一版非目标

第一版明确不做：

- 不做联网搜索
- 不做爬取招聘网站或面试题网站
- 不做 PDF、Word、简历上传解析
- 不做向量数据库
- 不做 embedding
- 不做完整 RAG
- 不做 MCP server
- 不做代码执行工具
- 不做长期错题统计
- 不新增面试 session 表
- 不改 `/chat` 请求格式
- 不改 `/chat` 响应格式
- 不要求前端立刻新增专门的面试 UI

第一版最终响应继续使用现有 `TutorReply`：

```text
answer
next_task
exercise
checkpoints
```

## 8. 面试资料来源

第一版使用已保存的岗位 JD 作为面试资料来源。

数据来源优先级：

1. 用户收集并粘贴的真实技术岗位 JD
2. 当前项目相关的 AI Agent / LLM 应用开发岗位
3. Python AI、AI 全栈、AI 应用开发等相近岗位
4. 后续再加入题库、项目经历和历史回答

第一版不自动从互联网抓取数据。

首批 JD 聚焦当前项目和常见 AI 应用开发面试：

- AI Agent / LLM 应用开发
- Python AI Agent 开发
- AI 全栈开发
- AI 应用开发 / 工作流搭建

## 9. 第一版 JD 范围

第一版先保存少量真实 JD，每条 JD 代表一种目标岗位画像。数量不用多，3 到 5 条足够支撑工具调用闭环。

首批 JD 应覆盖：

- LLM / Agent 应用开发
- RAG / Function Calling / 工具调用
- LangChain / LangGraph / AutoGen 等 Agent 框架
- Python / Java / Vue / Web API / 数据库 / 部署等工程基础
- Prompt 设计、上下文管理、效果评估
- 后端或全栈落地能力

第一版不追求 JD 数量，而是追求字段完整：标题、原文、职责、核心技能、优先技能、关键词和面试重点都要尽量可检索。

## 10. 数据组织

第一版 JD 存在 SQLite 表：

```text
interview_jds
```

种子数据可以保存在 JSON 文件中，作为开发和演示数据来源：

```text
app/data/sample_interview_jds.json
```

但工具运行时不直接查这个 JSON，而是查 SQLite 表。JSON 只负责方便导入和复现样例数据。

未来如果加入题库，再单独新增：

```text
app/data/interview_materials.json
```

## 11. 数据结构

`interview_jds` 表的核心字段：

```text
id
user_id
title
role_family
seniority
target_graduation_years_json
raw_text
responsibilities_json
must_have_json
core_skills_json
preferred_skills_json
bonus_skills_json
keywords_json
interview_focus_json
created_at
updated_at
```

工具输出不暴露数据库 `id`，但数据库内部仍然保留 `id`，用于普通 API、列表展示、后续编辑删除等场景。

示例工具输出条目：

```json
{
  "title": "Python AI Agent 开发工程师",
  "role_family": "python_ai_agent_engineer",
  "seniority": "junior_mid",
  "match_score": 12,
  "matched_fields": ["core_skills", "keywords", "interview_focus"],
  "responsibilities": ["基于 LLM 开发 AI Agent"],
  "must_have": ["Python 或 Java 编程能力"],
  "core_skills": ["Function Calling", "RAG", "LLM API"],
  "preferred_skills": ["MCP", "A2A"],
  "bonus_skills": ["NetOps/AIOps"],
  "keywords": ["Python", "Agent", "RAG"],
  "interview_focus": ["Agent 工具调用流程"],
  "raw_text_excerpt": "负责基于 LLM 的 AI Agent 开发..."
}
```

字段要求：

- `title`：岗位标题，必须存在
- `raw_text`：JD 原文，必须存在
- `responsibilities`：岗位职责，可为空列表
- `must_have`：基础要求，可为空列表
- `core_skills`：核心技能，可为空列表
- `preferred_skills`：优先技能，可为空列表
- `bonus_skills`：加分项，可为空列表
- `keywords`：检索关键词，可为空列表
- `interview_focus`：面试重点，可为空列表

## 12. 工具接口设计

工具名：

```text
interview_jd_search
```

用途：

```text
Search saved technical interview job descriptions for responsibilities, skills, keywords, interview focus, and relevant JD excerpts.
```

输入参数：

```json
{
  "query": "AI Agent 工具调用 RAG 面试",
  "limit": 3
}
```

字段说明：

- `query`：必填，用户当前想准备的岗位方向、技术主题或面试意图
- `limit`：可选，默认 3，最小 1，最大 5

第一版工具参数不使用 `id`。`id` 只属于数据库内部记录和普通 API，不暴露给模型工具调用。模型表达的是检索意图，不应该被要求知道某条 JD 的数据库编号。

第一版也不设计 `shared/private`。所有已保存的 JD 都可以被检索。等产品真的出现用户资料隔离或公共资料库需求，再扩展数据权限模型。

输出结构：

```json
{
  "ok": true,
  "query": "AI Agent 工具调用 RAG 面试",
  "items": [
    {
      "title": "Python AI Agent 开发工程师",
      "role_family": "python_ai_agent_engineer",
      "seniority": "junior_mid",
      "match_score": 12,
      "matched_fields": ["core_skills", "keywords", "interview_focus"],
      "responsibilities": [
        "基于 LLM 开发 AI Agent",
        "封装 Function Calling 工具接口",
        "对接主流大模型 API"
      ],
      "must_have": ["Python 或 Java 编程能力", "大模型 API 调用经验"],
      "core_skills": ["Python", "LLM API", "Function Calling", "RAG"],
      "preferred_skills": ["MCP", "A2A"],
      "bonus_skills": ["NetOps/AIOps", "ICT 行业经验"],
      "keywords": ["Python", "Agent", "LLM", "Function Calling", "RAG"],
      "interview_focus": ["Agent 工具调用流程", "RAG 基本架构"],
      "raw_text_excerpt": "负责基于 LLM 的 AI Agent 开发，构建具备感知、规划、工具调用能力的智能应用..."
    }
  ],
  "summary": {
    "returned_count": 1,
    "searched_count": 4
  }
}
```

无结果时：

```json
{
  "ok": true,
  "query": "量子通信产品经理",
  "items": [],
  "summary": {
    "returned_count": 0,
    "searched_count": 4
  },
  "message": "No interview JD matched the query."
}
```

错误时：

```json
{
  "ok": false,
  "error": "invalid_arguments",
  "message": "query must be a non-empty string."
}
```

## 13. 搜索策略

第一版使用关键词搜索，不做向量检索。

搜索字段：

- `title`
- `role_family`
- `responsibilities`
- `must_have`
- `core_skills`
- `preferred_skills`
- `bonus_skills`
- `keywords`
- `interview_focus`
- `raw_text`

排序策略：

```text
按 query 关键词在各字段中的命中数量和字段权重排序。
title、role_family 命中权重最高。
core_skills、keywords、interview_focus 命中权重较高。
responsibilities、must_have、preferred_skills、bonus_skills 次之。
raw_text 命中权重最低，只作为兜底召回。
返回前 limit 条。
```

建议权重：

```text
title / role_family：+4
core_skills / keywords / interview_focus：+3
responsibilities / must_have / preferred_skills / bonus_skills：+2
raw_text：+1
```

第一版搜索质量只需要支撑小型 JD 库，不追求复杂相关性排序。后续数据量变大后，可以在不改变工具输入输出的前提下，把内部实现替换为 embedding/RAG 检索。

## 14. Agent 调用工具策略

Agent 不应每轮都调用工具。

需要调用 `interview_jd_search` 的场景：

- 用户想准备某个技术岗位面试
- 用户要求根据 JD 或岗位要求制定复习重点
- 用户要求模拟 AI Agent、RAG、Python AI、AI 全栈等技术面试
- 用户要求 Agent 根据岗位要求出题、追问或点评
- 用户回答后，Agent 需要判断回答是否覆盖岗位要求中的核心技能

不需要调用工具的场景：

- 普通寒暄
- 解释当前功能怎么用
- 用户表达情绪
- 总结当前对话
- 与 JD、岗位、面试准备无关的普通学习辅导

系统提示词需要强调：

```text
你是技术面试训练导师。
当用户要准备岗位面试、根据 JD 出题、评分、追问或规划复习重点时，优先调用 interview_jd_search。
如果正在模拟面试，一次只问一个问题。
用户回答后，按岗位职责、核心技能和面试重点指出覆盖点、漏点，并给出更好的面试化回答。
最终回复必须是 JSON，包含 answer、next_task、exercise、checkpoints。
```

## 15. 模拟面试流程

第一版模拟面试采用轻量流程，不新增专门状态表。

基本循环：

```text
1. 用户选择方向
   例：我想练 AI Agent 开发岗位面试

2. Agent 调用 interview_jd_search
   query = AI Agent 开发 岗位 面试
   limit = 3

3. Agent 从 JD 结果中提炼岗位重点
   例如：Function Calling、RAG、LangChain、上下文管理、API 集成

4. Agent 围绕一个重点提出一道题
   一次只问一道题

5. 用户回答

6. Agent 必要时再次调用 interview_jd_search
   query = 最近题目关键词 + 岗位方向
   limit = 1

7. Agent 按 JD 中的职责、技能要求和面试重点给反馈

8. Agent 引导用户选择：
   重答、追问、换一个 JD 重点
```

第一版不强制自动跑完整面试。每轮只推进一个小步骤。

## 16. TutorReply 映射

第一版不改 API 响应结构。面试模式下仍然使用：

```text
answer
next_task
exercise
checkpoints
```

映射规则：

- `answer`：当前轮的主要反馈、提问、讲解或评分
- `next_task`：用户下一步要做什么
- `exercise`：一个具体练习，例如重答、举例、补充一个场景
- `checkpoints`：本题评分点或回答检查点

示例：

```json
{
  "answer": "这题我给 2/4。你答到了 useEffect 在渲染后执行，也知道 useLayoutEffect 更早，但漏了浏览器绘制前/后、同步/异步、是否阻塞绘制这三个面试关键词。",
  "next_task": "请你用 45 秒重新回答一次，必须包含“绘制后异步”和“绘制前同步”这两个短语。",
  "exercise": "用一个实际场景说明什么时候会考虑 useLayoutEffect。",
  "checkpoints": [
    "能说出 useEffect 在浏览器绘制后异步执行",
    "能说出 useLayoutEffect 在浏览器绘制前同步执行",
    "能说明 useLayoutEffect 可能阻塞绘制"
  ]
}
```

## 17. 后端模块设计

新增模块放在：

```text
app/services/agent/tools/
```

建议结构：

```text
app/services/agent/tools/
  __init__.py
  registry.py
  executor.py
  interview_jd_search.py
```

职责划分：

`ToolRegistry`：

- 提供 OpenAI-compatible tools schema
- 注册可用工具
- 第一版只注册 `interview_jd_search`

`ToolExecutor`：

- 接收模型返回的 tool call
- 校验工具名
- 解析参数
- 执行对应工具
- 返回结构化工具结果
- 遇到未知工具或参数错误时返回结构化错误，不让 `/chat` 崩溃

`InterviewJDSearchTool`：

- 从 SQLite 的 `interview_jds` 表读取已保存 JD
- 执行关键词搜索
- 返回匹配 JD 的岗位职责、技能要求、面试重点和原文片段

`TutorAgentService`：

- 继续作为 `/chat` 主流程编排入口
- 从“一次模型调用”扩展为“最多一轮工具调用 + 最终模型回复”
- 不直接实现具体搜索逻辑

## 18. Function Calling 主流程

当前主流程：

```text
PromptBuilder.build_messages(context)
-> call model
-> ResponseParser.parse_model_reply(raw_reply)
-> MemoryManager.save_turn_and_update_summary(...)
-> return ChatResponse
```

第一版工具调用后：

```text
PromptBuilder.build_messages(context)
-> call model with tools
-> 如果模型没有 tool_calls：
     parse content
-> 如果模型有 tool_calls：
     append assistant tool_calls message
     ToolExecutor 执行工具
     append tool result messages
     call model again without further tool calls
     parse final content
-> MemoryManager.save_turn_and_update_summary(...)
-> return ChatResponse
```

第一版限制：

```text
每次 /chat 最多执行一轮工具调用。
```

这样避免复杂 Agent loop，同时足以演示 function calling。

## 19. 模型消息处理

第一次模型调用：

- 带上 `tools`
- 使用 `tool_choice="auto"`
- 允许模型选择是否调用工具

如果没有工具调用：

- 使用模型 `content` 作为最终回复
- 走现有解析逻辑

如果有工具调用：

- 把 assistant 的 tool call 消息加入 `messages`
- 每个工具结果作为 `role="tool"` 消息加入 `messages`
- 第二次调用模型生成最终 JSON
- 第二次调用不再传 tools，避免多轮工具循环

最终内容必须交给 `ResponseParser.parse_model_reply(...)` 解析成 `TutorReply`。

## 20. PromptBuilder 调整

`PromptBuilder` 仍负责构建 messages，不负责执行工具。

系统提示词需要从“新手友好的后端开发导师”调整为兼容两种模式：

- 普通学习辅导
- 技术面试训练

提示词关键要求：

```text
你是一个学习导师，也可以作为技术面试训练导师。
当用户明确要准备岗位面试、根据 JD 练习、请求评分、追问或规划复习重点时，优先调用 interview_jd_search。
工具返回的 JD 是依据，不要原样堆给用户。
最终回复必须是 JSON，不要返回 Markdown，不要返回 JSON 之外的文字。
如果正在模拟面试，一次只问一个问题。
用户回答后，按岗位职责、核心技能和面试重点指出覆盖点和漏点。
```

## 21. 错误处理

工具搜不到资料：

```text
Agent 明确说明当前 JD 库没有找到对应岗位资料。
Agent 可以按通用经验临时组织面试练习，但要说明这不是基于已保存 JD。
Agent 推荐用户补充或切换到已有方向，例如 AI Agent、Python AI、AI 全栈、AI 应用开发。
```

工具执行失败：

```text
ToolExecutor 返回 ok=false 的结构化错误。
模型基于错误结果生成兜底回复。
不让 /chat 因工具失败直接崩溃。
```

模型未返回最终内容：

```text
沿用现有空回复错误处理。
```

模型最终返回非 JSON：

```text
沿用 ResponseParser fallback，保证 API 响应结构稳定。
```

未知工具名：

```text
ToolExecutor 返回 tool_not_found 错误。
```

参数错误：

```text
ToolExecutor 返回 invalid_arguments 错误。
```

## 22. 测试策略

新增测试应覆盖：

1. JD 搜索

- 搜索 Agent / RAG 能返回 AI Agent 相关 JD
- 搜索全栈 / Vue 能返回 AI 全栈相关 JD
- 搜索不存在主题返回空 items
- limit 生效
- 工具输出不暴露数据库 `id`

2. ToolRegistry

- tools schema 包含 `interview_jd_search`
- schema 只包含 query、limit 参数

3. ToolExecutor

- 合法 tool call 能执行
- 未知工具返回结构化错误
- 非法参数返回结构化错误

4. TutorAgentService 无工具路径

- 模型直接返回最终 JSON 时，现有 `/chat` 行为保持可用

5. TutorAgentService 有工具路径

- fake client 第一次返回 tool call
- 后端执行 `interview_jd_search`
- fake client 第二次返回最终 TutorReply JSON
- 最终 `ChatResponse.reply` 正常解析
- 对话保存逻辑仍然执行

6. PromptBuilder

- 系统提示词包含技术面试训练和工具调用规则
- 仍然保留 JSON 输出要求

## 23. 验收标准

功能验收：

- `/chat` 可以处理普通学习问题，原有行为不破坏
- 用户说“我想练 AI Agent 岗位面试”时，模型可以调用 `interview_jd_search`
- 工具能从已保存 JD 中返回相关岗位要求
- Agent 能基于 JD 结果问一道技术面试题
- 用户回答后，Agent 能基于岗位职责、核心技能和面试重点给出覆盖点、漏点和改进建议
- 用户要求追问时，Agent 能基于 JD 要求提出下一问
- 工具无结果时，Agent 能给出清楚兜底说明
- 所有现有测试通过
- 新增工具相关测试通过

学习验收：

- 能解释 function calling 的完整流程
- 能解释为什么第一版不直接做 RAG
- 能解释工具调用和 RAG、MCP 的关系
- 能解释 `ToolRegistry` 和 `ToolExecutor` 的职责
- 能解释为什么第一版只允许一轮工具调用

## 24. 开发阶段建议

后续实现计划应拆成以下阶段：

1. JD 搜索阶段

- 复用已存在的 `interview_jds` 表和种子 JD
- 实现全表 JD 检索，不按 `id` 查询
- 返回结构化岗位要求和原文片段

2. 工具阶段

- 实现 `InterviewJDSearchTool`
- 实现关键词搜索
- 补 JD 搜索测试

3. Registry / Executor 阶段

- 实现 `ToolRegistry`
- 实现 `ToolExecutor`
- 补工具注册和执行测试

4. Agent 编排阶段

- 修改 `TutorAgentService`
- 支持第一次模型调用请求工具
- 支持执行工具后第二次模型调用生成最终回复
- 限制每次请求最多一轮工具调用

5. Prompt 阶段

- 更新系统提示词
- 让模型理解技术面试训练模式
- 保持最终 JSON 输出要求

6. 端到端测试阶段

- 用 fake client 模拟 tool call
- 验证 `/chat` 工具路径
- 验证普通聊天路径不受影响

7. 手动体验阶段

- 启动 API
- 用真实模型测试“我想练 AI Agent 岗位面试”
- 测试“继续追问我”
- 测试“我的答案是……请评分”

## 25. 后续演进

第一版完成后，可以逐步加入：

1. 面试反馈记忆

```text
save_interview_feedback
get_weak_interview_points
```

用于记录用户哪些评分点经常漏掉。

2. JD 和项目经历工具

```text
save_target_jd
search_user_project_experience
jd_project_match
```

用于将用户项目包装成面试表达。

3. RAG 升级

```text
interview_jd_search 内部从关键词搜索升级为 embedding 检索。
```

接口保持不变，替换内部检索实现。

4. MCP 化

```text
把 interview_jd_search 或后续 interview_material_search 做成独立 MCP tool server。
```

适合未来多个 Agent 或客户端复用同一套面试资料工具。

5. 代码执行工具

仅当产品范围扩展到编程面试、算法题、SQL 题或数据分析题时再加入。

## 26. JD 资料存储与岗位匹配扩展

用户粘贴的岗位 JD 不应直接混入 `interview_materials.json` 题库。题库资料和 JD 资料的用途不同：

```text
interview_materials.json：存面试题、评分点、常见误区和追问
interview_jds：存岗位描述、职责、技能要求、关键词和面试重点
```

JD 的第一版用途是先建立“岗位资料地基”，再用 `interview_jd_search` 把这批资料接入工具调用：

- 用户可以通过表单保存目标岗位 JD
- 后端可以按 `user_id` 保存和查询 JD
- Agent 未来可以基于 JD 判断岗位重点、生成备考路径、匹配项目经历
- 后续工具可以从 JD 中检索职责、核心技能、优先技能和加分项

第一版 JD 采用 SQLite 存储，而不是只放本地 JSON。原因是 JD 来自用户输入，需要随用户和时间变化；JSON 更适合内置种子资料，SQLite 更适合用户数据。

建议新增表：

```text
interview_jds
```

核心字段：

```text
id
user_id
title
role_family
seniority
target_graduation_years_json
raw_text
responsibilities_json
must_have_json
core_skills_json
preferred_skills_json
bonus_skills_json
keywords_json
interview_focus_json
created_at
updated_at
```

第一版表单只需要覆盖最关键字段：

- `title`：岗位名称，例如“AI Agent / LLM 应用开发岗位”
- `raw_text`：用户粘贴的完整 JD 原文
- `core_skills`：核心技能，例如 LangChain、LangGraph
- `preferred_skills`：优先技能，例如 RAG、Agent 评测
- `keywords`：检索关键词，例如 LLM、Agent、RAG、FastAPI
- `interview_focus`：面试准备重点，例如 Agent 工具调用、RAG 系统设计

表单不负责自动解析所有 JD 细节。第一版允许用户手动填写结构化字段；后续可以加入 `parse_job_description` 工具，由 LLM 根据 `raw_text` 自动提取字段。

建议新增 API：

```text
POST /interview-jds
GET /interview-jds?user_id=...
```

`POST /interview-jds` 用于保存一条 JD；`GET /interview-jds` 用于查询某个用户保存过的 JD。第一版不做删除和编辑，避免范围过大。

示例数据可先保存一条 AI Agent 岗位 JD，覆盖：

- LLM Agent 应用开发
- RAG 系统设计
- LangChain / LangGraph 工作流
- Agent 评测
- Python、FastAPI、Docker、Git、NLP 等加分项

这条 JD 与当前 Tutor Agent 项目高度相关，可以用于后续项目包装和模拟面试：

```text
当前项目已经具备 FastAPI 后端、React 前端、多会话、滚动摘要和结构化回复。
下一阶段加入 function calling 和 interview_jd_search 后，可以对应 JD 中的 Agent 应用、工具使用、多轮对话、RAG 演进和后端落地能力。
```

后续工具演进建议：

```text
interview_jd_search：检索已保存的 JD
jd_project_match：把 JD 要求和用户项目经历做匹配
parse_job_description：把 raw_text 自动拆成职责、技能、关键词和面试重点
interview_material_search：检索题库、评分点、常见误区和追问
```

第一版开发顺序应先做 JD 存储和表单，再做 `interview_jd_search`。这样工具不是凭空查题，而是可以围绕真实目标岗位生成训练内容。题库型 `interview_material_search` 放到后续阶段，用于给 JD 重点匹配更标准的题目和评分点。

## 27. 当前设计结论

第一版技术面试工具调用设计如下：

```text
复用 interview_jds 表中已经保存的技术岗位 JD。
新增 interview_jd_search 工具，先用关键词检索 JD。
工具输入只包含 query 和 limit，不要求模型传数据库 id。
第一版不设计 shared/private，所有已保存 JD 都可被检索。
新增 ToolRegistry 和 ToolExecutor，接入 OpenAI-compatible function calling。
TutorAgentService 支持最多一轮工具调用，然后生成最终 TutorReply JSON。
Agent 在用户准备岗位面试、请求根据 JD 出题、评分、追问或规划复习重点时调用工具。
第一版不实现完整 RAG、MCP、联网搜索、代码执行、题库搜索或长期错题系统。
```

这条路线能用最小工程量看清楚工具调用，同时保留未来升级成 RAG 和 MCP 的空间。
