"""NousResearch LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import NOUS_RESEARCH_BASE_URL, NOUS_RESEARCH_DEFAULT_MODEL

NousResearchProvider = build_provider_class(
    name="nous_research",
    base_url=NOUS_RESEARCH_BASE_URL,
    default_model=NOUS_RESEARCH_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="NousResearchProvider",
)
