"""Cloudflare LLM Provider Adapter (generated via factory)."""
import os
from pathlib import Path

from app.providers.factory import build_provider_class
from .config import CLOUDFLARE_BASE_URL, CLOUDFLARE_DEFAULT_MODEL

CloudflareProvider = build_provider_class(
    name="cloudflare",
    base_url=CLOUDFLARE_BASE_URL,
    default_model=CLOUDFLARE_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="CloudflareProvider",
)
