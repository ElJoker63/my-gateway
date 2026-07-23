""" Unit test for sensenova provider."""
import pytest
from app.providers.sensenova import SenseNovaProvider

@pytest.mark.asyncio
async def test_sensenova_metadata():
    provider = SenseNovaProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "sensenova"
    assert meta["default_model"] == "SenseChat-5"
