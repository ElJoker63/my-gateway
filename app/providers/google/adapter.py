"""Google AI Studio LLM Provider Adapter."""
import json
from pathlib import Path
from app.providers.openai_adapter import OpenAIAdapter
from .config import GOOGLE_BASE_URL, GOOGLE_DEFAULT_MODEL

class GoogleProvider(OpenAIAdapter):
    """Google AI Studio (Gemini) Provider."""

    def __init__(self, api_key: str = ""):
        metadata_file = Path(__file__).parent / "metadata.json"
        capabilities = {}
        if metadata_file.exists():
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
                capabilities = metadata.get("capabilities", {})

        super().__init__(
            name="google",
            base_url=GOOGLE_BASE_URL,
            default_model=GOOGLE_DEFAULT_MODEL,
            default_api_key=api_key,
            capabilities=capabilities,
        )
