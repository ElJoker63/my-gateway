""" Unit test for hunyuan provider."""
import pytest
from app.providers.hunyuan import HunyuanProvider

@pytest.mark.asyncio
async def test_hunyuan_metadata():
    provider = HunyuanProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "hunyuan"
    assert meta["default_model"] == "hunyuan-pro"
