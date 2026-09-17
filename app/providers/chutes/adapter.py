"""Chutes LLM Provider Adapter (generated via factory)."""
import os
from pathlib import Path

from app.providers.factory import build_provider_class
from .config import CHUTES_BASE_URL, CHUTES_DEFAULT_MODEL

ChutesProvider = build_provider_class(
    name="chutes",
    base_url=CHUTES_BASE_URL,
    default_model=CHUTES_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="ChutesProvider",
)
