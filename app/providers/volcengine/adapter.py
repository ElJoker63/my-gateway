"""Volcengine LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import VOLCENGINE_BASE_URL, VOLCENGINE_DEFAULT_MODEL

VolcengineProvider = build_provider_class(
    name="volcengine",
    base_url=VOLCENGINE_BASE_URL,
    default_model=VOLCENGINE_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="VolcengineProvider",
)
