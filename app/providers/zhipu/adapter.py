"""Zhipu LLM Provider Adapter (generated via factory)."""
import os
from pathlib import Path

from app.providers.factory import build_provider_class
from .config import ZHIPU_BASE_URL, ZHIPU_DEFAULT_MODEL

ZhipuProvider = build_provider_class(
    name="zhipu",
    base_url=ZHIPU_BASE_URL,
    default_model=ZHIPU_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="ZhipuProvider",
)
