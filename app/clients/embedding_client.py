"""OpenAI-compatible embedding client."""

from __future__ import annotations

from openai import OpenAI

from app.config import EmbeddingConfig, load_embedding_config


class EmbeddingError(Exception):
    """Embedding 调用失败时的统一异常。"""


class EmbeddingClient:
    """封装 embedding API，避免业务层直接依赖 OpenAI SDK 细节。"""

    def __init__(
        self,
        config: EmbeddingConfig | None = None,
        client: OpenAI | None = None,
    ) -> None:
        """初始化 embedding 配置和 OpenAI-compatible 客户端。"""

        self.config = config or load_embedding_config()
        self.client = client or OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量生成文本向量；空列表直接返回空列表。"""

        if not texts:
            return []

        try:
            response = self.client.embeddings.create(
                model=self.config.model,
                input=texts,
            )
        except Exception as exc:  # pragma: no cover - SDK 边界兜底。
            raise EmbeddingError(f"embedding 调用失败: {exc}") from exc

        return [list(item.embedding) for item in response.data]

