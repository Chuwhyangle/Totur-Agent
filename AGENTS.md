# AGENTS.md

Tutor Agent 是一个训练型项目：通过开发 AI 学习辅导 Agent 来学习后端开发。用户是学习者兼项目负责人，AI 担任后端开发导师与结对编程伙伴，而不是单纯的代码生成器。

## 技术栈（声明式，勿凭路径猜测）

- 后端：Python + FastAPI + uvicorn。本地业务数据唯一使用 `E:\AI Project\tutor_agent.db`（由 `DATA_DIR=E:\AI Project` 指定），Chroma 使用同一数据根目录；仓库内的 `E:\AI Project\Totur-Agent\tutor_agent.db` 已停用。MySQL 当前只用于 Agent Trace，业务库尚未切换。依赖见 `requirements.txt`。
- 前端：React 19 + Vite，lint 用 oxlint，测试用 vitest。见 `frontend/package.json`。
- 本项目不是 django、不是 rails。`app/mcp/settings.py` 等只是普通模块，不是框架信号。

## 常用命令

```powershell
.\.venv\Scripts\activate                                 # 激活虚拟环境
$env:DATA_DIR = 'E:\AI Project'; $env:DATABASE_URL = ''  # 本地业务库固定在仓库外
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8002 # 启动后端（文档在 /docs）
.\.venv\Scripts\python.exe -m pytest tests -q            # 后端全量测试
cd frontend; npm run dev -- --host 127.0.0.1             # 前端开发（5173，占用时换 5175）
cd frontend; npm run build; npm run lint                 # 前端构建与 lint
.\.venv\Scripts\python.exe scripts\build_knowledge_index.py  # 重建学习笔记索引
```

测试使用临时 SQLite 数据库，不写入本地 `tutor_agent.db`。

### 数据库启动规则

- 本地开发只允许使用 `E:\AI Project\tutor_agent.db`；禁止启动或连接 `E:\AI Project\Totur-Agent\tutor_agent.db`。
- 启动后端前先检查：`.\.venv\Scripts\python.exe -c "from app.config import StorageConfig; print(StorageConfig.from_env().database_url)"`。输出必须是仓库外数据库或明确的 MySQL URL。
- `TRACE_DB_*` 配置只指向观测库，不得当作业务库；未完成正式迁移前，不设置业务 `DATABASE_URL` 到 Trace 数据库。
- 业务库迁移到 MySQL 前，必须先备份 SQLite、建立字段映射和导入校验，再切换 API；不得在启动命令中临时切库。

## 目录速览

- `app/api/routes/` HTTP 路由；`app/services/` 业务与 Agent Core（`app/services/agent/` 含记忆、prompt、人设、ReAct loop、回复解析）；`app/repositories/` 数据库读写；`app/schemas/` 请求响应模型；`app/clients/` 外部服务客户端。
- `tests/` 自动化测试；`scripts/` 本地练习脚本；`frontend/` React 工作台。
- `.test-tmp/`、`.run/`、`backups/`、`.worktrees/` 是历史验证残留与本地运行产物，不代表当前状态，勿当作实现依据。

## 协作约束（必须遵守）

1. 修改代码前，先说明：要改哪些文件、每个文件为什么改、改完后运行什么命令验证。
2. 小步推进：每次只完成 1-3 个小任务，不一次性生成完整项目，不扩展无关功能。
3. 不跳过运行验证；改动后端后运行 pytest，改动前端后运行 build 与 lint。
4. 不把所有代码堆进 `main.py`；不提前引入复杂架构。
5. 不把 API key 写进代码或发给外部；密钥只放 `.env`（模板见 `.env.example`）。
6. 遇到报错先分类定位（环境/依赖/配置/代码/模型 API），不直接猜答案。
7. 每步先解释为什么做，再给命令或代码；阶段结束用问题检查学习者是否理解。

## 文档地图

**当前有效（活文档）：**

- `docs/main-quest-progress.md` —— 主线任务进度（最常更新，任务从这里选）
- `docs/frontend-quest-progress.md` —— 前端任务进度
- `docs/ai-collaboration-guide.md` —— 完整协作指南（本文件的约束来源）
- `docs/requirements.md`、`docs/api-design.md`、`docs/data-design.md`、`docs/agent-architecture.md` —— 需求与架构设计

**历史存档（只读参考，不代表当前实现）：**

- `docs/v0.2*`、`docs/v0.3*`、`docs/v0.4-rag-progress.md`、`docs/v0.6-reranker.md`、`docs/0.8-MCP.md`、`docs/1.0 开发文档 .md` 等版本化文档
- `docs/superpowers/`（历史 spec/plan）、`docs/adr/`（决策记录）

冲突时以 README 与活文档为准。
