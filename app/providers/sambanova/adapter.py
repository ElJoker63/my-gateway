"""SambaNova LLM Provider Adapter (generated via factory)."""
import os
from pathlib import Path

from app.providers.factory import build_provider_class
from .config import SAMBANOVA_BASE_URL, SAMBANOVA_DEFAULT_MODEL

SambaNovaProvider = build_provider_class(
    name="sambanova",
    base_url=SAMBANOVA_BASE_URL,
    default_model=SAMBANOVA_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="SambaNovaProvider",
)
