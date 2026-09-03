"""Model adapter selection."""

from agno.models.openai import OpenAIResponses
from agno.models.openai.like import OpenAILike
from agno.models.vllm import VLLM

from agno_app.settings import settings


def build_model():  # noqa: ANN201 - provider adapters share a framework protocol
    common = {
        "id": settings.model_id,
    }
    if settings.model_api_key:
        common["api_key"] = settings.model_api_key
    if settings.model_base_url:
        common["base_url"] = settings.model_base_url

    if settings.model_provider == "openai":
        return OpenAIResponses(**common)

    if settings.model_provider == "vllm":
        return VLLM(**common)

    if settings.model_provider == "openai-like":
        return OpenAILike(**common)

    raise RuntimeError(f"Unsupported model provider: {settings.model_provider}")


model = build_model()
