""" Moonshot LLM Provider Adapter."""
import json
from pathlib import Path
from app.providers.openai_adapter import OpenAIAdapter
from .config import MOONSHOT_BASE_URL, MOONSHOT_DEFAULT_MODEL

class MoonshotProvider(OpenAIAdapter):
    """Moonshot Provider."""

    def __init__(self, api_key: str = ""):
        metadata_file = Path(__file__).parent / "metadata.json"
        capabilities = {}
        if metadata_file.exists():
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                capabilities = metadata.get("capabilities", {})

        super().__init__(
            name="moonshot",
            base_url=MOONSHOT_BASE_URL,
            default_model=MOONSHOT_DEFAULT_MODEL,
            default_api_key=api_key,
            capabilities=capabilities,
        )
