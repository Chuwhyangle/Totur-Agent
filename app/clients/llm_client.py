"""大模型客户端封装。

这个文件负责：
1. 根据配置创建 OpenAI-compatible client。
2. 把底层 SDK 的创建细节集中到一个地方。

新手理解：
以后 service 层不应该自己到处 new OpenAI(...)。
service 只应该拿到“已经准备好的客户端”来用。
"""

from openai import OpenAI

from app.config import LLMConfig


def create_llm_client(config: LLMConfig) -> OpenAI:
    """创建 OpenAI 兼容的大模型客户端。

    TODO(阶段 4 - 客户端任务 1): OK！
    用 config.api_key 和 config.base_url 创建 OpenAI 实例。

    TODO(阶段 4 - 客户端任务 2):
    先不要在这里写复杂逻辑，保持“创建客户端”这一件事单纯一点。

    TODO(阶段 4 - 客户端任务 3):
    如果后面要支持多个模型供应商，可以在这里继续扩展。
    """

    return OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
    )
