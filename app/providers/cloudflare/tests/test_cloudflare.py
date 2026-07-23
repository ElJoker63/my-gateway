""" Unit test for cloudflare provider."""
import pytest
from app.providers.cloudflare import CloudflareProvider

@pytest.mark.asyncio
async def test_cloudflare_metadata():
    provider = CloudflareProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "cloudflare"
    assert meta["default_model"] == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
