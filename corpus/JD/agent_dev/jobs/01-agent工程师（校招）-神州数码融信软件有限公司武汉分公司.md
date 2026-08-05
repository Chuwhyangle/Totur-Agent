# agent工程师（校招）

> 来源：[https://www.ncss.cn/student/jobs/QVVKkAvkGX4GrApqn7LRiK/detail.html](https://www.ncss.cn/student/jobs/QVVKkAvkGX4GrApqn7LRiK/detail.html)
> 采集时间：2026-08-04 17:24（北京时间）

## 职位原文

```text
agent工程师（校招）[全职]——神州数码融信软件有限公司武汉分公司招聘agent工程师（校招）
16k-20k|本科及以上|招聘 10人07-31 15:11 更新
专业不限来源： 国家大学生就业服务平台
全国
职位详情
【工作职责】

1、负责AI Agent系统的需求分析、架构设计与核心模块开发，包括任务规划、工具调用、多轮对话管理、记忆机制及自主决策能力实现； 

2、基于大语言模型（LLM）构建可扩展、高可用的Agent应用，完成Prompt工程优化、RAG增强、Function Calling集成及Agent编排框架开发；

3、与产品研发、项目交付团队协同推进Agent在业务场景（软件工艺开发如需求、设计、开发、测试等内部提效工具等）中的落地部署与迭代优化； 

【任职资格】

1、计算机科学、人工智能、软件工程或相关专业，有AI应用或Agent系统开发经验者优先； 

2、熟练掌握Python，熟悉主流AI开发框架（如LangChain、LlamaIndex、AutoGen、Semantic Kernel等）；

3、具备扎实的算法与数据结构基础，熟悉RESTful API设计、异步编程、分布式任务调度及常见中间件（Redis、MQ等）的应用； 

4、具备优秀的逻辑思维、问题解决能力与跨团队协作意识，对AI技术发展保持持续关注与实践热情。
```

## 结构化字段

| 字段 | 值 |
|---|---|
| 职位名称 | agent工程师（校招） |
| 招聘类型 | 全职 |
| 薪资 | 16k-20k |
| 学历要求 | 本科及以上 |
| 招聘人数 | 10人 |
| 专业要求 | 专业不限 |
| 工作地区 | 全国 |
| 更新时间 | 07-31 15:11 |
| 信息来源 | 国家大学生就业服务平台 |
| 命中搜索词 | Agent、数字人 |
| 相关度 | 直接相关（分值 67） |

## 公司信息

| 字段 | 值 |
|---|---|
| 招聘主体 | 神州数码融信软件有限公司武汉分公司 |
| 所属行业 | 计算机服务（系统/数据/维护/安全） |
| 涉及领域 | 计算机服务（系统/数据/维护/安全） |
| 公司性质 | 民营企业 |
| 公司规模 | 100-499人 |
| 公司网址 | http://www.dcits.com/company/ |
| 所在地址 | 湖北省武汉市湖北省武汉市武昌区中山路254号4-9栋肩并肩孵化器A906 |

## 福利标签

五险一金、带薪年假、岗位晋升、技能培训、弹性工作、股权激励、定期体检、扁平管理、午餐补助

## 技术关键词

Python、大模型/LLM、Agent、RAG、Prompt、Memory/上下文、Function Calling/工具调用、任务规划/编排、LangChain、LlamaIndex、AutoGen、Semantic Kernel、API/HTTP、数据库、算法/数据结构、异步/并发

## 与 Tutor Agent 项目的对应点

- **Python** → 整个后端都是 Python，含类型标注、pytest 自动化测试和本地脚本工具链。
- **大模型/LLM** → OpenAI-compatible 客户端接入，chat 与 embedding 走两套独立配置（`OPENAI_BASE_URL` / `EMBEDDING_BASE_URL`），密钥走环境变量不入库。
- **Agent** → `app/services/agent/` 里的 ReAct 多轮工具循环：模型可连续多轮请求工具，`tool_trace.calls[]` 记录工具名、参数、结果摘要和 round。
- **RAG** → `scripts/build_knowledge_index.py` 扫描 `docs/**/*.md` 建 Chroma `learning_notes` 索引，`search_learning_notes` 检索后强制回答标注来源。
- **Prompt** → prompt 模块 + 可切换导师人设（`GET /personas`），以及结构化回复的解析与容错。
- **Memory/上下文** → 多会话记忆 + 会话摘要 + SQLite 持久化；会话绑定 persona_id，切换历史会话能恢复人设。
- **Function Calling/工具调用** → 工具注册与调用链路，`search_learning_notes` 等工具的参数校验、结果摘要和失败回退。
- **任务规划/编排** → ReAct 循环里的「思考—选工具—看结果—再决策」控制流，以及回复解析成 answer / next_task / exercise / checkpoints 四段式的输出编排。
- **API/HTTP** → FastAPI 路由分层：`/chat`、`/sessions`、`/personas`、`/interview-jds`，请求/响应用 schemas 约束。
- **数据库** → SQLite 表设计与 `repositories/` 读写分层，持久化对话、会话、摘要和面试 JD。
- **异步/并发** → FastAPI 异步接口链路，以及工具调用的超时与异常处理。

## 同模板的其他投放

以下 19 条职位的 JD 正文与本条完全一致（同一份模板在不同主体/分公司重复投放），统计技能频次时应视为 1 条：

- 神州数码融信软件有限公司太原分公司 — [https://www.ncss.cn/student/jobs/W1dWjjvm5MANceTPtWqQoQ/detail.html](https://www.ncss.cn/student/jobs/W1dWjjvm5MANceTPtWqQoQ/detail.html)
- 神州数码信息系统有限公司宁波分公司 — [https://www.ncss.cn/student/jobs/TSRURoz8Nxnqij9t9gPR1X/detail.html](https://www.ncss.cn/student/jobs/TSRURoz8Nxnqij9t9gPR1X/detail.html)
- 神州数码融信软件有限公司上海分公司 — [https://www.ncss.cn/student/jobs/PaksANiMUytKV5rbMemrRE/detail.html](https://www.ncss.cn/student/jobs/PaksANiMUytKV5rbMemrRE/detail.html)
- 神州数码融信软件有限公司杭州分公司 — [https://www.ncss.cn/student/jobs/6HaWhRKLrKvz4tnUQ1C1Tv/detail.html](https://www.ncss.cn/student/jobs/6HaWhRKLrKvz4tnUQ1C1Tv/detail.html)
- 北京云核网络技术有限公司 — [https://www.ncss.cn/student/jobs/QNH5Ufgg5pvTuka9cJiW4p/detail.html](https://www.ncss.cn/student/jobs/QNH5Ufgg5pvTuka9cJiW4p/detail.html)
- 神州数码信息服务集团股份有限公司 — [https://www.ncss.cn/student/jobs/3QwrjM3B8pXvwZpKQy6WzU/detail.html](https://www.ncss.cn/student/jobs/3QwrjM3B8pXvwZpKQy6WzU/detail.html)
- 神州数码系统集成服务有限公司合肥分公司 — [https://www.ncss.cn/student/jobs/AEoUJXYzVjKQ1xuhqYAZ5n/detail.html](https://www.ncss.cn/student/jobs/AEoUJXYzVjKQ1xuhqYAZ5n/detail.html)
- 神州数码系统集成服务有限公司深圳分公司 — [https://www.ncss.cn/student/jobs/XcdvkSBK6voyiaWkZgCKht/detail.html](https://www.ncss.cn/student/jobs/XcdvkSBK6voyiaWkZgCKht/detail.html)
- 神州数码系统集成服务有限公司福州分公司 — [https://www.ncss.cn/student/jobs/QGSHbudq6GD1xSPKCo5bz4/detail.html](https://www.ncss.cn/student/jobs/QGSHbudq6GD1xSPKCo5bz4/detail.html)
- 神州数码系统集成服务有限公司广州分公司 — [https://www.ncss.cn/student/jobs/WU88digdvMshZtRcrxYxp9/detail.html](https://www.ncss.cn/student/jobs/WU88digdvMshZtRcrxYxp9/detail.html)
- 神州数码系统集成服务有限公司成都分公司 — [https://www.ncss.cn/student/jobs/CLBUqPz3SrLCt8CqaotbZm/detail.html](https://www.ncss.cn/student/jobs/CLBUqPz3SrLCt8CqaotbZm/detail.html)
- 神州数码系统集成服务有限公司上海分公司 — [https://www.ncss.cn/student/jobs/5fgRQeh8kYqv9TA9wmVpRs/detail.html](https://www.ncss.cn/student/jobs/5fgRQeh8kYqv9TA9wmVpRs/detail.html)
- 北京神州数码锐行快捷信息技术服务有限公司 — [https://www.ncss.cn/student/jobs/Cqzk312GSLhn1q9rK1rG68/detail.html](https://www.ncss.cn/student/jobs/Cqzk312GSLhn1q9rK1rG68/detail.html)
- 北京神州数字科技有限公司 — [https://www.ncss.cn/student/jobs/CVoHNXNsSNh5GJuUrNw5ok/detail.html](https://www.ncss.cn/student/jobs/CVoHNXNsSNh5GJuUrNw5ok/detail.html)
- 神州数码系统集成服务有限公司 — [https://www.ncss.cn/student/jobs/2Y75wRPQgGPqvhXMvLbCKw/detail.html](https://www.ncss.cn/student/jobs/2Y75wRPQgGPqvhXMvLbCKw/detail.html)
- 神州数码融信软件有限公司 — [https://www.ncss.cn/student/jobs/WJfEhbRQsL8k9hgjDxsQGZ/detail.html](https://www.ncss.cn/student/jobs/WJfEhbRQsL8k9hgjDxsQGZ/detail.html)
- 神州数码信息服务集团股份有限公司北京分公司 — [https://www.ncss.cn/student/jobs/TU7VbQgMtxYqEePPmaewN3/detail.html](https://www.ncss.cn/student/jobs/TU7VbQgMtxYqEePPmaewN3/detail.html)
- 神州数码融信软件有限公司西安分公司 — [https://www.ncss.cn/student/jobs/U6GB83odbbgU83DMZgAvJE/detail.html](https://www.ncss.cn/student/jobs/U6GB83odbbgU83DMZgAvJE/detail.html)
- 神州数码信息系统有限公司 — [https://www.ncss.cn/student/jobs/LH5AFvkwysGx1Me1QztLP5/detail.html](https://www.ncss.cn/student/jobs/LH5AFvkwysGx1Me1QztLP5/detail.html)
