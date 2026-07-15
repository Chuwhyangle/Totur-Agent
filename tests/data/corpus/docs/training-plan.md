# Tutor Agent API 培训计划

## 1. 培训目标

这份计划面向后端开发新手，目标是通过 Tutor Agent API 项目，从 0 到 1 学会后端开发的基础流程。

训练方式不是先学完理论再做项目，而是：

```text
学一个概念
写一点代码
跑起来
测试一下
解释给 AI 听
让 AI 纠正理解
写下复盘
```

每个阶段都必须产出一个能运行、能测试、能解释的结果。

## 2. 学习路线总览

- 阶段 0：开发环境与后端基本感觉
- 阶段 1：跑通模型调用脚本
- 阶段 2：FastAPI 基础接口
- 阶段 3：项目分层与可替换 LLMClient
- 阶段 4：结构化导师回复
- 阶段 5：SQLite 保存对话历史
- 阶段 6：错误处理与测试
- 阶段 7：复盘与下一版本规划

可打勾的执行清单见 [main-quest-progress.md](main-quest-progress.md)。

## 3. 阶段 0：开发环境与后端基本感觉

目标：让学习者知道一个 Python 后端项目是怎么启动的。

学习重点：

- Python 版本
- Python 虚拟环境
- `pip`
- `requirements.txt`
- `.env`
- `.env.example`
- `README.md`
- 如何把报错发给 AI 分析

交付物：

- 项目根目录
- 虚拟环境
- `requirements.txt`
- `.env.example`
- `README.md`

验收标准：

- 能说清楚虚拟环境是干什么的
- 能说清楚为什么 API key 不应该写进代码
- 能独立执行依赖安装
- 能向 AI 描述当前项目目录结构

## 4. 阶段 1：跑通模型调用脚本

目标：先不做 Web，不做数据库，只确认后端能和模型对话。

学习重点：

- SDK
- API key
- 环境变量
- prompt
- 模型请求
- 模型响应
- 常见模型调用错误

交付物：

- `scripts/test_llm.py`
- `.env.example` 中的模型配置示例
- 控制台打印模型回复

验收标准：

- 能通过命令行调用模型
- 能说清楚 API key 从哪里来、代码在哪里读取
- 能解释后端调用模型的基本流程
- 能大致区分配置错误、网络错误、代码错误

## 5. 阶段 2：FastAPI 基础接口

目标：把模型调用包成 HTTP API。

学习重点：

- HTTP
- GET
- POST
- JSON
- 路由
- 请求体
- 响应体
- Swagger / OpenAPI 文档页面

交付物：

- `app/main.py`
- `GET /health`
- `POST /chat`
- 本地 `/docs` 页面

验收标准：

- 能解释什么是 API
- 能解释什么是路由
- 能说清楚 GET 和 POST 的区别
- 能说明 `/chat` 的请求字段和响应字段
- 能通过 Swagger 手动测试接口

## 6. 阶段 3：项目分层与可替换 LLMClient

目标：从能跑升级到结构清楚。

学习重点：

- route、service、client 的职责区别
- 项目分层
- 接口封装
- 可替换模型客户端
- 配置管理
- AI 辅助开发时的文件边界

交付物：

- `app/core/config.py`
- `app/api/routes/health.py`
- `app/api/routes/chat.py`
- `app/schemas/chat.py`
- `app/services/llm_client.py`
- `app/services/tutor_agent.py`
- `/chat` 通过 service 调用真实 LLMClient

验收标准：

- 能说清楚 route 负责什么
- 能说清楚 service 负责什么
- 能说清楚 LLMClient 负责什么
- 能指出以后换模型主要改哪里
- 能让 AI 只修改某个模块，而不是全项目一起改

## 7. 阶段 4：结构化导师回复

目标：让 Agent 从普通聊天变成学习辅导。

学习重点：

- response schema
- 结构化输出
- Pydantic
- JSON 解析
- 模型输出格式约束
- fallback

交付物：

- `/chat` 返回结构化 JSON
- 响应包含 `answer`
- 响应包含 `next_task`
- 响应包含 `exercise`
- 响应包含 `checkpoints`
- 模型返回不规范时系统不会直接崩溃

验收标准：

- 能解释为什么结构化回复适合学习产品
- 能看懂 Pydantic schema
- 能说明 fallback 的作用
- 能检查 `/chat` 响应里是否有固定字段

## 8. 阶段 5：SQLite 保存对话历史

目标：加入最小数据库能力。

学习重点：

- 数据库
- SQLite
- 表
- 字段
- 主键
- CRUD
- repository
- 数据隔离

交付物：

- SQLite 数据库文件
- `conversations` 表
- `/chat` 保存每次对话
- `GET /conversations/{user_id}` 查询历史
- 不同 `user_id` 的历史互相隔离

验收标准：

- 能解释一条对话是怎么保存进数据库的
- 能解释 `user_id` 为什么是多用户雏形
- 能说清楚 repository 的职责
- 能查到某个用户最近 20 条历史

## 9. 阶段 6：错误处理与测试

目标：让项目从演示能跑变成比较可靠。

学习重点：

- 异常
- HTTP 状态码
- pytest
- API 测试
- mock
- 错误信息安全

交付物：

- `tests/test_health.py`
- `tests/test_chat.py`
- 核心接口自动化测试
- 常见错误有明确响应
- 测试可以稳定运行

验收标准：

- 能运行测试命令
- 能看懂一个失败测试在表达什么
- 能解释为什么模型失败适合返回 `502`
- 知道不能在错误响应里暴露敏感信息

## 10. 阶段 7：复盘与下一版本规划

目标：把项目经验沉淀下来，形成后续学习路线。

学习重点：

- 开发复盘
- 后端系统数据流
- V2 需求拆分
- 功能边界控制
- AI 辅导迭代

交付物：

- `docs/learning-journal.md`
- `docs/v2-roadmap.md`
- README 更新
- V2 需求草案

验收标准：

- 能画出用户请求到数据库保存的完整流程
- 能讲清楚这个后端系统有哪些模块
- 能说明下一版要加什么、为什么加
- 能把一个大功能拆成几个小阶段

## 11. 日常学习节奏

建议每次学习或开发按 60 到 90 分钟一轮：

```text
第 1 步：打开 docs/main-quest-progress.md，选择一个小任务
第 2 步：让 AI 解释这个任务的意义
第 3 步：让 AI 带你修改一个很小的部分
第 4 步：运行命令或接口测试
第 5 步：把结果发给 AI 判断
第 6 步：用自己的话总结这一步
第 7 步：在任务表里打勾
```

如果当天状态不好，只做一个小任务也可以。后端能力来自持续的小闭环。

## 12. 训练底线

- 不一次性生成整个大项目
- 不跳过运行验证
- 不复制完全看不懂的代码
- 不把 API key 发给 AI
- 不把所有代码都堆进 `main.py`
- 不为了看起来高级提前引入复杂架构
- 不在没理解前进入下一阶段
