""" Unit test for volcengine provider."""
import pytest
from app.providers.volcengine import VolcengineProvider

@pytest.mark.asyncio
async def test_volcengine_metadata():
    provider = VolcengineProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "volcengine"
    assert meta["default_model"] == "doubao-pro-128k"
