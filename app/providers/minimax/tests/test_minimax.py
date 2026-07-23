""" Unit test for minimax provider."""
import pytest
from app.providers.minimax import MiniMaxProvider

@pytest.mark.asyncio
async def test_minimax_metadata():
    provider = MiniMaxProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "minimax"
    assert meta["default_model"] == "MiniMax-Text-01"
