# 记忆与多轮对话计划文档

## 1. 目标

这个文档用来规划 Tutor Agent 的记忆能力。

我们最后会做 6 个层级，但当前只先实现前两个阶段：

```text
第一阶段：user_id 级别短期记忆
第二阶段：session_id 会话隔离
```

第一阶段先让 Agent 学会“接上最近几轮对话”。第二阶段马上补上“每个会话有自己的短期记忆”，避免同一个用户开新窗口或切换话题时混上下文。

## 2. 6 层路线图

| 层级 | 能力 | 用户体感 | 技术做法 | 当前安排 |
| --- | --- | --- | --- | --- |
| 1. 多轮上下文 | 记住当前用户最近几轮 | 用户说“继续”“刚才那个”能接上 | 从 SQLite 查最近 N 轮，拼进 `messages` | 第一阶段实现 |
| 2. 会话隔离 | 同一个用户可以有不同话题 | 学 FastAPI 和学数据库不会混在一起 | 增加 `chat_sessions` 表和 `session_id` | 第二阶段马上实现 |
| 3. 滚动摘要 | 长对话不会越聊越贵 | 很多轮之后仍然保持主线 | 保存 `summary`，只带摘要 + 最近几轮 | TODO |
| 4. 长期记忆 | 记住用户水平、偏好、薄弱点 | “你上次 SQL 卡在 JOIN” | `user_profile` / `learning_memories` 表 | TODO |
| 5. 语义检索记忆 | 从很多历史或资料里找相关内容 | 找回以前相似问题或学习资料 | `embedding` + 向量数据库 | TODO |
| 6. RAG 学习资料 | 基于学习材料答疑 | 回答能引用资料来源 | 文档切片、检索、引用来源 | TODO |

## 3. 为什么分成两个阶段

短期记忆有两个问题要解决：

```text
问题 1：模型怎么看到上一轮？
问题 2：不同窗口、不同话题怎么隔离？
```

第一阶段只解决问题 1：

```text
根据 user_id 查询最近几轮历史
把历史拼进模型 messages
让模型能理解“继续”“刚才那个”
```

第二阶段解决问题 2：

```text
引入 session_id
短期记忆范围从 user_id 变成 user_id + session_id
同一个用户的不同会话互不干扰
```

这样拆的好处是学习路径清楚。先理解“历史如何进入 prompt”，再理解“短期记忆如何划分边界”。

## 4. 第一阶段：user_id 级别短期记忆

### 4.1 阶段目标

让 `/chat` 在调用模型前，自动读取当前 `user_id` 最近几轮对话，并把它们放进模型上下文。

第一阶段的短期记忆边界是：

```text
同一个 user_id 的最近 N 条对话
```

例如：

```text
user_id = default
最近 6 条 conversations 记录
```

### 4.2 当前已知限制

第一阶段会有一个明确限制：

```text
如果同一个 user_id 开多个窗口，或者突然切换学习话题，历史会共享。
```

例如：

```text
窗口 A：user_id = default，正在学 FastAPI
窗口 B：user_id = default，开始学 SQLite
```

窗口 B 可能会带上窗口 A 的 FastAPI 历史。

这不是最终设计，只是第一阶段为了先跑通短期记忆而接受的临时限制。第二阶段会通过 `session_id` 修复。

### 4.3 第一阶段不做什么

第一阶段不做：

- 不增加 `session_id`
- 不改 `/chat` 请求体
- 不新增数据库表
- 不做滚动摘要
- 不做长期记忆
- 不做 embedding
- 不做向量数据库
- 不做 RAG

### 4.4 第一阶段用户体感

实现前：

```text
用户：FastAPI 的路由是什么？
Agent：解释 FastAPI 路由。
用户：能不能再简单一点？
Agent：不知道“什么”再简单一点，只能泛泛回答。
```

实现后：

```text
用户：FastAPI 的路由是什么？
Agent：解释 FastAPI 路由。
用户：能不能再简单一点？
Agent：知道用户指的是 FastAPI 路由，于是换一种更简单的方式解释。
```

### 4.5 第一阶段后端流程

```text
用户请求 POST /chat
  -> route 接收 ChatRequest
  -> request 里有 user_id 和 message
  -> TutorAgentService 根据 user_id 查询最近 N 条历史
  -> 把历史从旧到新排列
  -> 把历史转换成模型 messages
  -> 把当前 message 放到 messages 最后
  -> 调用模型
  -> 解析模型 JSON 回复
  -> 保存本轮 message 和 reply_json
  -> 返回 ChatResponse
```

### 4.6 第一阶段 messages 结构

模型最终收到的 `messages` 大概是：

```python
[
    {
        "role": "system",
        "content": "你是一个新手友好的后端开发导师。你必须只返回 JSON..."
    },
    {
        "role": "user",
        "content": "FastAPI 的路由是什么？"
    },
    {
        "role": "assistant",
        "content": "FastAPI 的路由可以理解为 URL 和 Python 函数之间的绑定。"
    },
    {
        "role": "user",
        "content": "能不能再简单一点？"
    }
]
```

其中：

- `system`：固定导师规则和 JSON 输出要求
- 历史 `user`：数据库里的历史 `message`
- 历史 `assistant`：数据库里 `reply_json` 的 `answer` 字段
- 最后的 `user`：本轮用户新问题

### 4.7 第一阶段实现任务

- [x] 在 `TutorAgentService.chat` 里拿到 `user_id`
- [x] 调用 `list_recent_conversations(user_id=user_id, limit=N)`
- [x] 设置一个清楚的历史条数上限，例如 `RECENT_HISTORY_LIMIT = 6`
- [x] 数据库返回的是最新在前，拼 prompt 前要反转成旧到新
- [x] 为每条历史添加一条 `user` message
- [x] 从 `reply_json` 里解析 `answer`
- [x] 为每条历史添加一条 `assistant` message
- [x] 把当前用户新问题放在最后
- [x] 调用模型
- [x] 保存本轮对话
- [x] 保持现有 `/conversations/{user_id}` 行为不变

### 4.8 第一阶段测试任务

- [x] 测试没有历史时，`/chat` 仍然正常工作
- [x] 测试第二轮请求时，传给模型的 `messages` 包含第一轮用户问题
- [x] 测试第二轮请求时，传给模型的 `messages` 包含第一轮 `answer`
- [x] 测试不同 `user_id` 的历史不会混进同一个 prompt
- [x] 测试最多只带最近 N 条历史
- [x] 测试历史里某条 `reply_json` 不规范时，不让接口崩溃

### 4.9 第一阶段验收标准

第一阶段完成后，应该能解释清楚：

- 为什么模型默认不会记住上一轮
- 为什么短期记忆要由后端拼进 `messages`
- 为什么历史要按旧到新的顺序放进 prompt
- 为什么不能无限带历史
- 第一阶段为什么会有“同 user_id 多窗口混上下文”的限制

功能上应该满足：

```text
第一轮：FastAPI 的路由是什么？
第二轮：能不能再简单一点？
```

第二轮调用模型时，`messages` 里能看到第一轮问题和第一轮回答。

## 5. 第二阶段：session_id 会话隔离

### 5.1 阶段目标

把短期记忆的边界从：

```text
user_id
```

升级成：

```text
user_id + session_id
```

这样同一个用户可以有多个独立会话。

### 5.2 第二阶段用户体感

```text
会话 A：学习 FastAPI
会话 B：学习 SQLite
```

用户在会话 B 里问：

```text
继续讲刚才那个例子
```

Agent 只会参考 SQLite 会话里的历史，不会拿 FastAPI 会话的历史来回答。

### 5.3 第二阶段接口设计

`POST /chat` 请求体从：

```json
{
  "user_id": "default",
  "message": "继续讲刚才那个"
}
```

升级为：

```json
{
  "user_id": "default",
  "session_id": 1,
  "message": "继续讲刚才那个"
}
```

为了兼容第一阶段，`session_id` 可以先设计成可选：

```text
如果请求没有 session_id，后端默认使用“默认会话”
```

### 5.4 第二阶段数据库设计

新增 `chat_sessions` 表：

```text
id          INTEGER PRIMARY KEY
user_id     TEXT NOT NULL
title       TEXT NOT NULL
created_at  TEXT NOT NULL
updated_at  TEXT NOT NULL
```

给 `conversations` 表增加字段：

```text
session_id  INTEGER
```

查询历史时，从：

```sql
WHERE user_id = ?
```

升级为：

```sql
WHERE user_id = ? AND session_id = ?
```

已有旧数据迁移方案：

```text
给每个已有 user_id 创建一个“默认会话”
把该 user_id 旧的 conversations 记录都归入这个默认会话
```

### 5.5 第二阶段实现任务

- [x] 新增 `chat_sessions` 表
- [x] 给 `conversations` 表增加 `session_id`
- [x] 处理已有 SQLite 数据库的迁移问题
- [x] 给每个已有 `user_id` 创建一个“默认会话”
- [x] 把旧 conversations 记录归入默认会话
- [x] 新增 `ChatSessionRecord`
- [x] 新增 `session_repository.py`
- [x] 修改 `save_conversation`，保存 `session_id`
- [x] 修改 `list_recent_conversations`，支持按 `user_id + session_id` 查询
- [x] 更新测试
- [x] 新增 Sessions API：创建会话、查询会话列表、查询某个会话消息
- [x] 给 `ChatRequest` 增加可选 `session_id`
- [x] 给 `ChatResponse` 返回 `session_id`
- [x] 修改 `TutorAgentService.chat`，使用 `session_id` 查询历史
- [ ] 更新 `/conversations/{user_id}` 是否需要支持按 `session_id` 过滤

### 5.6 第二阶段测试任务

- [x] 老数据库能迁移到默认会话
- [x] `save_conversation` 不传 `session_id` 时默认进入“默认会话”
- [x] `list_recent_conversations` 可以按 `session_id` 过滤
- [x] 老测试仍然通过
- [x] API 可以创建会话、查询会话列表、查询某个会话的消息
- [x] 同一个 `user_id`、同一个 `session_id` 能接上历史
- [x] 同一个 `user_id`、不同 `session_id` 不会混历史
- [x] 不同 `user_id`、不同 `session_id` 不会混历史

### 5.7 第二阶段验收标准

第二阶段完成后，短期记忆边界必须是：

```text
同一个 user_id
同一个 session_id
最近 N 条历史
```

这时再打开新窗口或新话题，只要前端选中新的 `session_id`，上下文就不会混。

## 6. 后续 TODO

### 6.1 层级 3：滚动摘要

暂不实现。目标是解决长对话 token 越来越多的问题。

未来可能方案：

```text
prompt = system + conversation_summary + 最近 N 轮 + 当前问题
```

### 6.2 层级 4：长期记忆

暂不实现。目标是记录用户长期学习状态。

未来可能保存：

- 用户当前水平
- 用户喜欢的解释方式
- 用户反复卡住的知识点
- 用户已完成的学习任务

### 6.3 层级 5：语义检索记忆

暂不实现。目标是在很多历史里找和当前问题语义相关的内容。

未来可能使用：

- embedding
- 本地向量索引
- 向量数据库

### 6.4 层级 6：RAG 学习资料

暂不实现。目标是让 Tutor Agent 基于课程资料、项目文档和学习材料答疑。

未来可能能力：

- 导入文档
- 切片
- 检索
- 回答时引用来源

## 7. 当前推荐推进顺序

```text
1. 先实现第一阶段 user_id 级别短期记忆
2. 跑通测试，确认模型能接上“继续”“刚才那个”
3. 复盘第一阶段限制
4. 马上实现第二阶段 session_id 会话隔离
5. 再考虑滚动摘要和长期记忆
```

这个顺序的重点是：先让系统“能接话”，再让系统“知道每段话属于哪个会话”。
