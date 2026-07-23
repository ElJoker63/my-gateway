""" Sensenova LLM Provider Adapter."""
import json
from pathlib import Path
from app.providers.openai_adapter import OpenAIAdapter
from .config import SENSENOVA_BASE_URL, SENSENOVA_DEFAULT_MODEL

class SenseNovaProvider(OpenAIAdapter):
    """Sensenova Provider."""

    def __init__(self, api_key: str = ""):
        metadata_file = Path(__file__).parent / "metadata.json"
        capabilities = {}
        if metadata_file.exists():
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                capabilities = metadata.get("capabilities", {})

        super().__init__(
            name="sensenova",
            base_url=SENSENOVA_BASE_URL,
            default_model=SENSENOVA_DEFAULT_MODEL,
            default_api_key=api_key,
            capabilities=capabilities,
        )
