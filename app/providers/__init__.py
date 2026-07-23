"""
LLM Provider registry and factory.
Manages provider instances and provides a get_provider() accessor.
"""

import logging
from typing import Optional

from app.config import get_settings
from .base import LLMProvider
from .nvidia import NvidiaProvider
from .openai import OpenAIProvider

logger = logging.getLogger(__name__)

# Provider registry
_providers: dict[str, LLMProvider] = {}


def init_providers():
    """Initialize all configured providers."""
    global _providers
    settings = get_settings()

    # Always register NVIDIA if key is configured
    if settings.nvidia_api_key:
        _providers["nvidia"] = NvidiaProvider()
        logger.info("Registered provider: nvidia")

    # Always register OpenAI if key is configured
    if settings.openai_api_key:
        _providers["openai"] = OpenAIProvider()
        logger.info("Registered provider: openai")

    if not _providers:
        logger.warning("No LLM providers configured! Set NVIDIA_API_KEY or OPENAI_API_KEY in .env")


def get_provider(name: Optional[str] = None) -> LLMProvider:
    """
    Get a provider by name, falling back to the default.

    Args:
        name: Provider name ('nvidia', 'openai'). None uses default.

    Returns:
        LLMProvider instance.

    Raises:
        ValueError: If the requested provider is not available.
    """
    if not _providers:
        init_providers()

    settings = get_settings()
    provider_name = name or settings.default_provider

    if provider_name not in _providers:
        available = list(_providers.keys())
        if available:
            # Fall back to first available
            provider_name = available[0]
            logger.warning(f"Requested provider '{name}' not available, using '{provider_name}'")
        else:
            raise ValueError(
                "No LLM providers available. Configure NVIDIA_API_KEY or OPENAI_API_KEY."
            )

    return _providers[provider_name]


def list_providers() -> list[str]:
    """List all registered provider names."""
    if not _providers:
        init_providers()
    return list(_providers.keys())


async def close_providers():
    """Close all provider connections."""
    for name, provider in _providers.items():
        if hasattr(provider, "close"):
            await provider.close()
            logger.info(f"Closed provider: {name}")
    _providers.clear()
