"""GithubModels LLM Provider Adapter (generated via factory)."""
from pathlib import Path

from app.providers.factory import build_provider_class

from .config import GITHUB_MODELS_BASE_URL, GITHUB_MODELS_DEFAULT_MODEL

GithubModelsProvider = build_provider_class(
    name="github_models",
    base_url=GITHUB_MODELS_BASE_URL,
    default_model=GITHUB_MODELS_DEFAULT_MODEL,
    package_dir=Path(__file__).parent,
    class_name="GithubModelsProvider",
)
