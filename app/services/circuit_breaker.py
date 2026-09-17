"""
Circuit breaker per provider (+model).

A provider/model that fails `failure_threshold` consecutive times opens the
circuit for `unhealthy_duration` seconds, during which requests skip it
entirely. After the window expires it half-opens (single probe allowed).
State lives in Redis when available so workers share it; falls back to
process-local memory when Redis is down.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from app.database.redis import get_redis

logger = logging.getLogger(__name__)

# Redis key prefix — mirrors the cache/key conventions
CB_PREFIX = "gw:circuit:"


@dataclass
class CircuitState:
    """Snapshot of a circuit's health."""
    state: str  # "closed" | "open" | "half_open"
    consecutive_failures: int
    open_until: float  # unix timestamp; 0 when closed


class CircuitBreakerRegistry:
    """
    Tracks per-target breaker state. In-memory hot path with Redis durability.

    `key` convention: "{provider}" or "{provider}:{model}".
    """

    def __init__(self, failure_threshold: int = 3, unhealthy_duration: float = 60.0):
        self.failure_threshold = max(1, failure_threshold)
        self.unhealthy_duration = max(0.01, unhealthy_duration)
        # Local mirror (provider:model -> (failures, open_until))
        self._local: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    def _key(self, provider: str, model: str | None = None) -> str:
        return f"{provider}:{model}" if model else provider

    async def is_available(self, provider: str, model: str | None = None) -> bool:
        """True if the target can accept traffic right now."""
        key = self._key(provider, model)
        # Fast path: local mirror says open
        local = self._local.get(key)
        if local and time.time() < local[1]:
            return False

        try:
            redis = await get_redis()
            raw = await redis.get(f"{CB_PREFIX}{key}")
            if raw is None:
                return True
            failures, open_until = raw.decode().split(":")
            if time.time() < float(open_until):
                self._local[key] = (int(failures), float(open_until))
                return False
        except Exception as e:
            # Redis down → trust the local mirror if present, else assume closed
            logger.debug(f"Circuit breaker Redis read failed ({e}); using local state")
            if local:
                return time.time() >= local[1]
            return True

        # Window expired — half-open: allow the probe through
        return True

    async def record_success(self, provider: str, model: str | None = None):
        """A successful call resets the failure counter and closes the circuit."""
        key = self._key(provider, model)
        async with self._lock:
            self._local.pop(key, None)
        try:
            redis = await get_redis()
            await redis.delete(f"{CB_PREFIX}{key}")
        except Exception:
            pass

    async def record_failure(self, provider: str, model: str | None = None) -> CircuitState:
        """Increment the failure counter; open the circuit when threshold is hit."""
        key = self._key(provider, model)
        now = time.time()

        async with self._lock:
            failures, _prev_open = self._local.get(key, (0, 0.0))
            failures += 1
            open_until = 0.0 if failures < self.failure_threshold else now + self.unhealthy_duration
            self._local[key] = (failures, open_until)

        try:
            redis = await get_redis()
            await redis.set(
                f"{CB_PREFIX}{key}",
                f"{failures}:{open_until}",
                ex=int(self.unhealthy_duration) * 2,
            )
        except Exception:
            pass

        if open_until > 0:
            logger.warning(
                f"Circuit OPEN for {key}: {failures} consecutive failures; "
                f"unavailable for {self.unhealthy_duration:.0f}s"
            )
        state = "open" if open_until > now else "closed"
        return CircuitState(state=state, consecutive_failures=failures, open_until=open_until)

    async def get_state(self, provider: str, model: str | None = None) -> CircuitState:
        """Current state for diagnostics."""
        key = self._key(provider, model)
        failures, open_until = self._local.get(key, (0, 0.0))
        now = time.time()
        if open_until > now:
            state = "open"
        elif failures >= self.failure_threshold and open_until <= now < open_until + 5:
            state = "half_open"
        elif failures > 0:
            state = "closed"  # recovered
        else:
            state = "closed"
        return CircuitState(state=state, consecutive_failures=failures, open_until=open_until)

    async def get_all_states(self) -> dict[str, CircuitState]:
        """Snapshot of every tracked target."""
        return {k: await self.get_state(*tuple(k.split(":", 1)) if ":" in k else (k, None)) for k in self._local}


# Singleton
circuit_breaker = CircuitBreakerRegistry()


def configure_circuit_breaker(threshold: int | None = None, duration: float | None = None):
    """Applied at startup from settings (see main.lifespan)."""
    if threshold is not None:
        circuit_breaker.failure_threshold = max(1, threshold)
    if duration is not None:
        circuit_breaker.unhealthy_duration = max(0.01, duration)
