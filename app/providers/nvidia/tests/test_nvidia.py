""" Unit test for nvidia provider."""
import pytest
from app.providers.nvidia import NvidiaProvider

@pytest.mark.asyncio
async def test_nvidia_metadata():
    provider = NvidiaProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "nvidia"
    assert meta["default_model"] == "meta/llama-3.1-70b-instruct"
