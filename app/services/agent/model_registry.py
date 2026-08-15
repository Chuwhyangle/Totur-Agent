"""Model catalog and environment-backed availability rules."""

from dataclasses import dataclass, field
import os
from typing import Any, Literal

from dotenv import load_dotenv

from app.config import load_provider_configs


@dataclass(frozen=True)
class ModelSpec:
    """Capabilities and fixed request parameters for one public model option."""

    model_id: str
    display_name: str
    description: str
    provider: str
    api_model: str
    supports_tools: bool
    supports_thinking: bool
    wire_api: Literal["chat_completions", "responses", "anthropic"] = (
        "chat_completions"
    )
    top_level_params: dict[str, Any] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)
    concurrency_hint: int | None = None


MODEL_CATALOG: dict[str, ModelSpec] = {
    "ds-flash-fast": ModelSpec(
        model_id="ds-flash-fast",
        display_name="DeepSeek Flash · 快速",
        description="不开思考，延迟最低，适合日常问答",
        provider="deepseek",
        api_model="deepseek-v4-flash",
        supports_tools=True,
        supports_thinking=False,
        extra_body={"thinking": {"type": "disabled"}},
        concurrency_hint=2500,
    ),
    "ds-flash-think": ModelSpec(
        model_id="ds-flash-think",
        display_name="DeepSeek Flash · 思考",
        description="开启思考，速度与质量平衡",
        provider="deepseek",
        api_model="deepseek-v4-flash",
        supports_tools=True,
        supports_thinking=True,
        extra_body={"thinking": {"type": "enabled"}},
        concurrency_hint=2500,
    ),
    "ds-pro-deep": ModelSpec(
        model_id="ds-pro-deep",
        display_name="DeepSeek Pro · 深度思考",
        description="最强推理，适合复杂架构与算法问题",
        provider="deepseek",
        api_model="deepseek-v4-pro",
        supports_tools=True,
        supports_thinking=True,
        top_level_params={"reasoning_effort": "high"},
        extra_body={"thinking": {"type": "enabled"}},
        concurrency_hint=500,
    ),
}


class InvalidModelError(ValueError):
    """Raised when a request selects a model outside the available set."""

    def __init__(self, model_id: str, available_model_ids: list[str]) -> None:
        self.model_id = model_id
        self.available_model_ids = available_model_ids
        super().__init__(f"invalid model_id: {model_id}")


def _enabled_model_ids() -> set[str]:
    load_dotenv()
    return {
        model_id.strip()
        for model_id in os.getenv("ENABLED_MODELS", "").split(",")
        if model_id.strip()
    }


def available_models() -> dict[str, ModelSpec]:
    """Return catalog entries enabled in env and backed by a configured provider."""

    enabled = _enabled_model_ids()
    providers = load_provider_configs()
    result = {
        model_id: spec
        for model_id, spec in MODEL_CATALOG.items()
        if model_id in enabled and spec.provider in providers
    }
    if result:
        return result

    unknown_models = sorted(enabled.difference(MODEL_CATALOG))
    missing_providers = sorted(
        {
            spec.provider
            for model_id, spec in MODEL_CATALOG.items()
            if model_id in enabled and spec.provider not in providers
        }
    )
    raise RuntimeError(
        "没有可用模型。"
        f"ENABLED_MODELS={sorted(enabled) or ['（空）']}；"
        f"catalog 未定义={unknown_models or ['（无）']}；"
        f"provider 配置不完整={missing_providers or ['（无）']}"
    )


def available_model_ids() -> list[str]:
    """Return available public model identifiers in catalog order."""

    return list(available_models())


def default_model_id() -> str:
    """Return the configured default after validating its availability."""

    load_dotenv()
    configured = os.getenv("DEFAULT_MODEL_ID", "").strip()
    available = available_models()
    if not configured:
        raise RuntimeError("没有配置 DEFAULT_MODEL_ID")
    if configured not in available:
        raise RuntimeError(
            f"DEFAULT_MODEL_ID={configured} 不可用；"
            f"available_models={list(available)}"
        )
    return configured


def resolve_model(model_id: str | None = None) -> ModelSpec:
    """Resolve an explicit model or the configured default model."""

    available = available_models()
    resolved_id = model_id or default_model_id()
    try:
        return available[resolved_id]
    except KeyError as exc:
        raise InvalidModelError(resolved_id, list(available)) from exc


def validate_model_configuration() -> None:
    """Fail application startup when no usable default model exists."""

    default_model_id()
