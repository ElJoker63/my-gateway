"""
Provider metadata registry.
Holds per-provider capabilities discovered at init (from metadata.json),
exposed to /v1/models and diagnostics. In-memory only — rebuilt on startup.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_METADATA_CACHE: dict[str, dict] = {}


def register_provider_metadata(provider_name: str, metadata: dict):
    """Register provider capabilities metadata (called at provider init)."""
    _METADATA_CACHE[provider_name] = metadata


def get_provider_metadata(provider_name: Optional[str] = None) -> dict:
    """Get metadata for a provider, or all providers when no name is given."""
    if provider_name:
        return _METADATA_CACHE.get(provider_name, {})
    return dict(_METADATA_CACHE)
