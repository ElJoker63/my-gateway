"""Hyperbolic LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import HYPERBOLIC_BASE_URL, HYPERBOLIC_DEFAULT_MODEL

HyperbolicProvider = build_provider_class(
    name="hyperbolic",
    base_url=HYPERBOLIC_BASE_URL,
    default_model=HYPERBOLIC_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="HyperbolicProvider",
)
