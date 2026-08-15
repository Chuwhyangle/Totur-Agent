"""Thread-safe OpenAI-compatible client pool keyed by provider."""

from threading import Lock

from openai import OpenAI

from app.config import load_provider_configs


_client_lock = Lock()
_clients: dict[str, OpenAI] = {}


def get_llm_client(provider: str) -> OpenAI:
    """Create once and reuse the client for one configured provider."""

    client = _clients.get(provider)
    if client is not None:
        return client

    with _client_lock:
        client = _clients.get(provider)
        if client is not None:
            return client

        config = load_provider_configs().get(provider)
        if config is None:
            raise RuntimeError(f"模型 provider 未配置完整: {provider}")
        client = OpenAI(api_key=config.api_key, base_url=config.base_url)
        _clients[provider] = client
        return client


def close_llm_clients() -> None:
    """Close and clear every cached provider client."""

    with _client_lock:
        clients = list(_clients.values())
        _clients.clear()
    for client in clients:
        client.close()
