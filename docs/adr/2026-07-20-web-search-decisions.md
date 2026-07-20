# ADR: Web Search 关键设计决策

> 状态：Accepted  
> 日期：2026-07-20  
> 规格：`docs/tools/web-search-tool-spec.md`  
> 实施计划：`docs/superpowers/plans/2026-07-20-web-search.md`

## 背景

Tutor Agent 已有 ToolRegistry、ToolExecutor、最多 3 轮的 ReactOrchestrator，以及本地 RAG、JD 检索和确定性评分工具。新增 Web Search 的目标是补齐最新和外部公开信息，而不是替换现有 Agent 架构。

本 ADR 记录容易随开发顺序或供应商变化而被反复讨论的关键决策。工具契约和测试细节以 Tool Spec 为准。

## ADR-001：增量接入，不重写 Agent

**决策**

把 `web_search` 注册为第 4 个工具，继续使用现有：

```text
ToolRegistry → ToolExecutor → ReactOrchestrator
```

**原因**

- 当前 3 轮 ReAct 已能完成本地检索 → Web 检索 → 回答。
- 重写编排会扩大回归面，不能直接提升搜索质量。
- 当前没有持久化工作流、人工审批或长时间任务需求。

**后果**

- Web Search 必须适配现有同步工具结果格式。
- 单次任务复杂度受 3 轮上限约束。
- 未来出现长任务和恢复需求时再评估 LangGraph 等工作流框架。

## ADR-002：首个供应商使用 Tavily，但业务接口供应商无关

**决策**

MVP 使用 Tavily Adapter；Agent 只依赖 `WebSearchClient` 和统一结果模型。

**原因**

- 先用一个供应商验证完整闭环。
- 避免 Tool schema 出现 Tavily 专用字段。
- 未来可替换 Brave、Serper 或其他供应商。

**后果**

- `freshness_days` 必须由 Adapter 转换，不能透传。
- 不同 Provider 可以有不同内部映射，但输出必须一致。
- 供应商切换只修改 Adapter 和配置，不修改 Prompt 或工具契约。

## ADR-003：Tavily MVP 固定低成本搜索参数

**决策**

固定：

```json
{
  "search_depth": "basic",
  "include_answer": false,
  "include_raw_content": false,
  "auto_parameters": false
}
```

`freshness_days` 转换为：

```python
start_date = clock.today_utc() - timedelta(days=freshness_days)
```

**原因**

- 避免高级搜索深度带来的额外延迟和费用。
- 不使用供应商生成 answer，保持证据与回答生成职责分离。
- 不返回 raw content，控制上下文和不可信输入体积。
- `start_date` 比 day/week/month/year 更准确表达任意天数。

**后果**

- MVP 的召回能力可能低于 advanced search。
- 如果评估显示 basic 不足，应通过数据调整，而不是让供应商自动决定。

## ADR-004：同步 HTTP，但 Client 必须复用和可注入

**决策**

MVP 使用同步 `httpx.Client`，通过构造函数注入并在应用生命周期关闭。

**原因**

- 当前 ToolExecutor 和 `/chat` 链路是同步的。
- 先避免异步改造扩大范围。
- Client 注入可直接使用 `httpx.MockTransport` 做无网络测试。

**后果**

- 单次搜索会占用当前请求线程。
- 必须设置 5～8 秒超时。
- 并发和 P95 成为瓶颈时，再迁移 AsyncClient、并发限制和 singleflight。

## ADR-005：MVP 不增加确定性 Router

**决策**

MVP 通过工具描述和公共 Prompt 路由；使用真实模型评估阈值验收，不宣称 100% 保证。

**原因**

- 新 Router 会增加模型调用、延迟和维护成本。
- 当前需求允许通过已有 ReAct 自主选择工具。
- 先收集误路由数据，再判断是否需要硬路由。

**验收阈值**

- 必须搜索召回率 ≥ 90%。
- 不必要搜索率 ≤ 10%。
- 本地资料优先 RAG ≥ 90%。

**后果**

- 单个请求仍可能误路由。
- 如果未来业务要求强制联网或强制禁止联网，应增加确定性策略层，而不是继续堆 Prompt。

## ADR-006：引用使用服务端 Evidence ID，不接受模型 URL

**决策**

Orchestrator 为每个安全结果分配本轮唯一 `web_N`；模型只输出 `source_ids`，最终 URL 由服务端 ledger 构建。

**原因**

模型输出 URL 后再做白名单比较仍存在：

- answer 正文直接生成虚假 URL。
- 删除非法来源后位置编号错位。
- URL 规范化误伤大小写敏感路径或查询参数。

**后果**

- answer 使用 `[web_1]`，不使用易错位的 `[1]`。
- `Source` 公开包含 `id`，前端按 ID 关联卡片。
- 服务端必须扫描 answer，禁止原始 HTTP(S) URL。
- evidence ledger 是请求级内部状态，不进入公开 trace。

## ADR-007：Web Search 预算由 Orchestrator 管理

**决策**

每次 `/chat` 最多两次 Web Search，由 `ReactOrchestrator.run()` 计数和拒绝。

**原因**

- 预算是一次 Agent 运行级约束，不是单个函数参数。
- ToolExecutor 的默认参数合并不适合管理跨调用计数。
- 不为 MVP 引入完整 `ToolExecutionContext`。

**后果**

- 第三次调用返回 `web_search_budget_exceeded`。
- ToolExecutor 保持通用职责。
- 如果以后多个工具共享费用预算，再设计统一 ExecutionContext。

## ADR-008：M1 必须失败安全，M4 才做优化

**决策**

M1 包含：

- 超时。
- HTTP/响应错误分类。
- 配置缺失。
- 最终异常边界。
- `/chat` 降级收尾。

M4 包含：

- 一次重试。
- TTL 缓存。
- 结构化指标完善。
- 可选熔断。

**原因**

外部服务从第一天就可能失败；失败安全不是性能增强项。

**后果**

M1 工作量略高，但完成后具备可上线的基本故障边界。

## ADR-009：Prompt 不是隐私边界

**决策**

发送前增加敏感凭证检测；默认日志只记录 query hash 和长度，不记录原文。

**原因**

工具参数技术上可以接收任意字符串，仅靠“不要发送隐私”的 Prompt 不能形成确定性保护。

**后果**

- 可能出现少量误报，需要通过指标调整规则。
- 不承诺 MVP 自动识别所有 PII。
- 日志排障需要显式、安全的开发开关。

## ADR-010：前端 Tool Trace 不承担生产指标

**决策**

Provider 延迟、工具总延迟、错误码、cache hit、retry count 和 `/chat` 延迟写入结构化日志或评估结果。

**原因**

前端 trace 面向单请求调试，无法可靠聚合生产 P95，也不应承载敏感或大体积数据。

**后果**

- trace 保持轻量。
- 需要独立指标聚合或离线评估脚本。
- 性能验收基于结构化数据，而不是人工查看 DebugDetails。

## ADR-011：MVP 只搜索，不抓取网页全文

**决策**

MVP 只使用 Search API 的标题、URL 和 snippet，不实现通用页面抓取。

**原因**

- 降低 Prompt Injection 内容体积。
- 避免 SSRF、下载文件和动态页面处理。
- 先验证搜索路由与引用闭环。

**后果**

- 某些复杂问题的证据深度有限。
- 若后续增加全文读取，必须单独提交安全设计和 ADR。


## ADR-012：API Key 只通过服务端配置注入

**决策**

Tavily Key 使用服务端环境变量，读取优先级：

```text
WEB_SEARCH_API_KEY > TAVILY_API_KEY
```

不提供设置、读取或回显 API Key 的 HTTP 接口，也不允许模型通过 Tool 参数传入 Key。

**原因**

- `TAVILY_API_KEY` 兼容 Tavily 常用配置方式。
- `WEB_SEARCH_API_KEY` 保留供应商无关的部署覆盖能力。
- 避免 Key 进入浏览器、聊天历史、Tool trace 或模型上下文。

**后果**

- 修改 Key 通过部署环境或本地 `.env` 完成。
- 两个变量都缺失时，应用仍可启动；首次搜索返回 `search_not_configured`。
- 日志和异常必须对鉴权信息脱敏。
## 参考

- [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Tavily Search Best Practices](https://docs.tavily.com/documentation/best-practices/best-practices-search)

