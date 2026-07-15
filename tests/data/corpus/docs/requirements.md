# Tutor Agent API 需求文档

## 1. 项目背景

本项目面向后端开发新手，目标不是一次性做出复杂商业系统，而是通过一个真实可运行的 AI Agent 后端项目，学习后端开发、AI 模型调用、API 设计、数据库存储和基础工程流程。

项目选择 **AI 学习辅导 Agent** 作为第一版主题。它既是学习后端的练习项目，也是后续可以继续帮助开发者学习的工具。

## 2. 项目名称

**Tutor Agent API**

第一版版本号：`v0.1`

## 3. 项目定位

Tutor Agent API 是一个训练型后端 API 项目。

它有两个目标：

- 项目目标：做出一个可运行的 FastAPI 后端，支持用户发送学习问题，Agent 调用大模型生成结构化辅导回复，并保存简单对话历史。
- 学习目标：通过这个项目学会后端开发的基础流程，包括项目结构、API 设计、请求响应、环境变量、数据库、服务分层、错误处理、测试和逐步迭代。

第一版不追求大而全，只追求能支撑学习闭环的核心能力。

## 4. 用户角色

第一版只有一个轻量用户模型：学习者。

学习者可以：

- 通过 API 发送学习问题
- 获得 AI 学习导师的结构化回复
- 查询自己的最近对话历史

第一版不做真实登录注册，用请求中的 `user_id` 字符串区分不同学习者。

示例：

```json
{
  "user_id": "default",
  "message": "FastAPI 的路由是什么？"
}
```

## 5. 第一版功能范围

Tutor Agent API v0.1 只做以下核心能力。

### 5.1 FastAPI 后端基础

- 能启动 FastAPI 服务
- 提供健康检查接口
- 提供学习对话接口
- 提供对话历史查询接口
- 自动生成 Swagger / OpenAPI 文档页面

### 5.2 学习辅导 Agent

- 接收用户学习问题
- 调用大模型
- 返回结构化导师回复
- 回复包含解释、下一步任务、练习题、检查点

结构化回复格式：

```json
{
  "answer": "解释用户的问题",
  "next_task": "建议用户下一步做什么",
  "exercise": "给用户一个小练习",
  "checkpoints": [
    "完成后应该能做到什么"
  ]
}
```

### 5.3 可替换模型接口

- 业务代码不直接依赖某一家模型厂商
- 统一通过 `LLMClient` 调用模型
- 第一版实现 `OpenAICompatibleClient`
- 模型 API key、模型名称、base URL 从环境变量读取

### 5.4 简单对话历史

- 使用 SQLite 保存用户问题和 Agent 回复
- 使用 `user_id` 区分不同学习者
- `/chat` 成功后保存一条对话记录
- `/conversations/{user_id}` 返回某个用户最近 20 条对话

### 5.5 基础工程习惯

- 清晰项目目录结构
- `.env.example`
- `README.md`
- 基础测试
- 基础错误处理
- 学习文档和复盘文档

## 6. 第一版明确不做的功能

这些功能有价值，但不属于 v0.1 范围：

- 登录注册
- JWT
- 复杂权限
- 前端页面
- 移动端
- 管理员后台
- 长期记忆
- 向量数据库
- 学习画像
- 学习任务完成状态
- 知识点图谱
- 多 Agent 协作
- RAG 文档问答
- 文件上传
- 生产级部署
- 支付系统
- 消息队列
- 微服务
- Docker

第一版先把后端 API、模型调用、SQLite 历史、项目分层和测试跑通。

## 7. API 列表

第一版 API：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| POST | `/chat` | 发送学习问题，获得导师回复 |
| GET | `/conversations/{user_id}` | 查询某个用户的最近对话历史 |

详细请求和响应格式见 [api-design.md](api-design.md)。

## 8. 数据存储范围

第一版使用 SQLite，只保存简单对话历史。

核心表：`conversations`

字段：

- `id`
- `user_id`
- `message`
- `reply_json`
- `created_at`

详细数据设计见 [data-design.md](data-design.md)。

## 9. 错误处理要求

第一版至少处理以下情况：

- `message` 为空
- `user_id` 为空
- 模型 API key 未配置
- 模型调用失败
- 模型返回格式不规范
- 数据库写入失败
- 数据库查询失败

错误响应要求：

- 不暴露 API key
- 不暴露敏感配置
- 尽量让错误信息对新手可理解
- 模型服务失败时可以返回 `502`
- 服务器内部错误可以返回 `500`

## 10. 项目目录目标

第一版目标结构：

```text
tutor-agent-api/
  app/
    main.py
    core/
      config.py
    api/
      routes/
        health.py
        chat.py
        conversations.py
    schemas/
      chat.py
      conversation.py
    services/
      tutor_agent.py
      llm_client.py
    repositories/
      conversation_repository.py
    db/
      database.py
      models.py
  tests/
    test_health.py
    test_chat.py
  docs/
    requirements.md
    main-quest-progress.md
    training-plan.md
    ai-collaboration-guide.md
    api-design.md
    data-design.md
    learning-journal.md
    v2-roadmap.md
  scripts/
    test_llm.py
  .env.example
  requirements.txt
  README.md
```

## 11. 第一版验收标准

功能验收：

- 能启动 FastAPI 服务
- 能访问 `/health`
- 能访问 `/docs`
- 能调用 `/chat`
- `/chat` 能调用可替换 LLMClient
- `/chat` 能返回结构化导师回复
- `/chat` 能保存对话历史
- 能通过 `user_id` 查询最近历史
- 有基础错误处理
- 有基础测试

学习验收：

- 学习者能解释项目目录结构
- 学习者能解释一次 `/chat` 请求的完整流转
- 学习者能解释 route、schema、service、client、repository、database 各自的职责
- 学习者能解释为什么第一版不做登录、复杂前端、长期记忆
- 学习者能根据文档继续让 AI 辅导开发下一阶段

## 12. v0.1 完成标志

学习者应该能完整讲出这段流程：

```text
用户通过 POST /chat 发送 user_id 和 message。
FastAPI 路由接收请求，并用 Pydantic 校验数据。
路由调用 TutorAgentService。
Service 组织学习导师 prompt，并通过 LLMClient 调用模型。
模型返回结构化导师回复。
Service 把用户问题和回复交给 Repository 保存到 SQLite。
API 最后把 user_id、message、reply、conversation_id 返回给用户。
用户可以通过 GET /conversations/{user_id} 查询最近 20 条历史。
```

如果学习者能讲清楚这段话，就已经跨过后端开发入门的第一道门槛。
