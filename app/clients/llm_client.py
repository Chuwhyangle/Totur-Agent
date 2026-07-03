"""OpenAI-compatible model client factory."""

from openai import OpenAI

from app.config import LLMConfig


def create_llm_client(config: LLMConfig) -> OpenAI:
    """Create an OpenAI-compatible client from app configuration."""

    return OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
    )
