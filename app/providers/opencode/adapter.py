"""OpenCode LLM Provider Adapter (generated via factory)."""
import os
from pathlib import Path

from app.providers.factory import build_provider_class
from .config import OPENCODE_BASE_URL, OPENCODE_DEFAULT_MODEL

OpenCodeProvider = build_provider_class(
    name="opencode",
    base_url=OPENCODE_BASE_URL,
    default_model=OPENCODE_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="OpenCodeProvider",
)
