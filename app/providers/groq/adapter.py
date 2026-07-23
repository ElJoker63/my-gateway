"""Groq LLM Provider Adapter."""
import json
from pathlib import Path
from app.providers.openai_adapter import OpenAIAdapter
from .config import GROQ_BASE_URL, GROQ_DEFAULT_MODEL

class GroqProvider(OpenAIAdapter):
    """Groq Cloud API provider."""

    def __init__(self, api_key: str = ""):
        metadata_file = Path(__file__).parent / "metadata.json"
        capabilities = {}
        if metadata_file.exists():
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
                capabilities = metadata.get("capabilities", {})

        super().__init__(
            name="groq",
            base_url=GROQ_BASE_URL,
            default_model=GROQ_DEFAULT_MODEL,
            default_api_key=api_key,
            capabilities=capabilities,
        )
