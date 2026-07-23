""" Unit test for modelscope provider."""
import pytest
from app.providers.modelscope import ModelScopeProvider

@pytest.mark.asyncio
async def test_modelscope_metadata():
    provider = ModelScopeProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "modelscope"
    assert meta["default_model"] == "Qwen/Qwen2.5-72B-Instruct"
