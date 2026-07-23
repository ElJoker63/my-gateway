""" Unit test for zhipu provider."""
import pytest
from app.providers.zhipu import ZhipuProvider

@pytest.mark.asyncio
async def test_zhipu_metadata():
    provider = ZhipuProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "zhipu"
    assert meta["default_model"] == "glm-4-plus"
