# Agent开发实习生

> 来源：[https://www.ncss.cn/student/jobs/NGwwn7V3FAVmGMo71Pem8Q/detail.html](https://www.ncss.cn/student/jobs/NGwwn7V3FAVmGMo71Pem8Q/detail.html)
> 采集时间：2026-08-04 17:24（北京时间）

## 职位原文

```text
Agent开发实习生[实习]——中原AI院招聘Agent开发实习生
3k-5k|本科及以上|招聘 2人07-30 16:12 更新
专业不限来源： 国家大学生就业服务平台
河南省郑州市市辖区
职位详情
因工作需要，现面向在校生公开招聘JAVA开发实习生1-2名。

一、工作描述

1.扎实的工程基础，具备良好的代码设计与工程实践能力；

2.熟悉主流编程语言(Python/Go/Java 等)；

3.了解数据结构与算法；

4.熟悉数据库、缓存、消息队列等常用中间件；

5.理解并发编程模型(多线程/协程/异步IO)；

6.了解 TCP/IP、HTTP 等网络协议；

7.了解操作系统、进程/线程调度、内存管理等服务器基本原理；

8.理解 Agent 的核心概念与架构(感知-规划-行劫-记忆)；

9.熟悉 Agent 的工作流程与工具调用(Tool Use)；

10.了解Prompt、Memory、RAG、FunctionCalling 等关键技术；

11.仅限2027年及以后毕业生报名，本科及以上学历；

12.实习期6个月以上，每周5天，实习补贴每月3000-5000元（视能力、学历、学校等综合因素而定）。



二、报名方式

将个人简历等资料发送至指定邮箱，邮件标题命名为：JAVA—姓名—学历—毕业院校-专业。

发送邮箱：aihr_criait@hnas.ac.cn

    

工作地点：河南省郑州市郑东新区龙子湖河南省科学院大楼
```

## 结构化字段

| 字段 | 值 |
|---|---|
| 职位名称 | Agent开发实习生 |
| 招聘类型 | 实习 |
| 薪资 | 3k-5k |
| 学历要求 | 本科及以上 |
| 招聘人数 | 2人 |
| 专业要求 | 专业不限 |
| 工作地区 | 河南省郑州市市辖区 |
| 更新时间 | 07-30 16:12 |
| 信息来源 | 国家大学生就业服务平台 |
| 命中搜索词 | Agent、Agent开发、人工智能 |
| 相关度 | 直接相关（分值 27） |

## 公司信息

| 字段 | 值 |
|---|---|
| 招聘主体 | 中原人工智能产业技术研究院 |
| 所属行业 | 计算机软件 |
| 涉及领域 | 计算机软件，计算机服务（系统/数据/维护/安全） |
| 公司性质 | 机关/事业单位/非营利机构 |
| 公司规模 | 50-99人 |
| 公司网址 | https://www.zhongyuanai.cn/ |
| 所在地址 | 河南省郑州市郑州市郑东新区龙子湖智慧岛崇实里228号 |

## 福利标签

五险一金、带薪年假、定期体检、扁平管理、年终奖、年底双薪、绩效奖金、交通补助、午餐补助、通讯津贴

## 技术关键词

Python、Java、Agent、RAG、Prompt、Function Calling/工具调用、API/HTTP、数据库、消息中间件、算法/数据结构、异步/并发

## 与 Tutor Agent 项目的对应点

- **Python** → 整个后端都是 Python，含类型标注、pytest 自动化测试和本地脚本工具链。
- **Agent** → `app/services/agent/` 里的 ReAct 多轮工具循环：模型可连续多轮请求工具，`tool_trace.calls[]` 记录工具名、参数、结果摘要和 round。
- **RAG** → `scripts/build_knowledge_index.py` 扫描 `docs/**/*.md` 建 Chroma `learning_notes` 索引，`search_learning_notes` 检索后强制回答标注来源。
- **Prompt** → prompt 模块 + 可切换导师人设（`GET /personas`），以及结构化回复的解析与容错。
- **Function Calling/工具调用** → 工具注册与调用链路，`search_learning_notes` 等工具的参数校验、结果摘要和失败回退。
- **API/HTTP** → FastAPI 路由分层：`/chat`、`/sessions`、`/personas`、`/interview-jds`，请求/响应用 schemas 约束。
- **数据库** → SQLite 表设计与 `repositories/` 读写分层，持久化对话、会话、摘要和面试 JD。
- **异步/并发** → FastAPI 异步接口链路，以及工具调用的超时与异常处理。
