from __future__ import annotations

from app.config import settings
from app.services.generation.anthropic_adapter import AnthropicAdapter
from app.services.generation.openai_adapter import OpenAIAdapter
from app.services.generation.provider import LLMProvider


def get_provider() -> LLMProvider:
    """Factory selecting the configured provider. Only the *selected* provider's API key is
    required — the other provider is never instantiated, never even key-checked, per
    ARCHITECTURE.md §7.2 and SPEC.md §9 ("если только один под рукой... молча не звать другой").
    """
    if settings.llm_provider == "anthropic":
        return AnthropicAdapter()
    if settings.llm_provider == "openai":
        return OpenAIAdapter()
    raise RuntimeError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
