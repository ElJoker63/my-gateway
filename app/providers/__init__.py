"""
LLM Provider registry and factory.
Manages provider instances and registers key pools with the KeyManager.
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
    """Initialize all configured providers and register their key pools."""
    global _providers
    settings = get_settings()
    from app.services.key_manager import key_manager

    # --- NVIDIA ---
    nvidia_keys = settings.get_provider_keys("nvidia")
    if nvidia_keys:
        _providers["nvidia"] = NvidiaProvider()
        key_manager.register_pool("nvidia", nvidia_keys)
        logger.info(f"Registered provider: nvidia ({len(nvidia_keys)} key(s))")

    # --- OpenAI ---
    openai_keys = settings.get_provider_keys("openai")
    if openai_keys:
        _providers["openai"] = OpenAIProvider()
        key_manager.register_pool("openai", openai_keys)
        logger.info(f"Registered provider: openai ({len(openai_keys)} key(s))")

    if not _providers:
        logger.warning(
            "No LLM providers configured! "
            "Set NVIDIA_API_KEY/NVIDIA_API_KEYS or OPENAI_API_KEY/OPENAI_API_KEYS in .env"
        )


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
                "No LLM providers available. Configure NVIDIA_API_KEY(S) or OPENAI_API_KEY(S)."
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
