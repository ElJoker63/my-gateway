"""
API Key Manager — Multi-key pool with rotation, rate limiting, and fallback.

Provides a provider-agnostic key management layer that:
- Maintains a pool of API keys per provider
- Selects the best available key per request (least_used or round_robin)
- Tracks per-key usage via Redis sliding window
- Automatically falls back to alternate keys on rate limit or error
- Masks keys in logs for security
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from app.config import get_settings
from app.database.redis import get_redis

logger = logging.getLogger(__name__)

# Redis key prefixes
KEY_PREFIX = "gw:keys"

# Lua script for atomic per-key rate limit check + increment
# Same sliding window as rate_limit.py but scoped per key
PER_KEY_RATE_LIMIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now, now .. '-' .. math.random(1000000))
    redis.call('EXPIRE', key, math.ceil(window / 1000))
    return {1, count + 1, 0}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 0
    if #oldest > 0 then
        retry_after = (tonumber(oldest[2]) + window) - now
    end
    return {0, count, retry_after}
end
"""


def mask_key(api_key: str) -> str:
    """Mask an API key for safe logging. Shows only last 4 characters."""
    if len(api_key) <= 8:
        return "****" + api_key[-2:] if len(api_key) > 2 else "****"
    return api_key[:3] + "****" + api_key[-4:]


@dataclass
class KeyInfo:
    """Information about a single API key."""
    key: str
    key_id: str  # Masked identifier for logs/Redis
    provider: str
    index: int  # Position in the pool

    # Runtime state (populated during acquire)
    requests_used: int = 0
    requests_limit: int = 0
    status: str = "active"  # active, rate_limited, error, cooldown


@dataclass
class KeyPool:
    """Pool of API keys for a single provider."""
    provider: str
    keys: list[KeyInfo] = field(default_factory=list)
    rpm_per_key: int = 35
    round_robin_index: int = 0


class KeyManager:
    """
    Manages pools of API keys across all providers.

    Usage:
        key_manager = KeyManager()
        key_manager.register_pool("nvidia", ["key1", "key2", "key3"], rpm_per_key=35)

        key_info = await key_manager.acquire_key("nvidia")
        # Use key_info.key for the request
        # On error: await key_manager.report_error("nvidia", key_info.key_id)
    """

    def __init__(self):
        self._pools: dict[str, KeyPool] = {}
        self._lua_sha: Optional[str] = None

    # =========================================================================
    # Registration
    # =========================================================================

    def register_pool(
        self,
        provider: str,
        keys: list[str],
        rpm_per_key: Optional[int] = None,
    ):
        """
        Register a pool of API keys for a provider.

        Args:
            provider: Provider name (e.g., 'nvidia', 'openai')
            keys: List of raw API key strings
            rpm_per_key: RPM limit per individual key
        """
        if not keys:
            logger.warning(f"No keys provided for provider '{provider}'")
            return

        settings = get_settings()
        limit = rpm_per_key or settings.key_rpm_limit or settings.max_requests_per_minute

        key_infos = []
        for i, raw_key in enumerate(keys):
            key_id = mask_key(raw_key)
            key_infos.append(KeyInfo(
                key=raw_key,
                key_id=key_id,
                provider=provider,
                index=i,
                requests_limit=limit,
            ))

        self._pools[provider] = KeyPool(
            provider=provider,
            keys=key_infos,
            rpm_per_key=limit,
        )

        logger.info(
            f"Registered key pool for '{provider}': "
            f"{len(key_infos)} keys, {limit} RPM/key"
        )
        for ki in key_infos:
            logger.info(f"  Key {ki.index}: {ki.key_id}")

    def has_pool(self, provider: str) -> bool:
        """Check if a provider has a registered key pool."""
        return provider in self._pools and len(self._pools[provider].keys) > 0

    def get_any_key(self, provider: str) -> Optional[str]:
        """Get any raw key for a provider (for health checks, etc)."""
        pool = self._pools.get(provider)
        if pool and pool.keys:
            return pool.keys[0].key
        return None

    # =========================================================================
    # Key Acquisition (core logic)
    # =========================================================================

    async def acquire_key(self, provider: str) -> KeyInfo:
        """
        Select the best available key for a provider.

        Strategy:
        1. Check all keys in the pool for availability (rate limit + error status)
        2. Select based on configured strategy (least_used or round_robin)
        3. If all keys are rate-limited, wait for the earliest one to free up
        4. If all keys are in error/cooldown, raise an exception

        Returns:
            KeyInfo with the selected key

        Raises:
            RuntimeError: If no keys are available
            TimeoutError: If wait timeout is reached
        """
        pool = self._pools.get(provider)
        if not pool or not pool.keys:
            raise RuntimeError(f"No key pool registered for provider '{provider}'")

        settings = get_settings()
        strategy = settings.key_selection_strategy
        max_wait = settings.rate_limit_wait_timeout
        waited = 0.0

        while True:
            # Gather status for all keys
            candidates = []
            rate_limited = []
            earliest_retry = float("inf")

            for ki in pool.keys:
                status = await self._get_key_status(ki)

                if status["in_cooldown"]:
                    continue  # Skip keys in error cooldown

                if status["rate_limited"]:
                    rate_limited.append(ki)
                    retry = status["retry_after_seconds"]
                    if retry < earliest_retry:
                        earliest_retry = retry
                    continue

                # Key is available
                ki_copy = KeyInfo(
                    key=ki.key,
                    key_id=ki.key_id,
                    provider=ki.provider,
                    index=ki.index,
                    requests_used=status["requests_used"],
                    requests_limit=ki.requests_limit,
                    status="active",
                )
                candidates.append(ki_copy)

            # --- Select from candidates ---
            if candidates:
                selected = self._select_key(candidates, pool, strategy)
                # Consume a rate limit slot
                await self._consume_slot(selected)

                logger.info(
                    f"Provider: {provider} | Using key: {selected.key_id} | "
                    f"Used: {selected.requests_used + 1}/{selected.requests_limit}"
                    + (f" | Strategy: {strategy}" if len(pool.keys) > 1 else "")
                )
                return selected

            # --- All keys rate-limited: wait ---
            if rate_limited and earliest_retry < float("inf"):
                wait_time = min(earliest_retry + 0.1, max_wait - waited)
                if wait_time <= 0 or waited >= max_wait:
                    raise TimeoutError(
                        f"All {len(pool.keys)} keys for '{provider}' are rate-limited. "
                        f"Waited {waited:.1f}s. Try again later."
                    )
                logger.warning(
                    f"Provider: {provider} | All keys rate-limited | "
                    f"Waiting {wait_time:.1f}s (total waited: {waited:.1f}s)"
                )
                await asyncio.sleep(wait_time)
                waited += wait_time
                continue

            # --- All keys in error cooldown ---
            raise RuntimeError(
                f"All {len(pool.keys)} keys for '{provider}' are in error cooldown. "
                "No available keys."
            )

    def _select_key(
        self,
        candidates: list[KeyInfo],
        pool: KeyPool,
        strategy: str,
    ) -> KeyInfo:
        """Select a key from available candidates based on strategy."""
        if len(candidates) == 1:
            return candidates[0]

        if strategy == "round_robin":
            # Round-robin: cycle through candidates by pool index
            idx = pool.round_robin_index % len(candidates)
            pool.round_robin_index += 1
            return candidates[idx]

        # Default: least_used — pick the key with the most remaining capacity
        candidates.sort(key=lambda k: k.requests_used)
        return candidates[0]

    # =========================================================================
    # Per-Key Rate Limiting (Redis)
    # =========================================================================

    async def _get_lua_sha(self) -> str:
        """Load the Lua script into Redis."""
        if self._lua_sha is None:
            redis = await get_redis()
            self._lua_sha = await redis.script_load(PER_KEY_RATE_LIMIT_LUA)
        return self._lua_sha

    async def _get_key_status(self, ki: KeyInfo) -> dict:
        """Get the current rate limit and error status of a key."""
        try:
            redis = await get_redis()
            now_ms = int(time.time() * 1000)
            window_ms = 60_000

            # Check rate limit
            rate_key = f"{KEY_PREFIX}:{ki.provider}:{ki.index}:requests"
            await redis.zremrangebyscore(rate_key, 0, now_ms - window_ms)
            count = await redis.zcard(rate_key)

            rate_limited = count >= ki.requests_limit
            retry_after = 0.0

            if rate_limited:
                oldest = await redis.zrange(rate_key, 0, 0, withscores=True)
                if oldest:
                    retry_after = max(0, (oldest[0][1] + window_ms - now_ms) / 1000.0)

            # Check error cooldown
            error_key = f"{KEY_PREFIX}:{ki.provider}:{ki.index}:error"
            in_cooldown = await redis.exists(error_key)

            return {
                "requests_used": count,
                "rate_limited": rate_limited,
                "retry_after_seconds": retry_after,
                "in_cooldown": bool(in_cooldown),
            }
        except Exception as e:
            logger.error(f"Key status check error for {ki.key_id}: {e}")
            # Fail open
            return {
                "requests_used": 0,
                "rate_limited": False,
                "retry_after_seconds": 0,
                "in_cooldown": False,
            }

    async def _consume_slot(self, ki: KeyInfo):
        """Record a request against a key's rate limit window."""
        try:
            redis = await get_redis()
            now_ms = int(time.time() * 1000)
            window_ms = 60_000
            rate_key = f"{KEY_PREFIX}:{ki.provider}:{ki.index}:requests"

            sha = await self._get_lua_sha()
            await redis.evalsha(sha, 1, rate_key, now_ms, window_ms, ki.requests_limit)
        except Exception as e:
            logger.error(f"Failed to consume rate limit slot for {ki.key_id}: {e}")

    # =========================================================================
    # Error Reporting
    # =========================================================================

    async def report_error(self, provider: str, key_id: str, error_type: str = "unknown"):
        """
        Report an error for a key (rate limit 429, auth failure, etc).
        Puts the key in cooldown for the configured duration.
        """
        settings = get_settings()
        pool = self._pools.get(provider)
        if not pool:
            return

        for ki in pool.keys:
            if ki.key_id == key_id:
                try:
                    redis = await get_redis()
                    error_key = f"{KEY_PREFIX}:{ki.provider}:{ki.index}:error"
                    await redis.set(
                        error_key,
                        error_type,
                        ex=settings.key_error_cooldown,
                    )
                    logger.warning(
                        f"Provider: {provider} | Key {ki.key_id} | "
                        f"Error: {error_type} | Cooldown: {settings.key_error_cooldown}s"
                    )
                except Exception as e:
                    logger.error(f"Failed to report error for {ki.key_id}: {e}")
                break

    async def clear_error(self, provider: str, key_id: str):
        """Clear the error cooldown for a key."""
        pool = self._pools.get(provider)
        if not pool:
            return

        for ki in pool.keys:
            if ki.key_id == key_id:
                try:
                    redis = await get_redis()
                    error_key = f"{KEY_PREFIX}:{ki.provider}:{ki.index}:error"
                    await redis.delete(error_key)
                except Exception as e:
                    logger.error(f"Failed to clear error for {ki.key_id}: {e}")
                break

    # =========================================================================
    # Status & Monitoring
    # =========================================================================

    async def get_pool_status(self, provider: str) -> dict:
        """
        Get the full status of a provider's key pool.
        Returns masked key info suitable for API responses.
        """
        pool = self._pools.get(provider)
        if not pool:
            return {
                "provider": provider,
                "total_keys": 0,
                "available_keys": 0,
                "keys": [],
            }

        key_statuses = []
        available = 0

        for ki in pool.keys:
            status = await self._get_key_status(ki)

            if status["in_cooldown"]:
                state = "cooldown"
            elif status["rate_limited"]:
                state = "rate_limited"
            else:
                state = "active"
                available += 1

            key_statuses.append({
                "id": ki.key_id,
                "index": ki.index,
                "requests_used": status["requests_used"],
                "requests_limit": ki.requests_limit,
                "status": state,
                "retry_after_seconds": round(status["retry_after_seconds"], 2),
            })

        return {
            "provider": provider,
            "strategy": get_settings().key_selection_strategy,
            "total_keys": len(pool.keys),
            "available_keys": available,
            "rpm_per_key": pool.rpm_per_key,
            "keys": key_statuses,
        }

    async def get_all_pools_status(self) -> dict:
        """Get status for all registered provider pools."""
        result = {}
        for provider in self._pools:
            result[provider] = await self.get_pool_status(provider)
        return result

    def list_providers(self) -> list[str]:
        """List all providers with registered key pools."""
        return list(self._pools.keys())


# Singleton instance
key_manager = KeyManager()
