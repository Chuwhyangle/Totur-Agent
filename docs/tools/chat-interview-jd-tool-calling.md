# /chat 接入 interview_jd_search 工具调用

## 目标

本阶段把 `interview_jd_search` 接入 `/chat`，跑通第一版 function calling 闭环。

这只是临时编排方式，后续会升级为 ReAct 模式。当前版本只允许一次工具调用轮次，避免复杂循环。

## 临时流程

```text
PromptBuilder.build_messages
-> 第一次 call model with tools
-> 如果没有 tool_calls：走原有解析和保存流程
-> 如果有 tool_calls：ToolExecutor 执行工具
-> 把 assistant tool_calls 和 tool result 回填到 messages
-> 第二次 call model without tools
-> ResponseParser 解析最终 TutorReply
-> 保存对话并返回 /chat 响应
```

## 范围

本阶段只接入一个工具：

```text
interview_jd_search
```

本阶段不做：

- ReAct 多轮循环
- 多工具规划
- 并发工具调用
- 工具结果缓存
- 用户权限隔离
- 前端专门面试 UI

## 调用规则

模型只有在用户明确表达岗位面试、JD 准备、根据岗位出题、追问或点评时，才应该调用 `interview_jd_search`。

普通学习辅导、概念解释、闲聊和总结对话不需要调用工具。

## 错误处理

工具执行失败时，`ToolExecutor` 返回结构化错误。`/chat` 不直接崩溃，而是把错误作为 tool result 回填给模型，让模型生成兜底 TutorReply。

如果第二次模型调用仍然没有返回文本内容，沿用现有空回复错误处理。

## 测试重点

- 普通聊天路径仍然可用。
- 模型第一次返回 tool call 时，后端会执行 `interview_jd_search`。
- 工具结果会作为 `role="tool"` 消息加入第二次模型调用。
- 第二次模型返回的 JSON 能解析成 `TutorReply`。
- 对话保存和摘要更新逻辑不被破坏。

## 工具调用调试 Trace

为了开发和调试，`/chat` 响应增加可选的 `tool_trace` 字段。它只描述工具调用摘要，不参与模型回复生成。

无工具调用时：

```json
{
  "tool_trace": {
    "used": false,
    "calls": []
  }
}
```

有工具调用时：

```json
{
  "tool_trace": {
    "used": true,
    "calls": [
      {
        "name": "interview_jd_search",
        "arguments": {
          "query": "Agent RAG 面试",
          "limit": 1
        },
        "ok": true,
        "returned_count": 1,
        "top_titles": ["Python AI Agent 开发工程师"],
        "result_preview": [
          {
            "title": "Python AI Agent 开发工程师",
            "match_score": 18,
            "matched_fields": [
              "title",
              "core_skills",
              "keywords",
              "interview_focus",
              "raw_text"
            ],
            "core_skills": ["Function Calling", "RAG"],
            "keywords": ["Agent", "RAG"],
            "interview_focus": ["Agent 工具调用"],
            "raw_text_excerpt": "负责 Agent 工具调用和 RAG 应用开发..."
          }
        ],
        "error": null
      }
    ]
  }
}
```

当前 trace 返回摘要字段和轻量结果预览：

- `used`：本轮是否调用工具
- `name`：工具名
- `arguments`：工具参数
- `ok`：工具是否执行成功
- `returned_count`：返回条数
- `top_titles`：命中的 JD 标题摘要
- `result_preview`：命中 JD 的轻量预览，用于前端开发调试
- `error`：错误码

`result_preview` 不返回数据库 `id`，也不返回完整工具结果。它只保留标题、匹配分、命中字段、核心技能、关键词、面试重点和原文片段，避免 `/chat` 响应过大。前端调试区直接展示这些字段，方便观察模型这一轮到底拿到了哪些 JD 依据。
