"""
LLM Provider registry and factory.
Manages provider instances and registers key pools with the KeyManager across all 24 supported providers.
"""

import json
import logging

from app.config import get_settings
from app.services.model_sync import register_provider_metadata

from .antigravity import AntigravityProvider
from .base import LLMProvider
from .chutes import ChutesProvider
from .cloudflare import CloudflareProvider
from .dashscope import DashScopeProvider
from .deepseek import DeepSeekProvider
from .fireworks import FireworksProvider
from .github_models import GithubModelsProvider
from .google import GoogleProvider
from .groq import GroqProvider
from .hunyuan import HunyuanProvider
from .hyperbolic import HyperbolicProvider
from .kilocode import KilocodeProvider
from .kiro import KiroProvider
from .lingyiwanwu import LingyiWanwuProvider
from .minimax import MiniMaxProvider
from .modelscope import ModelScopeProvider
from .moonshot import MoonshotProvider
from .nous_research import NousResearchProvider

# Legacy root providers
from .nvidia import NvidiaProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .opencode import OpenCodeProvider
from .opencode_go import OpencodeGoProvider

# Package-based providers
from .openrouter import OpenRouterProvider
from .qianfan import QianfanProvider
from .sambanova import SambaNovaProvider
from .sensenova import SenseNovaProvider
from .siliconflow import SiliconFlowProvider
from .stepfun import StepFunProvider
from .volcengine import VolcengineProvider
from .zhipu import ZhipuProvider

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
    "opencode_go": OpencodeGoProvider,
    "kilocode": KilocodeProvider,
    "kiro": KiroProvider,
    "antigravity": AntigravityProvider,
    "nous_research": NousResearchProvider,
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

async def load_persisted_keys_from_redis():
    """
    Merge keys added at runtime (POST /api/providers/{name}/keys) back into
    the KeyManager pools on startup, on top of env-provided keys.
    """
    from app.services.key_manager import key_manager

    try:
        from app.database.redis import get_redis
        redis = await get_redis()
        keys_to_load = await redis.keys("gw:provider_keys:*")
        for raw_key in keys_to_load:
            full = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
            provider = full.removeprefix("gw:provider_keys:")
            raw = await redis.hget(full, "keys")
            if not raw:
                continue
            vals = json.loads(raw if isinstance(raw, str) else raw.decode())
            if not vals:
                continue
            pool = key_manager._pools.get(provider)
            existing = {k.key for k in pool.keys} if pool else set()
            to_add = [k for k in vals if k not in existing]
            if to_add:
                key_manager.add_keys_from_list(provider, to_add)
    except Exception as e:
        logger.warning(f"Could not reload runtime keys from Redis: {e}")


async def init_providers_async():
    """Async wrapper to also load any keys persisted in Redis earlier."""
    init_providers()
    await load_persisted_keys_from_redis()


_providers: dict[str, LLMProvider] = {}


def init_providers():
    """Initialize all configured providers and register their key pools."""
    global _providers
    settings = get_settings()
    from app.services.key_manager import key_manager
    from app.services.oauth_store import oauth_store

    OAUTH_PROVIDERS = {"kiro", "antigravity"}  # providers with OAuth token store

    for name, provider_cls in PROVIDER_CLASSES.items():
        keys = settings.get_provider_keys(name)
        try:
            # OAuth-backed providers (if any) get their access token last-backed from the OAuth store
            instance = None
            if name in OAUTH_PROVIDERS:
                stored = oauth_store._local.get(name)
                if stored:
                    instance = provider_cls(api_key=stored["access_token"])

            if instance is None:
                instance = provider_cls(api_key=keys[0] if keys else "")

            if not getattr(instance, "base_url", ""):
                logger.info(f"Skipping provider '{name}': no base_url configured")
                continue
            _providers[name] = instance
            rpm = settings.get_provider_rpm(name)
            key_manager.register_pool(name, keys if keys else [], rpm_per_key=rpm)
            register_provider_metadata(name, instance.get_metadata())
            logger.info(f"Registered provider: {name} ({len(keys)} key(s), {rpm} RPM/key)")
        except Exception as e:
            logger.error(f"Failed to initialize provider '{name}': {e}")

    if not _providers:
        logger.warning("No LLM providers configured!")



def get_provider(name: str | None = None) -> LLMProvider:
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
