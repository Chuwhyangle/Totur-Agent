"""记忆相关的统一配置。"""

# 每次聊天仍然保留最近 6 条原始历史，避免 prompt 无限变长。
RECENT_HISTORY_LIMIT = 6

# 可被压缩的旧消息达到 8 条后，才触发一次滚动摘要。
SUMMARY_TRIGGER_COUNT = 8
