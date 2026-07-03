# API 设计文档

## 1. API 设计目标

Tutor Agent API v0.1 的 API 保持少而完整。

第一版只提供 3 类接口：

- 健康检查
- 学习对话
- 对话历史查询

API 设计原则：

- 请求和响应格式清晰
- 响应尽量结构化
- 第一版不做登录鉴权
- 用 `user_id` 作为轻量多用户雏形
- 错误信息清晰，但不暴露敏感配置

## 2. 接口总览

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| POST | `/chat` | 发送学习问题，获取导师回复 |
| GET | `/conversations/{user_id}` | 查询某个用户最近对话历史 |

## 3. GET /health

用途：确认后端服务是否正常启动。

请求参数：无。

响应示例：

```json
{
  "status": "ok",
  "service": "tutor-agent-api"
}
```

验收方式：

- 启动服务后访问 `/health`
- 返回 `status` 为 `ok`
- 返回 `service` 为 `tutor-agent-api`

学习价值：

- 理解最基础的 GET 接口
- 理解 JSON 响应
- 理解健康检查接口的作用

## 4. POST /chat

用途：用户发送一个学习问题，Agent 返回结构化辅导内容，并保存对话历史。

请求体：

```json
{
  "user_id": "default",
  "message": "FastAPI 的路由是什么？"
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `user_id` | string | 是 | 学习者 ID，第一版不做登录，用它区分用户 |
| `message` | string | 是 | 用户发送的学习问题 |

成功响应：

```json
{
  "user_id": "default",
  "message": "FastAPI 的路由是什么？",
  "reply": {
    "answer": "FastAPI 的路由可以理解为 URL 和 Python 函数之间的绑定。",
    "next_task": "接下来你可以写一个 GET /health 接口，观察浏览器返回的 JSON。",
    "exercise": "请写一个 GET /hello 接口，让它返回 {\"message\": \"hello\"}。",
    "checkpoints": [
      "你能解释什么是 HTTP 路由",
      "你能写出一个 GET 接口",
      "你能在浏览器或 API 文档里测试接口"
    ]
  },
  "conversation_id": 1
}
```

响应字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_id` | string | 当前学习者 ID |
| `message` | string | 用户原始问题 |
| `reply` | object | Agent 的结构化导师回复 |
| `conversation_id` | integer | 保存到数据库后的对话记录 ID |

`reply` 字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `answer` | string | 对用户问题的解释 |
| `next_task` | string | 建议用户下一步做什么 |
| `exercise` | string | 给用户的小练习 |
| `checkpoints` | array[string] | 完成后应该达到的检查点 |

### 4.1 模型返回不规范时的 fallback

第一版要求模型尽量返回结构化 JSON。

如果模型返回不是合法 JSON，系统可以做简单兜底：

```json
{
  "answer": "模型原始回复内容",
  "next_task": "请根据上面的解释，整理一个你自己的理解。",
  "exercise": "请用 3 句话复述你刚学到的内容。",
  "checkpoints": [
    "你能说出本次问题的核心概念",
    "你能指出还有哪里不理解"
  ]
}
```

第一版不做复杂 JSON 修复器。

### 4.2 可能错误

| 场景 | 建议状态码 | 说明 |
| --- | --- | --- |
| `user_id` 缺失或为空 | 422 或 400 | 请求数据不合法 |
| `message` 缺失或为空 | 422 或 400 | 请求数据不合法 |
| 模型 API key 未配置 | 500 | 服务端配置错误 |
| 模型服务调用失败 | 502 | 上游模型服务不可用 |
| 数据库保存失败 | 500 | 服务端内部错误 |

错误响应不应暴露 API key 或敏感配置。

## 5. GET /conversations/{user_id}

用途：查询某个用户的最近对话历史。

路径参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `user_id` | string | 是 | 学习者 ID |

查询参数：

| 参数 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `limit` | integer | 否 | 20 | 返回最近多少条历史，当前允许 1 到 100 |

响应示例：

```json
{
  "user_id": "default",
  "items": [
    {
      "id": 1,
      "message": "FastAPI 的路由是什么？",
      "reply": {
        "answer": "FastAPI 的路由可以理解为 URL 和 Python 函数之间的绑定。",
        "next_task": "接下来你可以写一个 GET /health 接口。",
        "exercise": "请写一个 GET /hello 接口。",
        "checkpoints": [
          "你能解释什么是 HTTP 路由"
        ]
      },
      "created_at": "2026-06-30T10:00:00"
    }
  ]
}
```

响应字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `user_id` | string | 当前查询的学习者 ID |
| `items` | array | 最近对话列表 |

`items` 中每一项：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | integer | 对话记录 ID |
| `message` | string | 用户问题 |
| `reply` | object | 结构化导师回复 |
| `created_at` | string | 创建时间 |

查询规则：

- 默认返回最近 20 条
- 可通过 `limit` 自定义返回条数，例如 `/conversations/default?limit=5`
- 按 `created_at` 或 `id` 倒序查询
- 不同 `user_id` 的数据互相隔离
- 第一版不做分页

可能错误：

| 场景 | 建议状态码 | 说明 |
| --- | --- | --- |
| `user_id` 为空 | 400 或 422 | 请求参数不合法 |
| 数据库查询失败 | 500 | 服务端内部错误 |

## 6. API 数据流

`POST /chat` 数据流：

```text
用户请求 /chat
  -> FastAPI 路由接收请求
  -> Pydantic 校验 user_id 和 message
  -> TutorAgentService 组织导师 prompt
  -> LLMClient 调用模型
  -> 解析或兜底生成结构化 reply
  -> Repository 保存 message 和 reply
  -> API 返回 user_id、message、reply、conversation_id
```

`GET /conversations/{user_id}` 数据流：

```text
用户请求历史接口
  -> FastAPI 路由接收 user_id
  -> Repository 查询最近 20 条记录
  -> 将 reply_json 解析为 reply 对象
  -> API 返回历史列表
```

## 7. API 学习目标

完成第一版后，学习者应该能解释：

- 什么是 GET 接口
- 什么是 POST 接口
- 什么是请求体
- 什么是响应体
- 什么是路径参数
- 为什么 API 响应要结构化
- 为什么 API 是前端和后端之间的契约
