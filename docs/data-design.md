# 数据设计文档

## 1. 数据设计目标

Tutor Agent API v0.1 的数据设计只服务一个目标：

保存简单对话历史。

第一版不做复杂长期记忆，不做学习画像，不做向量数据库。先让学习者理解数据库的基础概念和最小 CRUD 流程。

## 2. 为什么选择 SQLite

第一版选择 SQLite，原因：

- 不需要单独安装数据库服务
- 适合本地开发
- 适合新手学习
- 配置简单
- 足够支撑第一版对话历史
- 后续可以迁移到 PostgreSQL

SQLite 的定位是：先让项目跑起来，让学习者理解数据持久化。

## 3. 第一版数据范围

第一版只保存：

- 用户 ID
- 用户问题
- Agent 结构化回复
- 创建时间

第一版不保存：

- 用户密码
- 用户资料
- 登录状态
- 学习任务状态
- 长期记忆摘要
- 知识点标签
- 向量数据
- 文件内容

## 4. chat_sessions 表

核心表名：`chat_sessions`

用途：表示一个用户的一个独立聊天窗口。

字段设计：

```text
id          INTEGER PRIMARY KEY
user_id     TEXT NOT NULL
title       TEXT NOT NULL
created_at  TEXT NOT NULL
updated_at  TEXT NOT NULL
```

当前规则：

- 旧数据会按 `user_id` 自动归入一个“默认会话”。
- 新会话标题后续会优先使用用户第一条消息，并做长度截断。
- `updated_at` 用来让最近聊过的会话排在前面。

## 5. conversations 表

核心表名：`conversations`

字段设计：

```text
id          INTEGER PRIMARY KEY
session_id  INTEGER
user_id     TEXT NOT NULL
message     TEXT NOT NULL
reply_json  TEXT NOT NULL
created_at  DATETIME NOT NULL
```

## 6. 字段说明

### id

类型：`INTEGER PRIMARY KEY`

含义：每条对话记录的唯一编号。

用途：

- 唯一标识一条对话
- 作为 `/chat` 响应里的 `conversation_id`
- 可用于按插入顺序查询最近记录

### session_id

类型：`INTEGER`

含义：这条对话属于哪个聊天窗口。

用途：

- 把同一个 `user_id` 的不同学习话题隔离开
- 后续支持左侧多会话列表
- 查询某个会话自己的历史记录

兼容规则：

- 老数据没有 `session_id` 时，初始化数据库会自动创建“默认会话”
- 同一个 `user_id` 的旧记录会归入同一个默认会话

### user_id

类型：`TEXT NOT NULL`

含义：学习者 ID。

第一版不做登录注册，所以 `user_id` 只是一个普通字符串，例如：

- `default`
- `alex`
- `student_001`

用途：

- 区分不同学习者
- 查询某个学习者的历史
- 训练多用户数据隔离意识

注意：第一版的 `user_id` 不是安全身份认证，只是轻量多用户雏形。

### message

类型：`TEXT NOT NULL`

含义：用户发送的原始学习问题。

示例：

```text
FastAPI 的路由是什么？
```

用途：

- 查看历史对话
- 后续可作为上下文或复盘材料

### reply_json

类型：`TEXT NOT NULL`

含义：Agent 返回的结构化回复，以 JSON 字符串形式保存。

示例：

```json
{
  "answer": "FastAPI 的路由可以理解为 URL 和 Python 函数之间的绑定。",
  "next_task": "写一个 GET /health 接口。",
  "exercise": "写一个 GET /hello 接口。",
  "checkpoints": [
    "能解释什么是 HTTP 路由"
  ]
}
```

为什么第一版用 JSON 字符串：

- 实现简单
- 适合结构化回复
- 不需要一开始设计很多表
- 后续可以按需要拆分字段

### created_at

类型：`DATETIME NOT NULL`

含义：记录创建时间。

用途：

- 查询最近 20 条历史
- 展示对话时间
- 后续做学习日志或进度分析

## 7. 保存时机

当 `/chat` 调用模型并生成结构化回复后，系统保存一条记录。

保存内容：

- `user_id`
- `session_id`
- `message`
- `reply_json`
- `created_at`

保存成功后，API 返回 `conversation_id`。

## 8. 查询逻辑

`GET /conversations/{user_id}` 查询逻辑：

```text
根据 user_id 查询 conversations 表
按 created_at 或 id 倒序排列
最多返回 20 条
将 reply_json 解析为 reply 对象
返回给 API 调用方
```

后续多会话查询会进一步按 `session_id` 过滤：

```text
根据 user_id + session_id 查询 conversations 表
只返回当前会话里的消息
```

第一版不做分页。

## 9. 数据隔离

不同学习者的数据通过 `user_id` 区分。

示例：

- `user_id = "default"` 只能查到自己的历史
- `user_id = "alex"` 只能查到自己的历史

这不是安全权限系统，但能训练多用户系统的基本数据隔离思想。

多会话阶段还会通过 `session_id` 区分同一个用户的不同学习话题。

## 10. Repository 职责

数据库操作集中放在 repository 中。

建议文件：

```text
app/repositories/conversation_repository.py
app/repositories/session_repository.py
```

Repository 负责：

- 创建和查询会话
- 保存对话记录
- 按 `user_id` 或 `user_id + session_id` 查询最近历史
- 隐藏数据库操作细节

Service 不应该到处直接写 SQL 或数据库调用。

这样做的好处：

- API 层更干净
- 业务逻辑更清楚
- 数据库以后更容易替换
- AI 修改代码时更容易定位文件边界

## 11. 第一版不做的复杂记忆

第一版不做：

- 长期记忆总结
- 薄弱知识点抽取
- 复习计划生成
- 学习画像
- embedding
- 向量数据库
- 记忆冲突处理
- 记忆压缩

原因：

这些功能会引入过多新概念。第一版先理解最小数据持久化。

## 12. 后续扩展方向

### v0.2：学习进度

可能新增表：

```text
learning_tasks
```

可能字段：

- `id`
- `user_id`
- `title`
- `description`
- `topic`
- `status`
- `created_at`
- `completed_at`

### v0.3：工具调用

可能新增：

- 创建任务工具
- 查询任务工具
- 标记完成工具
- 生成练习工具

### v0.5：长期记忆

可能新增表：

```text
user_profiles
learning_summaries
weak_points
review_schedule
```

可能能力：

- 总结学习偏好
- 记录薄弱知识点
- 生成复习建议
- 把学习摘要作为模型上下文

### v0.6：RAG

可能新增：

- 文档表
- 文档切片表
- 向量索引
- 引用来源

## 13. 数据设计学习目标

完成第一版后，学习者应该能解释：

- 数据库是什么
- 表是什么
- 字段是什么
- 主键是什么
- 一条对话是怎么保存进数据库的
- 为什么第一版用 SQLite
- 为什么第一版只用一张 `conversations` 表
- repository 在后端项目中负责什么
- `user_id` 如何形成轻量多用户雏形
