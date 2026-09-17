"""
Telemetry — lightweight in-process metrics with rolling percentile window.
Ported (heavily trimmed) from openproxy's analytics: counters per provider,
latency percentiles (p50/p95/p99) over a rolling window, and race stats.

State is kept in memory (per worker) and mirrored to Redis so /api/metrics
can be served by any worker without losing history on restart.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field

from app.database.redis import get_redis

logger = logging.getLogger(__name__)

METRICS_KEY = "gw:metrics:summary"
LATENCY_PREFIX = "gw:metrics:latency:"
WINDOW = 512  # samples kept per latency metric


@dataclass
class MetricSample:
    timestamp: float
    latency_ms: float
    tokens: int = 0


@dataclass
class MetricsStore:
    """Rolling-window metrics, one bucket per (provider, model) pair."""

    total_requests: int = 0
    total_errors: int = 0
    total_races: int = 0
    race_wins: int = 0
    per_provider: dict = field(default_factory=dict)
    _latency: dict = field(default_factory=dict)  # key -> deque[MetricSample]
    _started_at: float = field(default_factory=time.time)

    def record(
        self,
        provider: str,
        model: str | None,
        latency_ms: float,
        ok: bool,
        tokens: int = 0,
        raced: bool = False,
        won_race: bool = False,
    ):
        """Record one upstream call."""
        key = f"{provider}:{model or ''}"
        self.total_requests += 1
        if not ok:
            self.total_errors += 1
        if raced:
            self.total_races += 1
            if won_race:
                self.race_wins += 1

        bucket = self.per_provider.setdefault(
            provider,
            {"requests": 0, "errors": 0, "tokens": 0, "models": set()},
        )
        bucket["requests"] += 1
        bucket["errors"] += 0 if ok else 1
        bucket["tokens"] += tokens
        if model:
            bucket["models"].add(model)

        buf = self._latency.setdefault(key, deque(maxlen=WINDOW))
        buf.append(MetricSample(timestamp=time.time(), latency_ms=latency_ms, tokens=tokens))

    def summary(self) -> dict:
        """Aggregate counters + latency percentiles for /api/metrics."""
        def pct(samples, p):
            if not samples:
                return None
            arr = sorted(s.latency_ms for s in samples)
            k = (len(arr) - 1) * (p / 100.0)
            f = int(k)
            c = min(f + 1, len(arr) - 1)
            frac = k - f
            return round(arr[f] + (arr[c] - arr[f]) * frac, 2)

        latency = {}
        for key, buf in self._latency.items():
            samples = list(buf)
            latency[key] = {
                "count": len(samples),
                "p50_ms": pct(samples, 50),
                "p95_ms": pct(samples, 95),
                "p99_ms": pct(samples, 99),
                "avg_ms": round(sum(s.latency_ms for s in samples) / len(samples), 2) if samples else None,
                "min_ms": round(min(s.latency_ms for s in samples), 2) if samples else None,
                "max_ms": round(max(s.latency_ms for s in samples), 2) if samples else None,
            }

        uptime_s = round(time.time() - self._started_at, 1)
        providers = {
            name: {
                "requests": data["requests"],
                "errors": data["errors"],
                "error_rate": round(data["errors"] / data["requests"], 4) if data["requests"] else 0.0,
                "tokens": data["tokens"],
                "models": sorted(data["models"]),
            }
            for name, data in sorted(self.per_provider.items())
        }

        return {
            "uptime_seconds": uptime_s,
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate": round(self.total_errors / self.total_requests, 4) if self.total_requests else 0.0,
            "total_races": self.total_races,
            "race_wins": self.race_wins,
            "race_win_rate": round(self.race_wins / self.total_races, 4) if self.total_races else 0.0,
            "providers": providers,
            "latency": latency,
        }


metrics = MetricsStore()


async def summarize_persisted() -> dict:
    """Merge the in-memory snapshot with the Redis mirror (multi-worker-safe)."""
    local = metrics.summary()
    try:
        redis = await get_redis()
        raw = await redis.get(METRICS_KEY)
        if not raw:
            return local
        persisted = __import__("json").loads(raw)
        # Merge: keep the larger counters (approximation across restarts)
        merged = dict(local)
        merged["total_requests"] = max(local["total_requests"], persisted.get("total_requests", 0))
        merged["total_errors"] = max(local["total_errors"], persisted.get("total_errors", 0))
        return merged
    except Exception:
        return local


async def persist_snapshot():
    """Best-effort flush of the in-memory summary to Redis (called periodically)."""
    try:
        redis = await get_redis()
        import json
        await redis.set(METRICS_KEY, json.dumps(metrics.summary()))
    except Exception as e:
        logger.debug(f"Metrics persist failed: {e}")
