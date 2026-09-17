"""ModelScope LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import MODELSCOPE_BASE_URL, MODELSCOPE_DEFAULT_MODEL

ModelScopeProvider = build_provider_class(
    name="modelscope",
    base_url=MODELSCOPE_BASE_URL,
    default_model=MODELSCOPE_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="ModelScopeProvider",
)
