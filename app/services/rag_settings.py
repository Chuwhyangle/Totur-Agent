"""RAG 相关的统一配置。"""

# 分块器默认块大小，对齐 v0.3 设计文档和 DeepTutor 的基础参数。
CHUNK_SIZE = 512

# 超长文本用滑动窗口兜底切分时，相邻块保留 50 个字符重叠。
CHUNK_OVERLAP = 50

# 离线索引脚本调用 embedding 接口时的默认批大小。
EMBEDDING_BATCH_SIZE = 32

