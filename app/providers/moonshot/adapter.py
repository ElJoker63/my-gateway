"""Moonshot LLM Provider Adapter (generated via factory)."""
import os
from pathlib import Path

from app.providers.factory import build_provider_class
from .config import MOONSHOT_BASE_URL, MOONSHOT_DEFAULT_MODEL

MoonshotProvider = build_provider_class(
    name="moonshot",
    base_url=MOONSHOT_BASE_URL,
    default_model=MOONSHOT_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="MoonshotProvider",
)
