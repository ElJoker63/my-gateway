""" Unit test for lingyiwanwu provider."""
import pytest
from app.providers.lingyiwanwu import LingyiWanwuProvider

@pytest.mark.asyncio
async def test_lingyiwanwu_metadata():
    provider = LingyiWanwuProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "lingyiwanwu"
    assert meta["default_model"] == "yi-lightning"
