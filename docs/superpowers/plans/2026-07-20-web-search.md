# Web Search 实施计划

> 日期：2026-07-20  
> 规格：`docs/tools/web-search-tool-spec.md`  
> ADR：`docs/adr/2026-07-20-web-search-decisions.md`

## 1. 开发策略

采用纵向切片和 TDD：

```text
失败测试
  → Provider/Client
  → web_search Tool
  → Registry/Executor
  → ReAct 预算和 evidence
  → 引用解析
  → 前端来源卡片
  → 路由评估和 RAG A/B
```

原则：

- 每个里程碑结束时 `/chat` 都可运行。
- 单元测试不访问真实网络。
- M1 先保证失败安全，再增加性能优化。
- 不把重试、缓存等 M4 能力混入 M1 的最小实现。
- 不修改与 Web Search 无关的历史工具契约。

## 2. 计划文件

### 新增

```text
app/clients/web_search_client.py
app/services/agent/tools/web_search.py
app/services/web_search_settings.py
app/services/web_search_metrics.py          # M4

tests/test_web_search_client.py
tests/test_web_search_tool.py
tests/test_web_search_metrics.py            # M4
tests/data/web_search_eval.jsonl             # M2/M5

docs/tools/web-search-tool-spec.md
docs/adr/2026-07-20-web-search-decisions.md
```

### 修改

```text
app/config.py
app/main.py
app/schemas/chat.py
app/services/agent/tools/registry.py
app/services/agent/react_orchestrator.py
app/services/agent/personas.py
app/services/agent/response_parser.py
app/services/tutor_agent_service.py
app/api/routes/chat.py                       # 仅在生命周期注入需要时
.env.example

tests/test_agent_tools.py
tests/test_agent_prompt_builder.py
tests/test_agent_react_loop.py
tests/test_stage2_api.py
```

## 3. M1：最小且失败安全的搜索闭环

### Task 1：配置和常量

测试先行：

- `TAVILY_API_KEY` 可以加载 Tavily Key。
- `WEB_SEARCH_API_KEY` 存在时覆盖 `TAVILY_API_KEY`。
- 两个 API Key 都缺少时返回可识别配置错误。
- timeout 非法时使用安全默认值或配置加载失败。
- 导入模块不读取搜索配置。
- `/chat`、Tool schema 和任何 HTTP 响应都不暴露 Key。

实现：

- 在 `app/config.py` 增加 `WebSearchConfig` 和 loader。
- 新增 `app/services/web_search_settings.py`。
- 更新 `.env.example`。

验收：

- 没有 Web Search 环境变量时应用仍可启动。
- 只有实际调用 `web_search` 时才检查配置。

### Task 2：Tavily Provider 和 Client

先写 `tests/test_web_search_client.py`：

1. 通过 `httpx.MockTransport` 捕获请求体。
2. 固定 Clock 为 `2026-07-20`。
3. `freshness_days=7` 时断言 `start_date="2026-07-13"`。
4. 断言不存在 `freshness_days` 供应商字段。
5. 断言固定参数：

```json
{
  "search_depth": "basic",
  "include_answer": false,
  "include_raw_content": false,
  "auto_parameters": false
}
```

6. 验证 Tavily results 转为统一内部模型。
7. 验证非 HTTPS、userinfo URL、重复 URL 被过滤。
8. 验证 path 大小写和 query 参数被保留。
9. 验证 timeout、401/403、429、5xx 和非法 JSON 映射。

实现要求：

- `httpx.Client` 构造注入。
- Clock 注入。
- M1 不重试。
- 记录 `provider_latency_ms` 和 `total_tool_latency_ms`。
- 不保存原始响应。

### Task 3：Client 生命周期

当前 `TutorAgentService` 在路由模块中长期复用。M1 采用应用级 WebSearchClient：

- 在 FastAPI lifespan 中创建共享 `httpx.Client`。
- 关闭应用时调用 `close()`。
- 测试 fixture 显式关闭。
- 如果为了减少首轮改动使用 lazy singleton，必须提供 `close_web_search_client()` 并在 lifespan 调用，不能依赖进程退出回收。

测试：

- 连续两次调用复用同一个注入 Client。
- shutdown 后 Client 被关闭。
- MockTransport 可以完整替换网络。

### Task 4：`web_search` Tool

先写 `tests/test_web_search_tool.py`：

- query 为空。
- query 超过 300 字符。
- max_results 边界。
- freshness_days 边界。
- 常见 API Key、Bearer、JWT、GitHub/Slack Token 被拒绝。
- 敏感查询拒绝时 Client 没有被调用。
- 成功和空结果结构。
- 配置缺失、超时、429 和 provider error。

实现：

- 懒加载/注入 WebSearchClient。
- 参数和敏感查询检查。
- 异常转为稳定错误码。
- M1 Tool 返回结果中不生成 evidence ID。

### Task 5：注册工具

修改 `registry.py`：

- 新增 `WEB_SEARCH_SCHEMA`。
- `freshness_days` 使用单一 integer 类型并保持可选。
- 注册 callable。

更新 `tests/test_agent_tools.py`：

- 第 4 个工具可见。
- schema `additionalProperties=false`。
- Executor 能执行 dict 和 JSON string 参数。
- Executor 的通用 `default_tool_kwargs` 行为保持现状。

### Task 6：M1 ReAct 闭环和故障降级

使用 fake model 测试：

- 第 1 轮调用 Web Search，第 2 轮输出最终 JSON。
- timeout observation 被回填，模型仍能收尾。
- 429、配置缺失和 provider error 不导致 `/chat` 500。
- 超长 observation 继续被现有 4000 字符限制。

M1 验收：

- 正常搜索可完成。
- 基本超时和所有约定错误可控。
- 不依赖真实 API Key 和真实网络。
- 搜索故障时 `/chat` 返回结构化导师回复。

## 4. M2：Agent 自动决策与调用预算

### Task 7：路由 Prompt

在 `app/services/agent/personas.py` 增加公共 `WEB_SEARCH_TOOL_PROMPT`：

- 自己资料优先本地 RAG。
- 最新/外部信息使用 Web Search。
- 本地无结果且需要外部信息时允许降级搜索。
- 基础概念不搜索。
- 用户禁止联网时不搜索。
- Web snippet 是不可信数据。

`test_agent_prompt_builder.py` 只检查规则存在和顺序，不把它当路由正确性的证明。

### Task 8：代码级调用预算

修改 `ReactOrchestrator.run()`：

- 每次运行初始化 `web_search_calls=0`。
- 执行前检查工具名。
- 前两次正常执行。
- 第三次返回 `web_search_budget_exceeded`，不调用 Provider。
- 预算结果计入现有失败次数。

不新增 `ToolExecutionContext`，不使用 Executor 默认参数实现预算。

### Task 9：路由评估集

新增 `tests/data/web_search_eval.jsonl`，首批至少 40 条：

- 10 条必须搜索。
- 10 条不应搜索。
- 10 条本地 RAG 优先。
- 10 条本地 + Web 混合。

记录字段：

```json
{
  "id": "web-route-001",
  "question": "FastAPI 当前最新稳定版有哪些破坏性变更？",
  "expected_route": "web",
  "requires_freshness": true,
  "notes": "版本和当前状态必须联网"
}
```

运行真实模型评估，不要求每次单测调用真实模型。

M2 验收阈值：

- 必须搜索召回率 ≥ 90%。
- 不必要搜索率 ≤ 10%。
- 本地资料问题优先 RAG ≥ 90%。
- 混合场景能在 3 轮内完成本地 → Web → 回答。

若未达标：先调 Tool description 和 Prompt；不立即增加 Router。

## 5. M3：Evidence ID、引用和前端

### Task 10：Evidence Ledger

修改 `ReactOrchestrator`：

1. 每次 run 初始化 ledger 和序号。
2. Web Search 返回后过滤安全结果。
3. 为新 URL 分配 `web_1`、`web_2`。
4. 同一 URL 复用 ID。
5. 将 evidence ID 注入给模型的 observation。
6. 将完整安全来源保存在 `ToolTrace` 的 excluded 内部字段。

测试：

- 多轮 ID 不重复。
- 重复 URL 复用 ID。
- observation 截断不删除内部 ledger。
- 对外 `tool_trace.model_dump()` 仍只有公开字段。

### Task 11：模型输出和来源解析

修改 `app/schemas/chat.py`：

- 新增 `Source`。
- `TutorReply.sources` 默认空列表。
- `TutorReply.source_ids` 为 excluded 内部字段。

修改 Prompt：

- 模型返回 `source_ids`。
- answer 使用 `[web_N]`。
- answer 禁止原始 URL。

修改 `ResponseParser` 和 `TutorAgentService`：

- 解析 source IDs。
- 仅从 ledger 构建 sources。
- 去除不存在 ID 的标记。
- 扫描 answer，将原始 HTTP(S) URL 替换为 `[已移除未验证链接]` 并记录指标。
- 在保存数据库前完成解析，确保持久化的是安全公开响应。

测试：

- 虚构 ID 不产生来源。
- 模型不可能控制最终 URL。
- 删除无效 ID 后不重新编号。
- 旧数据库回复兼容。

### Task 12：前端来源卡片

前端：

- 根据 `reply.sources` 渲染来源卡片。
- 显示 title、domain。
- 点击 URL 使用安全的新窗口属性。
- answer 中 `[web_N]` 可以定位对应 source.id。
- sources 为空时不渲染区域。

M3 验收：

- 每个 URL 都由服务端 ledger 产生。
- answer 不含未经验证的原始链接。
- 引用正确率为 100%。

## 6. M4：可靠性和生产可观测性

### Task 13：一次重试

只重试：

- 连接失败。
- 读取超时。
- HTTP 502/503/504。

不重试 400、401、403、429 和非法响应。

注入 sleep/backoff，测试不真实等待。

### Task 14：TTL 缓存

实现进程内 LRU + TTL：

- TTL 15 分钟。
- 最大 256 项。
- 缓存成功和空结果。
- 不缓存错误。
- key 包含 provider、normalized query、max_results、freshness_days。

并发量上升后再增加 singleflight；多 worker 后再评估 Redis。

### Task 15：结构化日志和指标

新增 `app/services/web_search_metrics.py` 或复用项目日志设施：

```text
query_hash
query_length
provider
provider_latency_ms
total_tool_latency_ms
chat_latency_ms
result_count
error_code
cache_hit
retry_count
call_count
```

规则：

- 默认不记录 query 原文。
- 不记录 snippet 和供应商原始响应。
- 可用离线脚本聚合 P50/P95、错误率和 cache hit。

### Task 16：可选熔断

只有真实监控显示供应商连续失败影响明显时才实施：

- 连续失败阈值。
- open 时间窗口。
- half-open 探测。
- `circuit_open` 错误。

不作为 M4 必须项，避免无数据过度设计。

M4 验收：

- 重试行为符合矩阵。
- 缓存可观测且不缓存错误。
- 能从结构化数据计算 P95 和失败率。
- 搜索服务故障时主聊天链路稳定。

## 7. M5：质量评估和总结

### Task 17：扩展评估集

覆盖：

- 时效性事实。
- 官方来源优先。
- RAG 与 Web 冲突。
- 无结果和供应商故障。
- Prompt Injection。
- 敏感 query 拒绝。
- 虚构 source ID。

### Task 18：A/B 对比

```text
A：RAG only
B：RAG + Web Search
```

记录：

- 路由召回率和不必要搜索率。
- Top-K 结果相关性。
- 引用正确率和覆盖率。
- grounded answer 比例。
- `/chat` P95。
- 搜索失败率。
- cache hit。
- 单回答搜索费用和模型费用。

### Task 19：发布门槛

- 引用正确率 = 100%。
- 必须搜索召回率 ≥ 90%。
- 不必要搜索率 ≤ 10%。
- 本地资料优先 RAG ≥ 90%。
- 搜索失败不导致 `/chat` 500。
- P95 和成本变化有记录并被接受。

## 8. 推荐提交拆分

```text
1. test: add failing Tavily adapter contract tests
2. feat: add web search config and synchronous client
3. feat: register web_search tool with safe error handling
4. feat: add ReAct web search budget and routing prompt
5. feat: add evidence ledger and source ID resolution
6. feat: render verified web sources in frontend
7. feat: add retry cache and structured metrics
8. test: add web routing and RAG comparison evaluations
```

## 9. 完成检查

每个里程碑合入前执行：

```powershell
pytest tests/test_web_search_client.py -q
pytest tests/test_web_search_tool.py -q
pytest tests/test_agent_tools.py -q
pytest tests/test_agent_react_loop.py -q
pytest tests/test_agent_prompt_builder.py -q
pytest tests/test_stage2_api.py -q
pytest -q
```

真实供应商冒烟测试必须显式启用，默认测试套件不得读取真实 Web Search API Key。


