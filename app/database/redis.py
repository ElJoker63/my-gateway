"""
Async Redis connection pool management.
Provides a singleton Redis connection used across the application.
"""

import logging
import time

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)

# Singleton connection pool
_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Get the shared async Redis connection. Creates it on first call."""
    global _redis_pool
    if _redis_pool is None:
        await init_redis()
    return _redis_pool


async def init_redis() -> aioredis.Redis:
    """Initialize the Redis connection pool and verify connectivity."""
    global _redis_pool
    settings = get_settings()

    kwargs = {
        "host": settings.redis_host,
        "port": settings.redis_port,
        "decode_responses": False,
        "max_connections": 20,
        "socket_connect_timeout": 5,
        "retry_on_timeout": True,
    }

    if settings.redis_password:
        kwargs["password"] = settings.redis_password

    client = aioredis.Redis(**kwargs)
    # Real connectivity check — fail loudly at startup instead of at first request
    await client.ping()
    _redis_pool = client
    logger.info(f"Redis connection pool initialized: {settings.redis_host}:{settings.redis_port}")
    return _redis_pool


async def close_redis():
    """Close the Redis connection pool."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("Redis connection pool closed")


async def redis_health_check() -> dict:
    """Check Redis connectivity and return health info."""
    try:
        r = await get_redis()
        start = time.monotonic()
        await r.ping()
        latency = (time.monotonic() - start) * 1000
        return {"status": "healthy", "latency_ms": round(latency, 2)}
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}
