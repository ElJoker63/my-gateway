"""Tests for the KeyManager service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.key_manager import (
    KeyManager,
    mask_key,
    key_fingerprint,
    KeyInfo,
)


def test_mask_key():
    """Test key masking for logs."""
    assert mask_key("short") == "****rt"
    assert mask_key("12345678") == "****78"
    assert mask_key("nvapi-123456789abcdef") == "nva****cdef"
    assert mask_key("sk-proj-abcdef123456") == "sk-****3456"


def test_key_fingerprint_unique_for_similar_keys():
    """Two keys sharing the same mask must get distinct fingerprints."""
    a = key_fingerprint("nvapi-AAAA-xxxxBBBB")
    b = key_fingerprint("nvapi-CCCC-xxxxBBBB")
    assert a != b
    # deterministic
    assert key_fingerprint("nvapi-AAAA-xxxxBBBB") == a


class TestKeyManagerUnit:
    """Unit tests for KeyManager registration and selection."""

    def test_register_pool(self):
        """Should register a key pool and create KeyInfo objects."""
        km = KeyManager()
        km.register_pool("nvidia", ["key1", "key2"], rpm_per_key=20)

        assert km.has_pool("nvidia")
        assert len(km._pools["nvidia"].keys) == 2
        assert km.get_any_key("nvidia") == "key1"
        # fingerprint-based ids, distinct and not equal to the mask
        k0, k1 = km._pools["nvidia"].keys
        assert k0.key_id != k1.key_id
        assert k0.display.startswith("key") or "****" in k0.display

    def test_order_candidates_least_used(self):
        """Should order candidates by least usage."""
        km = KeyManager()

        k1 = KeyInfo(key="k1", key_id="f1", display="d1", provider="test", index=0)
        k2 = KeyInfo(key="k2", key_id="f2", display="d2", provider="test", index=1)
        k3 = KeyInfo(key="k3", key_id="f3", display="d3", provider="test", index=2)

        ordered = km._order_candidates(
            [(k1, {"requests_used": 10}), (k2, {"requests_used": 2}), (k3, {"requests_used": 5})],
            pool=MagicMock(),
            strategy="least_used",
        )
        assert [k for k, _ in ordered][0].key == "k2"

    def test_order_candidates_round_robin_rotates(self):
        """Round-robin must rotate the starting candidate."""
        km = KeyManager()

        class MockPool:
            round_robin_index = 0

        pool = MockPool()
        k1 = KeyInfo(key="k1", key_id="f1", display="d1", provider="t", index=0)
        k2 = KeyInfo(key="k2", key_id="f2", display="d2", provider="t", index=1)
        cands = [(k1, {"requests_used": 0}), (k2, {"requests_used": 0})]

        first = km._order_candidates(cands, pool, "round_robin")[0][0]
        second = km._order_candidates(cands, pool, "round_robin")[0][0]
        third = km._order_candidates(cands, pool, "round_robin")[0][0]

        assert (first.key, second.key, third.key) == ("k1", "k2", "k1")


@pytest.mark.asyncio
class TestKeyManagerAsync:
    """Async tests for KeyManager Redis interaction and fallback."""

    async def test_acquire_key_single(self):
        """Should acquire a key when pool has 1 key."""
        km = KeyManager()
        km.register_pool("nvidia", ["nvapi-key1"], rpm_per_key=35)

        with (
            patch.object(km, "_get_key_status", new=AsyncMock(return_value={
                "requests_used": 5, "rate_limited": False,
                "retry_after_seconds": 0.0, "in_cooldown": False,
            })),
            patch.object(km, "_try_acquire", new=AsyncMock(return_value="acquired")),
        ):
            key_info = await km.acquire_key("nvidia")
            assert key_info.key == "nvapi-key1"
            assert key_info.key_id == key_fingerprint("nvapi-key1")

    async def test_acquire_key_rotation_least_used(self):
        """Should prefer the key with less usage."""
        km = KeyManager()
        km.register_pool("nvidia", ["key-a", "key-b"], rpm_per_key=35)

        async def status_side_effect(ki):
            return {
                "requests_used": 10 if ki.index == 0 else 2,
                "rate_limited": False,
                "retry_after_seconds": 0.0,
                "in_cooldown": False,
            }

        with (
            patch.object(km, "_get_key_status", new=AsyncMock(side_effect=status_side_effect)),
            patch.object(km, "_try_acquire", new=AsyncMock(return_value="acquired")),
        ):
            key_info = await km.acquire_key("nvidia")
            assert key_info.key == "key-b"

    async def test_acquire_falls_through_when_first_loses_race(self):
        """When the first candidate's atomic acquire fails, try the next one."""
        km = KeyManager()
        km.register_pool("nvidia", ["key-a", "key-b"], rpm_per_key=35)

        async def status_side_effect(ki):
            return {
                "requests_used": 0,
                "rate_limited": False,
                "retry_after_seconds": 0.0,
                "in_cooldown": False,
            }

        attempts = []

        async def acquire_side_effect(ki):
            attempts.append(ki.key)
            return "rate_limited" if ki.key == "key-a" else "acquired"

        with (
            patch.object(km, "_get_key_status", new=AsyncMock(side_effect=status_side_effect)),
            patch.object(km, "_try_acquire", new=AsyncMock(side_effect=acquire_side_effect)),
        ):
            key_info = await km.acquire_key("nvidia")
            assert key_info.key == "key-b"
            assert attempts == ["key-a", "key-b"]

    async def test_all_cooldown_raises(self):
        """All keys in error cooldown must raise RuntimeError."""
        km = KeyManager()
        km.register_pool("nvidia", ["key-a"], rpm_per_key=35)

        with patch.object(km, "_get_key_status", new=AsyncMock(return_value={
            "requests_used": 0, "rate_limited": False,
            "retry_after_seconds": 0.0, "in_cooldown": True,
        })):
            with pytest.raises(RuntimeError, match="error cooldown"):
                await km.acquire_key("nvidia")

    async def test_try_acquire_acquired(self):
        """_try_acquire maps status 1 to 'acquired' and records usage."""
        km = KeyManager()
        km.register_pool("nvidia", ["key-a"], rpm_per_key=35)
        ki = km._pools["nvidia"].keys[0]

        with patch.object(km, "_eval_acquire", new=AsyncMock(return_value=[1, 7, 0])):
            result = await km._try_acquire(ki)
            assert result == "acquired"
            assert ki.requests_used == 7

    async def test_try_acquire_rate_limited(self):
        with patch.object(KeyManager, "_eval_acquire", new=AsyncMock(return_value=[0, 35, 500])):
            km = KeyManager()
            km.register_pool("nvidia", ["key-a"], rpm_per_key=35)
            ki = km._pools["nvidia"].keys[0]
            assert await km._try_acquire(ki) == "rate_limited"

    async def test_try_acquire_cooldown(self):
        with patch.object(KeyManager, "_eval_acquire", new=AsyncMock(return_value=[2, 0, 0])):
            km = KeyManager()
            km.register_pool("nvidia", ["key-a"], rpm_per_key=35)
            ki = km._pools["nvidia"].keys[0]
            assert await km._try_acquire(ki) == "cooldown"

    async def test_try_acquire_fail_open_on_redis_error(self):
        """Redis outage must not block traffic — acquire without tracking."""
        with patch.object(KeyManager, "_eval_acquire", new=AsyncMock(side_effect=Exception("redis down"))):
            km = KeyManager()
            km.register_pool("nvidia", ["key-a"], rpm_per_key=35)
            ki = km._pools["nvidia"].keys[0]
            assert await km._try_acquire(ki) == "acquired"

    async def test_report_error_sets_cooldown(self, mock_redis):
        """Reporting an error must set a Redis cooldown key by fingerprint."""
        km = KeyManager()
        km.register_pool("nvidia", ["key-1"], rpm_per_key=35)
        key_id = key_fingerprint("key-1")

        with patch("app.services.key_manager.get_redis", return_value=mock_redis):
            await km.report_error("nvidia", key_id, "rate_limit")
            mock_redis.set.assert_called_once()
            call_args = mock_redis.set.call_args
            assert "gw:keys:nvidia:0:error" in call_args[0][0]

    async def test_get_pool_status(self):
        """Should return formatted pool status."""
        km = KeyManager()
        km.register_pool("nvidia", ["key-1", "key-2"], rpm_per_key=35)

        with patch.object(km, "_get_key_status", new=AsyncMock(return_value={
            "requests_used": 5, "rate_limited": False,
            "retry_after_seconds": 0.0, "in_cooldown": False,
        })):
            status = await km.get_pool_status("nvidia")
            assert status["provider"] == "nvidia"
            assert status["total_keys"] == 2
            assert status["available_keys"] == 2
            assert len(status["keys"]) == 2
            assert status["keys"][0]["status"] == "active"
            assert status["keys"][0]["id"] == key_fingerprint("key-1")

    async def test_get_key_status_uses_pipeline(self, mock_redis):
        """_get_key_status must do one pipelined round-trip."""
        km = KeyManager()
        km.register_pool("nvidia", ["key-a"], rpm_per_key=35)
        ki = km._pools["nvidia"].keys[0]

        pipe = AsyncMock()
        pipe.zremrangebyscore = MagicMock(return_value=pipe)
        pipe.zcard = MagicMock(return_value=pipe)
        pipe.zrange = MagicMock(return_value=pipe)
        pipe.exists = MagicMock(return_value=pipe)
        pipe.execute = AsyncMock(return_value=[0, 3, [], 0])
        mock_redis.pipeline = MagicMock(return_value=pipe)

        with patch("app.services.key_manager.get_redis", return_value=mock_redis):
            status = await km._get_key_status(ki)
            assert status["requests_used"] == 3
            assert status["rate_limited"] is False
            pipe.execute.assert_awaited_once()
