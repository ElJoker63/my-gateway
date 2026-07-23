""" Unit test for github_models provider."""
import pytest
from app.providers.github_models import GithubModelsProvider

@pytest.mark.asyncio
async def test_github_models_metadata():
    provider = GithubModelsProvider()
    meta = provider.get_metadata()
    assert meta["name"] == "github_models"
    assert meta["default_model"] == "gpt-4o"
