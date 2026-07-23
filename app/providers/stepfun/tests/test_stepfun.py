""" Unit test for stepfun provider."""
import pytest
from app.providers.stepfun import StepFunProvider

@pytest.mark.asyncio
async def test_stepfun_metadata():
    provider = StepFunProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "stepfun"
    assert meta["default_model"] == "step-2-16k"
