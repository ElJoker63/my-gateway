"""
Abstract base class for LLM providers.
All providers must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional


class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    name: str = "base"

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stop: Optional[list[str]] = None,
        **kwargs,
    ) -> dict:
        """
        Send a chat completion request and return the full response.

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
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stop: Optional[list[str]] = None,
        **kwargs,
    ) -> AsyncIterator[dict]:
        """
        Send a streaming chat completion request.

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

    def _build_params(
        self,
        messages: list[dict],
        model: Optional[str],
        temperature: Optional[float],
        max_tokens: Optional[int],
        top_p: Optional[float],
        stop: Optional[list[str]],
        stream: bool = False,
        **kwargs,
    ) -> dict:
        """Build the request payload for OpenAI-compatible APIs."""
        params = {
            "model": model or self.default_model,
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
