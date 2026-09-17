"""Google LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import GOOGLE_BASE_URL, GOOGLE_DEFAULT_MODEL

GoogleProvider = build_provider_class(
    name="google",
    base_url=GOOGLE_BASE_URL,
    default_model=GOOGLE_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="GoogleProvider",
)
