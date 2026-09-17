"""Tests for the Kiro provider (CodeWhisperer device-flow + EventStream)."""

import json
import struct
import zlib

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.kiro.adapter import KiroProvider, _build_kiro_request, _as_text
from app.providers.kiro.eventstream import (
    EventStreamError,
    iter_eventstream_payloads,
    _crc32,
)


# ---------------------------------------------------------------
# Event stream framing helpers
# ---------------------------------------------------------------


def _frame(payload: bytes, headers: bytes = b"") -> bytes:
    """Build one valid EventStream frame around a payload."""
    prelude_len = 8
    headers_len = len(headers)
    total_len = prelude_len + 4 + headers_len + len(payload) + 4  # prelude + prelude_crc + headers + payload + msg_crc
    prelude = struct.pack(">II", total_len, headers_len)
    prelude_crc = struct.pack(">I", zlib.crc32(prelude) & 0xFFFFFFFF)
    body = prelude + prelude_crc + headers + payload
    return body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


class TestEventStreamParser:
    def test_single_frame(self):
        payload = json.dumps({"content": "hello"}).encode()
        frame = _frame(payload)
        payloads = list(iter_eventstream_payloads(frame))
        assert len(payloads) == 1
        assert json.loads(payloads[0]) == {"content": "hello"}

    def test_multiple_frames(self):
        parts = [json.dumps({"content": f"part-{i}"}).encode() for i in range(3)]
        buffer = b"".join(_frame(p) for p in parts)
        payloads = list(iter_eventstream_payloads(buffer))
        assert len(payloads) == 3
        assert json.loads(payloads[1]) == {"content": "part-1"}

    def test_truncated_frame_raises(self):
        payload = json.dumps({"content": "x"}).encode()
        frame = _frame(payload)
        with pytest.raises(EventStreamError):
            list(iter_eventstream_payloads(frame[:-5]))

    def test_empty_payload_skipped(self):
        payload = json.dumps({"content": "hi"}).encode()
        frame = _frame(payload) + b""  # trailing nothing
        payloads = list(iter_eventstream_payloads(frame))
        assert payloads == [payload]


class TestKiroRequestShape:
    def test_build_conversation_state(self):
        msgs = [
            {"role": "user", "content": "what is 2+2?"},
        ]
        body = _build_kiro_request(msgs, "claude-sonnet-4.5", None, None, None, None)
        cs = body["conversationState"]
        assert cs["chatTriggerType"] == "MANUAL"
        assert cs["currentMessage"]["userInputMessage"]["content"] == "what is 2+2?"
        assert cs["currentMessage"]["userInputMessage"]["origin"] == "AI_EDITOR"
        assert "history" not in cs

    def test_build_with_history(self):
        msgs = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
        ]
        body = _build_kiro_request(msgs, "claude-sonnet-4.5", None, None, None, None)
        history = body["conversationState"]["history"]
        assert len(history) == 1
        assert history[0]["userInputMessage"]["content"] == "q1"
        assert history[0]["assistantResponseMessage"]["content"] == "a1"
        assert body["conversationState"]["currentMessage"]["userInputMessage"]["content"] == "q2"

    def test_multimodal_content_flattened(self):
        msgs = [{"role": "user", "content": [{"type": "text", "text": "hello"}, {"type": "image_url", "image_url": {"url": "x"}}]}]
        body = _build_kiro_request(msgs, "m", None, None, None, None)
        assert body["conversationState"]["currentMessage"]["userInputMessage"]["content"] == "hello"

    def test_inference_config_optional_fields(self):
        body = _build_kiro_request([{"role": "user", "content": "hi"}], "m", 0.7, 512, 0.9, None)
        ic = body["inferenceConfig"]
        assert ic["maxTokens"] == 512
        assert ic["temperature"] == 0.7
        assert ic["topP"] == 0.9

    def test_no_user_message_raises(self):
        with pytest.raises(ValueError, match="user message"):
            _build_kiro_request([{"role": "system", "content": "sys"}], "m", None, None, None, None)


class TestKiroProvider:
    def test_init(self):
        p = KiroProvider(api_key="t")
        assert p.name == "kiro"
        assert p.default_model
        assert p.capabilities["chat"] is True

    @pytest.mark.asyncio
    async def test_health_check_without_token(self):
        p = KiroProvider()
        assert await p.health_check() is False

    @pytest.mark.asyncio
    async def test_chat_requires_key(self):
        p = KiroProvider()
        with pytest.raises(ValueError, match="OAuth"):
            await p.chat(messages=[{"role": "user", "content": "hi"}])

    @pytest.mark.asyncio
    async def test_chat_collects_eventstream(self):
        p = KiroProvider(api_key="tok")
        chunks = [
            json.dumps({"content": "Hello "}).encode(),
            json.dumps({"content": "world!"}).encode(),
        ]
        raw = b"".join(_frame(c) for c in chunks)

        resp = MagicMock()
        resp.content = raw
        resp.raise_for_status = MagicMock()

        with patch.object(KiroProvider, "_get_client", new=AsyncMock()) as gc:
            client = AsyncMock()
            client.post = AsyncMock(return_value=resp)
            gc.return_value = client
            out = await p.chat(messages=[{"role": "user", "content": "hi"}])

        assert out["content"] == "Hello world!"
        assert out["model"]
