"""Tests for the Antigravity provider (Google Cloud Code PKCE OAuth)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.providers.antigravity.adapter import (
    AntigravityProvider,
    _build_gemini_payload,
    _physical_model,
    _to_gemini_contents,
)


class TestGeminiTranslation:
    def test_system_becomes_instruction(self):
        contents, system = _to_gemini_contents([
            {"role": "system", "content": "Be terse"},
            {"role": "user", "content": "hi"},
        ])
        assert system == "Be terse"
        assert len(contents) == 1
        assert contents[0]["role"] == "user"

    def test_assistant_maps_to_model_role(self):
        contents, _ = _to_gemini_contents([
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ])
        assert contents[1]["role"] == "model"
        assert contents[1]["parts"][0]["text"] == "a"

    def test_tool_results_fold_into_user(self):
        contents, _ = _to_gemini_contents([
            {"role": "user", "content": "run x"},
            {"role": "tool", "content": "ok", "tool_call_id": "t1"},
        ])
        assert contents[1]["role"] == "user"
        assert "tool result" in contents[1]["parts"][0]["text"]

    def test_multimodal_flattened(self):
        contents, _ = _to_gemini_contents([
            {"role": "user", "content": [{"type": "text", "text": "look"}, {"type": "image_url", "image_url": {"url": "x"}}]},
        ])
        assert contents[0]["parts"][0]["text"] == "look"


class TestPayloadBuilding:
    def test_generation_config(self):
        p = _build_gemini_payload(
            [{"role": "user", "content": "hi"}], "m",
            temperature=0.2, max_tokens=64, top_p=0.95, stop=["END"],
        )
        gc = p["generationConfig"]
        assert gc["temperature"] == 0.2
        assert gc["maxOutputTokens"] == 64
        assert gc["topP"] == 0.95
        assert gc["stopSequences"] == ["END"]

    def test_model_alias_mapping(self):
        assert _physical_model("gemini-3.1-pro-high") == "gemini-pro-agent"
        assert _physical_model("gemini-3.5-flash-high") == "gemini-3-flash-agent"
        assert _physical_model("other-model") == "other-model"


@pytest.mark.asyncio
class TestAntigravityProvider:
    async def test_requires_oauth_key(self):
        p = AntigravityProvider()
        with pytest.raises(ValueError, match="OAuth"):
            await p.chat(messages=[{"role": "user", "content": "hi"}])

    async def test_chat_builds_cloudcode_envelope(self):
        """The request must carry the Cloud Code envelope with project + agent type."""
        p = AntigravityProvider(api_key="tok")

        captured = {}

        class FakeStream:
            def __init__(self):
                self._lines = [
                    'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}]}}]}',
                    'data: {"candidates":[{"content":{"parts":[{"text":" world"}]}}],"usageMetadata":{"promptTokenCount":5,"candidatesTokenCount":7,"totalTokenCount":12}}',
                    "data: [DONE]",
                ]

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

            def raise_for_status(self):
                pass

            async def aiter_lines(self):
                for line in self._lines:
                    yield line

        client = MagicMock()
        def _stream(method, url, **kw):
            captured["url"] = url
            captured["body"] = kw.get("json")
            captured["headers"] = kw.get("headers")
            return FakeStream()
        client.stream = _stream

        with (
            patch.object(AntigravityProvider, "_get_client", new=AsyncMock(return_value=client)),
            patch.object(AntigravityProvider, "_project_id", new=AsyncMock(return_value="proj-123")),
        ):
            out = await p.chat(messages=[{"role": "user", "content": "hi"}])

        assert out["content"] == "Hello world"
        assert out["usage"]["total_tokens"] == 12

        body = captured["body"]
        assert body["project"] == "proj-123"
        assert body["requestType"] == "agent"
        assert body["userAgent"] == "antigravity"
        assert body["request"]["contents"][0]["parts"][0]["text"] == "hi"
        assert "/v1internal:streamGenerateContent" in captured["url"]
        assert captured["headers"]["Authorization"].startswith("Bearer ")

    async def test_project_id_from_oauth_store(self):
        """project_id must come from the stored OAuth session."""
        with patch("app.providers.antigravity.adapter.AntigravityProvider._project_id") as m:
            m.return_value = AsyncMock(return_value="x")
        # directly exercise the real lookup:
        from app.services.oauth_store import oauth_store
        with patch.object(oauth_store, "get", new=AsyncMock(return_value={"meta": {"project_id": "p42"}})):
            p = AntigravityProvider(api_key="tok")
            assert await p._project_id() == "p42"

    async def test_project_id_missing_raises(self):
        from app.services.oauth_store import oauth_store
        with patch.object(oauth_store, "get", new=AsyncMock(return_value=None)):
            p = AntigravityProvider(api_key="tok")
            with pytest.raises(ValueError, match="project_id"):
                await p._project_id()
