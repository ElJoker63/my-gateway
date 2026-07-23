"""
NVIDIA API LLM provider.
Uses NVIDIA's OpenAI-compatible API endpoint.
"""

import json
import logging
from typing import AsyncIterator, Optional

import httpx

from app.config import get_settings
from .base import LLMProvider

logger = logging.getLogger(__name__)


class NvidiaProvider(LLMProvider):
    """NVIDIA API provider using their OpenAI-compatible endpoint."""

    name = "nvidia"

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.nvidia_api_key
        self.base_url = settings.nvidia_base_url.rstrip("/")
        self.default_model = settings.nvidia_model
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        return self._client

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
        """Send a non-streaming chat completion request to NVIDIA API."""
        client = await self._get_client()
        params = self._build_params(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
            stream=False,
            **kwargs,
        )

        logger.debug(f"NVIDIA chat request: model={params['model']}, messages={len(messages)}")

        response = await client.post("/chat/completions", json=params)
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return {
            "content": content,
            "model": data.get("model", params["model"]),
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "raw": data,
        }

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
        """Send a streaming chat completion request to NVIDIA API."""
        client = await self._get_client()
        params = self._build_params(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
            stream=True,
            **kwargs,
        )

        logger.debug(f"NVIDIA stream request: model={params['model']}, messages={len(messages)}")

        async with client.stream("POST", "/chat/completions", json=params) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue

                data_str = line[6:].strip()  # Remove "data: " prefix
                if data_str == "[DONE]":
                    return

                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    finish_reason = chunk["choices"][0].get("finish_reason")

                    yield {
                        "content": delta.get("content", ""),
                        "role": delta.get("role"),
                        "finish_reason": finish_reason,
                        "model": chunk.get("model", params["model"]),
                    }
                except (json.JSONDecodeError, KeyError, IndexError) as e:
                    logger.warning(f"Failed to parse stream chunk: {e}")
                    continue

    async def health_check(self) -> bool:
        """Check if NVIDIA API is reachable."""
        if not self.api_key:
            logger.warning("NVIDIA API key not configured")
            return False
        try:
            client = await self._get_client()
            response = await client.get("/models", timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"NVIDIA health check failed: {e}")
            return False

    async def close(self):
        """Close the httpx client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
