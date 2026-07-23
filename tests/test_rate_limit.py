"""Tests for the rate limiter service."""

import pytest
from unittest.mock import AsyncMock, patch

from app.services.rate_limit import RateLimiter


@pytest.mark.asyncio
class TestRateLimiter:
    """Test the sliding window rate limiter."""

    async def test_allowed_when_under_limit(self, mock_redis):
        """Should allow requests when under the limit."""
        mock_redis.evalsha = AsyncMock(return_value=[1, 5, 0])

        limiter = RateLimiter()
        limiter._script_sha = "test-sha"

        with patch("app.services.rate_limit.get_redis", return_value=mock_redis):
            result = await limiter.check_rate_limit("test", max_rpm=35)
            assert result["allowed"] is True
            assert result["current_count"] == 5

    async def test_blocked_when_at_limit(self, mock_redis):
        """Should block requests when at the limit."""
        mock_redis.evalsha = AsyncMock(return_value=[0, 35, 5000])

        limiter = RateLimiter()
        limiter._script_sha = "test-sha"

        with patch("app.services.rate_limit.get_redis", return_value=mock_redis):
            result = await limiter.check_rate_limit("test", max_rpm=35)
            assert result["allowed"] is False
            assert result["retry_after_seconds"] == 5.0

    async def test_wait_if_needed_allowed(self, mock_redis):
        """Should return immediately if allowed."""
        mock_redis.evalsha = AsyncMock(return_value=[1, 1, 0])

        limiter = RateLimiter()
        limiter._script_sha = "test-sha"

        with patch("app.services.rate_limit.get_redis", return_value=mock_redis):
            result = await limiter.wait_if_needed("test", max_rpm=35, timeout=5)
            assert result["allowed"] is True
            assert result["waited_seconds"] == 0.0

    async def test_get_status(self, mock_redis):
        """Should return current rate limit status."""
        mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        mock_redis.zcard = AsyncMock(return_value=10)
        mock_redis.zrange = AsyncMock(return_value=[])

        limiter = RateLimiter()

        with patch("app.services.rate_limit.get_redis", return_value=mock_redis):
            status = await limiter.get_status("test")
            assert status["requests_used"] == 10
            assert status["limit_per_minute"] == 35

    async def test_fail_open_on_redis_error(self, mock_redis):
        """Should allow requests if Redis is down (fail open)."""
        mock_redis.evalsha = AsyncMock(side_effect=Exception("Connection refused"))

        limiter = RateLimiter()
        limiter._script_sha = "test-sha"

        with patch("app.services.rate_limit.get_redis", return_value=mock_redis):
            result = await limiter.check_rate_limit("test")
            assert result["allowed"] is True
