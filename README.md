# Tutor Agent API

这是一个面向后端新手的训练型项目。

项目目标不是一次性做出复杂商业系统，而是通过一个 AI 学习辅导 Agent 后端项目，从 0 到 1 学会后端开发、API 设计、模型调用、数据库存储和基础工程流程。

## 当前定位

- 项目类型：AI 学习辅导 Agent 后端 API
- 第一版目标：FastAPI + 可替换模型接口 + SQLite 对话历史
- 辅导方式：混合型导师
- 学习路线：以后端为主，逐步补充前端和 Agent 能力

## 当前阶段

当前项目处在 **阶段 2：FastAPI 基础接口**。

已经完成的内容：

- 阶段 0：开发环境与后端基本感觉
- 阶段 1：跑通模型调用脚本的基础骨架
- 阶段 2：FastAPI 基础接口框架

当前已经有的接口：

- `GET /health`
- `POST /chat`

当前 `POST /chat` 还是占位版本，暂时不调用真实模型。

## 已完成的进度记录

### 阶段 0：开发环境与后端基本感觉

- 创建了 Python 虚拟环境
- 配置了 `.env.example`
- 写了 `README.md`
- 安装并验证了基础依赖
- 学会了如何把报错发给 AI

### 阶段 1：跑通模型调用脚本

- 写了 `scripts/test_SDK.py`
- 完成了 `.env` 读取
- 完成了 OpenAI-compatible client 创建
- 完成了模型请求函数 `ask_model()`
- 目前脚本还在持续打磨，后续会继续完善和重构

### 阶段 2：FastAPI 基础接口

- 新增了 FastAPI 应用入口 `app/main.py`
- 新增了 `GET /health`
- 新增了 `POST /chat`
- 为请求和响应写了 Pydantic 模型
- 写了阶段 2 的测试 `tests/test_stage2_api.py`
- 本地测试和真实 HTTP 请求都已经验证通过

## 如何运行

先激活虚拟环境：

```powershell
.\.venv\Scripts\activate
```

安装依赖：

```powershell
pip install -r requirements.txt
```

运行阶段 1 的模型脚本：

```powershell
python scripts/test_SDK.py
```

启动 FastAPI 服务：

```powershell
python -m uvicorn app.main:app --reload
```

打开 API 文档：

```text
http://127.0.0.1:8000/docs
```

## 项目目录

```text
tutor-agent-api/
  app/
    main.py
  scripts/
    test_SDK.py
  tests/
    test_stage2_api.py
  docs/
    requirements.md
    main-quest-progress.md
    training-plan.md
    ai-collaboration-guide.md
    api-design.md
    data-design.md
  .env.example
  .gitignore
  requirements.txt
  README.md
```

## 接下来要做什么

- 把阶段 1 的脚本继续整理好
- 把阶段 2 的 `app/main.py` 拆到更清晰的目录结构里
- 进入阶段 3：项目分层与可替换 LLMClient
- 后续加入 SQLite 对话历史

## 训练规则

- 每次只推进一个小任务
- 每一步都先理解，再编码
- 每次改完都要运行验证
- 每个阶段都要做复盘
- 不要一次性把整个项目做太大

## 学习文档

- [需求文档](docs/requirements.md)
- [培训计划](docs/training-plan.md)
- [AI 协作指南](docs/ai-collaboration-guide.md)
- [API 设计文档](docs/api-design.md)
- [数据设计文档](docs/data-design.md)
- [主线任务进度表](docs/main-quest-progress.md)

## 存档说明

这个 README 会随着项目推进持续更新，像一个轻量存档点。

每完成一个阶段，我会把：

- 当前进度
- 已完成内容
- 运行方式
- 下一步计划

继续补进来。
