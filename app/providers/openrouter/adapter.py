"""OpenRouter LLM Provider Adapter."""
import json
from pathlib import Path
from app.providers.openai_adapter import OpenAIAdapter
from .config import OPENROUTER_BASE_URL, OPENROUTER_DEFAULT_MODEL

class OpenRouterProvider(OpenAIAdapter):
    """OpenRouter Provider."""

    def __init__(self, api_key: str = ""):
        metadata_file = Path(__file__).parent / "metadata.json"
        capabilities = {}
        if metadata_file.exists():
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
                capabilities = metadata.get("capabilities", {})

        super().__init__(
            name="openrouter",
            base_url=OPENROUTER_BASE_URL,
            default_model=OPENROUTER_DEFAULT_MODEL,
            default_api_key=api_key,
            extra_headers={
                "HTTP-Referer": "https://github.com/ElJoker63/my-gateway",
                "X-Title": "My Gateway AI",
            },
            capabilities=capabilities,
        )
