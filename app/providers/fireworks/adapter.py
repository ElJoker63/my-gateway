"""Fireworks LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import FIREWORKS_BASE_URL, FIREWORKS_DEFAULT_MODEL

FireworksProvider = build_provider_class(
    name="fireworks",
    base_url=FIREWORKS_BASE_URL,
    default_model=FIREWORKS_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="FireworksProvider",
)
