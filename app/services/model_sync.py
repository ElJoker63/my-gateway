"""
Automatic Model Synchronization & Capability Discovery Service.
Fetches, caches, and stores model lists and capability metadata across all registered providers.
"""

import json
import logging
from typing import Optional
from app.config import get_settings

logger = logging.getLogger(__name__)

# Memory cache for provider models and capabilities
_MODEL_CACHE: dict[str, list[dict]] = {}
_METADATA_CACHE: dict[str, dict] = {}


async def sync_provider_models(provider_name: str, provider_instance) -> list[dict]:
    """Fetch latest models from provider and update cache."""
    try:
        models = await provider_instance.list_models()
        if models:
            _MODEL_CACHE[provider_name] = models
            logger.info(f"Synchronized {len(models)} models for provider '{provider_name}'")
            return models
    except Exception as e:
        logger.warning(f"Error synchronizing models for '{provider_name}': {e}")
    return _MODEL_CACHE.get(provider_name, [])


def get_cached_models(provider_name: Optional[str] = None) -> dict:
    """Get cached models for a provider or all providers."""
    if provider_name:
        return {provider_name: _MODEL_CACHE.get(provider_name, [])}
    return _MODEL_CACHE


def register_provider_metadata(provider_name: str, metadata: dict):
    """Register provider capabilities metadata."""
    _METADATA_CACHE[provider_name] = metadata


def get_provider_metadata(provider_name: Optional[str] = None) -> dict:
    """Get metadata for a provider or all providers."""
    if provider_name:
        return _METADATA_CACHE.get(provider_name, {})
    return _METADATA_CACHE
