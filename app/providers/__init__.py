"""
LLM Provider registry and factory.
Manages provider instances and registers key pools with the KeyManager across all 24 supported providers.
"""

import logging
from typing import Optional

from app.config import get_settings
from app.services.model_sync import register_provider_metadata
from .base import LLMProvider

# Legacy root providers
from .nvidia import NvidiaProvider
from .openai import OpenAIProvider
from .groq import GroqProvider
from .ollama import OllamaProvider

# Package-based providers
from .openrouter import OpenRouterProvider
from .google import GoogleProvider
from .cloudflare import CloudflareProvider
from .github_models import GithubModelsProvider
from .sambanova import SambaNovaProvider
from .chutes import ChutesProvider
from .fireworks import FireworksProvider
from .hyperbolic import HyperbolicProvider
from .opencode import OpenCodeProvider
from .deepseek import DeepSeekProvider
from .siliconflow import SiliconFlowProvider
from .modelscope import ModelScopeProvider
from .zhipu import ZhipuProvider
from .moonshot import MoonshotProvider
from .minimax import MiniMaxProvider
from .dashscope import DashScopeProvider
from .hunyuan import HunyuanProvider
from .qianfan import QianfanProvider
from .sensenova import SenseNovaProvider
from .stepfun import StepFunProvider
from .lingyiwanwu import LingyiWanwuProvider
from .volcengine import VolcengineProvider

logger = logging.getLogger(__name__)

# Provider map
PROVIDER_CLASSES = {
    "nvidia": NvidiaProvider,
    "openai": OpenAIProvider,
    "groq": GroqProvider,
    "ollama": OllamaProvider,
    "openrouter": OpenRouterProvider,
    "google": GoogleProvider,
    "cloudflare": CloudflareProvider,
    "github_models": GithubModelsProvider,
    "sambanova": SambaNovaProvider,
    "chutes": ChutesProvider,
    "fireworks": FireworksProvider,
    "hyperbolic": HyperbolicProvider,
    "opencode": OpenCodeProvider,
    "deepseek": DeepSeekProvider,
    "siliconflow": SiliconFlowProvider,
    "modelscope": ModelScopeProvider,
    "zhipu": ZhipuProvider,
    "moonshot": MoonshotProvider,
    "minimax": MiniMaxProvider,
    "dashscope": DashScopeProvider,
    "hunyuan": HunyuanProvider,
    "qianfan": QianfanProvider,
    "sensenova": SenseNovaProvider,
    "stepfun": StepFunProvider,
    "lingyiwanwu": LingyiWanwuProvider,
    "volcengine": VolcengineProvider,
}

_providers: dict[str, LLMProvider] = {}


def init_providers():
    """Initialize all configured providers and register their key pools."""
    global _providers
    settings = get_settings()
    from app.services.key_manager import key_manager

    for name, provider_cls in PROVIDER_CLASSES.items():
        keys = settings.get_provider_keys(name)
        if keys or name in ("ollama", "nvidia", "openai"):  # initialize default/demo providers or if keys present
            try:
                instance = provider_cls()
                _providers[name] = instance
                rpm = settings.get_provider_rpm(name)
                key_manager.register_pool(name, keys or ["default-key"], rpm_per_key=rpm)
                register_provider_metadata(name, instance.get_metadata())
                logger.info(f"Registered provider: {name} ({len(keys)} key(s), {rpm} RPM/key)")
            except Exception as e:
                logger.error(f"Failed to initialize provider '{name}': {e}")

    if not _providers:
        logger.warning("No LLM providers configured!")


def get_provider(name: Optional[str] = None) -> LLMProvider:
    """Get a provider by name, falling back to default."""
    if not _providers:
        init_providers()

    settings = get_settings()
    provider_name = name or settings.default_provider

    if provider_name not in _providers:
        available = list(_providers.keys())
        if available:
            provider_name = available[0]
            logger.warning(f"Requested provider '{name}' not available, using '{provider_name}'")
        else:
            raise ValueError("No LLM providers available.")

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
