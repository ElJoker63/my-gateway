""" Opencode LLM Provider Adapter."""
import json
from pathlib import Path
from app.providers.openai_adapter import OpenAIAdapter
from .config import OPENCODE_BASE_URL, OPENCODE_DEFAULT_MODEL

class OpenCodeProvider(OpenAIAdapter):
    """Opencode Provider."""

    def __init__(self, api_key: str = ""):
        metadata_file = Path(__file__).parent / "metadata.json"
        capabilities = {}
        if metadata_file.exists():
            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
                capabilities = metadata.get("capabilities", {})

        super().__init__(
            name="opencode",
            base_url=OPENCODE_BASE_URL,
            default_model=OPENCODE_DEFAULT_MODEL,
            default_api_key=api_key,
            capabilities=capabilities,
        )
