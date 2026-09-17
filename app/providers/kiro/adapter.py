"""
Kiro AI provider — AWS CodeWhisperer via OIDC device-code OAuth.

Unlike the OpenAI-compatible providers, CodeWhisperer speaks a custom JSON
with Binary EventStream framing. This adapter builds the `generateAssistant
Response` envelope from OpenAI-shaped chat calls and unpacks the stream.
"""

import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.providers.base import LLMProvider

from .config import KIRO_BASE_URL, KIRO_DEFAULT_MODEL
from .eventstream import EventStreamError, iter_eventstream_payloads

logger = logging.getLogger(__name__)


def _as_text(content) -> str:
    """Normalize OpenAI message content (string or multi-modal list) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(p for p in parts if p)
    return str(content or "")


def _build_kiro_request(
    messages: list[dict],
    model: str,
    temperature: float | None,
    max_tokens: int | None,
    top_p: float | None,
    stop: list[str] | None,
) -> dict:
    """Translate an OpenAI message list into the CodeWhisperer request body."""
    last_user_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            last_user_idx = i
            break
    if last_user_idx is None:
        raise ValueError("Kiro requires at least one user message")

    history = []
    prior = messages[:last_user_idx]
    for i in range(0, len(prior) - 1, 2):
        u, a = prior[i], prior[i + 1]
        if u.get("role") == "user" and a.get("role") == "assistant":
            history.append({
                "userInputMessage": {"content": _as_text(u.get("content")), "modelId": model, "origin": "AI_EDITOR"},
                "assistantResponseMessage": {"content": _as_text(a.get("content"))},
            })

    current = _as_text(messages[last_user_idx].get("content"))

    inference_config = {}
    if max_tokens is not None:
        inference_config["maxTokens"] = max_tokens
    if temperature is not None:
        inference_config["temperature"] = temperature
    if top_p is not None:
        inference_config["topP"] = top_p
    if stop:
        inference_config["stop"] = stop

    body = {
        "conversationState": {
            "chatTriggerType": "MANUAL",
            "currentMessage": {
                "userInputMessage": {
                    "content": current,
                    "modelId": model,
                    "origin": "AI_EDITOR",
                }
            },
        }
    }
    if history:
        body["conversationState"]["history"] = history
    if inference_config:
        body["inferenceConfig"] = inference_config

    return body


class KiroProvider(LLMProvider):
    """Kiro AI (AWS CodeWhisperer) — requires OAuth device flow credentials."""

    name = "kiro"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key  # OAuth access token after connect
        self.base_url = KIRO_BASE_URL.rstrip("/")
        self.default_model = KIRO_DEFAULT_MODEL
        self.capabilities = {
            "chat": True,
            "streaming": True,
            "vision": False,
            "embeddings": False,
            "tool_calling": False,
            "reasoning": True,
        }
        self.embedding_model = ""
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        return self._client

    def _headers(self, api_key: str) -> dict:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "x-amz-target": "AmazonCodeWhispererStreamingService.GenerateAssistantResponse",
            "x-amz-user-agent": "aws-sdk-js/3.0.0 kiro/0.1",
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
        model_id = model or self.default_model
        payload = _build_kiro_request(messages, model_id, temperature, max_tokens, top_p, stop)

        client = await self._get_client()
        key = api_key or self.api_key
        if not key:
            raise ValueError("Kiro requires an OAuth access token — connect via /api/oauth/kiro/start")

        response = await client.post(
            f"{self.base_url}/generateAssistantResponse",
            json=payload,
            headers=self._headers(key),
        )
        response.raise_for_status()

        content = _collect_eventstream_text(response.content)
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

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
        """Kiro streams via EventStream — we surface it as one-chunk-at-a-time deltas."""
        model_id = model or self.default_model
        payload = _build_kiro_request(messages, model_id, temperature, max_tokens, top_p, stop)

        client = await self._get_client()
        key = api_key or self.api_key
        if not key:
            raise ValueError("Kiro requires an OAuth access token")

        async with client.stream(
            "POST",
            f"{self.base_url}/generateAssistantResponse",
            json=payload,
            headers=self._headers(key),
        ) as response:
            response.raise_for_status()
            buffer = b""
            async for chunk in response.aiter_bytes():
                buffer += chunk
                # try to drain complete frames
                while True:
                    try:
                        # peek total length
                        if len(buffer) < 12:
                            break
                        import struct
                        total_len = struct.unpack_from(">I", buffer, 0)[0]
                        if len(buffer) < total_len or total_len < 16:
                            break
                        frame = buffer[:total_len]
                        buffer = buffer[total_len:]
                        text = _extract_text_from_frame(frame)
                        if text:
                            yield {
                                "content": text,
                                "role": None,
                                "finish_reason": None,
                                "model": model_id,
                            }
                    except EventStreamError:
                        break
            # flush anything left
            if buffer:
                text = _collect_eventstream_text(buffer)
                if text:
                    yield {"content": text, "role": None, "finish_reason": None, "model": model_id}

            yield {"content": "", "role": None, "finish_reason": "stop", "model": model_id}

    async def health_check(self) -> bool:
        """Health = we hold a token (a real probe needs OAuth, so this is local)."""
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


def _extract_text_from_frame(frame: bytes) -> str:
    """Pull assistant text out of one EventStream frame payload."""
    try:
        for payload in iter_eventstream_payloads(frame):
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            # Common shapes seen in the wild
            for key in ("content", "text", "assistantResponseMessage"):
                node = data.get(key)
                if isinstance(node, str) and node:
                    return node
                if isinstance(node, dict):
                    inner = node.get("content")
                    if isinstance(inner, str) and inner:
                        return inner
            # Payload may be a plain string chunk
            if isinstance(data, str):
                return data
    except EventStreamError:
        return ""
    return ""


def _collect_eventstream_text(raw: bytes) -> str:
    """Concatenate assistant text chunks from an EventStream buffer."""
    parts: list[str] = []
    try:
        for payload in iter_eventstream_payloads(raw):
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                # Not every frame is JSON — for CodeWhisperer most are
                continue
            for key in ("content", "text"):
                node = data.get(key)
                if isinstance(node, str) and node:
                    parts.append(node)
                    break
    except EventStreamError:
        # Defensive: return what we have
        pass
    return "".join(parts)
