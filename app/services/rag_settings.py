"""RAG 相关的统一配置。"""

# 分块器默认块大小，对齐 v0.3 设计文档和 DeepTutor 的基础参数。
CHUNK_SIZE = 512

# 超长文本用滑动窗口兜底切分时，相邻块保留 50 个字符重叠。
CHUNK_OVERLAP = 50

# 检索工具默认返回的候选块数量。
RAG_TOP_K = 3

# 相似度低于该阈值的结果会被丢弃，宁可说没找到也不硬凑。
SIMILARITY_THRESHOLD = 0.35

# Chroma 集合名，后续工具和脚本都通过这个名字访问学习笔记索引。
KNOWLEDGE_COLLECTION_NAME = "learning_notes"

# Chroma 本地持久化目录，默认位于项目根目录。
CHROMA_PERSIST_DIR = "chroma_db"

# 第一版只索引本地 docs 目录下的 Markdown 笔记。
KNOWLEDGE_SOURCE_DIR = "docs"

# 离线索引脚本调用 embedding 接口时的默认批大小。
EMBEDDING_BATCH_SIZE = 32
