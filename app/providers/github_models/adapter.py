""" Github_models LLM Provider Adapter."""
import json
from pathlib import Path
from app.providers.openai_adapter import OpenAIAdapter
from .config import GITHUB_MODELS_BASE_URL, GITHUB_MODELS_DEFAULT_MODEL

class GithubModelsProvider(OpenAIAdapter):
    """Github_models Provider."""

    def __init__(self, api_key: str = ""):
        metadata_file = Path(__file__).parent / "metadata.json"
        capabilities = {}
        if metadata_file.exists():
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                capabilities = metadata.get("capabilities", {})

        super().__init__(
            name="github_models",
            base_url=GITHUB_MODELS_BASE_URL,
            default_model=GITHUB_MODELS_DEFAULT_MODEL,
            default_api_key=api_key,
            capabilities=capabilities,
        )
