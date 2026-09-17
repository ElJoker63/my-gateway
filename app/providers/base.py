"""
Abstract base class for LLM providers.
All providers must implement this interface.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    name: str = "base"

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stop: list[str] | None = None,
        api_key: str | None = None,
        **kwargs,
    ) -> dict:
        """
        Send a chat completion request and return the full response.

        Args:
            api_key: Override API key for this request (from KeyManager).
                     If None, uses the provider's default key.

        Returns dict with keys:
            - content: str (assistant response text)
            - model: str (model used)
            - usage: dict (prompt_tokens, completion_tokens, total_tokens)
            - raw: dict (full provider response)
        """
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        top_p: float | None = None,
        stop: list[str] | None = None,
        api_key: str | None = None,
        **kwargs,
    ) -> AsyncIterator[dict]:
        """
        Send a streaming chat completion request.

        Args:
            api_key: Override API key for this request (from KeyManager).

        Yields dicts with keys:
            - content: str (delta text)
            - finish_reason: Optional[str]
            - model: str
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is reachable and configured."""
        ...

    async def embeddings(
        self,
        input_text: str | list[str],
        model: str | None = None,
        api_key: str | None = None,
        **kwargs,
    ) -> dict:
        """Generate text embeddings."""
        raise NotImplementedError(f"Embeddings not implemented for provider '{self.name}'")

    async def list_models(self, api_key: str | None = None) -> list[dict]:
        """Fetch available models dynamically from provider endpoint."""
        return []

    def get_metadata(self) -> dict:
        """Return provider capabilities and metadata."""
        return {
            "name": getattr(self, "name", "base"),
            "default_model": getattr(self, "default_model", ""),
            "capabilities": getattr(self, "capabilities", {}),
        }

    @staticmethod
    def _get_auth_headers(api_key: str) -> dict:
        """Build authorization headers for a request."""
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _build_params(
        self,
        messages: list[dict],
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        top_p: float | None,
        stop: list[str] | None,
        stream: bool = False,
        **kwargs,
    ) -> dict:
        """Build the request payload for OpenAI-compatible APIs."""
        params = {
            "model": model or getattr(self, "default_model", ""),
            "messages": messages,
        }
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        if top_p is not None:
            params["top_p"] = top_p
        if stop is not None:
            params["stop"] = stop
        if stream:
            params["stream"] = True

        # Pass through any extra params
        for key, value in kwargs.items():
            if value is not None and key not in params:
                params[key] = value

        return params

