"""SenseNova LLM Provider Adapter (generated via factory)."""
import os
from pathlib import Path

from app.providers.factory import build_provider_class
from .config import SENSENOVA_BASE_URL, SENSENOVA_DEFAULT_MODEL

SenseNovaProvider = build_provider_class(
    name="sensenova",
    base_url=SENSENOVA_BASE_URL,
    default_model=SENSENOVA_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="SenseNovaProvider",
)
