"""Application configuration."""

from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class StorageConfig:
    """存储路径配置：数据库和 Chroma 持久化目录的根路径。"""

    DATA_DIR: Path

    @property
    def database_path(self) -> Path:
        return self.DATA_DIR / "tutor_agent.db"

    @property
    def chroma_persist_dir(self) -> Path:
        return self.DATA_DIR / "chroma_db"

    @staticmethod
    def from_env() -> "StorageConfig":
        load_dotenv()
        data_dir = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[2])))
        return StorageConfig(DATA_DIR=data_dir)


@dataclass(frozen=True)
class ServerConfig:
    """服务器相关配置：CORS 白名单和 API 前缀。"""

    ALLOWED_ORIGINS: list[str] = field(default_factory=list)
    ROOT_PATH: str = ""

    @staticmethod
    def from_env() -> "ServerConfig":
        load_dotenv()
        raw_origins = os.getenv(
            "ALLOWED_ORIGINS",
            "http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5175,"
            "http://localhost:5173,http://localhost:5174,http://localhost:5175",
        )
        origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
        root_path = os.getenv("ROOT_PATH", "").strip()
        return ServerConfig(ALLOWED_ORIGINS=origins, ROOT_PATH=root_path)


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


@dataclass
class WebSearchConfig:
    """Server-side web search provider configuration."""

    provider: str
    api_key: str
    base_url: str
    timeout_seconds: float


@dataclass(frozen=True)
class RerankerConfig:
    """External reranker provider configuration."""

    provider: str
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float


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


def load_web_search_config() -> WebSearchConfig:
    """Load web search configuration only when search is first requested."""

    load_dotenv()

    provider = os.getenv("WEB_SEARCH_PROVIDER", "tavily").strip().lower() or "tavily"
    api_key = (
        os.getenv("WEB_SEARCH_API_KEY", "").strip()
        or os.getenv("TAVILY_API_KEY", "").strip()
    )
    base_url = (
        os.getenv("WEB_SEARCH_BASE_URL", "https://api.tavily.com").strip()
        or "https://api.tavily.com"
    ).rstrip("/")

    timeout_seconds = 7.0
    raw_timeout = os.getenv("WEB_SEARCH_TIMEOUT_SECONDS", "7").strip()
    try:
        configured_timeout = float(raw_timeout)
    except (TypeError, ValueError):
        configured_timeout = timeout_seconds
    if 5.0 <= configured_timeout <= 8.0:
        timeout_seconds = configured_timeout

    if not api_key:
        raise RuntimeError("web search api key is not configured")
    if provider != "tavily":
        raise RuntimeError("unsupported web search provider")

    return WebSearchConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )


def load_reranker_config() -> RerankerConfig:
    """Load reranker configuration only when reranking is requested."""

    load_dotenv()

    provider = os.getenv("RERANK_PROVIDER", "").strip().lower()
    api_key = os.getenv("RERANK_API_KEY", "").strip()
    base_url = os.getenv("RERANK_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("RERANK_MODEL", "").strip()

    raw_timeout = os.getenv("RERANK_TIMEOUT_SECONDS", "5").strip()
    try:
        timeout_seconds = float(raw_timeout)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("invalid reranker timeout") from exc

    if not api_key:
        raise RuntimeError("reranker api key is not configured")
    if not base_url:
        raise RuntimeError("reranker base url is not configured")
    if not model:
        raise RuntimeError("reranker model is not configured")
    if timeout_seconds <= 0:
        raise RuntimeError("invalid reranker timeout")

    return RerankerConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )
