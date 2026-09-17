"""
Provider factory — builds OpenAI-compatible provider classes from a package's
metadata.json + config, eliminating the 23 byte-identical adapter files.

Usage inside a provider package's adapter.py:

    from app.providers.factory import build_provider_class
    from .config import GROQ_BASE_URL, GROQ_DEFAULT_MODEL

    GroqProvider = build_provider_class(
        name="groq",
        base_url=GROQ_BASE_URL,
        default_model=GROQ_DEFAULT_MODEL,
        package_dir=Path(__file__).parent,
    )

Each generated subclass loads capabilities from ``metadata.json`` sitting next
to the package's adapter module and reads ``{NAME}_EMBEDDING_MODEL`` from env.
"""

import json
import logging
import os
from pathlib import Path

from app.providers.openai_adapter import OpenAIAdapter

logger = logging.getLogger(__name__)


def _load_capabilities(metadata_path: Path) -> dict:
    """Load the capabilities block from a provider's metadata.json (if present)."""
    try:
        if metadata_path.exists():
            with open(metadata_path, encoding="utf-8") as f:
                return json.load(f).get("capabilities", {}) or {}
    except Exception as e:
        logger.warning(f"Failed to load metadata at {metadata_path}: {e}")
    return {}


def build_provider_class(
    name: str,
    base_url: str,
    default_model: str,
    package_dir: str,
    extra_headers: dict | None = None,
    class_name: str | None = None,
) -> type[OpenAIAdapter]:
    """
    Build an OpenAIAdapter subclass preconfigured for a provider.

    Args:
        name: provider name ("groq")
        base_url: OpenAI-compatible base URL
        default_model: default chat model
        package_dir: path of the provider package (for metadata.json lookup)
        extra_headers: provider-specific headers (e.g. OpenRouter referer)
        class_name: override the generated class name
    """
    metadata_path = Path(package_dir) / "metadata.json"
    capabilities = _load_capabilities(metadata_path)
    env_prefix = name.upper()

    cls_name = class_name or "".join(part.capitalize() for part in name.split("_")) + "Provider"

    def __init__(self, api_key: str = ""):
        OpenAIAdapter.__init__(
            self,
            name=name,
            base_url=base_url,
            default_model=default_model,
            default_api_key=api_key,
            capabilities=capabilities,
            extra_headers=extra_headers,
            embedding_model=os.getenv(f"{env_prefix}_EMBEDDING_MODEL", ""),
        )

    new_cls = type(cls_name, (OpenAIAdapter,), {"__init__": __init__, "__module__": "app.providers"})
    new_cls.__qualname__ = cls_name
    return new_cls
