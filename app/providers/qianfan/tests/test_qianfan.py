""" Unit test for qianfan provider."""
import pytest
from app.providers.qianfan import QianfanProvider

@pytest.mark.asyncio
async def test_qianfan_metadata():
    provider = QianfanProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "qianfan"
    assert meta["default_model"] == "ERNIE-4.0-8K"
