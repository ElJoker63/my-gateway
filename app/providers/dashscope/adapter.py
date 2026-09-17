"""DashScope LLM Provider Adapter (generated via factory)."""
import os
from pathlib import Path

from app.providers.factory import build_provider_class
from .config import DASHSCOPE_BASE_URL, DASHSCOPE_DEFAULT_MODEL

DashScopeProvider = build_provider_class(
    name="dashscope",
    base_url=DASHSCOPE_BASE_URL,
    default_model=DASHSCOPE_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="DashScopeProvider",
)
