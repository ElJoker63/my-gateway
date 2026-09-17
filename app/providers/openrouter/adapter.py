"""OpenRouter LLM Provider Adapter (generated via factory)."""
import os
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import OPENROUTER_BASE_URL, OPENROUTER_DEFAULT_MODEL

OpenRouterProvider = build_provider_class(
    name="openrouter",
    base_url=OPENROUTER_BASE_URL,
    default_model=OPENROUTER_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="OpenRouterProvider",
    extra_headers={
        "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://github.com/ElJoker63/my-gateway"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "My Gateway AI"),
    },

)
