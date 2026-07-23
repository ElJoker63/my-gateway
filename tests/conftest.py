"""Test configuration and shared fixtures."""

import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment variables BEFORE importing app modules
os.environ.update({
    "NVIDIA_API_KEY": "test-nvidia-key",
    "NVIDIA_MODEL": "test-model",
    "NVIDIA_BASE_URL": "https://test.nvidia.com/v1",
    "OPENAI_API_KEY": "test-openai-key",
    "OPENAI_MODEL": "test-model",
    "OPENAI_BASE_URL": "https://test.openai.com/v1",
    "REDIS_HOST": "localhost",
    "QDRANT_HOST": "localhost",
    "GATEWAY_API_KEY": "test-gateway-key",
    "EMBEDDING_MODEL": "local",
    "LOG_LEVEL": "DEBUG",
})

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.config import get_settings, Settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear the cached settings between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings():
    """Get test settings."""
    return get_settings()


@pytest_asyncio.fixture
async def client():
    """Create an async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": "Bearer test-gateway-key"},
    ) as ac:
        yield ac


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.ping = AsyncMock(return_value=True)
    mock.hincrby = AsyncMock(return_value=1)
    mock.hgetall = AsyncMock(return_value={})
    mock.evalsha = AsyncMock(return_value=[1, 1, 0])
    mock.script_load = AsyncMock(return_value="test-sha")
    mock.zremrangebyscore = AsyncMock(return_value=0)
    mock.zcard = AsyncMock(return_value=0)
    mock.zrange = AsyncMock(return_value=[])
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_qdrant():
    """Create a mock Qdrant client."""
    mock = MagicMock()
    mock.get_collections = MagicMock(return_value=MagicMock(collections=[]))
    mock.create_collection = MagicMock()
    mock.upsert = MagicMock()
    mock.search = MagicMock(return_value=[])
    mock.scroll = MagicMock(return_value=([], None))
    mock.close = MagicMock()
    return mock


@pytest.fixture
def sample_messages():
    """Sample chat messages for testing."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
    ]


@pytest.fixture
def sample_llm_response():
    """Sample LLM response for testing."""
    return {
        "content": "I'm doing well, thank you!",
        "model": "test-model",
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 10,
            "total_tokens": 25,
        },
        "raw": {},
    }
