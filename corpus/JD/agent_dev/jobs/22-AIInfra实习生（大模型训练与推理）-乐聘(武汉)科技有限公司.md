# AI Infra实习生（大模型训练与推理）

> 来源：[https://www.ncss.cn/student/jobs/9dDP7wudPnsXPDVHWvAXy5/detail.html](https://www.ncss.cn/student/jobs/9dDP7wudPnsXPDVHWvAXy5/detail.html)
> 采集时间：2026-08-04 17:24（北京时间）

## 职位原文

```text
AI Infra实习生（大模型训练与推理）[实习]——关键词：AI Infra、分布式训练、CUDA、NCCL、Megatron-LM、DeepSpeed、vLLM、推理优化。
10k-20k|硕士及以上|招聘 3人07-30 16:16 更新
计算机 人工智能 自动化 机器人 AI 软件工程 软件 电子工程 电子来源： 国家大学生就业服务平台
浙江省杭州市西湖区
职位详情
岗位职责

参与LLM、World Model及多模态模型训练基础设施建设；

优化分布式训练中的数据并行、模型并行和流水线并行策略；

分析通信、显存、计算及IO瓶颈，提升GPU利用率和训练稳定性；

参与大模型推理服务建设，开展量化、KV Cache、Continuous Batching等优化；

对Megatron-LM、DeepSpeed、FSDP、vLLM等框架进行测试、分析和改进；

参与新型GPU硬件、通信方案及训练推理软件栈的评测。



任职要求

计算机、软件工程、电子工程等相关专业在读硕士或博士；

熟练使用Python或C++，具备扎实的数据结构与系统基础；

了解GPU体系结构、CUDA、NCCL或分布式计算；

有PyTorch分布式训练、DeepSpeed、Megatron-LM或FSDP项目经验者优先；

有vLLM、TensorRT-LLM、SGLang等推理框架实践者优先；

有MLSys、OSDI、SOSP、SC等相关论文或开源贡献者优先。
```

## 结构化字段

| 字段 | 值 |
|---|---|
| 职位名称 | AI Infra实习生（大模型训练与推理） |
| 招聘类型 | 实习 |
| 薪资 | 10k-20k |
| 学历要求 | 硕士及以上 |
| 招聘人数 | 3人 |
| 专业要求 | 计算机 人工智能 自动化 机器人 AI 软件工程 软件 电子工程 电子 |
| 工作地区 | 浙江省杭州市西湖区 |
| 更新时间 | 07-30 16:16 |
| 信息来源 | 国家大学生就业服务平台 |
| 命中搜索词 | AI平台、AI技术、大模型 |
| 相关度 | 较相关（分值 9） |

## 公司信息

| 字段 | 值 |
|---|---|
| 招聘主体 | 乐聘(武汉)科技有限公司 |
| 所属行业 | 专业服务（财会/法律/翻译/人力资源等） |
| 涉及领域 | 电子技术/半导体/集成电路 |
| 公司性质 | 民营企业 |
| 公司规模 | 50-99人 |
| 公司网址 | https://1lux.xyz/jobmorse/app |
| 所在地址 | 湖北省武汉市武汉市汉阳区绿地国博财富中心13号楼812 |

## 福利标签

带薪年假、技能培训、扁平管理、绩效奖金、零食水果

## 技术关键词

Python、C++、大模型/LLM、推理部署、多模态、算法/数据结构、PyTorch/TensorFlow

## 与 Tutor Agent 项目的对应点

- **Python** → 整个后端都是 Python，含类型标注、pytest 自动化测试和本地脚本工具链。
- **大模型/LLM** → OpenAI-compatible 客户端接入，chat 与 embedding 走两套独立配置（`OPENAI_BASE_URL` / `EMBEDDING_BASE_URL`），密钥走环境变量不入库。
- **推理部署** → 项目走的是 API 接入而非自建推理，面试时讲清楚取舍即可，不要伪装部署经验。
