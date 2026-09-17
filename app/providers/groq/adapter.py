"""Groq LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import GROQ_BASE_URL, GROQ_DEFAULT_MODEL

GroqProvider = build_provider_class(
    name="groq",
    base_url=GROQ_BASE_URL,
    default_model=GROQ_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="GroqProvider",
)
