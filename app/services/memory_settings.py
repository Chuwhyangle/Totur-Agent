"""记忆相关的统一配置。"""

# 每次聊天仍然保留最近 6 条原始历史，避免 prompt 无限变长。
RECENT_HISTORY_LIMIT = 6

# 可被压缩的旧消息达到 8 条后，才触发一次滚动摘要。
SUMMARY_TRIGGER_COUNT = 8

# ReAct 工具循环最多执行 4 轮，覆盖四路由下最长合法链路
# （附件强制 + JD + 笔记 + 打分 = 4 轮）。
MAX_TOOL_ROUNDS = 4

# 单条工具 observation 回填给模型前的最大字符数，防止长工具结果撑爆上下文。
TOOL_OBSERVATION_MAX_CHARS = 4000

# 单次 ReAct 运行中最多允许 2 次工具失败，超过后转入无工具收尾。
MAX_TOOL_FAILURES = 2
