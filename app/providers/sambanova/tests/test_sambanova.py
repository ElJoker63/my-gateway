""" Unit test for sambanova provider."""
import pytest
from app.providers.sambanova import SambaNovaProvider

@pytest.mark.asyncio
async def test_sambanova_metadata():
    provider = SambaNovaProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "sambanova"
    assert meta["default_model"] == "Meta-Llama-3.3-70B-Instruct"
