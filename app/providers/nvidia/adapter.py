"""Nvidia LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import NVIDIA_BASE_URL, NVIDIA_DEFAULT_MODEL

NvidiaProvider = build_provider_class(
    name="nvidia",
    base_url=NVIDIA_BASE_URL,
    default_model=NVIDIA_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="NvidiaProvider",
)
