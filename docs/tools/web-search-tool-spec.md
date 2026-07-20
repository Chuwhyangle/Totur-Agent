# Tool Spec: web_search

> 状态：Approved for M1  
> 日期：2026-07-20  
> 相关计划：`docs/superpowers/plans/2026-07-20-web-search.md`  
> 相关决策：`docs/adr/2026-07-20-web-search-decisions.md`

## 1. 定位

`web_search` 是 Tutor Agent 的外部公开信息检索工具，作为现有工具系统中的第 4 个工具接入：

| 工具 | 数据边界 |
| --- | --- |
| `search_learning_notes` | 用户自己的学习资料和项目文档 |
| `interview_jd_search` | 本地 SQLite 中已保存的 JD |
| `score_jd_skill_fit` | 确定性技能匹配计算 |
| `web_search` | 最新或外部公开信息 |

继续复用现有链路：

```text
/chat → PromptBuilder → ReactOrchestrator
                         → ToolRegistry
                         → ToolExecutor
                         → web_search
                         → WebSearchClient
                         → Tavily Adapter
```

不重写 Agent，不在 MVP 引入 LangGraph 或独立 Router 模型。

## 2. 目标

- 为“最新、当前、近期版本、外部资料”等问题提供可追溯证据。
- 通过 Provider Adapter 隔离搜索供应商。
- 保持工具输入、输出和错误码稳定。
- 防止模型生成未被工具返回的来源。
- 外部服务失败时保证 `/chat` 可以降级回答。
- 为路由质量、延迟、失败率和费用建立评估入口。

## 3. 非目标

MVP 不做：

- 任意 URL 全文抓取。
- 浏览器自动化、登录、点击和 JavaScript 渲染。
- 多供应商并行聚合。
- Deep Research 无限循环。
- 将搜索供应商生成的 answer 作为最终证据。
- 将网页正文、完整聊天历史或本地 RAG 内容发送给搜索服务。

后续增加 `fetch_web_page` 时必须另行设计 SSRF、重定向、私网地址、内容类型和下载大小限制。

## 4. 组件边界

```text
WebSearchConfig
    ↓
TavilyWebSearchProvider：供应商 HTTP 协议和字段转换
    ↓
WebSearchClient：供应商无关入口、Client 生命周期
    ↓
web_search()：参数、安全校验和稳定结果
    ↓
ToolRegistry / ToolExecutor
    ↓
ReactOrchestrator：轮次、预算、evidence ledger
    ↓
ResponseParser / TutorAgentService：source_ids 解析和来源构建
    ↓
TutorReply.sources
```

职责约束：

- Tool 不知道 Tavily 请求字段。
- Adapter 不知道 Agent、Persona 或聊天历史。
- ToolExecutor 只负责通用参数解析和函数执行。
- Web Search 调用预算由 `ReactOrchestrator.run()` 管理。
- 最终 URL 只能由服务端 evidence ledger 复制产生。

## 5. 配置

在 `app/config.py` 增加：

```python
@dataclass
class WebSearchConfig:
    provider: str
    api_key: str
    base_url: str
    timeout_seconds: float
```

`.env.example`：

```dotenv
WEB_SEARCH_PROVIDER=tavily
TAVILY_API_KEY=tvly-replace_with_your_tavily_key
# 可选的供应商无关覆盖值，优先级高于 TAVILY_API_KEY
# WEB_SEARCH_API_KEY=replace_with_your_search_api_key
WEB_SEARCH_BASE_URL=https://api.tavily.com
WEB_SEARCH_TIMEOUT_SECONDS=7
```

运行策略放在 `app/services/web_search_settings.py`：

```python
WEB_SEARCH_DEFAULT_RESULTS = 5
WEB_SEARCH_MAX_RESULTS = 5
WEB_SEARCH_MAX_CALLS_PER_CHAT = 2
WEB_SEARCH_MAX_QUERY_CHARS = 300
WEB_SEARCH_MAX_SNIPPET_CHARS = 800
WEB_SEARCH_RETRY_COUNT = 1
WEB_SEARCH_CACHE_TTL_SECONDS = 900
WEB_SEARCH_CACHE_MAX_ENTRIES = 256
```

约束：

- API Key 只从服务端环境变量读取，不提供上传、查询或返回 Key 的 HTTP API。
- Tavily Key 支持标准变量 `TAVILY_API_KEY`。
- 通用变量 `WEB_SEARCH_API_KEY` 作为显式覆盖值；读取优先级为 `WEB_SEARCH_API_KEY > TAVILY_API_KEY`。
- 两个 Key 都缺失时，首次调用返回 `search_not_configured`。
- 导入模块时不读取配置，首次实际调用时懒加载。
- 日志、trace、异常、Tool 参数和前端响应不得包含 API Key。

## 6. WebSearchClient

文件：`app/clients/web_search_client.py`

### 6.1 内部模型

```python
@dataclass(frozen=True)
class WebSearchItem:
    title: str
    url: str
    snippet: str
    domain: str
    published_at: str | None = None


@dataclass(frozen=True)
class WebSearchResponse:
    items: list[WebSearchItem]
    provider: str
    provider_latency_ms: int
    cached: bool = False
```

### 6.2 注入和生命周期

```python
class WebSearchClient:
    def __init__(
        self,
        provider: WebSearchProvider,
        *,
        http_client: httpx.Client,
    ) -> None:
        ...
```

要求：

- `httpx.Client` 必须可注入，测试使用 `httpx.MockTransport`。
- 生产环境复用一个 Client，禁止每次搜索都新建连接池。
- FastAPI lifespan/shutdown 负责关闭 Client。
- 测试中显式使用 context manager 或 fixture 关闭 Client。
- Provider、Clock、sleep 可以注入，保证日期和重试测试确定性。

## 7. 通用工具接口

文件：`app/services/agent/tools/web_search.py`

```python
def web_search(
    query: str,
    max_results: int = 5,
    freshness_days: int | None = None,
) -> dict[str, Any]:
    ...
```

OpenAI-compatible JSON Schema：

```json
{
  "type": "function",
  "function": {
    "name": "web_search",
    "description": "Search public web sources for current or external information. Use it for recent changes, current versions, news, policies, prices, schedules, or facts unavailable in local notes.",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {
          "type": "string",
          "description": "A concise standalone query without chat history, secrets, or private user data."
        },
        "max_results": {
          "type": "integer",
          "minimum": 1,
          "maximum": 5,
          "default": 5
        },
        "freshness_days": {
          "type": "integer",
          "minimum": 1,
          "maximum": 3650,
          "description": "Optional recency window in days. Omit when recency is not required."
        }
      },
      "required": ["query"],
      "additionalProperties": false
    }
  }
}
```

兼容性规则：

- `freshness_days` 不需要时直接省略，不使用 `"type": ["integer", "null"]`。
- Python 函数仍接受 `None`，用于直接调用和默认值。
- `query` 去除首尾空白后不能为空。
- `query` 超过 300 字符直接返回 `invalid_arguments`，不静默截断。
- `max_results` 归一化到 `1～5`。
- `freshness_days` 非空时归一化到 `1～3650`。
- 工具不接受 provider、API Key、请求头、目标 URL 或完整 messages。

## 8. Tavily Adapter 映射

`freshness_days` 是内部通用参数，不直接透传给 Tavily。

日期转换：

```python
today = clock.today_utc()
start_date = today - timedelta(days=freshness_days)
```

- `start_date` 使用 `YYYY-MM-DD`。
- `freshness_days is None` 时不发送 `start_date`。
- MVP 不把天数粗略转换成 `time_range`，避免 day/week/month/year 的粒度损失。
- `clock` 必须可注入，单元测试不得依赖真实当天日期。

Tavily MVP 固定请求策略：

```json
{
  "query": "latest FastAPI changes",
  "max_results": 5,
  "search_depth": "basic",
  "include_answer": false,
  "include_raw_content": false,
  "auto_parameters": false,
  "start_date": "2026-07-13"
}
```

其中 `start_date` 仅在提供 `freshness_days` 时出现。

固定这些参数的原因：

- `search_depth=basic`：控制 MVP 延迟和费用。
- `include_answer=false`：不引入供应商生成答案，Agent 只消费搜索证据。
- `include_raw_content=false`：不把全文塞入 observation。
- `auto_parameters=false`：避免供应商自动改变搜索深度等成本相关参数。

Adapter 只负责 Tavily 协议转换；未来 Brave、Serper Adapter 可以采用不同映射，但必须返回同一内部模型。

参考：

- [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Tavily Search Best Practices](https://docs.tavily.com/documentation/best-practices/best-practices-search)

## 9. 搜索结果标准化

Provider 返回结果后：

- 丢弃无标题、无 URL 或非 HTTPS 的结果。
- 拒绝 URL userinfo，例如 `https://user:pass@example.com/`。
- domain 由标准 URL parser 计算，不信任供应商字段。
- snippet 最大 800 字符。
- 按 URL 去重，保留供应商首次出现顺序。
- 不保存供应商完整原始响应。

URL 处理要求：

- 只规范化 scheme 和 host 的大小写。
- 删除 fragment。
- 可删除默认端口 `:443`。
- 保留 path 的大小写。
- 保留 query 参数和值，不自行重排或删除。
- 不再使用“模型 URL 与规范化 URL 比较”作为引用安全边界。

## 10. 工具返回

### 10.1 成功

Tool 初始返回不包含 `evidence_id`；ID 由 Orchestrator 在写入 observation 前分配：

```json
{
  "ok": true,
  "found": true,
  "query": "latest FastAPI changes",
  "items": [
    {
      "title": "FastAPI Release Notes",
      "url": "https://fastapi.tiangolo.com/release-notes/",
      "snippet": "...",
      "domain": "fastapi.tiangolo.com",
      "published_at": "2026-07-18"
    }
  ],
  "summary": {
    "returned_count": 1,
    "provider": "tavily",
    "provider_latency_ms": 820,
    "cached": false
  }
}
```

Orchestrator 写给模型的 observation：

```json
{
  "ok": true,
  "found": true,
  "query": "latest FastAPI changes",
  "items": [
    {
      "evidence_id": "web_1",
      "title": "FastAPI Release Notes",
      "url": "https://fastapi.tiangolo.com/release-notes/",
      "snippet": "...",
      "domain": "fastapi.tiangolo.com",
      "published_at": "2026-07-18"
    }
  ],
  "summary": {
    "returned_count": 1,
    "provider": "tavily",
    "provider_latency_ms": 820,
    "cached": false
  }
}
```

同一次 `/chat` 内 evidence ID 单调递增，跨多次 Web Search 不重复。

### 10.2 空结果

空结果是成功，不是错误：

```json
{
  "ok": true,
  "found": false,
  "query": "...",
  "items": [],
  "summary": {
    "returned_count": 0,
    "provider": "tavily",
    "provider_latency_ms": 430,
    "cached": false
  }
}
```

模型必须解释为“没有检索到足够证据”，不能推断“事实不存在”。

## 11. 错误契约

统一格式：

```json
{
  "ok": false,
  "error": "search_timeout",
  "message": "web search timed out"
}
```

| 错误码 | 含义 | 阶段 |
| --- | --- | --- |
| `invalid_arguments` | 参数非法 | M1 |
| `sensitive_query_rejected` | 查询疑似包含密钥或敏感凭证 | M1 |
| `search_not_configured` | 配置缺失 | M1 |
| `search_timeout` | 连接或读取超时 | M1 |
| `rate_limited` | HTTP 429 | M1 |
| `provider_auth_failed` | HTTP 401/403 | M1 |
| `provider_error` | 其他 HTTP 错误、非法 JSON 或字段异常 | M1 |
| `web_search_budget_exceeded` | 单次聊天调用次数超限 | M2 |
| `circuit_open` | 熔断期间拒绝请求 | M4，可选 |

M1 必须具备：

- 5～8 秒基本超时。
- HTTP 状态和响应错误映射。
- 配置缺失处理。
- Provider、Tool 和 ToolExecutor 最终异常边界。
- `/chat` 降级收尾，不因搜索故障直接返回 500。

M4 再增加：重试、缓存、结构化指标、可选熔断和更高级降级。

错误消息不得包含 API Key、供应商完整响应或堆栈。

## 12. Registry、Executor 与预算

`app/services/agent/tools/registry.py`：

- 新增 `WEB_SEARCH_SCHEMA`。
- 注册 `"web_search": web_search`。
- `get_tools_schema()` 返回第 4 个工具 schema。

`ToolExecutor` 保持通用执行职责。当前实现虽然支持 `default_tool_kwargs` 合并，但 Web Search 预算不使用该机制，也不新增 `ToolExecutionContext`。

预算由 `ReactOrchestrator.run()` 硬限制：

```text
每次 /chat 最多 2 次 web_search
每次最多 5 个结果
单条 snippet 最多 800 字符
observation 继续受现有 4000 字符限制
```

第三次调用不执行 Provider，直接生成 `web_search_budget_exceeded`。

## 13. 工具路由

不新增 Router 模型，通过 Tool description 和公共 system prompt 引导：

| 意图 | 行为 |
| --- | --- |
| 自己的项目、笔记、复盘 | 优先 `search_learning_notes` |
| 最新、当前、近期版本、政策、新闻、价格、日程 | 优先 `web_search` |
| 已保存的岗位/JD | 使用 `interview_jd_search` |
| 自己资料与行业现状对比 | 本地工具后再调用 `web_search` |
| 基础概念、纯推理、代码解释 | 不搜索 |
| 用户明确禁止联网 | 不调用 `web_search` |

Prompt 路由是概率行为，不作为 100% 确定性保证。M2 验收使用评估阈值：

- 必须搜索场景召回率 ≥ 90%。
- 不必要搜索率 ≤ 10%。
- 本地资料问题优先 RAG 的比例 ≥ 90%。

达不到阈值时先优化工具描述和 Prompt；如果业务未来需要 100% 硬保证，再增加确定性 Router。

## 14. Evidence ID 与引用

### 14.1 模型输出契约

模型不返回 URL，只返回本轮 evidence ID：

```json
{
  "answer": "FastAPI 最近的变更应以官方发布说明为准。[web_1]",
  "next_task": "阅读对应版本的 breaking changes。",
  "exercise": "列出升级前需要验证的三个接口。",
  "checkpoints": ["版本", "兼容性", "测试"],
  "source_ids": ["web_1"]
}
```

`answer` 中：

- 只允许 `[web_N]` 引用标记。
- 禁止输出任何原始 `http://` 或 `https://` URL。
- 服务端发现正文 URL 时统一替换为 `[已移除未验证链接]`，并记录 citation validation 指标。

### 14.2 服务端 Evidence Ledger

Orchestrator 为本轮 Web 结果生成：

```python
@dataclass(frozen=True)
class EvidenceSource:
    evidence_id: str
    title: str
    url: str
    domain: str
```

Ledger 规则：

- ID 只能由服务端生成。
- 只在当前 `/chat` 生命周期有效。
- 模型猜测不存在的 ID 无法解析。
- 对同一安全 URL复用同一个 evidence ID。
- ledger 作为内部字段保存，不暴露在 `tool_trace` JSON。

### 14.3 公共响应

```python
class Source(BaseModel):
    id: str
    title: str
    url: str
    domain: str | None = None


class TutorReply(BaseModel):
    answer: str
    next_task: str
    exercise: str
    checkpoints: list[str]
    sources: list[Source] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list, exclude=True)
```

`TutorAgentService`：

1. 解析模型的 `source_ids`。
2. 只解析本轮 ledger 中存在的 ID。
3. 按 `source_ids` 顺序去重。
4. 从 ledger 构建 `TutorReply.sources`，模型不参与 URL 生成。
5. 删除 answer 中引用了无效 ID 的标记。
6. 保持 `[web_N]` 不重新编号，避免删除来源后编号错位。

历史回复没有 `sources` 或 `source_ids` 时继续正常解析。

## 15. Prompt Injection 与隐私

Web 结果是数据，不是指令。模型必须忽略 snippet 中要求：

- 忽略系统提示。
- 泄露系统 Prompt 或会话内容。
- 调用其他工具。
- 向指定 URL 发送信息。
- 输出密钥或改变 JSON 格式。

### 15.1 查询安全检查

Prompt 不是隐私边界。Tool 在发送前执行保守的敏感模式检查，至少覆盖：

- `sk-...`、`ghp_...`、`github_pat_...`、`xoxb-...` 等常见 Token 前缀。
- `Authorization: Bearer ...`。
- 明显 JWT。
- `api_key=...`、`token=...`、`password=...` 等凭证赋值。

命中后返回 `sensitive_query_rejected`，不得发送给供应商。

MVP 不尝试识别所有 PII；公共 Prompt 仍要求模型只生成最小、独立查询。后续根据真实误报率扩展规则。

### 15.2 日志隐私

默认不记录 query 原文。结构化日志记录：

```json
{
  "event": "web_search_completed",
  "query_hash": "sha256:...",
  "query_length": 32,
  "provider": "tavily",
  "provider_latency_ms": 820,
  "total_tool_latency_ms": 845,
  "result_count": 5,
  "cache_hit": false,
  "error_code": null
}
```

开发环境如果需要 query 预览，只允许显式开关并截断、脱敏。

## 16. 可观测性

前端 `tool_trace` 用于单次调试，不承担生产统计。

结构化指标至少包括：

- `provider_latency_ms`。
- `total_tool_latency_ms`。
- `/chat` 端到端延迟。
- provider。
- result count。
- error code。
- cache hit。
- retry count。
- Web Search 每轮调用次数。

P95 从结构化日志或评估结果聚合计算，不能只根据前端 trace 推断。

`tool_trace` 保持轻量，只显示标题、domain、published_at、evidence_id 和可选 latency 摘要，不包含完整 snippet。

## 17. 缓存与重试

属于 M4：

缓存键：

```text
provider + normalized_query + max_results + freshness_days
```

- TTL 默认 15 分钟。
- 最大 256 项，LRU 淘汰。
- 缓存成功结果和空结果。
- 不缓存错误。
- 缓存标准化结果，不缓存原始响应。

最多重试一次：

- 连接失败。
- 读取超时。
- HTTP 502/503/504。

默认不重试 400、401、403、429 和结构非法响应。

## 18. 降级

| 场景 | 行为 |
| --- | --- |
| RAG 有结果，Web 超时 | 基于本地证据回答并说明未核对最新信息 |
| Web 空结果 | 说明证据不足，不推断事实不存在 |
| HTTP 429 | 本轮不重复搜索，使用已有上下文收尾 |
| 配置缺失 | trace 记录错误，`/chat` 继续返回 |
| 本地与 Web 冲突 | 同时说明来源和时间范围 |
| 模型返回无效 source ID | 删除无效引用并记录指标 |
| answer 含原始 URL | 替换为 `[已移除未验证链接]` 并记录指标 |
## 19. 规范性要求

以下要求属于工具契约，实施任务和验收步骤见开发计划：

- `freshness_days` 只能由 Provider Adapter 转换，不能作为供应商字段透传。
- Tavily 请求必须固定关闭 answer、raw content 和 auto parameters，并使用 basic depth。
- 基本超时、错误映射、配置缺失和最终异常边界是首版必备能力。
- 搜索预算必须由 Orchestrator 硬限制，不能只依赖 Prompt。
- 模型只能返回本轮 `source_ids`，不能生成公开 URL。
- answer 中出现原始 HTTP(S) URL 时，服务端替换为 `[已移除未验证链接]` 并记录校验失败。
- 无效 `[web_N]` 标记和 source ID 必须删除；有效 ID 保持原值，不做位置重编号。
- 查询发送前必须执行敏感凭证检查。
- 默认日志不得记录 query、snippet 或供应商原始响应。
- HTTP Client 必须可注入、复用并在应用生命周期结束时关闭。
- 路由正确性通过真实模型评估阈值衡量，不以 Prompt 单元测试代替。

## 20. 参考

- [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Tavily Search Best Practices](https://docs.tavily.com/documentation/best-practices/best-practices-search)


