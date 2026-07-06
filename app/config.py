"""Application configuration."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass
class LLMConfig:
    """大模型客户端所需的基础配置。"""

    api_key: str
    base_url: str
    model: str


@dataclass
class EmbeddingConfig:
    """Embedding 客户端所需的基础配置。"""

    api_key: str
    base_url: str
    model: str


def load_llm_config() -> LLMConfig:
    """Load and validate model configuration from environment variables."""

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "")
    model = os.getenv("OPENAI_MODEL", "")

    if not base_url:
        raise RuntimeError("没有Base URL")
    if not api_key:
        raise RuntimeError("没有 api key")
    if not model:
        raise RuntimeError("没有选择model")

    return LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


def load_embedding_config() -> EmbeddingConfig:
    """Load and validate embedding configuration from environment variables."""

    load_dotenv()

    # Embedding 服务独立于聊天模型，避免配置缺失时误打到聊天模型地址。
    api_key = (
        os.getenv("EMBEDDING_KEY", "").strip()
        or os.getenv("EMBEDDING_API_KEY", "").strip()
    )
    base_url = os.getenv("EMBEDDING_BASE_URL", "").strip()
    model = os.getenv("EMBEDDING_MODEL", "").strip()

    if not base_url:
        raise RuntimeError("没有 embedding Base URL")
    if not api_key:
        raise RuntimeError("没有 embedding api key")
    if not model:
        raise RuntimeError("没有选择 embedding model")

    return EmbeddingConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
