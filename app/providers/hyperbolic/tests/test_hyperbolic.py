""" Unit test for hyperbolic provider."""
import pytest
from app.providers.hyperbolic import HyperbolicProvider

@pytest.mark.asyncio
async def test_hyperbolic_metadata():
    provider = HyperbolicProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "hyperbolic"
    assert meta["default_model"] == "meta-llama/Meta-Llama-3.1-70B-Instruct"
