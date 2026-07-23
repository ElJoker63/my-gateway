"""Tests for the cache service."""

import json
import pytest
from unittest.mock import AsyncMock, patch

from app.services.cache import (
    _build_cache_key,
    get_cached_response,
    set_cached_response,
    get_cache_stats,
)


class TestCacheKeyGeneration:
    """Test cache key generation."""

    def test_deterministic_keys(self):
        """Same input should produce the same key."""
        messages = [{"role": "user", "content": "hello"}]
        key1 = _build_cache_key(messages, "test-model", "test-project")
        key2 = _build_cache_key(messages, "test-model", "test-project")
        assert key1 == key2

    def test_different_messages_different_keys(self):
        """Different messages should produce different keys."""
        msg1 = [{"role": "user", "content": "hello"}]
        msg2 = [{"role": "user", "content": "world"}]
        key1 = _build_cache_key(msg1, "model", "project")
        key2 = _build_cache_key(msg2, "model", "project")
        assert key1 != key2

    def test_different_models_different_keys(self):
        """Different models should produce different keys."""
        messages = [{"role": "user", "content": "hello"}]
        key1 = _build_cache_key(messages, "model-a", "project")
        key2 = _build_cache_key(messages, "model-b", "project")
        assert key1 != key2

    def test_different_projects_different_keys(self):
        """Different projects should produce different keys."""
        messages = [{"role": "user", "content": "hello"}]
        key1 = _build_cache_key(messages, "model", "project-a")
        key2 = _build_cache_key(messages, "model", "project-b")
        assert key1 != key2

    def test_key_has_prefix(self):
        """Keys should have the cache prefix."""
        messages = [{"role": "user", "content": "hello"}]
        key = _build_cache_key(messages, "model", "project")
        assert key.startswith("gw:cache:")


@pytest.mark.asyncio
class TestCacheOperations:
    """Test cache read/write operations."""

    async def test_cache_miss(self, mock_redis):
        """Should return None on cache miss."""
        with patch("app.services.cache.get_redis", return_value=mock_redis):
            result = await get_cached_response(
                [{"role": "user", "content": "test"}], "model", "project"
            )
            assert result is None

    async def test_cache_hit(self, mock_redis):
        """Should return cached data on hit."""
        cached_data = {"content": "cached response", "model": "test"}
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data).encode())

        with patch("app.services.cache.get_redis", return_value=mock_redis):
            result = await get_cached_response(
                [{"role": "user", "content": "test"}], "model", "project"
            )
            assert result is not None
            assert result["content"] == "cached response"

    async def test_set_cache(self, mock_redis):
        """Should store data in cache."""
        with patch("app.services.cache.get_redis", return_value=mock_redis):
            await set_cached_response(
                messages=[{"role": "user", "content": "test"}],
                model="model",
                response={"content": "response"},
                project="project",
            )
            mock_redis.set.assert_called_once()

    async def test_cache_stats(self, mock_redis):
        """Should return hit/miss stats."""
        mock_redis.hgetall = AsyncMock(return_value={b"hits": b"10", b"misses": b"5"})

        with patch("app.services.cache.get_redis", return_value=mock_redis):
            stats = await get_cache_stats()
            assert stats["hits"] == 10
            assert stats["misses"] == 5
