"""Hunyuan LLM Provider Adapter (generated via factory)."""
import os
from pathlib import Path

from app.providers.factory import build_provider_class
from .config import HUNYUAN_BASE_URL, HUNYUAN_DEFAULT_MODEL

HunyuanProvider = build_provider_class(
    name="hunyuan",
    base_url=HUNYUAN_BASE_URL,
    default_model=HUNYUAN_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="HunyuanProvider",
)
