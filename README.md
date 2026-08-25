# Tutor Agent

AI 学习辅导 Agent 练习项目。后端使用 FastAPI，前端使用 React + Vite；当前版本已经具备多会话记忆、结构化导师回复、ReAct 多轮工具调用，以及可切换的导师人设。

## 功能

- `GET /health`：健康检查。
- `POST /chat`：发送学习问题，返回 `answer` / `next_task` / `exercise` / `checkpoints` 四段式结构化回复。
- `POST /chat` 支持可选 `persona_id`；不传 `session_id` 时缺省为 `tutor`，传 `session_id` 时沿用会话绑定人设。
- `GET /personas`：读取当前可用人设列表，前端顶栏下拉框使用这个接口。
- 会话会绑定 `persona_id`；切换历史会话时，前端会恢复该会话的人设。
- ReAct 工具循环：模型可以连续多轮请求工具；`tool_trace.calls[]` 会记录工具名、参数、结果摘要和 `round`。
- RAG 学习笔记检索：`search_learning_notes` 会从本地 `docs/**/*.md` 的 Chroma 索引中检索，并要求回答标注来源。
- `GET /sessions`、`POST /sessions`、`GET /sessions/{session_id}/conversations`：多会话窗口。
- `GET /conversations/{user_id}`：查询某个用户的最近对话历史。
- `GET /interview-jds`、`POST /interview-jds`：保存和读取面试 JD，用于工具检索。
- SQLite 持久化对话、会话、摘要和面试 JD；本地开发数据库位于 `DATA_DIR` 指定的数据根目录，不放在仓库内。
- Chroma 持久化学习笔记、JD 和附件向量；它不保存业务主表。
- MySQL 当前只保存 Agent 可观测性：`agent_traces`、检索、LLM 和工具事件；`conversations`、`sessions`、`documents` 等业务表尚未迁移，业务 API 仍使用 SQLite。
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
EMBEDDING_KEY=...
EMBEDDING_BASE_URL=...
EMBEDDING_MODEL=...
```

聊天模型和 Embedding 模型可以来自不同 OpenAI-compatible 服务；Embedding 侧必须单独配置 `EMBEDDING_BASE_URL`，不会回退到 `OPENAI_BASE_URL`。

构建本地学习笔记索引：

```powershell
.\.venv\Scripts\python.exe scripts\build_knowledge_index.py
```

脚本会扫描 `docs/**/*.md`，写入本地 `chroma_db/learning_notes` 集合。文档更新后需要重新运行脚本。

启动 API：

```powershell
python -m uvicorn app.main:app --reload --port 8001
```

打开接口文档：

```text
http://127.0.0.1:8001/docs
```

## GitHub MCP（只读）

MCP Client 可接入 GitHub 官方 Hosted MCP Server（Streamable HTTP），只开放仓库、Issue、Pull Request 的只读工具。默认关闭（`MCP_CLIENT_ENABLED=false`），未配置的用户不受影响。

在 `.env` 中配置（参考 `.env.example`）：

```text
GITHUB_MCP_PAT=你自己的 PAT，绝不提交到代码或日志
MCP_CLIENT_ENABLED=true
MCP_CLIENT_TIMEOUT_SECONDS=20
MCP_CLIENT_RETRY_SECONDS=30
MCP_CLIENT_SERVERS=[{"name":"github","transport":"streamable-http","url":"https://api.githubcopilot.com/mcp/","headers":{"Authorization":"Bearer ${GITHUB_MCP_PAT}","X-MCP-Toolsets":"repos,issues,pull_requests","X-MCP-Readonly":"true"}}]
```

安全边界：

- `${GITHUB_MCP_PAT}` 由 `app/mcp/settings.py` 的 `expand_env_refs` 展开（fail-closed：引用缺失或为空 Bearer 时报错，只显示变量名，不显示值）。`GITHUB_MCP_PAT` 需定义在 `MCP_CLIENT_SERVERS` 之上（dotenv 按文件顺序插值）。
- 配置校验强制 `X-MCP-Readonly=true`，Toolsets 仅允许 `repos,issues,pull_requests`。
- 本地防御：`app/mcp/write_guard.py` 过滤 create/update/delete/merge/push 等明显写工具，不进入 Agent 工具列表。
- 发现或调用失败时降级：内部工具照常工作，错误消息脱敏，不打印 Authorization/PAT。

手动验证（只打印工具名和脱敏错误摘要，不打印 Token）：

```powershell
.\.venv\Scripts\python.exe scripts\check_mcp_client.py
```

## Agent Trace 与 MySQL

Trace 默认关闭。请求线程只把埋点放入有界内存队列，后台 Writer 才连接 MySQL；队列满或 MySQL 故障时记录会丢失，但聊天请求继续使用 SQLite 和 Chroma 正常工作。`TRACE_DB_CAPTURE_CONTENT=false` 时不保存 question 和检索 query，工具参数预览始终限长并脱敏常见凭据字段。

本地启动一个独立的 Trace MySQL（数据库名、用户和密码都来自 `.env`）：

```powershell
Copy-Item .env.example .env
# 编辑 .env：填写 OPENAI/Embedding 配置，并把 Trace 与 MYSQL_ROOT_PASSWORD 改成强密码
docker compose up -d mysql
docker compose run --rm --build trace-db-init
```

也可以在宿主机执行幂等初始化和 smoke test。`.env.example` 的宿主机端口默认是 3307：

```powershell
$env:TRACE_DB_ENABLED="true"
$env:TRACE_DB_HOST="127.0.0.1"
$env:TRACE_DB_PORT="3307"
python scripts/init_trace_db.py
python scripts/try_mysql.py
```

`init_trace_db.py` 可以对空库或历史 001-005 表重复执行，不会 DROP 表或删除数据。后台 Writer 首次连接也会执行同一套幂等初始化。查询最近 Trace 时使用密码提示，不要把密码写入命令历史：

```powershell
docker compose exec mysql mysql -u"$env:TRACE_DB_USER" -p -D "$env:TRACE_DB_NAME"
```

进入 MySQL 后可执行：

```sql
SELECT trace_id, status, total_ms, created_at, updated_at
FROM agent_traces
ORDER BY created_at DESC
LIMIT 20;
```

关闭 Trace：将 `.env` 中的 `TRACE_DB_ENABLED` 改为 `false` 后重启 API，或在本地进程启动前执行 `$env:TRACE_DB_ENABLED="false"`。关闭后所有 Trace API 都是低开销 no-op。

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

`DATA_DIR` 是运行时 SQLite 数据库和 Chroma 向量库的数据根目录。当前本地开发使用仓库外的 `E:\AI Project`；仓库内 `tutor_agent.db` 禁止作为运行数据源，相关运行产物都已在 `.gitignore` 中忽略。
## Docker 部署

生产环境使用 Docker Compose 启动前端 Nginx、后端 FastAPI 和独立的 MySQL Trace 服务。SQLite、Chroma 与附件统一持久化到 `tutor_data` 卷；MySQL 使用独立的 `trace_mysql_data` 卷。API 使用 `mysql:3306`，MySQL 不可用时 API 仍可启动并后台重连。

首次部署：

```bash
cp .env.example .env
# 编辑 .env，填写 OPENAI_*、EMBEDDING_*，并更换所有示例密码
docker compose up -d mysql
docker compose run --rm --build trace-db-init
docker compose up -d --build
docker compose run --rm api python scripts/build_knowledge_index.py
```

访问 `http://服务器地址/`，接口健康检查为 `http://服务器地址/health`。后续更新执行 `git pull && docker compose up -d --build`；备份 SQLite/Chroma 数据执行 `docker run --rm -v tutor_data:/data -v "$PWD/backups:/backup" alpine tar czf /backup/tutor-data-$(date +%F).tar.gz -C /data .`，MySQL Trace 卷需要单独备份。

