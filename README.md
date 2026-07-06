# Tutor Agent

AI 学习辅导 Agent 练习项目。后端使用 FastAPI，前端使用 React + Vite；当前版本已经具备多会话记忆、结构化导师回复、ReAct 多轮工具调用，以及可切换的导师人设。

## 功能

- `GET /health`：健康检查。
- `POST /chat`：发送学习问题，返回 `answer` / `next_task` / `exercise` / `checkpoints` 四段式结构化回复。
- `POST /chat` 支持可选 `persona_id`；不传 `session_id` 时缺省为 `tutor`，传 `session_id` 时沿用会话绑定人设。
- `GET /personas`：读取当前可用人设列表，前端顶栏下拉框使用这个接口。
- 会话会绑定 `persona_id`；切换历史会话时，前端会恢复该会话的人设。
- ReAct 工具循环：模型可以连续多轮请求工具；`tool_trace.calls[]` 会记录工具名、参数、结果摘要和 `round`。
- `GET /sessions`、`POST /sessions`、`GET /sessions/{session_id}/conversations`：多会话窗口。
- `GET /conversations/{user_id}`：查询某个用户的最近对话历史。
- `GET /interview-jds`、`POST /interview-jds`：保存和读取面试 JD，用于工具检索。
- SQLite 持久化对话、会话、摘要和面试 JD。
- OpenAI-compatible 模型客户端配置。

## 运行后端

激活虚拟环境：

```powershell
.\.venv\Scripts\activate
```

安装依赖：

```powershell
pip install -r requirements.txt
```

配置环境变量：

```text
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
OPENAI_MODEL=...
```

启动 API：

```powershell
python -m uvicorn app.main:app --reload --port 8001
```

打开接口文档：

```text
http://127.0.0.1:8001/docs
```

## 运行前端

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

默认访问：

```text
http://127.0.0.1:5173
```

如果本机已有其他 Vite 服务占用 5173，可以换到后端 CORS 已允许的 5175：

```powershell
npm run dev -- --host 127.0.0.1 --port 5175
```

## 测试

后端全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

前端构建与 lint：

```powershell
cd frontend
npm run build
npm run lint
```

测试会使用临时 SQLite 数据库，不会写入本地 `tutor_agent.db`。

## 项目结构

```text
app/
  api/routes/          HTTP 路由
  clients/             外部服务客户端
  db/                  SQLite 连接和表初始化
  repositories/        数据库读写
  schemas/             请求和响应模型
  services/
    agent/             Agent Core：记忆、prompt、人设、ReAct loop、回复解析
frontend/              React + Vite 前端工作台
docs/                  需求、架构、API 和学习进度文档
scripts/               本地练习脚本
tests/                 自动化测试
```

## 本地文件

`tutor_agent.db` 是运行时生成的本地 SQLite 数据库，已在 `.gitignore` 中忽略。
