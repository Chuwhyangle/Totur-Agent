# Tutor Agent API

AI 学习辅导 Agent 的 FastAPI 后端。第一版提供结构化聊天回复，并用 SQLite 保存和查询对话历史。

## 功能

- `GET /health`：健康检查
- `POST /chat`：发送学习问题，返回结构化导师回复
- `GET /conversations/{user_id}`：查询某个用户的最近对话历史
- SQLite 持久化对话记录
- OpenAI-compatible 模型客户端配置

## 运行

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

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_stage2_api.py -q
.\.venv\Scripts\python.exe -m compileall app tests
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
  services/            业务流程
docs/                  需求、API 和学习进度文档
scripts/               本地练习脚本
tests/                 自动化测试
```

## 本地文件

`tutor_agent.db` 是运行时生成的本地 SQLite 数据库，已在 `.gitignore` 中忽略。
