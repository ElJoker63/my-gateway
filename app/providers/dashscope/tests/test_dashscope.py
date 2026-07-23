""" Unit test for dashscope provider."""
import pytest
from app.providers.dashscope import DashScopeProvider

@pytest.mark.asyncio
async def test_dashscope_metadata():
    provider = DashScopeProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "dashscope"
    assert meta["default_model"] == "qwen-max"
