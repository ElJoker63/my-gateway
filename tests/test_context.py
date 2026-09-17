"""Tests for the context builder service."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.context import build_context, extract_text_content


class TestExtractTextContent:
    def test_plain_string(self):
        assert extract_text_content("hello") == "hello"

    def test_none(self):
        assert extract_text_content(None) == ""

    def test_text_blocks(self):
        content = [{"type": "text", "text": "part one"}, {"type": "text", "text": "part two"}]
        assert extract_text_content(content) == "part one part two"

    def test_mixed_blocks_drop_images(self):
        content = [
            {"type": "text", "text": "describe this"},
            {"type": "image_url", "image_url": {"url": "https://x/img.png"}},
        ]
        assert extract_text_content(content) == "describe this"

    def test_empty_list(self):
        assert extract_text_content([]) == ""


@pytest.mark.asyncio
class TestBuildContext:
    async def test_multimodal_user_message_is_normalized(self):
        """build_context must not crash on list-type message content."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": [{"type": "text", "text": "how does auth work?"}]},
        ]
        with patch("app.services.context.search_memory", new=AsyncMock(return_value=[])) as sm:
            out = await build_context(messages, project="proj")
            # search must be called with the extracted text, not a list
            assert sm.await_args.kwargs["query"] == "how does auth work?"
            assert out == messages  # no injection when nothing found

    async def test_injection_appends_system_context(self):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "question"},
        ]
        fake_mems = [{"text": "fact A", "type": "code", "file": "a.py", "score": 0.9}]
        with patch("app.services.context.search_memory", new=AsyncMock(return_value=fake_mems)):
            out = await build_context(messages, project="proj")
            assert out[0]["role"] == "system"
            assert "fact A" in out[0]["content"]
            assert "You are helpful." in out[0]["content"]

    async def test_default_project_skips_memory(self):
        with patch("app.services.context.search_memory", new=AsyncMock()) as sm:
            out = await build_context([{"role": "user", "content": "q"}], project="default")
            sm.assert_not_called()
