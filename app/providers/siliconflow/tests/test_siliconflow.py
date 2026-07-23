""" Unit test for siliconflow provider."""
import pytest
from app.providers.siliconflow import SiliconFlowProvider

@pytest.mark.asyncio
async def test_siliconflow_metadata():
    provider = SiliconFlowProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "siliconflow"
    assert meta["default_model"] == "deepseek-ai/DeepSeek-V3"
