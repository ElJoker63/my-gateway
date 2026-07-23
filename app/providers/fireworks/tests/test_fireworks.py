""" Unit test for fireworks provider."""
import pytest
from app.providers.fireworks import FireworksProvider

@pytest.mark.asyncio
async def test_fireworks_metadata():
    provider = FireworksProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "fireworks"
    assert meta["default_model"] == "accounts/fireworks/models/llama-v3p3-70b-instruct"
