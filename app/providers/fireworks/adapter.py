""" Fireworks LLM Provider Adapter."""
import json
from pathlib import Path
from app.providers.openai_adapter import OpenAIAdapter
from .config import FIREWORKS_BASE_URL, FIREWORKS_DEFAULT_MODEL

class FireworksProvider(OpenAIAdapter):
    """Fireworks Provider."""

    def __init__(self, api_key: str = ""):
        metadata_file = Path(__file__).parent / "metadata.json"
        capabilities = {}
        if metadata_file.exists():
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                capabilities = metadata.get("capabilities", {})

        super().__init__(
            name="fireworks",
            base_url=FIREWORKS_BASE_URL,
            default_model=FIREWORKS_DEFAULT_MODEL,
            default_api_key=api_key,
            capabilities=capabilities,
        )
