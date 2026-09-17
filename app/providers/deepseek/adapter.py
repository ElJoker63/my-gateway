"""DeepSeek LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import DEEPSEEK_BASE_URL, DEEPSEEK_DEFAULT_MODEL

DeepSeekProvider = build_provider_class(
    name="deepseek",
    base_url=DEEPSEEK_BASE_URL,
    default_model=DEEPSEEK_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="DeepSeekProvider",
)
