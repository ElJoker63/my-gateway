""" Unit test for moonshot provider."""
import pytest
from app.providers.moonshot import MoonshotProvider

@pytest.mark.asyncio
async def test_moonshot_metadata():
    provider = MoonshotProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "moonshot"
    assert meta["default_model"] == "moonshot-v1-128k"
