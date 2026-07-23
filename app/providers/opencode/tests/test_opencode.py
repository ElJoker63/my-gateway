""" Unit test for opencode provider."""
import pytest
from app.providers.opencode import OpenCodeProvider

@pytest.mark.asyncio
async def test_opencode_metadata():
    provider = OpenCodeProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "opencode"
    assert meta["default_model"] == "opencode-coder-70b"
