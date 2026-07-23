"""
Redis-backed sliding window rate limiter.
Protects against exceeding LLM provider API limits.
"""

import asyncio
import logging
import time
from typing import Optional

from app.config import get_settings
from app.database.redis import get_redis

logger = logging.getLogger(__name__)

# Redis key prefix for rate limiting
RATE_LIMIT_PREFIX = "gw:ratelimit:"

# Lua script for atomic sliding window rate limiting
# Returns: [allowed (0/1), current_count, retry_after_ms]
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

-- Remove entries outside the window
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current entries
local count = redis.call('ZCARD', key)

if count < limit then
    -- Add new entry
    redis.call('ZADD', key, now, now .. '-' .. math.random(1000000))
    redis.call('EXPIRE', key, math.ceil(window / 1000))
    return {1, count + 1, 0}
else
    -- Rate limited - find when earliest entry expires
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 0
    if #oldest > 0 then
        retry_after = (tonumber(oldest[2]) + window) - now
    end
    return {0, count, retry_after}
end
"""


class RateLimiter:
    """Sliding window rate limiter backed by Redis."""

    def __init__(self):
        self._script_sha: Optional[str] = None

    async def _get_script_sha(self) -> str:
        """Load the Lua script into Redis and cache its SHA."""
        if self._script_sha is None:
            redis = await get_redis()
            self._script_sha = await redis.script_load(SLIDING_WINDOW_LUA)
        return self._script_sha

    async def check_rate_limit(
        self,
        provider: str = "default",
        max_rpm: Optional[int] = None,
    ) -> dict:
        """
        Check if a request is allowed under the rate limit.

        Args:
            provider: Provider name for per-provider tracking
            max_rpm: Override max requests per minute

        Returns:
            dict with:
                - allowed: bool
                - current_count: int
                - retry_after_seconds: float
        """
        settings = get_settings()
        limit = max_rpm or settings.max_requests_per_minute
        window_ms = 60_000  # 1 minute in milliseconds
        now_ms = int(time.time() * 1000)
        key = f"{RATE_LIMIT_PREFIX}{provider}"

        try:
            redis = await get_redis()
            sha = await self._get_script_sha()
            result = await redis.evalsha(sha, 1, key, now_ms, window_ms, limit)

            allowed = bool(result[0])
            current_count = int(result[1])
            retry_after_ms = int(result[2])

            if not allowed:
                logger.warning(
                    f"Rate limit reached for '{provider}': "
                    f"{current_count}/{limit} RPM, retry in {retry_after_ms}ms"
                )

            return {
                "allowed": allowed,
                "current_count": current_count,
                "retry_after_seconds": retry_after_ms / 1000.0,
                "limit": limit,
            }

        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            # Fail open — allow the request if Redis is down
            return {
                "allowed": True,
                "current_count": 0,
                "retry_after_seconds": 0,
                "limit": limit,
            }

    async def wait_if_needed(
        self,
        provider: str = "default",
        max_rpm: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """
        Check rate limit and wait if necessary.
        Returns when the request is allowed or timeout is reached.

        Args:
            provider: Provider name
            max_rpm: Override max requests per minute
            timeout: Max seconds to wait (default from settings)

        Returns:
            dict with rate limit info + waited_seconds

        Raises:
            TimeoutError: If timeout is reached while waiting
        """
        settings = get_settings()
        max_wait = timeout or settings.rate_limit_wait_timeout
        waited = 0.0

        while True:
            result = await self.check_rate_limit(provider, max_rpm)

            if result["allowed"]:
                result["waited_seconds"] = waited
                return result

            wait_time = min(result["retry_after_seconds"], max_wait - waited)
            if wait_time <= 0 or waited >= max_wait:
                raise TimeoutError(
                    f"Rate limit timeout after {waited:.1f}s. "
                    f"Provider '{provider}' at {result['current_count']}/{result['limit']} RPM."
                )

            logger.info(f"Rate limited, waiting {wait_time:.1f}s (total waited: {waited:.1f}s)")
            await asyncio.sleep(wait_time)
            waited += wait_time

    async def get_status(self, provider: str = "default") -> dict:
        """Get current rate limit status without consuming a slot."""
        settings = get_settings()
        limit = settings.max_requests_per_minute
        key = f"{RATE_LIMIT_PREFIX}{provider}"
        now_ms = int(time.time() * 1000)
        window_ms = 60_000

        try:
            redis = await get_redis()
            # Remove expired entries
            await redis.zremrangebyscore(key, 0, now_ms - window_ms)
            count = await redis.zcard(key)

            # Find when the window resets
            oldest = await redis.zrange(key, 0, 0, withscores=True)
            reset_in = 0.0
            if oldest:
                oldest_ts = oldest[0][1]
                reset_in = max(0, (oldest_ts + window_ms - now_ms) / 1000.0)

            return {
                "provider": provider,
                "requests_used": count,
                "requests_remaining": max(0, limit - count),
                "limit_per_minute": limit,
                "reset_in_seconds": round(reset_in, 2),
            }

        except Exception as e:
            logger.error(f"Rate limit status error: {e}")
            return {
                "provider": provider,
                "requests_used": 0,
                "requests_remaining": limit,
                "limit_per_minute": limit,
                "reset_in_seconds": 0,
            }


# Singleton instance
rate_limiter = RateLimiter()
