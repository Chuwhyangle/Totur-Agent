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
-> 模型判断需要查面试资料
-> 后端执行 interview_material_search 工具
-> 工具返回题目、评分点、常见误区和追问
-> 模型基于工具结果生成结构化导师回复
```

## 2. 产品定位

这一阶段的 Tutor Agent 从“普通学习辅导”向“技术面试训练导师”扩展。

第一版聚焦技术面试，而不是期末复习、考公考研、论文学习或代码检查。

目标用户场景：

- 用户想练某个技术方向的面试题
- 用户想知道某道技术面试题怎么答
- 用户回答后，希望 Agent 按评分点指出覆盖点和漏点
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

- 不知道题库里有哪些题
- 不知道某道题的固定评分点
- 不知道常见误区和追问
- 不能稳定复用同一套标准给用户打分
- 不能基于用户自己的 JD、项目经历和历史薄弱点做个性化训练

所以工具调用的价值是让 Agent 接触“外部真实资料”，而不是凭空编答案。

第一版工具不追求大而全，只解决一个核心问题：

```text
当用户进行技术面试训练时，Agent 可以主动检索本地面试资料库，并基于检索结果提问、讲题、评分和追问。
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
interview_material_search = function calling + 本地 JSON 关键词搜索
```

未来升级：

```text
interview_material_search = function calling + embedding 向量检索 + rerank
```

再往后：

```text
ToolExecutor -> MCP client -> 外部 interview material MCP server
```

因此，本阶段先做 function calling，不直接实现完整 RAG 或 MCP。这样可以先学习清楚 Agent 编排闭环，同时不堵死后续演进路径。

## 5. 方案比较

### 推荐方案：技术面试资料搜索工具

工具名：

```text
interview_material_search
```

能力：

- 搜索本地技术面试资料
- 返回题目、评分点、常见误区、追问和标签
- 支持 Agent 进行提问、讲题、评分和追问

优点：

- 工具价值明显
- 实现范围小
- 可以自然升级为 RAG
- 与当前 Tutor Agent 项目技术栈贴合

缺点：

- 第一版资料量小
- 需要手写或整理种子题库

### 轻量替代：纯题库搜索

工具名可以是：

```text
question_bank_search
```

能力只覆盖题目和标准答案。

优点是更简单，缺点是面试教练感不足，因为缺少评分点、常见误区和追问。

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
interview_material_search
```

第一版支持四种对话能力：

1. 找题

```text
用户：我想练 React 面试。
Agent：调用 interview_material_search，找相关题目，选择一道题让用户回答。
```

2. 讲题

```text
用户：useEffect 这题面试里怎么答？
Agent：调用 interview_material_search，读取评分点，组织成面试化回答。
```

3. 判题

```text
用户回答上一道题。
Agent：调用 interview_material_search，读取对应评分点，指出覆盖点、漏点和改进答案。
```

4. 追问

```text
用户：继续追问我。
Agent：调用 interview_material_search，读取 followups，选择一个追问用户。
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

第一版使用手写或整理的小型种子资料库。

数据来源优先级：

1. 当前项目相关技术栈
2. 通用技术面试高频概念
3. 官方文档概念的自有改写
4. 未来用户粘贴的 JD、项目经历和历史回答

第一版不自动从互联网抓取数据。

首批资料聚焦当前项目和常见 AI 应用开发面试：

- Backend / FastAPI
- Database / SQLite
- Frontend / React
- AI Agent / LLM Integration

## 9. 第一版题库范围

第一版内置 12 到 16 条技术面试资料。每条资料代表一道面试题。

建议首批题目：

Backend / FastAPI：

- FastAPI 的路由是什么？GET 和 POST 的区别是什么？
- Pydantic 在 FastAPI 里起什么作用？
- route、service、repository 分层分别负责什么？
- 为什么模型调用失败适合返回 502？

Database / SQLite：

- SQLite 适合什么场景，不适合什么场景？
- 为什么要用 repository 封装数据库操作？
- 聊天历史表应该包含哪些字段？
- 如何避免不同用户或不同会话的数据混在一起？

Frontend / React：

- React 组件的 state 和 props 有什么区别？
- useEffect 常见用途和依赖数组是什么？
- 前端调用后端 API 时要处理哪些状态？
- 聊天界面为什么要维护 loading、error、empty 状态？

AI Agent / LLM Integration：

- 什么是 prompt，为什么要结构化输出？
- 为什么 LLM 不会自动记住历史？
- function calling / tool calling 解决什么问题？
- RAG 和工具调用是什么关系？

最终题目数量可以在实现阶段控制在 12 到 16 条之间，但每条必须有完整评分点。

## 10. 数据文件组织

第一版资料库放在：

```text
app/data/interview_materials.json
```

第一版只使用一个 JSON 文件，避免过早拆分。

未来资料变多后可拆成：

```text
app/data/interview/
  backend_fastapi.json
  database_sqlite.json
  frontend_react.json
  ai_agent_llm.json
```

## 11. 数据结构

`app/data/interview_materials.json` 顶层结构：

```json
{
  "version": "0.1",
  "items": []
}
```

每条资料结构：

```json
{
  "id": "backend-fastapi-001",
  "category": "backend",
  "topic": "FastAPI",
  "difficulty": "easy",
  "material_type": "interview_question",
  "question": "FastAPI 的路由是什么？GET 和 POST 的区别是什么？",
  "short_answer": "路由是 URL、HTTP 方法和处理函数之间的映射。GET 常用于查询资源，POST 常用于提交数据或触发业务处理。",
  "answer_points": [
    "路由由路径、HTTP 方法和处理函数组成",
    "GET 通常用于读取数据，请求参数常在 URL 或 query 中",
    "POST 通常用于提交请求体，创建或处理数据",
    "FastAPI 会基于路由函数和 Pydantic schema 生成 OpenAPI 文档"
  ],
  "common_mistakes": [
    "只说 URL，不提 HTTP 方法",
    "把 GET 和 POST 简化成一个安全一个不安全",
    "不知道请求体和 query 参数的区别"
  ],
  "followups": [
    "POST 一定是创建资源吗？",
    "为什么 GET 请求通常不放复杂请求体？",
    "FastAPI 的自动文档从哪里来？"
  ],
  "tags": ["FastAPI", "HTTP", "API", "backend"]
}
```

字段要求：

- `id`：稳定唯一标识
- `category`：大分类，例如 backend、database、frontend、ai_agent
- `topic`：主题，例如 FastAPI、SQLite、React、RAG
- `difficulty`：easy、medium、hard
- `material_type`：第一版固定为 interview_question
- `question`：面试题
- `short_answer`：简短参考答案
- `answer_points`：评分点，必须存在
- `common_mistakes`：常见误区，必须存在
- `followups`：追问，必须存在
- `tags`：检索标签，必须存在

## 12. 工具接口设计

工具名：

```text
interview_material_search
```

用途：

```text
Search the local technical interview material library for questions, answer points, common mistakes, and follow-up questions.
```

输入参数：

```json
{
  "query": "React Hooks useEffect",
  "material_type": "interview_question",
  "limit": 3
}
```

字段说明：

- `query`：必填，用户想练习或查询的技术主题
- `material_type`：可选，第一版支持 `interview_question` 和 `any`
- `limit`：可选，默认 3，最小 1，最大 5

输出结构：

```json
{
  "ok": true,
  "items": [
    {
      "id": "frontend-react-002",
      "category": "frontend",
      "topic": "React",
      "difficulty": "medium",
      "material_type": "interview_question",
      "question": "useEffect 常见用途和依赖数组是什么？",
      "short_answer": "...",
      "answer_points": ["..."],
      "common_mistakes": ["..."],
      "followups": ["..."],
      "tags": ["React", "Hooks"]
    }
  ]
}
```

无结果时：

```json
{
  "ok": true,
  "items": [],
  "message": "No interview material matched the query."
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

- `question`
- `topic`
- `tags`
- `answer_points`
- `common_mistakes`
- `followups`
- `short_answer`

排序策略：

```text
按 query 关键词在各字段中的命中数量排序。
topic、tags、question 命中权重大于 answer_points 和 common_mistakes。
返回前 limit 条。
```

第一版搜索质量只需要支撑小型题库，不追求复杂相关性排序。

## 14. Agent 调用工具策略

Agent 不应每轮都调用工具。

需要调用 `interview_material_search` 的场景：

- 用户想练某类技术面试题
- 用户要求给一道题
- 用户要求标准答案或面试答案
- 用户回答后需要评分
- 用户要求继续追问
- 用户想把项目经验转化成面试表达

不需要调用工具的场景：

- 普通寒暄
- 解释当前功能怎么用
- 用户表达情绪
- 总结当前对话
- 与面试资料无关的普通学习辅导

系统提示词需要强调：

```text
你是技术面试训练导师。
当用户要练题、评分、追问或查询面试答案时，优先调用 interview_material_search。
如果正在模拟面试，一次只问一个问题。
用户回答后，按评分点指出覆盖点、漏点，并给出更好的面试化回答。
最终回复必须是 JSON，包含 answer、next_task、exercise、checkpoints。
```

## 15. 模拟面试流程

第一版模拟面试采用轻量流程，不新增专门状态表。

基本循环：

```text
1. 用户选择方向
   例：我想练 React 面试

2. Agent 调用 interview_material_search
   query = React 面试
   limit = 3

3. Agent 从结果中选择一道题提问
   一次只问一道题

4. 用户回答

5. Agent 再调用 interview_material_search
   query = 最近题目关键词
   limit = 1

6. Agent 按 answer_points、common_mistakes 给反馈

7. Agent 引导用户选择：
   重答、追问、下一题
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
  interview_material_search.py

app/data/
  interview_materials.json
```

职责划分：

`ToolRegistry`：

- 提供 OpenAI-compatible tools schema
- 注册可用工具
- 第一版只注册 `interview_material_search`

`ToolExecutor`：

- 接收模型返回的 tool call
- 校验工具名
- 解析参数
- 执行对应工具
- 返回结构化工具结果
- 遇到未知工具或参数错误时返回结构化错误，不让 `/chat` 崩溃

`InterviewMaterialSearchTool`：

- 读取 `app/data/interview_materials.json`
- 执行关键词搜索
- 返回匹配资料

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
当用户明确要练技术面试、查面试题、请求评分、追问或面试化回答时，优先调用 interview_material_search。
工具返回的资料是依据，不要原样堆给用户。
最终回复必须是 JSON，不要返回 Markdown，不要返回 JSON 之外的文字。
如果正在模拟面试，一次只问一个问题。
用户回答后，按评分点指出覆盖点和漏点。
```

## 21. 错误处理

工具搜不到资料：

```text
Agent 明确说明当前内置题库没有找到对应资料。
Agent 可以按通用经验临时回答，但要说明这不是基于内置题库评分。
Agent 推荐用户切换到已有方向，例如 FastAPI、React、SQLite、AI Agent。
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

1. 资料库搜索

- 搜索 FastAPI 能返回 FastAPI 题
- 搜索 React 能返回 React 题
- 搜索不存在主题返回空 items
- limit 生效

2. ToolRegistry

- tools schema 包含 `interview_material_search`
- schema 包含 query、material_type、limit 参数

3. ToolExecutor

- 合法 tool call 能执行
- 未知工具返回结构化错误
- 非法参数返回结构化错误

4. TutorAgentService 无工具路径

- 模型直接返回最终 JSON 时，现有 `/chat` 行为保持可用

5. TutorAgentService 有工具路径

- fake client 第一次返回 tool call
- 后端执行 `interview_material_search`
- fake client 第二次返回最终 TutorReply JSON
- 最终 `ChatResponse.reply` 正常解析
- 对话保存逻辑仍然执行

6. PromptBuilder

- 系统提示词包含技术面试训练和工具调用规则
- 仍然保留 JSON 输出要求

## 23. 验收标准

功能验收：

- `/chat` 可以处理普通学习问题，原有行为不破坏
- 用户说“我想练 React 面试”时，模型可以调用 `interview_material_search`
- 工具能从本地资料库返回相关题目
- Agent 能基于工具结果问一道技术面试题
- 用户回答后，Agent 能基于评分点给出覆盖点、漏点和改进建议
- 用户要求追问时，Agent 能基于 `followups` 提出下一问
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

1. 资料库阶段

- 新增 `app/data/interview_materials.json`
- 写入 12 到 16 条技术面试资料
- 确保每条资料有评分点、常见误区和追问

2. 工具阶段

- 实现 `InterviewMaterialSearchTool`
- 实现关键词搜索
- 补资料库搜索测试

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
- 用真实模型测试“我想练 React 面试”
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
interview_material_search 内部从关键词搜索升级为 embedding 检索。
```

接口保持不变，替换内部检索实现。

4. MCP 化

```text
把 interview_material_search 做成独立 MCP tool server。
```

适合未来多个 Agent 或客户端复用同一套面试资料工具。

5. 代码执行工具

仅当产品范围扩展到编程面试、算法题、SQL 题或数据分析题时再加入。

## 26. 当前设计结论

第一版技术面试工具调用设计如下：

```text
新增本地技术面试资料库 app/data/interview_materials.json。
新增 interview_material_search 工具，先用关键词检索资料库。
新增 ToolRegistry 和 ToolExecutor，接入 OpenAI-compatible function calling。
TutorAgentService 支持最多一轮工具调用，然后生成最终 TutorReply JSON。
Agent 在用户练技术面试、请求评分、追问或面试化回答时调用工具。
第一版不实现完整 RAG、MCP、联网搜索、代码执行或长期错题系统。
```

这条路线能用最小工程量看清楚工具调用，同时保留未来升级成 RAG 和 MCP 的空间。
