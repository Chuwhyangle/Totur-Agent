r"""抓取国家大学生就业服务平台（ncss.cn）职位，按 JD 正文去重，一个 JD 输出一个 md。

用法：
    .\.venv\Scripts\python.exe scripts\fetch_ncss_jobs.py --direction agent --target 50
    .\.venv\Scripts\python.exe scripts\fetch_ncss_jobs.py --direction marketing --target 80

方向：
    agent      Agent / 大模型应用开发岗位（默认）
    marketing  运营 / 市场营销岗位（自动剔除保险、推销类）

数据来源全部是平台公开的职位列表接口和职位详情页，不涉及登录态。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://www.ncss.cn"
LIST_API = f"{BASE}/student/jobs/jobslist/ajax/"
DETAIL_URL = f"{BASE}/student/jobs/{{job_id}}/detail.html"

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / ".test-tmp" / "ncss_cache"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": f"{BASE}/student/jobs/index.html",
    "X-Requested-With": "XMLHttpRequest",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 搜索关键词：从最贴近 Agent 岗的词往外扩，先窄后宽，保证高相关的先进池子。
KEYWORDS = [
    "Agent", "智能体", "AI Agent", "多智能体", "智能体开发", "Agent开发", "智能助手",
    "大模型应用", "大模型开发", "大模型工程师", "大模型", "LLM", "大语言模型",
    "AIGC", "生成式AI", "AI工程师", "AI开发", "AI应用开发", "人工智能应用", "人工智能开发",
    "RAG", "检索增强", "知识库问答", "知识图谱", "提示词", "Prompt",
    "LangChain", "MCP", "工具调用", "Function Calling", "Dify", "Coze",
    "对话系统", "智能问答", "智能客服", "数字人", "NLP", "自然语言处理",
    "机器学习", "深度学习", "算法工程师", "人工智能", "模型开发", "AI平台",
    "AI应用", "AI技术", "AI算法", "AI大模型", "大模型算法", "AI助手",
    "智能系统", "智能软件", "AI训练", "智能开发", "AI研发", "算法开发",
    "软件工程师", "研发工程师", "应用开发工程师", "AI产品",
    "vibe coding", "Vibe Coding", "AI编程", "AI辅助开发", "智能编程",
    "代码生成", "编程助手", "Copilot", "编程智能体", "AI写代码",
]

# ---- 运营 / 市场营销方向 ---------------------------------------------------
# 入口关键词：从泛运营到具体职能，覆盖市场、品牌、内容、用户、商务、渠道等职能线
MARKETING_KEYWORDS = [
    "市场营销", "市场专员", "市场经理", "市场主管", "市场助理", "市场推广",
    "品牌运营", "品牌策划", "品牌专员", "品牌经理", "品牌推广",
    "新媒体运营", "内容运营", "短视频运营", "自媒体运营", "文案策划", "内容策划",
    "用户运营", "社群运营", "活动运营", "活动策划", "产品运营", "电商运营",
    "运营专员", "运营助理", "运营主管", "运营经理", "运营总监", "互联网运营",
    "营销", "数字营销", "网络营销", "营销策划", "整合营销", "品牌营销",
    "推广专员", "推广运营", "广告投放", "信息流优化", "渠道运营", "渠道专员",
    "商务专员", "商务拓展", "商务经理", "客户成功", "大客户",
    "增长", "用户增长", "数据分析", "市场调研", "品牌管理", "公关", "媒介",
]

# 运营方向剔除的岗位名特征：保险、推销、强销售导向的岗直接不要
MARKETING_EXCLUDE_TITLE_TERMS = [
    "保险", "寿险", "财产险", "理赔", "核保",
    "推销", "电销", "电话销售", "直销", "地推", "扫楼",
    "导购", "促销", "营业员", "店员", "收银", "柜员",
    "理财", "贷款", "信贷", "催收", "信用卡", "证券经纪", "投顾",
    "房产", "中介", "租赁", "置业", "月嫂", "家政",
]

# 营销上下文词：命中说明这条 JD 真的是运营/市场职能线
MARKETING_CTX_TERMS = [
    "市场营销", "品牌", "推广", "营销", "运营", "策划", "文案", "新媒体",
    "小红书", "抖音", "快手", "公众号", "视频号", "微博", "b站", "bilibili",
    "用户增长", "拉新", "留存", "促活", "转化", "投放", "广告", "流量",
    "社群", "内容", "直播", "短视频", "活动", "展会", "渠道", "商务",
    "市场调研", "数据分析", "增长", "seo", "sem", "信息流",
]

# ---- 相关度判定 ----------------------------------------------------------
# Agent 岗的核心特征词：命中即说明 JD 真的在讲智能体/工具编排这套东西
AGENT_CORE_TERMS = [
    "agent", "智能体", "coze", "扣子", "dify", "langgraph", "autogen", "semantic kernel",
    "llamaindex", "langchain", "function call", "functioncall", "tool use", "tool call",
    "工具调用", "任务规划", "任务编排", "任务拆解", "工作流编排", "mcp",
    "多轮对话", "记忆机制", "上下文管理", "智能助手", "ai助手", "自主决策",
    "rag", "检索增强", "向量检索", "知识库检索",
]
# 大模型上下文：说明岗位在 LLM 这条技术线上
LLM_CTX_TERMS = [
    "大模型", "大语言模型", "llm", "gpt", "生成式", "aigc", "prompt", "提示词",
    "微调", "fine-tune", "sft", "lora", "rlhf", "向量数据库", "embedding",
    "多模态", "vllm", "transformer", "deepseek", "qwen", "通义",
]
# 更外围的 AI 上下文
AI_CTX_TERMS = [
    "人工智能", "机器学习", "深度学习", "nlp", "自然语言", "计算机视觉", "知识图谱",
    "推荐算法", "pytorch", "tensorflow",
]
# 工程属性：没有这些信号的岗位不是研发岗（前台、销售、设计、标注等）
DEV_TERMS = [
    "python", "java", "c++", "golang", "go语言", "javascript", "typescript",
    "编程", "代码", "后端", "前端", "restful", "api", "sdk", "框架", "架构",
    "数据结构", "算法", "微调", "部署", "docker", "kubernetes", "linux", "sql",
    "git", "开发经验", "软件开发", "系统开发", "工程化", "接口", "调试", "源码",
]
# 明显不是 Agent 研发岗的职位名特征，直接剔除
EXCLUDE_TITLE_TERMS = [
    "前台", "预订", "客房", "餐饮", "酒店", "厨", "保安", "司机",
    "导演", "编导", "剪辑", "摄影", "原画", "美术", "插画", "平面", "视觉",
    "短剧", "漫剧", "抽卡", "设计师", "新媒体", "文案", "主播", "模特", "直播",
    "课程顾问", "招生", "销售", "客户经理", "运营专员", "人事", "行政", "财务",
    "标注", "测评师", "评判", "训练师", "采集", "众包", "兼职",
]

# 技术关键词抽取表：展示名 -> 匹配用的小写别名
TECH_MAP: dict[str, list[str]] = {
    "Python": ["python"],
    "Java": ["java"],
    "Go": ["golang", " go ", "go语言"],
    "C++": ["c++"],
    "JavaScript/TypeScript": ["javascript", "typescript", "node.js", "nodejs", " js ", "vue", "react"],
    "SQL": ["sql", "mysql", "postgre", "oracle"],
    "大模型/LLM": ["大模型", "大语言模型", "llm", "gpt", "通义", "deepseek", "qwen"],
    "Agent": ["agent", "智能体"],
    "多智能体": ["多智能体", "multi-agent", "multi agent"],
    "RAG": ["rag", "检索增强", "知识库检索"],
    "向量数据库": ["向量数据库", "milvus", "faiss", "chroma", "pinecone", "weaviate", "向量库"],
    "Prompt": ["prompt", "提示词"],
    "Memory/上下文": ["记忆机制", "上下文管理", "多轮对话", "长期记忆", "短期记忆", "上下文构建"],
    "Function Calling/工具调用": ["function call", "functioncall", "工具调用", "tool use", "tool call"],
    "任务规划/编排": ["任务规划", "任务编排", "工作流编排", "agent编排", "任务拆解", "流程编排"],
    "LangChain": ["langchain"],
    "LlamaIndex": ["llamaindex", "llama index"],
    "AutoGen": ["autogen"],
    "Semantic Kernel": ["semantic kernel"],
    "MCP": ["mcp", "model context protocol"],
    "Dify/Coze 等平台": ["dify", "coze", "扣子", "n8n"],
    "模型训练/微调": ["微调", "fine-tune", "finetune", "sft", "lora", "预训练", "强化学习", "rlhf"],
    "推理部署": ["推理部署", "模型部署", "vllm", "tensorrt", "onnx", "推理优化", "推理加速", "量化"],
    "多模态": ["多模态", "图文", "语音识别", "asr", "tts", "ocr", "视觉"],
    "API/HTTP": ["restful", "http", "api接口", "接口设计", "api设计"],
    "FastAPI/Flask/Django": ["fastapi", "flask", "django"],
    "Spring": ["spring"],
    "数据库": ["数据库", "mysql", "redis", "mongodb", "postgre"],
    "消息中间件": ["kafka", "rabbitmq", "rocketmq", " mq ", "消息队列"],
    "容器/云原生": ["docker", "kubernetes", "k8s", "容器", "微服务", "云原生"],
    "Linux": ["linux", "shell", "unix"],
    "Git": ["git ", "github", "gitlab", "版本管理"],
    "算法/数据结构": ["数据结构", "算法基础", "算法与数据结构", "扎实的算法"],
    "PyTorch/TensorFlow": ["pytorch", "tensorflow", "transformers", "huggingface", "hugging face"],
    "爬虫/数据处理": ["爬虫", "数据清洗", "数据标注", "数据处理", "etl"],
    "异步/并发": ["异步编程", "并发", "协程", "asyncio", "分布式任务"],
}

# 技术关键词 -> Tutor Agent 项目里可以直接拿出来讲的证据
PROJECT_EVIDENCE: dict[str, str] = {
    "Agent": "`app/services/agent/` 里的 ReAct 多轮工具循环：模型可连续多轮请求工具，`tool_trace.calls[]` 记录工具名、参数、结果摘要和 round。",
    "多智能体": "目前是单 Agent 多工具，可以讲清楚为什么没上多智能体（任务边界单一、编排收益不抵调试成本），这比硬凑更有说服力。",
    "任务规划/编排": "ReAct 循环里的「思考—选工具—看结果—再决策」控制流，以及回复解析成 answer / next_task / exercise / checkpoints 四段式的输出编排。",
    "Function Calling/工具调用": "工具注册与调用链路，`search_learning_notes` 等工具的参数校验、结果摘要和失败回退。",
    "Memory/上下文": "多会话记忆 + 会话摘要 + SQLite 持久化；会话绑定 persona_id，切换历史会话能恢复人设。",
    "RAG": "`scripts/build_knowledge_index.py` 扫描 `docs/**/*.md` 建 Chroma `learning_notes` 索引，`search_learning_notes` 检索后强制回答标注来源。",
    "向量数据库": "本地 Chroma 集合的建库、增量重建和检索评测（`scripts/run_retrieval_eval.py`）。",
    "Prompt": "prompt 模块 + 可切换导师人设（`GET /personas`），以及结构化回复的解析与容错。",
    "大模型/LLM": "OpenAI-compatible 客户端接入，chat 与 embedding 走两套独立配置（`OPENAI_BASE_URL` / `EMBEDDING_BASE_URL`），密钥走环境变量不入库。",
    "模型训练/微调": "项目没做训练，别硬写；可以讲检索/生成侧的离线评测脚本（`run_retrieval_eval.py`、`run_generation_eval.py`）来对齐「效果度量」这件事。",
    "推理部署": "项目走的是 API 接入而非自建推理，面试时讲清楚取舍即可，不要伪装部署经验。",
    "API/HTTP": "FastAPI 路由分层：`/chat`、`/sessions`、`/personas`、`/interview-jds`，请求/响应用 schemas 约束。",
    "FastAPI/Flask/Django": "后端就是 FastAPI，路由 / schemas / repositories / services 分层清晰。",
    "数据库": "SQLite 表设计与 `repositories/` 读写分层，持久化对话、会话、摘要和面试 JD。",
    "Python": "整个后端都是 Python，含类型标注、pytest 自动化测试和本地脚本工具链。",
    "异步/并发": "FastAPI 异步接口链路，以及工具调用的超时与异常处理。",
    "JavaScript/TypeScript": "`frontend/` 的 React + Vite 工作台，含会话列表、人设下拉和工具调用轨迹展示。",
    "Git": "仓库有规范的 commit 记录（feat / fix / refactor / docs / test 前缀）和文档目录 `docs/`。",
    "爬虫/数据处理": "本次 NCSS 职位抓取脚本本身就是样例：公开接口分页、详情页解析、正文哈希去重、结构化落盘。",
}

BJ_TZ = timezone(timedelta(hours=8))


@dataclass
class Job:
    job_id: str
    title: str = ""
    company: str = ""
    headline: str = ""
    salary: str = ""
    degree: str = ""
    head_count: str = ""
    updated_at: str = ""
    major: str = ""
    source: str = ""
    locations: str = ""
    jd_text: str = ""
    benefits: str = ""
    industry: str = ""
    sectors: str = ""
    property_: str = ""
    scale: str = ""
    website: str = ""
    address: str = ""
    recruit_type: str = ""
    search_keywords: set[str] = field(default_factory=set)
    url: str = ""
    relevance: str = ""
    score: int = 0
    tech: list[str] = field(default_factory=list)
    jd_hash: str = ""
    duplicates: list[tuple[str, str]] = field(default_factory=list)  # (company, url)


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def search_jobs(sess: requests.Session, keyword: str, offset: int, limit: int = 20) -> tuple[list[dict], int]:
    params = {
        "jobType": "", "areaCode": "", "jobName": keyword, "monthPay": "",
        "industrySectors": "", "recruitType": "", "property": "", "categoryCode": "",
        "memberLevel": "", "offset": str(offset), "limit": str(limit),
        "keyUnits": "", "degreeCode": "", "sourcesName": "0", "sourcesType": "",
    }
    resp = sess.get(LIST_API, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("flag"):
        return [], 0
    data = payload.get("data") or {}
    return data.get("list") or [], (data.get("pagenation") or {}).get("count", 0)


def fetch_detail_html(sess: requests.Session, job_id: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{job_id}.html"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    resp = sess.get(DETAIL_URL.format(job_id=job_id), timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    cached.write_text(resp.text, encoding="utf-8")
    time.sleep(0.4)
    return resp.text


def _txt(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def _txt_tight(node) -> str:
    """标题行/薪资行按原样拼接，不要在行内标签之间塞空格。"""
    return re.sub(r"\s+", " ", node.get_text("", strip=False)).strip() if node else ""


def parse_detail(html: str, job: Job) -> Job:
    soup = BeautifulSoup(html, "html.parser")

    title_node = soup.select_one("#jobName")
    job.title = _txt(title_node)

    work_ul = title_node.find_parent("ul") if title_node else None
    if work_ul:
        parts = [_txt_tight(li) for li in work_ul.find_all("li", recursive=False)]
        job.headline = "".join(p for p in parts if p)
        for p in parts:
            if p.startswith("[") and p.endswith("]"):
                job.recruit_type = p.strip("[]").strip()

    salary_items = [_txt_tight(li) for li in soup.select("ul.salary > li")]
    salary_items = [x for x in salary_items if x and x != "|"]
    for item in salary_items:
        if item.startswith("招聘"):
            job.head_count = item
        elif "更新" in item:
            job.updated_at = item.replace("更新", "").strip()
        elif item.endswith("及以上") or item in {"不限", "学历不限"}:
            job.degree = item
        elif not job.salary:
            job.salary = item

    job.major = _txt(soup.select_one(".major-bl .major"))
    job.source = _txt(soup.select_one(".major-bl .source-sp"))
    job.locations = "、".join(_txt(t) for t in soup.select("ul.address .site-tag") if _txt(t))

    pre = soup.select_one("pre.mainContent")
    if pre:
        job.jd_text = pre.get_text().replace("\r\n", "\n").strip()

    job.company = _txt(soup.select_one("#realCorpName")) or job.company
    job.industry = _txt(soup.select_one("#mainindustries"))
    job.sectors = _txt(soup.select_one("#industrySectors"))
    job.address = _txt(soup.select_one("#companyNameMap"))

    for li in soup.select(".con-right .company ul.details > li"):
        label = _txt(li.select_one(".ico"))
        value_node = li.select_one(".show")
        value = _txt(value_node)
        if not label or not value:
            continue
        if "公司性质" in label:
            job.property_ = value
        elif "公司规模" in label:
            job.scale = value
        elif "公司网址" in label:
            job.website = value

    return job


def score_relevance(job: Job, direction: str = "agent", loose: bool = False) -> tuple[str, int]:
    """判定这条 JD 到底是不是目标方向的岗。

    agent 方向：先卡两道硬门槛（职位名不能是明显的非研发岗、正文必须有工程信号），
    再按 Agent 核心词 / 大模型上下文 / 泛 AI 上下文三层给档。

    loose=True 时跳过"正文必须有编程词"这道门槛：只要命中大模型/AI 上下文
    词就保留为「相邻岗位」，用于扩大候选池（会混入 AI 产品/运营等非开发岗）。

    marketing 方向：不做编程词门槛（运营岗本来就不写代码），只做两件事：
    标题含保险/推销类特征词直接剔除，其余按营销上下文词命中数打分。
    """
    title = job.title.lower()
    if direction == "marketing":
        if any(term in title for term in MARKETING_EXCLUDE_TITLE_TERMS):
            return "无关", 0
        blob = f"{job.title} {job.jd_text}".lower()
        hits = [t for t in MARKETING_CTX_TERMS if t in blob]
        score = len(hits)
        if score >= 3:
            return "直接相关", score
        if score >= 1:
            return "较相关", score
        return "无关", score

    if any(term in title for term in EXCLUDE_TITLE_TERMS):
        return "无关", 0

    blob = f"{job.title} {job.jd_text}".lower()
    if not loose and not any(term in blob for term in DEV_TERMS):
        return "无关", 0

    core = [t for t in AGENT_CORE_TERMS if t in blob]
    llm = [t for t in LLM_CTX_TERMS if t in blob]
    ai = [t for t in AI_CTX_TERMS if t in blob]
    score = len(core) * 5 + len(llm) * 2 + len(ai)

    title_is_agent = any(t in title for t in ("agent", "智能体", "智能助手"))
    if core and (llm or title_is_agent):
        return "直接相关", score
    if len(llm) >= 2:
        return "较相关", score
    if llm or ai:
        return "相邻岗位", score
    return "无关", score


def extract_tech(job: Job) -> list[str]:
    blob = f" {job.title} {job.jd_text} ".lower()
    hits = []
    for name, aliases in TECH_MAP.items():
        if any(alias in blob for alias in aliases):
            hits.append(name)
    return hits


def normalize_jd(text: str) -> str:
    """去掉排版差异后的正文，用于判定「同一份 JD 模板」。"""
    t = re.sub(r"[\s　]+", "", text)
    t = re.sub(r"[，。；、：（）()【】\[\]<>《》,.;:!?\-—/\\|·\"'“”‘’]", "", t)
    return t.lower()


def safe_filename(text: str, limit: int = 48) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]', "", text).strip().replace(" ", "")
    cleaned = cleaned.strip(".")
    return cleaned[:limit] or "job"


def collect(sess: requests.Session, target: int, page_limit: int, direction: str = "agent", loose: bool = False) -> tuple[list[Job], dict]:
    keywords = MARKETING_KEYWORDS if direction == "marketing" else KEYWORDS
    seen_ids: dict[str, Job] = {}
    stats = {"list_records": 0, "keywords_used": 0, "direction": direction}

    for keyword in keywords:
        stats["keywords_used"] += 1
        offset = 1
        while offset <= page_limit:
            try:
                rows, total = search_jobs(sess, keyword, offset)
            except Exception as exc:  # noqa: BLE001
                print(f"  [warn] 搜索失败 {keyword} offset={offset}: {exc}")
                break
            if not rows:
                break
            stats["list_records"] += len(rows)
            for row in rows:
                jid = row.get("jobId")
                if not jid:
                    continue
                if jid in seen_ids:
                    seen_ids[jid].search_keywords.add(keyword)
                    continue
                job = Job(
                    job_id=jid,
                    title=row.get("jobName") or "",
                    company=row.get("recName") or "",
                    benefits=row.get("recTags") or "",
                    url=DETAIL_URL.format(job_id=jid),
                )
                job.search_keywords.add(keyword)
                seen_ids[jid] = job
            if offset * 20 >= total:
                break
            offset += 1
            time.sleep(0.25)
        print(f"  关键词「{keyword}」累计候选 {len(seen_ids)} 条")
        time.sleep(0.2)

    print(f"\n候选职位（按 jobId 去重）：{len(seen_ids)} 条，开始抓详情页 ...")
    jobs: list[Job] = []
    for i, job in enumerate(seen_ids.values(), 1):
        try:
            html = fetch_detail_html(sess, job.job_id)
            parse_detail(html, job)
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] 详情失败 {job.job_id}: {exc}")
            continue
        if not job.jd_text:
            continue
        job.relevance, job.score = score_relevance(job, direction, loose)
        if direction != "marketing":
            job.tech = extract_tech(job)
        job.jd_hash = hashlib.sha1(normalize_jd(job.jd_text).encode("utf-8")).hexdigest()[:12]
        jobs.append(job)
        if i % 25 == 0:
            print(f"  已解析 {i}/{len(seen_ids)}")

    print(f"详情解析成功：{len(jobs)} 条")
    return jobs, stats


def dedupe(jobs: list[Job]) -> tuple[list[Job], int]:
    """同一份 JD 正文只保留一条代表，其余挂到 duplicates 上。"""
    order = {"直接相关": 0, "较相关": 1, "相邻岗位": 2, "无关": 3}
    jobs = sorted(jobs, key=lambda j: (order.get(j.relevance, 9), -j.score, -len(j.jd_text)))
    groups: dict[str, Job] = {}
    dup_count = 0
    for job in jobs:
        rep = groups.get(job.jd_hash)
        if rep is None:
            groups[job.jd_hash] = job
        else:
            rep.duplicates.append((job.company, job.url))
            rep.search_keywords |= job.search_keywords
            dup_count += 1
    return list(groups.values()), dup_count


def project_notes(tech: list[str]) -> list[str]:
    notes = []
    for name in tech:
        evidence = PROJECT_EVIDENCE.get(name)
        if evidence:
            notes.append(f"- **{name}** → {evidence}")
    return notes


PLACEHOLDERS = {"--", "-", "—", "无", "暂无"}


def _clean(value: str) -> str:
    """页面上没填的字段会渲染成 `--` 之类的占位符，不能当成真值。"""
    return "" if value.strip() in PLACEHOLDERS else value


def render_job_md(seq: int, job: Job, direction: str = "agent") -> str:
    lines: list[str] = []
    lines.append(f"# {job.title}")
    lines.append("")
    lines.append(f"> 来源：[{job.url}]({job.url})")
    lines.append(f"> 采集时间：{datetime.now(BJ_TZ):%Y-%m-%d %H:%M}（北京时间）")
    lines.append("")

    lines.append("## 职位原文")
    lines.append("")
    lines.append("```text")
    if job.headline:
        lines.append(job.headline)
    head2 = "|".join(x for x in [job.salary, job.degree, job.head_count] if x)
    if job.updated_at:
        head2 = f"{head2}{job.updated_at} 更新" if head2 else f"{job.updated_at} 更新"
    if head2:
        lines.append(head2)
    line3 = f"{job.major}来源： {job.source}".strip()
    if line3:
        lines.append(line3)
    if job.locations:
        lines.append(job.locations)
    lines.append("职位详情")
    lines.append(job.jd_text)
    lines.append("```")
    lines.append("")

    lines.append("## 结构化字段")
    lines.append("")
    lines.append("| 字段 | 值 |")
    lines.append("|---|---|")
    rows = [
        ("职位名称", job.title),
        ("招聘类型", job.recruit_type),
        ("薪资", job.salary),
        ("学历要求", job.degree),
        ("招聘人数", job.head_count.replace("招聘", "").strip() if job.head_count else ""),
        ("专业要求", job.major),
        ("工作地区", job.locations),
        ("更新时间", job.updated_at),
        ("信息来源", job.source),
        ("命中搜索词", "、".join(sorted(job.search_keywords))),
        ("相关度", f"{job.relevance}（分值 {job.score}）"),
    ]
    for k, v in rows:
        if _clean(v):
            lines.append(f"| {k} | {_clean(v)} |")
    lines.append("")

    lines.append("## 公司信息")
    lines.append("")
    lines.append("| 字段 | 值 |")
    lines.append("|---|---|")
    for k, v in [
        ("招聘主体", job.company),
        ("所属行业", job.industry),
        ("涉及领域", job.sectors),
        ("公司性质", job.property_),
        ("公司规模", job.scale),
        ("公司网址", job.website),
        ("所在地址", job.address),
    ]:
        if _clean(v):
            lines.append(f"| {k} | {_clean(v)} |")
    lines.append("")

    if job.benefits:
        lines.append("## 福利标签")
        lines.append("")
        lines.append("、".join(x.strip() for x in re.split(r"[，,]", job.benefits) if x.strip()))
        lines.append("")

    if direction == "marketing":
        lines.append("## 岗位特征")
        lines.append("")
        blob = f"{job.title} {job.jd_text}".lower()
        hits = [t for t in MARKETING_CTX_TERMS if t in blob]
        lines.append("、".join(hits) if hits else "（未识别到明确营销职能关键词）")
        lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    lines.append("## 技术关键词")
    lines.append("")
    lines.append("、".join(job.tech) if job.tech else "（未识别到明确技术栈关键词）")
    lines.append("")

    notes = project_notes(job.tech)
    lines.append("## 与 Tutor Agent 项目的对应点")
    lines.append("")
    if notes:
        lines.extend(notes)
    else:
        lines.append("- 该 JD 未命中项目已有能力，若要投递需要补做对应模块。")
    lines.append("")

    if job.duplicates:
        lines.append("## 同模板的其他投放")
        lines.append("")
        lines.append(
            f"以下 {len(job.duplicates)} 条职位的 JD 正文与本条完全一致（同一份模板在不同主体/分公司重复投放），"
            "统计技能频次时应视为 1 条：")
        lines.append("")
        for company, url in job.duplicates:
            lines.append(f"- {company} — [{url}]({url})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_index_md(kept: list[Job], all_jobs: list[Job], dup_count: int, stats: dict, file_names: list[str], direction: str = "agent") -> str:
    direction_label = "运营 / 市场营销" if direction == "marketing" else "Agent 开发"
    keyword_label = "营销" if direction == "marketing" else "Agent"
    today = f"{datetime.now(BJ_TZ):%Y-%m-%d}"
    lines: list[str] = []
    lines.append(f"# 国家大学生就业服务平台：{direction_label}相关职位（按 JD 正文去重）")
    lines.append("")
    lines.append(f"- 采集日期：{today}")
    lines.append(f"- 搜索关键词：{stats['keywords_used']} 个，列表接口共返回 {stats['list_records']} 条记录")
    lines.append(f"- 详情页解析成功：{len(all_jobs)} 条")
    lines.append(f"- **按 JD 正文哈希去重后：{len(kept)} 份不同的 JD**（合并掉 {dup_count} 条同模板重复投放）")
    lines.append("- 每份 JD 一个 md 文件，存放在 `jobs/` 目录下，正文为详情页原文，未做改写")
    lines.append("")

    lines.append("## 去重口径")
    lines.append("")
    lines.append("同一份 JD 会被不同分公司/主体重复投放，正文一字不差。判定方法：")
    lines.append("")
    lines.append("1. 取详情页 `<pre class=\"mainContent\">` 的完整正文；")
    lines.append("2. 去掉所有空白和标点后取 SHA1 前 12 位作为指纹；")
    lines.append("3. 指纹相同的归为一组，只保留相关度最高的一条作为代表，其余在该文件的「同模板的其他投放」里列出。")
    lines.append("")

    multi = sorted([j for j in kept if j.duplicates], key=lambda j: -len(j.duplicates))
    if multi:
        lines.append("### 重复投放最多的模板")
        lines.append("")
        lines.append("| JD 代表职位 | 代表主体 | 同模板条数 |")
        lines.append("|---|---|---:|")
        for job in multi[:15]:
            lines.append(f"| {job.title} | {job.company} | {len(job.duplicates) + 1} |")
        lines.append("")

    by_rel: dict[str, int] = {}
    for job in kept:
        by_rel[job.relevance] = by_rel.get(job.relevance, 0) + 1
    lines.append("## 相关度分布（去重后）")
    lines.append("")
    for name in ["直接相关", "较相关", "相邻岗位"]:
        if by_rel.get(name):
            lines.append(f"- {name}：{by_rel[name]} 份")
    lines.append("")

    tech_count: dict[str, int] = {}
    for job in kept:
        for t in job.tech:
            tech_count[t] = tech_count.get(t, 0) + 1
    if tech_count:
        lines.append(f"## 高频技术要求（按 {len(kept)} 份不同 JD 统计，每份只计 1 次）")
        lines.append("")
        lines.append("| 技术项 | 出现 JD 数 | 占比 |")
        lines.append("|---|---:|---:|")
        for name, cnt in sorted(tech_count.items(), key=lambda kv: -kv[1])[:30]:
            lines.append(f"| {name} | {cnt} | {cnt / len(kept) * 100:.0f}% |")
        lines.append("")

    degree_count: dict[str, int] = {}
    for job in kept:
        if job.degree:
            degree_count[job.degree] = degree_count.get(job.degree, 0) + 1
    lines.append("## 学历要求（去重后）")
    lines.append("")
    for name, cnt in sorted(degree_count.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {name}：{cnt} 份")
    lines.append("")

    lines.append("## JD 清单")
    lines.append("")
    lines.append("| # | 相关度 | 职位 | 招聘主体 | 薪资 / 学历 | 地区 | 同模板条数 | 文件 |")
    lines.append("|---:|---|---|---|---|---|---:|---|")
    for i, (job, fname) in enumerate(zip(kept, file_names), 1):
        dup = len(job.duplicates) + 1
        enc = fname.replace(" ", "%20")
        lines.append(
            f"| {i} | {job.relevance} | {job.title} | {job.company} | "
            f"{job.salary} \\| {job.degree} | {job.locations} | {dup} | [打开](jobs/{enc}) |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--direction", type=str, default="agent", choices=["agent", "marketing"],
                        help="方向：agent（Agent/大模型开发）或 marketing（运营/市场营销）")
    parser.add_argument("--loose", action="store_true",
                        help="agent 方向跳过编程词硬门槛，保留「相邻岗位」（会混入 AI 产品/运营等非开发岗）")
    parser.add_argument("--target", type=int, default=50, help="目标不同 JD 份数")
    parser.add_argument("--page-limit", type=int, default=5, help="每个关键词最多翻多少页")
    parser.add_argument("--out", type=str, default="", help="输出目录名")
    args = parser.parse_args()

    direction = args.direction
    direction_tag = "marketing" if direction == "marketing" else "agent"

    sess = session()
    print(f"开始按关键词搜索（方向：{direction}，loose={args.loose}）...")
    jobs, stats = collect(sess, args.target, args.page_limit, direction, args.loose)

    relevant = [j for j in jobs if j.relevance != "无关"]
    print(f"相关职位：{len(relevant)} 条（过滤掉 {len(jobs) - len(relevant)} 条无关）")

    kept, dup_count = dedupe(relevant)
    print(f"按 JD 正文去重后：{len(kept)} 份不同 JD（合并 {dup_count} 条重复）")

    order = {"直接相关": 0, "较相关": 1, "相邻岗位": 2}
    kept.sort(key=lambda j: (order.get(j.relevance, 9), -(len(j.duplicates) + 1), -j.score))
    if args.target > 0:
        kept = kept[: args.target]
        print(f"取前 {len(kept)} 份写入文件")

    today = f"{datetime.now(BJ_TZ):%Y-%m-%d}"
    out_dir = ROOT / "exports" / (args.out or f"ncss_{direction_tag}_jobs_{today}")
    jobs_dir = out_dir / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    file_names: list[str] = []
    for i, job in enumerate(kept, 1):
        fname = f"{i:02d}-{safe_filename(job.title, 30)}-{safe_filename(job.company, 26)}.md"
        (jobs_dir / fname).write_text(render_job_md(i, job, direction), encoding="utf-8")
        file_names.append(fname)

    (out_dir / "README.md").write_text(
        render_index_md(kept, jobs, dup_count, stats, file_names, direction), encoding="utf-8"
    )

    csv_path = out_dir / f"ncss_{direction_tag}_jobs_{today}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "序号", "文件", "相关度", "相关度分值", "职位", "招聘主体", "薪资", "学历",
            "招聘人数", "专业", "地区", "更新时间", "所属行业", "公司性质", "公司规模",
            "技术关键词", "同模板条数", "JD指纹", "详情页",
        ])
        for i, (job, fname) in enumerate(zip(kept, file_names), 1):
            writer.writerow([
                i, fname, job.relevance, job.score, job.title, job.company, job.salary,
                job.degree, job.head_count, job.major, job.locations, job.updated_at,
                job.industry, job.property_, job.scale, "、".join(job.tech),
                len(job.duplicates) + 1, job.jd_hash, job.url,
            ])

    raw_path = out_dir / "raw_jobs.json"
    raw_path.write_text(
        json.dumps(
            [
                {
                    **{k: v for k, v in job.__dict__.items() if k != "search_keywords"},
                    "search_keywords": sorted(job.search_keywords),
                }
                for job in jobs
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n完成：{out_dir}")
    print(f"  - README.md（索引 + 去重报告 + 聚合统计）")
    print(f"  - jobs/ 共 {len(file_names)} 个 md")
    print(f"  - {csv_path.name}")
    print(f"  - raw_jobs.json（{len(jobs)} 条未去重原始记录）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
