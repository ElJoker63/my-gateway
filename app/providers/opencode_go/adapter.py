"""OpencodeGo LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import OPENCODE_GO_BASE_URL, OPENCODE_GO_DEFAULT_MODEL

OpencodeGoProvider = build_provider_class(
    name="opencode_go",
    base_url=OPENCODE_GO_BASE_URL,
    default_model=OPENCODE_GO_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="OpencodeGoProvider",
)
