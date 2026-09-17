"""
API Key Manager — Multi-key pool with rotation, rate limiting, and fallback.

Provides a provider-agnostic key management layer that:
- Maintains a pool of API keys per provider
- Selects the best available key per request (least_used or round_robin)
- Tracks per-key usage via Redis sliding window
- Automatically falls back to alternate keys on rate limit or error
- Masks keys in logs for security

Key acquisition is ATOMIC: status check + slot consumption happen in a single
Lua script, so concurrent workers can never double-book the last free slot.
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field

from app.config import get_settings
from app.database.redis import get_redis

logger = logging.getLogger(__name__)

# Redis key prefixes
KEY_PREFIX = "gw:keys"

# Atomic acquire: checks error cooldown, checks the sliding-window rate limit,
# and (only if there is room) consumes a slot — all in one Redis round-trip.
#
# Return: {status, used, retry_after_ms}
#   status 2 → key is in error cooldown
#   status 1 → slot consumed, `used` is the new window count
#   status 0 → rate limited, retry_after_ms until the oldest request expires
ACQUIRE_SLOT_LUA = """
local rate_key = KEYS[1]
local error_key = KEYS[2]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local nonce = ARGV[4]

if redis.call('EXISTS', error_key) == 1 then
    return {2, 0, 0}
end

redis.call('ZREMRANGEBYSCORE', rate_key, 0, now - window)
local count = redis.call('ZCARD', rate_key)

if count < limit then
    redis.call('ZADD', rate_key, now, now .. '-' .. nonce)
    redis.call('PEXPIRE', rate_key, window)
    return {1, count + 1, 0}
end

local oldest = redis.call('ZRANGE', rate_key, 0, 0, 'WITHSCORES')
local retry_after = 0
if #oldest > 0 then
    retry_after = (tonumber(oldest[2]) + window) - now
end
return {0, count, retry_after}
"""


def mask_key(api_key: str) -> str:
    """Mask an API key for safe logging. Shows only first 3 and last 4 characters."""
    if len(api_key) <= 8:
        return "****" + api_key[-2:] if len(api_key) > 2 else "****"
    return api_key[:3] + "****" + api_key[-4:]


def key_fingerprint(api_key: str) -> str:
    """
    Stable, collision-safe identifier derived from the full key.
    Used internally for error reporting and status lookups — mask_key is
    for display only (different keys can share a mask).
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:10]


@dataclass
class KeyInfo:
    """Information about a single API key."""
    key: str
    key_id: str  # Stable fingerprint (sha256 prefix) — unique per key
    display: str  # Masked form for logs/UI
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
        self._lua_sha: str | None = None

    # =========================================================================
    # Registration
    # =========================================================================

    def register_pool(
        self,
        provider: str,
        keys: list[str],
        rpm_per_key: int | None = None,
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
            key_infos.append(KeyInfo(
                key=raw_key,
                key_id=key_fingerprint(raw_key),
                display=mask_key(raw_key),
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
            logger.info(f"  Key {ki.index}: {ki.display} (id={ki.key_id})")

    def has_pool(self, provider: str) -> bool:
        """Check if a provider has a registered key pool."""
        return provider in self._pools and len(self._pools[provider].keys) > 0

    def get_any_key(self, provider: str) -> str | None:
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

        The status snapshot (ordering candidates) is separate from the atomic
        acquire: each candidate is tried in preference order with a Lua script
        that checks cooldown + rate limit and consumes the slot in one
        round-trip. A candidate that lost the race simply moves to the next.

        Returns:
            KeyInfo with the selected key

        Raises:
            RuntimeError: If no keys are available (all in error cooldown)
            TimeoutError: If wait timeout is reached while rate-limited
        """
        pool = self._pools.get(provider)
        if not pool or not pool.keys:
            raise RuntimeError(f"No key pool registered for provider '{provider}'")

        settings = get_settings()
        strategy = settings.key_selection_strategy
        max_wait = settings.rate_limit_wait_timeout
        waited = 0.0

        while True:
            # 1. Snapshot all keys in parallel (single Redis round-trip)
            statuses = await asyncio.gather(
                *(self._get_key_status(ki) for ki in pool.keys)
            )

            candidates: list[tuple[KeyInfo, dict]] = []
            rate_limited: list[KeyInfo] = []
            earliest_retry = float("inf")

            for ki, status in zip(pool.keys, statuses, strict=True):
                if status["in_cooldown"]:
                    continue
                if status["rate_limited"]:
                    rate_limited.append(ki)
                    if status["retry_after_seconds"] < earliest_retry:
                        earliest_retry = status["retry_after_seconds"]
                    continue
                candidates.append((ki, status))

            # 2. Order candidates by strategy
            if candidates:
                ordered = self._order_candidates(candidates, pool, strategy)

                # 3. Atomic acquire attempt in order — racing losers fall through
                for ki, _status in ordered:
                    outcome = await self._try_acquire(ki)
                    if outcome == "acquired":
                        logger.info(
                            f"Provider: {provider} | Using key: {ki.display} "
                            f"(id={ki.key_id}) | "
                            f"Used: {ki.requests_used}/{ki.requests_limit}"
                            + (f" | Strategy: {strategy}" if len(pool.keys) > 1 else "")
                        )
                        return ki
                    elif outcome == "rate_limited" and ki not in rate_limited:
                        rate_limited.append(ki)
                    # "cooldown" or "rate_limited" → try next candidate

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

    def _order_candidates(
        self,
        candidates: list[tuple[KeyInfo, dict]],
        pool: KeyPool,
        strategy: str,
    ) -> list[tuple[KeyInfo, dict]]:
        """Order candidate keys by the configured selection strategy."""
        if len(candidates) == 1:
            return candidates

        if strategy == "round_robin":
            idx = pool.round_robin_index % len(candidates)
            pool.round_robin_index += 1
            return candidates[idx:] + candidates[:idx]

        # Default: least_used — prefer the key with the most remaining capacity
        return sorted(candidates, key=lambda item: item[1]["requests_used"])

    # =========================================================================
    # Per-Key Rate Limiting (Redis)
    # =========================================================================

    async def _eval_acquire(self, *args) -> list:
        """
        Eval the acquire Lua script, reloading it on NOSCRIPT errors
        (happens after SCRIPT FLUSH or a Redis restart).
        """
        redis = await get_redis()
        try:
            if self._lua_sha is None:
                self._lua_sha = await redis.script_load(ACQUIRE_SLOT_LUA)
            return await redis.evalsha(self._lua_sha, *args)
        except Exception as e:
            if "NOSCRIPT" in str(e).upper():
                self._lua_sha = await redis.script_load(ACQUIRE_SLOT_LUA)
                return await redis.evalsha(self._lua_sha, *args)
            raise

    async def _try_acquire(self, ki: KeyInfo) -> str:
        """
        Atomically check cooldown + window and consume a slot for a key.

        Returns "acquired" | "rate_limited" | "cooldown". On Redis failure the
        key is acquired without consumption (fail-open) and a warning is logged,
        so a Redis outage degrades rate limiting without breaking traffic.
        """
        now_ms = int(time.time() * 1000)
        window_ms = 60_000
        rate_key = f"{KEY_PREFIX}:{ki.provider}:{ki.index}:requests"
        error_key = f"{KEY_PREFIX}:{ki.provider}:{ki.index}:error"
        nonce = f"{time.monotonic_ns()}"

        try:
            status, used, _retry_ms = await self._eval_acquire(
                2, rate_key, error_key, now_ms, window_ms, ki.requests_limit, nonce
            )
        except Exception as e:
            logger.warning(
                f"Rate-limit store unavailable ({e}); allowing key {ki.display} "
                "without tracking (fail-open)"
            )
            ki.requests_used += 1
            return "acquired"

        if status == 2:
            return "cooldown"
        if status == 1:
            ki.requests_used = used
            return "acquired"
        return "rate_limited"

    async def _get_key_status(self, ki: KeyInfo) -> dict:
        """Get the current rate limit and error status of a key (read-only)."""
        try:
            redis = await get_redis()
            now_ms = int(time.time() * 1000)
            window_ms = 60_000

            rate_key = f"{KEY_PREFIX}:{ki.provider}:{ki.index}:requests"
            error_key = f"{KEY_PREFIX}:{ki.provider}:{ki.index}:error"

            pipe = redis.pipeline(transaction=False)
            pipe.zremrangebyscore(rate_key, 0, now_ms - window_ms)
            pipe.zcard(rate_key)
            pipe.zrange(rate_key, 0, 0, withscores=True)
            pipe.exists(error_key)
            _purge, count, oldest, in_cooldown = await pipe.execute()

            rate_limited = count >= ki.requests_limit
            retry_after = 0.0
            if rate_limited and oldest:
                retry_after = max(0.0, (oldest[0][1] + window_ms - now_ms) / 1000.0)

            return {
                "requests_used": count,
                "rate_limited": rate_limited,
                "retry_after_seconds": retry_after,
                "in_cooldown": bool(in_cooldown),
            }
        except Exception as e:
            logger.error(f"Key status check error for {ki.display}: {e}")
            # Fail open: treat the key as usable; the atomic acquire stays authoritative
            return {
                "requests_used": 0,
                "rate_limited": False,
                "retry_after_seconds": 0.0,
                "in_cooldown": False,
            }

    # =========================================================================
    # Error Reporting
    # =========================================================================

    async def report_error(self, provider: str, key_id: str, error_type: str = "unknown"):
        """
        Report an error for a key (rate limit 429, auth failure, etc).
        Puts the key in cooldown for the configured duration.
        key_id is the collision-safe fingerprint (see key_fingerprint).
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
                        f"Provider: {provider} | Key {ki.display} (id={ki.key_id}) | "
                        f"Error: {error_type} | Cooldown: {settings.key_error_cooldown}s"
                    )
                except Exception as e:
                    logger.error(f"Failed to report error for {ki.display}: {e}")
                return

    async def clear_error(self, provider: str, key_id: str):
        """Clear the error cooldown for a key (by fingerprint)."""
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
                    logger.error(f"Failed to clear error for {ki.display}: {e}")
                return

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

        # Probe all keys in parallel instead of sequentially
        statuses = await asyncio.gather(*(self._get_key_status(ki) for ki in pool.keys))

        key_statuses = []
        available = 0

        for ki, status in zip(pool.keys, statuses, strict=True):
            if status["in_cooldown"]:
                state = "cooldown"
            elif status["rate_limited"]:
                state = "rate_limited"
            else:
                state = "active"
                available += 1

            key_statuses.append({
                "id": ki.key_id,
                "display": ki.display,
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
