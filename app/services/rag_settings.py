"""RAG 相关的统一配置。"""

# 分块器默认块大小，对齐 v0.3 设计文档和 DeepTutor 的基础参数。
CHUNK_SIZE = 512

# 超长文本用滑动窗口兜底切分时，相邻块保留 50 个字符重叠。
CHUNK_OVERLAP = 50

# 检索工具默认返回的候选块数量。
RAG_TOP_K = 3

# 相似度低于该阈值的结果会被丢弃；v0.4 评测集基线校准为 0.45。
SIMILARITY_THRESHOLD = 0.45

# Chroma 集合名，后续工具和脚本都通过这个名字访问学习笔记索引。
KNOWLEDGE_COLLECTION_NAME = "learning_notes"

# Chroma 本地持久化目录，默认位于项目根目录。
CHROMA_PERSIST_DIR = "chroma_db"

# 第一版只索引本地 docs 目录下的 Markdown 笔记。
KNOWLEDGE_SOURCE_DIR = "docs"

# Formal rebuild combines the local notes and the imported self-llm snapshot.
KNOWLEDGE_SOURCE_DIRS = ("docs", "corpus/self-llm/docs")

# 离线索引脚本调用 embedding 接口时的默认批大小。
EMBEDDING_BATCH_SIZE = 32

# v0.4 Hybrid 检索候选池大小：向量和 BM25 各取 top_k * 2 后融合。
HYBRID_CANDIDATE_MULTIPLIER = 2

# Hybrid 融合权重：向量与 BM25 各半，已在 retrieval eval 上校准。
HYBRID_VECTOR_WEIGHT = 0.5
HYBRID_BM25_WEIGHT = 0.5

# 生产 Hybrid 检索开关。True 时 search_learning_notes 走向量 + BM25 融合；
# 高并发应急可一键切回纯向量（BM25 融合是可牺牲的昂贵步骤）。
ENABLE_HYBRID_RETRIEVAL = True

# v0.4 FR4.6 种子检索实验默认关闭，避免未经生成层评测就改变 /chat 主链路。
ENABLE_RAG_SEED_CONTEXT = False

# 进入 ReAct 循环前预检索的种子块数量和注入上下文字符上限。
RAG_SEED_TOP_K = 2
RAG_SEED_MAX_CHARS = 900

# ????????????????? learning_notes ?????
ENABLE_SUBJECT_SHARDING = False
COLLECTION_PREFIX = "learning_notes_"
EXTERNAL_CORPUS_SUBJECT = "llm"

# ?????????? collection slug ???????????????????? slug?
SUBJECT_SLUGS: dict[str, str] = {
    "\u7269\u7406": "physics",
    "\u6570\u5b66": "math",
    "\u5316\u5b66": "chemistry",
    "\u751f\u7269": "biology",
    "\u8ba1\u7b97\u673a": "computer-science",
    "\u8ba1\u7b97\u673a\u79d1\u5b66": "computer-science",
    "\u82f1\u8bed": "english",
    "\u8bed\u6587": "chinese",
    "\u5386\u53f2": "history",
    "\u5730\u7406": "geography",
    "\u653f\u6cbb": "politics",
    "\u901a\u7528": "general",
    "\u5176\u4ed6": "general",
}


def validate_subject_slug(slug: str) -> str:
    """Validate a Chroma-compatible subject slug and return it unchanged."""

    import re

    if not isinstance(slug, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{1,61}[A-Za-z0-9]", slug):
        raise ValueError(
            "subject slug must be 3-63 characters, start/end with a letter or digit, "
            "and contain only letters, digits, '_' or '-'"
        )
    return slug


def subject_slug(subject: str) -> str:
    """Resolve a display subject or slug to the canonical collection suffix."""

    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("subject must be a non-empty string")
    value = subject.strip()
    return validate_subject_slug(SUBJECT_SLUGS.get(value, value))


def collection_name_for_subject(slug: str) -> str:
    """Return the logical Chroma collection name for a validated subject."""

    return f"{COLLECTION_PREFIX}{validate_subject_slug(slug)}"


def subject_from_source(source_path: str) -> str:
    """Infer a canonical subject from a corpus-relative POSIX source path."""

    normalized = str(source_path).replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part]
    marker = ["corpus", "self-llm", "docs"]
    if len(parts) >= 4 and parts[:3] == marker:
        return EXTERNAL_CORPUS_SUBJECT
    if len(parts) >= 2 and parts[0] == "docs":
        if len(parts) == 2 and parts[1].lower().endswith(".md"):
            return "general"
        return subject_slug(parts[1])
    return "general"
