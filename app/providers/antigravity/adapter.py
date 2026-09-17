"""
Antigravity (Google Cloud Code) provider — Gemini-format requests wrapped in
the Cloud Code envelope, authenticated via Google PKCE OAuth.

Wire format (from openproxy's adapters):
  POST /v1internal:streamGenerateContent?alt=sse
  {
    "project": "<project from loadCodeAssist>",
    "model": "<physical model>",
    "requestType": "agent",
    "requestId": "<uuid>",
    "userAgent": "antigravity",
    "request": { ...Gemini generateContent request... },
    "enabledCreditTypes": ["GOOGLE_ONE_AI"],
  }
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator

import httpx

from app.providers.base import LLMProvider
from app.providers.kiro.adapter import _as_text

from .config import ANTIGRAVITY_BASE_URL, ANTIGRAVITY_DEFAULT_MODEL

logger = logging.getLogger(__name__)


def _to_gemini_contents(messages: list[dict]) -> tuple[list[dict], str | None]:
    """Translate OpenAI messages to Gemini's `contents` + `systemInstruction`."""
    system_parts: list[str] = []
    contents: list[dict] = []

    for m in messages:
        role = m.get("role")
        text = _as_text(m.get("content"))

        if role == "system":
            if text:
                system_parts.append(text)
            continue
        if role == "user":
            contents.append({"role": "user", "parts": [{"text": text}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": text}]})
        # tool messages aren't supported by the minimal translator — surface as user text
        elif role == "tool":
            contents.append({"role": "user", "parts": [{"text": f"[tool result] {text}"}]})

    system_instruction = "\n\n".join(system_parts) if system_parts else None
    return contents, system_instruction


def _build_gemini_payload(
    messages: list[dict],
    model: str,
    temperature: float | None,
    max_tokens: int | None,
    top_p: float | None,
    stop: list[str] | None,
) -> dict:
    contents, system_instruction = _to_gemini_contents(messages)

    generation_config = {}
    if temperature is not None:
        generation_config["temperature"] = temperature
    if max_tokens is not None:
        generation_config["maxOutputTokens"] = max_tokens
    if top_p is not None:
        generation_config["topP"] = top_p
    if stop:
        generation_config["stopSequences"] = stop

    payload: dict = {"contents": contents}
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    if generation_config:
        payload["generationConfig"] = generation_config
    return payload


# openproxy's map: some "friendly" names map to physical model ids
_MODEL_MAP = {
    "gemini-3.1-pro-high": "gemini-pro-agent",
    "gemini-3.1-pro-medium": "gemini-pro-agent",
    "gemini-3.5-flash-high": "gemini-3-flash-agent",
}


def _physical_model(model: str) -> str:
    return _MODEL_MAP.get(model, model)


class AntigravityProvider(LLMProvider):
    """Antigravity via Google Cloud Code (PKCE OAuth)."""

    name = "antigravity"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.base_url = ANTIGRAVITY_BASE_URL.rstrip("/")
        self.default_model = ANTIGRAVITY_DEFAULT_MODEL
        self.capabilities = {
            "chat": True,
            "streaming": True,
            "vision": True,
            "embeddings": False,
            "tool_calling": True,
            "reasoning": True,
        }
        self.embedding_model = ""
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0))
        return self._client

    async def _project_id(self) -> str:
        from app.services.oauth_store import oauth_store

        stored = await oauth_store.get(self.name)
        if stored:
            project = (stored.get("meta") or {}).get("project_id")
            if project:
                return project
        raise ValueError("Antigravity: no project_id in OAuth session — reconnect via /api/oauth/antigravity/start")

    def _headers(self, api_key: str) -> dict:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "antigravity/1.0",
        }

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
        """Non-streaming chat — request sends alt=sse but we gather the full frame."""
        model_id = _physical_model(model or self.default_model)
        key = api_key or self.api_key
        if not key:
            raise ValueError("Antigravity requires an OAuth access token — connect via /api/oauth/antigravity/start")

        inner = _build_gemini_payload(messages, model_id, temperature, max_tokens, top_p, stop)
        body = {
            "project": await self._project_id(),
            "model": model_id,
            "requestType": "agent",
            "requestId": str(uuid.uuid4()),
            "userAgent": "antigravity",
            "request": inner,
            "enabledCreditTypes": ["GOOGLE_ONE_AI"],
        }

        client = await self._get_client()
        url = f"{self.base_url}/v1internal:streamGenerateContent?alt=sse"

        content = ""
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        async with client.stream("POST", url, json=body, headers=self._headers(key)) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                text = _extract_gemini_text(chunk)
                if text:
                    content += text
                # usage comes in the last chunk
                usage_meta = chunk.get("usageMetadata") or (chunk.get("response") or {}).get("usageMetadata")
                if usage_meta:
                    usage = {
                        "prompt_tokens": usage_meta.get("promptTokenCount", 0),
                        "completion_tokens": usage_meta.get("candidatesTokenCount", 0)
                                            + usage_meta.get("thoughtsTokenCount", 0),
                        "total_tokens": usage_meta.get("totalTokenCount", 0),
                    }

        return {
            "content": content,
            "model": model_id,
            "usage": usage,
            "raw": {},
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
        model_id = _physical_model(model or self.default_model)
        key = api_key or self.api_key
        if not key:
            raise ValueError("Antigravity requires an OAuth access token")

        inner = _build_gemini_payload(messages, model_id, temperature, max_tokens, top_p, stop)
        body = {
            "project": await self._project_id(),
            "model": model_id,
            "requestType": "agent",
            "requestId": str(uuid.uuid4()),
            "userAgent": "antigravity",
            "request": inner,
            "enabledCreditTypes": ["GOOGLE_ONE_AI"],
        }

        client = await self._get_client()
        url = f"{self.base_url}/v1internal:streamGenerateContent?alt=sse"

        async with client.stream("POST", url, json=body, headers=self._headers(key)) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                text = _extract_gemini_text(chunk)
                if text:
                    yield {
                        "content": text,
                        "role": None,
                        "finish_reason": None,
                        "model": model_id,
                    }

            yield {"content": "", "role": None, "finish_reason": "stop", "model": model_id}

    async def health_check(self) -> bool:
        return bool(self.api_key)

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "default_model": self.default_model,
            "capabilities": self.capabilities,
        }

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


def _extract_gemini_text(chunk: dict) -> str:
    """Extract text from one streaming chunk (Gemini-format response)."""
    # The envelope may wrap in "response"; peek the candidates' parts
    node = chunk.get("response", chunk)
    candidates = node.get("candidates") or []
    out: list[str] = []
    for cand in candidates:
        content = cand.get("content") or {}
        for part in content.get("parts", []):
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                out.append(part["text"])
    return "".join(out)
