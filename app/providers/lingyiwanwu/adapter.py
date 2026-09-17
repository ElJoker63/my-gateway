"""LingyiWanwu LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import LINGYIWANWU_BASE_URL, LINGYIWANWU_DEFAULT_MODEL

LingyiWanwuProvider = build_provider_class(
    name="lingyiwanwu",
    base_url=LINGYIWANWU_BASE_URL,
    default_model=LINGYIWANWU_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="LingyiWanwuProvider",
)
