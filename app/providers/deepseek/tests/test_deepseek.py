""" Unit test for deepseek provider."""
import pytest
from app.providers.deepseek import DeepSeekProvider

@pytest.mark.asyncio
async def test_deepseek_metadata():
    provider = DeepSeekProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "deepseek"
    assert meta["default_model"] == "deepseek-chat"
