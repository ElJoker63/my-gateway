"""
Common OpenAI-compatible base adapter.
Used by providers with OpenAI-compliant REST endpoints (Groq, DeepSeek, OpenRouter, SiliconFlow, Fireworks, etc.).
"""

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.providers.base import LLMProvider

logger = logging.getLogger(__name__)


class OpenAIAdapter(LLMProvider):
    """Generic adapter for OpenAI-compatible chat, streaming, embedding, and model endpoints."""

    def __init__(
        self,
        name: str,
        base_url: str,
        default_model: str,
        default_api_key: str = "",
        timeout: float = 60.0,
        extra_headers: dict | None = None,
        capabilities: dict | None = None,
        embedding_model: str | None = None,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.default_api_key = default_api_key
        self.timeout = timeout
        self.extra_headers = extra_headers or {}
        self.embedding_model = embedding_model or ""
        self.capabilities = capabilities if capabilities else {
            "chat": True,
            "streaming": True,
            "embeddings": False,
            "vision": False,
            "tool_calling": True,
            "reasoning": False,
        }
        self.client = httpx.AsyncClient(timeout=self.timeout)

    def _get_headers(self, api_key: str | None = None) -> dict:
        key = api_key or self.default_api_key
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        headers.update(self.extra_headers)
        return headers

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
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers(api_key)
        payload = self._build_params(
            messages=messages,
            model=model or self.default_model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
            stream=False,
            **kwargs,
        )

        response = await self.client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        content = choice["message"].get("content", "") or ""
        model_used = data.get("model", model or self.default_model)
        usage = data.get("usage", {})

        return {
            "content": content,
            "model": model_used,
            "usage": usage,
            "raw": data,
        }

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
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers(api_key)
        payload = self._build_params(
            messages=messages,
            model=model or self.default_model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            stop=stop,
            stream=True,
            **kwargs,
        )

        async with self.client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choice = chunk.get("choices", [{}])[0]
                        delta = choice.get("delta", {})
                        content = delta.get("content", "") or ""
                        reasoning = delta.get("reasoning_content", "") or ""
                        finish_reason = choice.get("finish_reason")

                        yield {
                            "content": content,
                            "reasoning_content": reasoning,
                            "finish_reason": finish_reason,
                            "model": chunk.get("model", model or self.default_model),
                        }
                    except json.JSONDecodeError:
                        continue

    async def embeddings(
        self,
        input_text: str | list[str],
        model: str | None = None,
        api_key: str | None = None,
        **kwargs,
    ) -> dict:
        if not self.capabilities.get("embeddings", False):
            raise NotImplementedError(
                f"Provider '{self.name}' does not support embeddings"
            )
        if not model:
            model = self.embedding_model
        if not model:
            raise ValueError(
                f"No embedding model configured for provider '{self.name}' — "
                f"pass model= explicitly or set {self.name.upper()}_EMBEDDING_MODEL"
            )

        url = f"{self.base_url}/embeddings"
        headers = self._get_headers(api_key)
        payload = {
            "model": model,
            "input": input_text,
        }
        payload.update(kwargs)

        response = await self.client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    async def list_models(self, api_key: str | None = None) -> list[dict]:
        url = f"{self.base_url}/models"
        headers = self._get_headers(api_key)
        response = await self.client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])

    async def health_check(self) -> bool:
        """
        Real connectivity check: GET /models must succeed.
        Returns False when the provider is unreachable or the key is rejected.
        """
        try:
            url = f"{self.base_url}/models"
            headers = self._get_headers()
            response = await self.client.get(url, headers=headers, timeout=10.0)
            return response.status_code < 400
        except Exception:
            return False

    async def close(self):
        await self.client.aclose()
