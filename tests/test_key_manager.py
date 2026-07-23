"""Tests for the KeyManager service."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.key_manager import KeyManager, mask_key, KeyInfo


def test_mask_key():
    """Test key masking for logs."""
    assert mask_key("short") == "****rt"
    assert mask_key("12345678") == "****78"
    assert mask_key("nvapi-123456789abcdef") == "nva****cdef"
    assert mask_key("sk-proj-abcdef123456") == "sk-****3456"


class TestKeyManagerUnit:
    """Unit tests for KeyManager registration and selection."""

    def test_register_pool(self):
        """Should register a key pool and create KeyInfo objects."""
        km = KeyManager()
        km.register_pool("nvidia", ["key1", "key2"], rpm_per_key=20)

        assert km.has_pool("nvidia")
        assert len(km._pools["nvidia"].keys) == 2
        assert km.get_any_key("nvidia") == "key1"

    def test_select_key_least_used(self):
        """Should select candidate with lowest request count in least_used mode."""
        km = KeyManager()
        pool = km._pools.setdefault("test", AsyncMock())
        pool.keys = []

        k1 = KeyInfo(key="k1", key_id="masked1", provider="test", index=0, requests_used=10)
        k2 = KeyInfo(key="k2", key_id="masked2", provider="test", index=1, requests_used=2)
        k3 = KeyInfo(key="k3", key_id="masked3", provider="test", index=2, requests_used=5)

        selected = km._select_key([k1, k2, k3], pool, strategy="least_used")
        assert selected.key == "k2"

    def test_select_key_round_robin(self):
        """Should cycle through candidates in round_robin mode."""
        km = KeyManager()

        class MockPool:
            round_robin_index = 0

        pool = MockPool()

        k1 = KeyInfo(key="k1", key_id="m1", provider="test", index=0)
        k2 = KeyInfo(key="k2", key_id="m2", provider="test", index=1)
        candidates = [k1, k2]

        sel1 = km._select_key(candidates, pool, strategy="round_robin")
        sel2 = km._select_key(candidates, pool, strategy="round_robin")
        sel3 = km._select_key(candidates, pool, strategy="round_robin")

        assert sel1.key == "k1"
        assert sel2.key == "k2"
        assert sel3.key == "k1"


@pytest.mark.asyncio
class TestKeyManagerAsync:
    """Async tests for KeyManager Redis interaction and fallback."""

    async def test_acquire_key_single(self, mock_redis):
        """Should acquire a key when pool has 1 key."""
        km = KeyManager()
        km.register_pool("nvidia", ["nvapi-key1"], rpm_per_key=35)
        km._lua_sha = "test-sha"

        mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=5)
        mock_redis.exists = AsyncMock(return_value=0)
        mock_redis.evalsha = AsyncMock(return_value=[1, 6, 0])

        with patch("app.services.key_manager.get_redis", return_value=mock_redis):
            key_info = await km.acquire_key("nvidia")
            assert key_info.key == "nvapi-key1"
            assert key_info.key_id == "nva****key1"

    async def test_acquire_key_rotation_least_used(self, mock_redis):
        """Should pick the least used key among active ones."""
        km = KeyManager()
        km.register_pool("nvidia", ["key-a", "key-b"], rpm_per_key=35)
        km._lua_sha = "test-sha"

        # Mock status response for each key (key 0 used 10 times, key 1 used 2 times)
        async def mock_zcard(rate_key):
            if ":0:requests" in rate_key:
                return 10
            return 2

        mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(side_effect=mock_zcard)
        mock_redis.exists = AsyncMock(return_value=0)
        mock_redis.evalsha = AsyncMock(return_value=[1, 3, 0])

        with patch("app.services.key_manager.get_redis", return_value=mock_redis):
            key_info = await km.acquire_key("nvidia")
            assert key_info.key == "key-b"  # key-b had less usage (2 < 10)

    async def test_error_cooldown_and_fallback(self, mock_redis):
        """Key in cooldown should be skipped."""
        km = KeyManager()
        km.register_pool("nvidia", ["key-bad", "key-good"], rpm_per_key=35)
        km._lua_sha = "test-sha"

        # Mock exists: key-bad (index 0) is in error cooldown
        async def mock_exists(err_key):
            if ":0:error" in err_key:
                return 1
            return 0

        mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=1)
        mock_redis.exists = AsyncMock(side_effect=mock_exists)
        mock_redis.evalsha = AsyncMock(return_value=[1, 2, 0])

        with patch("app.services.key_manager.get_redis", return_value=mock_redis):
            key_info = await km.acquire_key("nvidia")
            assert key_info.key == "key-good"

    async def test_report_error_sets_cooldown(self, mock_redis):
        """Reporting an error should set a Redis cooldown key."""
        km = KeyManager()
        km.register_pool("nvidia", ["key-1"], rpm_per_key=35)
        key_id = mask_key("key-1")

        with patch("app.services.key_manager.get_redis", return_value=mock_redis):
            await km.report_error("nvidia", key_id, "rate_limit")
            mock_redis.set.assert_called_once()
            call_args = mock_redis.set.call_args
            assert "gw:keys:nvidia:0:error" in call_args[0][0]

    async def test_get_pool_status(self, mock_redis):
        """Should return formatted pool status."""
        km = KeyManager()
        km.register_pool("nvidia", ["key-1", "key-2"], rpm_per_key=35)

        mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=5)
        mock_redis.exists = AsyncMock(return_value=0)

        with patch("app.services.key_manager.get_redis", return_value=mock_redis):
            status = await km.get_pool_status("nvidia")
            assert status["provider"] == "nvidia"
            assert status["total_keys"] == 2
            assert status["available_keys"] == 2
            assert len(status["keys"]) == 2
            assert status["keys"][0]["status"] == "active"
