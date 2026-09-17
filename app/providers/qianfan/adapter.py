"""Qianfan LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import QIANFAN_BASE_URL, QIANFAN_DEFAULT_MODEL

QianfanProvider = build_provider_class(
    name="qianfan",
    base_url=QIANFAN_BASE_URL,
    default_model=QIANFAN_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="QianfanProvider",
)
