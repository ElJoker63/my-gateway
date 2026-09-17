"""Kilocode LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import KILOCODE_BASE_URL, KILOCODE_DEFAULT_MODEL

KilocodeProvider = build_provider_class(
    name="kilocode",
    base_url=KILOCODE_BASE_URL,
    default_model=KILOCODE_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="KilocodeProvider",
)
