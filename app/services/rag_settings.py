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

# v0.4 Hybrid 检索初始融合权重；评测证明收益后再作为线上默认。
HYBRID_VECTOR_WEIGHT = 0.5
HYBRID_BM25_WEIGHT = 0.5

# v0.4 FR4.6 种子检索实验默认关闭，避免未经生成层评测就改变 /chat 主链路。
ENABLE_RAG_SEED_CONTEXT = False

# 进入 ReAct 循环前预检索的种子块数量和注入上下文字符上限。
RAG_SEED_TOP_K = 2
RAG_SEED_MAX_CHARS = 900
