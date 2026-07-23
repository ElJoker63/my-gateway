""" Unit test for chutes provider."""
import pytest
from app.providers.chutes import ChutesProvider

@pytest.mark.asyncio
async def test_chutes_metadata():
    provider = ChutesProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "chutes"
    assert meta["default_model"] == "chutes-llama-3.3-70b"
